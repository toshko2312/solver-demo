"""The teaching day: periods, the обедна почивка, Saturday, and the daily cap.

A period is a block of two academic hours and it is the atomic unit -- there is
no finer thing to place. That makes most of this file short: the obligations that
would need enforcing if a session could be split across the day simply do not
arise.

The обедна почивка is the interesting case. It is not a rule anywhere in the
model: it is the stretch of clock between period 3 and period 4 that no period
covers, so nothing can be scheduled across it. A break defined by absence.
"""

import json

from app.models import SolveRequest
from app.timetable_solver import solve_timetable
from conftest import SMALL_SEED_PATH, offering, problem, room, teacher


def solve(payload):
    return solve_timetable(SolveRequest(**payload))


def simple(hours=6, **over):
    """One group, one teacher, one room, `hours` of упражнения."""
    over.setdefault(
        "offerings",
        [offering("o1", exerciseHours=hours, exerciseRoomTypes=["зала"],
                  exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    return problem(**over)


# ---------------------------------------------------------------------------
# A period is the unit
# ---------------------------------------------------------------------------


def test_a_session_occupies_exactly_one_period():
    result = solve(simple())
    assert result.status == "OPTIMAL"
    for a in result.assignments:
        assert a.slot == f"{a.date.isoformat()}-{a.period}"
        assert 1 <= a.period <= 6


def test_two_sessions_never_share_a_period_in_one_room():
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1"), room("r2")],
        teachers=[teacher("t1"), teacher("t2")],
        groups=[
            {"id": "g1", "name": "гр. 1", "size": 10, "courseInstanceId": "c1"},
            {"id": "g2", "name": "гр. 2", "size": 10, "courseInstanceId": "c1"},
        ],
        offerings=[
            offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["t1", "t2"], exerciseUnitIds=["g1", "g2"])
        ],
    )
    result = solve(payload)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    seen = set()
    for a in result.assignments:
        key = (a.roomId, a.slot)
        assert key not in seen, f"{a.roomId} taken twice in {a.slot}"
        seen.add(key)


def test_a_blocked_period_is_simply_not_on_offer():
    """Blocking is weekday-keyed, so it removes that period every week. The
    solver never learns it was blocked -- the slot is not in the request."""
    blocked = {f"{d}-1" for d in ("mon", "tue", "wed", "thu", "fri", "sat")}
    result = solve(simple(hours=6, blocked=blocked))
    assert result.status == "OPTIMAL"
    assert all(a.period != 1 for a in result.assignments)


def test_an_empty_grid_is_infeasible_not_a_crash():
    result = solve(simple(periods=0))
    assert result.status == "INFEASIBLE"
    assert any("No teachable periods" in h.title for h in result.hints)


# ---------------------------------------------------------------------------
# Обедната почивка, which is a hole in the clock rather than a rule
# ---------------------------------------------------------------------------


def test_nothing_is_taught_across_the_lunch_break(seed):
    """The academy's day runs 08:00-18:45 with обедна почивка 13:00-13:45. No
    period covers it, so no session can -- this asserts the consequence rather
    than a constraint, because there is no constraint to assert."""
    times = json.loads(SMALL_SEED_PATH.read_text())["slotConfig"]["periodTimes"]
    spans = [t.split("-") for t in times]

    # The template itself leaves the gap.
    assert any(
        end <= "13:00" and next_start >= "13:45"
        for (_start, end), (next_start, _e) in zip(spans, spans[1:])
    ), times

    result = solve(seed)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    for a in result.assignments:
        start, end = spans[a.period - 1]
        assert not (start < "13:45" and end > "13:00"), (
            f"{a.subjectName} runs {start}-{end}, across the обедна почивка"
        )


# ---------------------------------------------------------------------------
# Saturday
# ---------------------------------------------------------------------------


def test_saturday_is_a_teaching_day():
    """Курсанти have Saturday classes, so nothing may hardcode Mon-Fri."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-27",
        days=["Sat"],
        offerings=[offering("o1", exerciseHours=4, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert {a.day for a in result.assignments} == {"Sat"}


def test_a_saturday_preference_is_honoured_like_any_other():
    payload = problem(
        start="2025-09-15",
        end="2025-09-27",
        teachers=[teacher("t1", preferredSlots=["sat-1"])],
        offerings=[offering("o1", exerciseHours=4, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert result.stats.preferenceViolations == 0
    assert {(a.day, a.period) for a in result.assignments} == {("Sat", 1)}


def test_switching_saturday_off_removes_it_entirely():
    payload = problem(
        start="2025-09-15",
        end="2025-09-27",
        days=["Mon", "Tue", "Wed", "Thu", "Fri"],
        offerings=[offering("o1", exerciseHours=4, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert "Sat" not in {a.day for a in result.assignments}


# ---------------------------------------------------------------------------
# The daily cap
# ---------------------------------------------------------------------------


def test_a_group_is_never_given_more_periods_in_a_day_than_its_course_allows():
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        max_periods_per_day=2,
        offerings=[offering("o1", exerciseHours=20, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    per_day = {}
    for a in result.assignments:
        per_day.setdefault(a.date, set()).add(a.period)
    assert max(len(v) for v in per_day.values()) <= 2
    assert result.validation.ok


def test_a_daily_cap_tighter_than_the_load_is_infeasible_and_says_so():
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        max_periods_per_day=1,
        offerings=[offering("o1", exerciseHours=6, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert any("too many sessions" in h.title for h in result.hints), [
        h.title for h in result.hints
    ]
