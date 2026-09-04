"""Where in the semester an offering's sessions land.

Three modes, and the third is the one this file is really about. `whole` and
`range` balance the teaching weeks of their window; `block` deliberately does
not, because задочна форма compresses a whole semester into a two- or three-week
присъствен период, where an even weekly spread is simply the wrong shape.
"""

from collections import Counter

from app.models import SolveRequest
from app.timetable_solver import solve_timetable
from conftest import offering, problem, room, teacher


def solve(payload):
    return solve_timetable(SolveRequest(**payload))


def spread(mode, hours, window=None, start="2025-09-15", end="2025-10-25", **over):
    extra = {"spread": mode}
    if window:
        extra["window"] = {"start": window[0], "end": window[1]}
    over.setdefault("rooms", [room("r1"), room("r2")])
    over.setdefault("teachers", [teacher("t1"), teacher("t2")])
    return problem(
        start=start,
        end=end,
        seconds=20.0,
        offerings=[offering("o1", exerciseHours=hours, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1", "t2"],
                            exerciseUnitIds=["g1"], **extra)],
        **over,
    )


def weeks_of(result):
    return Counter(a.date.isocalendar()[:2] for a in result.assignments)


# ---------------------------------------------------------------------------
# whole and range still balance the weeks
# ---------------------------------------------------------------------------


def test_whole_spreads_evenly_across_every_teaching_week():
    result = solve(spread("whole", hours=12))
    assert result.status == "OPTIMAL"
    counts = weeks_of(result)
    assert len(counts) == 6
    assert set(counts.values()) == {1}


def test_range_spreads_evenly_inside_its_window():
    result = solve(spread("range", hours=6, window=("2025-10-06", "2025-10-25")))
    assert result.status == "OPTIMAL"
    assert all(
        "2025-10-06" <= a.date.isoformat() <= "2025-10-25" for a in result.assignments
    )
    assert set(weeks_of(result).values()) == {1}


def test_a_window_is_required_for_range():
    payload = problem(
        offerings=[offering("o1", exerciseHours=4, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"],
                            spread="range")]
    )
    result = solve(payload)
    assert result.status == "MODEL_INVALID"
    assert any("names no window" in h.detail for h in result.hints)


# ---------------------------------------------------------------------------
# block saturates its window instead
# ---------------------------------------------------------------------------


def test_block_confines_everything_to_its_window():
    result = solve(spread("block", hours=20, window=("2025-10-06", "2025-10-18")))
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert all(
        "2025-10-06" <= a.date.isoformat() <= "2025-10-18" for a in result.assignments
    )
    assert result.validation.ok


def test_block_is_exempt_from_the_weekly_floor_and_ceiling():
    """Ten sessions in a two-week window: an even spread would force five a week.
    Block does not, and the proof is that it will happily saturate one week when
    that is what the rest of the timetable wants."""
    payload = spread("block", hours=20, window=("2025-10-06", "2025-10-18"))
    # Only one of the two weeks has any teaching left in it.
    payload["courseInstances"][0]["nonTeaching"] = [
        {"start": "2025-10-13", "end": "2025-10-18", "kind": "стаж"}
    ]
    result = solve(payload)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    counts = weeks_of(result)
    assert len(counts) == 1, counts
    assert sum(counts.values()) == 10


def test_block_can_do_what_an_even_spread_cannot():
    """The contrast задочна форма exists for, in one pair of assertions.

    A two-week присъствен период whose first week has a single teaching day, and
    fourteen sessions to place. An even spread demands seven a week and that one
    day holds only six periods, so `range` is impossible. `block` has no weekly
    ceiling at all, so it simply packs them where they fit -- which is what
    saturating a window means.
    """
    window = ("2025-10-06", "2025-10-18")
    closed = [{"start": "2025-10-07", "end": "2025-10-11", "kind": "стаж"}]

    even = spread("range", hours=28, window=window,
                  start="2025-10-06", end="2025-10-18", non_teaching=closed)
    assert solve(even).status == "INFEASIBLE"

    saturated = spread("block", hours=28, window=window,
                       start="2025-10-06", end="2025-10-18", non_teaching=closed)
    result = solve(saturated)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert len(result.assignments) == 14
    # The point: one week carries more than an even spread would ever allow.
    assert max(weeks_of(result).values()) > 7
    assert result.validation.ok


def test_block_still_runs_in_period_order():
    """Symmetry breaking is unrelated to the spread mode: a series' sessions are
    still forced into strictly increasing period order, which is what keeps the
    search from re-exploring their permutations."""
    result = solve(spread("block", hours=12, window=("2025-10-06", "2025-10-18")))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    ordered = sorted((a.date, a.period) for a in result.assignments)
    assert len(set(ordered)) == len(ordered)


def test_block_without_symmetry_breaking_reaches_the_same_answer():
    """The week-band pruning in `_session_slots` is switched off for block, so
    this is the check that nothing else quietly depended on it."""
    window = ("2025-10-06", "2025-10-18")
    with_it = solve(spread("block", hours=12, window=window))
    without = solve(dict(spread("block", hours=12, window=window),
                         useSymmetryBreaking=False))
    assert with_it.status == without.status
    assert with_it.stats.objectiveValue == without.stats.objectiveValue


def test_a_window_is_required_for_block():
    payload = problem(
        offerings=[offering("o1", exerciseHours=4, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"],
                            spread="block")]
    )
    result = solve(payload)
    assert result.status == "MODEL_INVALID"
    assert any("names no window" in h.detail for h in result.hints)


def test_a_block_window_outside_the_term_is_explained():
    result = solve(spread("block", hours=4, window=("2026-03-01", "2026-03-14")))
    assert result.status == "INFEASIBLE"
    assert any("no usable dates" in h.title for h in result.hints), [
        h.title for h in result.hints
    ]
