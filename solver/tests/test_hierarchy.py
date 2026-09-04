"""Групи, подгрупи and потоци.

Two rules that pull against each other, and the whole point of the split:

  * a group-level session -- a поток лекция, or a упражнение taught to a whole
    група -- excludes every подгрупа of that група, and
  * two подгрупи of the same група may be taught at the same time.

A union over "everything the group could be doing" would satisfy the first and
break the second, which would make splitting a група pointless: гр. 1а at
стрелбището while гр. 1б is in АЕ is exactly what подгрупи exist for.
"""

from app.models import ActivityKind, SolveRequest
from app.timetable_solver import solve_timetable
from conftest import offering, problem, room, teacher


def solve(payload):
    return solve_timetable(SolveRequest(**payload))


def split_group(**over):
    """One група of 24, split into two подгрупи of 12."""
    over.setdefault("subgroups", [
        {"id": "a", "groupId": "g1", "name": "гр. 1а", "size": 12},
        {"id": "b", "groupId": "g1", "name": "гр. 1б", "size": 12},
    ])
    over.setdefault("groups", [
        {"id": "g1", "name": "гр. 1", "size": 24, "courseInstanceId": "c1"}
    ])
    return problem(**over)


def dated_slot(a):
    return a.slot


# ---------------------------------------------------------------------------
# Подгрупи run side by side
# ---------------------------------------------------------------------------


def test_two_subgroups_of_one_group_may_share_a_period():
    """One day, one period, two подгрупи, two instructors and two стрелбища. If
    the model treated a group's подгрупи as one calendar this would be
    INFEASIBLE."""
    payload = split_group(
        start="2025-09-15",
        end="2025-09-15",
        periods=1,
        rooms=[room("r1", "стрелбище", 15), room("r2", "стрелбище", 15)],
        teachers=[teacher("t1"), teacher("t2")],
        offerings=[
            offering("o1", exerciseHours=2, exerciseRoomTypes=["стрелбище"],
                     exerciseTeacherIds=["t1", "t2"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a", "b"])
        ],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    assert len(result.assignments) == 2
    assert len({dated_slot(a) for a in result.assignments}) == 1
    assert {a.subgroupId for a in result.assignments} == {"a", "b"}
    assert result.validation.ok


def test_a_subgroup_is_never_taught_twice_in_one_period():
    payload = split_group(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "стрелбище", 15), room("r2", "стрелбище", 15)],
        teachers=[teacher("t1"), teacher("t2")],
        offerings=[
            offering("o1", exerciseHours=6, exerciseRoomTypes=["стрелбище"],
                     exerciseTeacherIds=["t1", "t2"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a", "b"])
        ],
    )
    result = solve(payload)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    seen = set()
    for a in result.assignments:
        key = (a.subgroupId, dated_slot(a))
        assert key not in seen
        seen.add(key)


# ---------------------------------------------------------------------------
# ... but never against their own group
# ---------------------------------------------------------------------------


def test_a_group_level_session_excludes_every_subgroup_of_that_group():
    """Fill all but one period of the day with група-level упражнения; the two
    подгрупи have to share what is left, and may not sit on top of the група."""
    payload = split_group(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "зала", 100), room("r2", "стрелбище", 15),
               room("r3", "стрелбище", 15)],
        teachers=[teacher("t1"), teacher("t2"), teacher("t3")],
        subjects=[
            {"id": "s1", "code": "S1", "name": "Право", "katedraId": "k1"},
            {"id": "s2", "code": "СП", "name": "Стрелкова", "katedraId": "k1"},
        ],
        offerings=[
            # Five of the six periods go to the whole група.
            offering("o1", "s1", exerciseHours=10, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"]),
            # Both подгрупи still fit -- in the one period that is left, together.
            offering("o2", "s2", exerciseHours=2, exerciseRoomTypes=["стрелбище"],
                     exerciseTeacherIds=["t2", "t3"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a", "b"]),
        ],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    group_level = {dated_slot(a) for a in result.assignments if a.subgroupId is None}
    subgroup = {dated_slot(a) for a in result.assignments if a.subgroupId}
    assert len(group_level) == 5
    assert len(subgroup) == 1
    assert not (group_level & subgroup)
    assert result.validation.ok


def test_a_potok_lecture_excludes_the_subgroups_of_every_stream_group():
    payload = split_group(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "зала", 100), room("r2", "стрелбище", 15),
               room("r3", "стрелбище", 15)],
        teachers=[teacher("t1"), teacher("t2"), teacher("t3")],
        subjects=[
            {"id": "s1", "code": "S1", "name": "Право", "katedraId": "k1"},
            {"id": "s2", "code": "СП", "name": "Стрелкова", "katedraId": "k1"},
        ],
        offerings=[
            offering("o1", "s1", lectureHours=10, lectureRoomTypes=["зала"],
                     streamGroupIds=["g1"], leadTeacherId="t1"),
            offering("o2", "s2", exerciseHours=2, exerciseRoomTypes=["стрелбище"],
                     exerciseTeacherIds=["t2", "t3"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a", "b"]),
        ],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    lectures = {dated_slot(a) for a in result.assignments
                if a.activity is ActivityKind.lektsiya}
    subgroup = {dated_slot(a) for a in result.assignments if a.subgroupId}
    assert not (lectures & subgroup)


# ---------------------------------------------------------------------------
# Sizes, rooms and streams
# ---------------------------------------------------------------------------


def test_a_subgroup_session_is_sized_by_the_subgroup_not_the_group():
    """A стрелбище that holds twelve can take a подгрупа but not the група --
    which is the reason the split exists at all."""
    payload = split_group(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "стрелбище", 12)],
        offerings=[
            offering("o1", exerciseHours=2, exerciseRoomTypes=["стрелбище"],
                     exerciseTeacherIds=["t1"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a"])
        ],
    )
    assert solve(payload).status == "OPTIMAL"

    whole = split_group(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "стрелбище", 12)],
        offerings=[
            offering("o1", exerciseHours=2, exerciseRoomTypes=["стрелбище"],
                     exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])
        ],
    )
    assert solve(whole).status == "INFEASIBLE"


def test_a_horarium_is_per_unit_not_per_offering():
    """15 упражнителни часа means fifteen hours *each*: the хорариум is what one
    student is owed, not what the катедра delivers once."""
    payload = split_group(
        start="2025-09-15",
        end="2025-09-20",
        rooms=[room("r1", "стрелбище", 15), room("r2", "стрелбище", 15)],
        teachers=[teacher("t1"), teacher("t2")],
        offerings=[
            offering("o1", exerciseHours=6, exerciseRoomTypes=["стрелбище"],
                     exerciseTeacherIds=["t1", "t2"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a", "b"])
        ],
    )
    result = solve(payload)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    per_unit = {}
    for a in result.assignments:
        per_unit[a.subgroupId] = per_unit.get(a.subgroupId, 0) + 1
    assert per_unit == {"a": 3, "b": 3}


def test_a_stream_busies_every_group_in_it():
    """Two групи merged for a лекция: neither can be anywhere else in that period."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "зала", 100), room("r2", "зала", 100)],
        teachers=[teacher("t1"), teacher("t2")],
        groups=[
            {"id": "g1", "name": "гр. 1", "size": 20, "courseInstanceId": "c1"},
            {"id": "g2", "name": "гр. 2", "size": 20, "courseInstanceId": "c1"},
        ],
        subjects=[
            {"id": "s1", "code": "S1", "name": "Право", "katedraId": "k1"},
            {"id": "s2", "code": "S2", "name": "Психология", "katedraId": "k1"},
        ],
        offerings=[
            offering("o1", "s1", lectureHours=4, lectureRoomTypes=["зала"],
                     streamGroupIds=["g1", "g2"], leadTeacherId="t1"),
            offering("o2", "s2", exerciseHours=4, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["t2"], exerciseUnitIds=["g2"]),
        ],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    lectures = {dated_slot(a) for a in result.assignments
                if a.activity is ActivityKind.lektsiya}
    others = {dated_slot(a) for a in result.assignments
              if a.activity is not ActivityKind.lektsiya}
    assert not (lectures & others)


def test_a_stream_is_sized_by_the_sum_of_its_groups():
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "зала", 30)],
        groups=[
            {"id": "g1", "name": "гр. 1", "size": 20, "courseInstanceId": "c1"},
            {"id": "g2", "name": "гр. 2", "size": 20, "courseInstanceId": "c1"},
        ],
        offerings=[
            offering("o1", lectureHours=2, lectureRoomTypes=["зала"],
                     streamGroupIds=["g1", "g2"], leadTeacherId="t1")
        ],
    )
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert any("does not fit any room" in h.title for h in result.hints)


def test_a_room_may_take_several_groups_when_it_says_so():
    """maxConcurrentGroups is the escape hatch: one for everything by default, and
    emphatically one for стрелбище and малка зала."""
    payload = split_group(
        start="2025-09-15",
        end="2025-09-15",
        periods=1,
        rooms=[room("r1", "спортен комплекс", 60, maxConcurrentGroups=2)],
        teachers=[teacher("t1"), teacher("t2")],
        offerings=[
            offering("o1", exerciseHours=2,
                     exerciseRoomTypes=["спортен комплекс"],
                     exerciseTeacherIds=["t1", "t2"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a", "b"])
        ],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL", result.message
    assert {a.roomId for a in result.assignments} == {"r1"}
    assert len({dated_slot(a) for a in result.assignments}) == 1
    assert result.validation.ok


def test_the_default_room_limit_is_one():
    """The same problem with the default limit has nowhere for the second
    подгрупа to go in that period."""
    payload = split_group(
        start="2025-09-15",
        end="2025-09-15",
        periods=1,
        rooms=[room("r1", "спортен комплекс", 60)],
        teachers=[teacher("t1"), teacher("t2")],
        offerings=[
            offering("o1", exerciseHours=2,
                     exerciseRoomTypes=["спортен комплекс"],
                     exerciseTeacherIds=["t1", "t2"], exerciseAudience="subgroup",
                     exerciseUnitIds=["a", "b"])
        ],
    )
    assert solve(payload).status == "INFEASIBLE"


def test_a_subgroup_naming_no_group_is_reported():
    payload = split_group(
        subgroups=[{"id": "a", "groupId": "ghost", "name": "гр. 1а", "size": 12}],
        offerings=[],
    )
    result = solve(payload)
    assert result.status == "MODEL_INVALID"
    assert any("ghost" in h.detail for h in result.hints)
