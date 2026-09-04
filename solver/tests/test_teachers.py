"""Преподаватели: hard availability, weekly caps, and водещ преподавател.

The line this file draws is between a preference and a constraint. A
preferredSlot is bought and sold by the objective; hardAvailability is not
available at any price, because a хоноруван преподавател genuinely cannot be in
the building. When it cannot be met the answer is INFEASIBLE with a name
attached, not an expensive timetable.
"""

from app.models import ActivityKind, SolveRequest
from app.timetable_solver import solve_timetable
from conftest import offering, problem, room, teacher


def solve(payload):
    return solve_timetable(SolveRequest(**payload))


# ---------------------------------------------------------------------------
# Hard availability
# ---------------------------------------------------------------------------


def test_hard_availability_is_never_violated():
    payload = problem(
        start="2025-09-15",
        end="2025-09-27",
        teachers=[teacher("t1", "хон. преп. Радева", role="honorary_lecturer",
                          hardAvailability=["fri-5", "sat-1"])],
        offerings=[offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    assert {(a.day, a.period) for a in result.assignments} <= {
        ("Fri", 5), ("Sat", 1)
    }
    assert result.validation.ok


def test_an_impossible_hard_availability_is_infeasible_not_expensive():
    """The difference from a preference, stated as a test: one period a week and
    four sessions to teach is not a penalty, it is impossible."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        teachers=[teacher("t1", "хон. преп. Радева", role="honorary_lecturer",
                          hardAvailability=["sat-1"])],
        offerings=[offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert any("over-committed" in h.title for h in result.hints), [
        h.title for h in result.hints
    ]
    assert any("хон. преп. Радева" in h.title for h in result.hints)


def test_the_same_narrow_window_as_a_preference_is_merely_expensive():
    """Same numbers, `preferredSlots` instead of `hardAvailability`: the timetable
    comes back, and the misses are paid for in the objective."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        teachers=[teacher("t1", "преп. Радева", role="lecturer",
                          preferredSlots=["sat-1"])],
        offerings=[offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert result.stats.numPlaced == 4
    assert result.stats.preferenceViolations == 3


def test_an_empty_hard_availability_means_always_available():
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        teachers=[teacher("t1", hardAvailability=[])],
        offerings=[offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    assert solve(payload).status == "OPTIMAL"


def test_availability_narrows_the_pool_not_the_offering():
    """One candidate is free only on Saturday and the other only on Monday; both
    are used, because the pool is chosen per session."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        rooms=[room("r1"), room("r2")],
        teachers=[
            teacher("t1", hardAvailability=["mon-1"]),
            teacher("t2", hardAvailability=["sat-1"]),
        ],
        groups=[
            {"id": "g1", "name": "гр. 1", "size": 10, "courseInstanceId": "c1"},
            {"id": "g2", "name": "гр. 2", "size": 10, "courseInstanceId": "c1"},
        ],
        offerings=[offering("o1", exerciseHours=2, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1", "t2"],
                            exerciseUnitIds=["g1", "g2"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    assert {a.teacherId for a in result.assignments} == {"t1", "t2"}
    for a in result.assignments:
        expected = ("Mon", 1) if a.teacherId == "t1" else ("Sat", 1)
        assert (a.day, a.period) == expected


def test_availability_outranks_rank():
    """A проф. whose window is closed does not get the period anyway: the ladder
    orders preferences, and this is not one."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        periods=2,
        rooms=[room("r1"), room("r2")],
        teachers=[
            teacher("prof", "проф.", role="professor", preferredSlots=["mon-1"],
                    hardAvailability=["mon-2"]),
            teacher("asis", "ас.", role="assistant", preferredSlots=["mon-1"]),
        ],
        subjects=[
            {"id": "s1", "code": "S1", "name": "Едно", "katedraId": "k1"},
            {"id": "s2", "code": "S2", "name": "Друго", "katedraId": "k1"},
        ],
        offerings=[
            offering("o1", "s1", exerciseHours=2, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["prof"], exerciseUnitIds=["g1"]),
            offering("o2", "s2", exerciseHours=2, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["asis"], exerciseUnitIds=["g1"]),
        ],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    by_teacher = {a.teacherId: a.period for a in result.assignments}
    assert by_teacher["prof"] == 2
    assert by_teacher["asis"] == 1


# ---------------------------------------------------------------------------
# Weekly load
# ---------------------------------------------------------------------------


def test_a_weekly_cap_is_a_hard_constraint():
    payload = problem(
        start="2025-09-15",
        end="2025-09-27",
        teachers=[teacher("t1", maxWeeklyPeriods=2)],
        offerings=[offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    per_week = {}
    for a in result.assignments:
        week = a.date.isocalendar()[:2]
        per_week[week] = per_week.get(week, 0) + 1
    assert max(per_week.values()) <= 2
    assert result.validation.ok


def test_a_weekly_cap_below_the_load_is_infeasible():
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        teachers=[teacher("t1", "преп. Донев", maxWeeklyPeriods=1)],
        offerings=[offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert any("over-committed" in h.title for h in result.hints)


def test_no_cap_means_no_constraint():
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        teachers=[teacher("t1", maxWeeklyPeriods=None)],
        offerings=[offering("o1", exerciseHours=8, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert len(result.assignments) == 4


# ---------------------------------------------------------------------------
# Водещ преподавател
# ---------------------------------------------------------------------------


def test_a_lecture_is_taught_by_its_named_lead_and_nobody_else():
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        teachers=[teacher("t1"), teacher("t2")],
        offerings=[offering("o1", lectureHours=6, lectureRoomTypes=["зала"],
                            streamGroupIds=["g1"], leadTeacherId="t1",
                            exerciseTeacherIds=["t2"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert {a.teacherId for a in result.assignments} == {"t1"}
    assert all(a.activity is ActivityKind.lektsiya for a in result.assignments)


def test_lecture_hours_without_a_lead_are_reported_not_dropped():
    payload = problem(
        offerings=[offering("o1", lectureHours=6, lectureRoomTypes=["зала"],
                            streamGroupIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "MODEL_INVALID"
    assert any("водещ преподавател" in h.detail for h in result.hints)


def test_lectures_and_exercises_of_one_offering_can_want_different_rooms():
    """The хорариум is '30/15' and the two halves rarely sit in the same room."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        rooms=[room("r1", "зала", 100), room("r2", "малка зала", 30)],
        teachers=[teacher("t1"), teacher("t2")],
        offerings=[offering("o1", lectureHours=4, exerciseHours=4,
                            lectureRoomTypes=["зала"],
                            exerciseRoomTypes=["малка зала"],
                            streamGroupIds=["g1"], leadTeacherId="t1",
                            exerciseTeacherIds=["t2"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    where = {a.activity: a.roomId for a in result.assignments}
    assert where[ActivityKind.lektsiya] == "r1"
    assert where[ActivityKind.uprazhnenie] == "r2"


def test_an_odd_horarium_rounds_up_rather_than_short_changing_the_plan():
    """15 hours at two an hour is 8 periods, not 7: a leftover hour is a smaller
    lie than a missing one."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-27",
        offerings=[offering("o1", exerciseHours=15, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert len(result.assignments) == 8
