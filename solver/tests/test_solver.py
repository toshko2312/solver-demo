"""What the solver promises.

Seven sections, in the order a reader would want them:

  1. the seed dataset solves, and the schedule it returns is valid
  2. impossible problems come back INFEASIBLE with a usable hint
  3. room-type sets and teacher pools are really choices
  4. soft constraints behave softly
  5. the solver settings are wired through and do what they say
  6. rank, ranked rooms, and the priority ladder
  7. dated semesters: terms, non-teaching periods, spread, semester scoping

The teaching day, подгрупи, hard availability and block spread have files of their
own -- test_periods.py, test_hierarchy.py, test_teachers.py, test_spread.py.
"""

import json
from collections import Counter, defaultdict

import pytest

from app.models import (
    DEFAULT_ROLES,
    DEFAULT_SOLVE_SECONDS,
    UNRANKED_WEIGHT,
    ActivityKind,
    SearchParams,
    SolveRequest,
    Teacher,
    effective_weight,
)
from app.sessions import build_series
from app.timetable_solver import solve_timetable
from conftest import (
    SMALL_SEED_PATH,
    build_slots,
    offering,
    problem,
    room,
    teacher,
)

DEFAULT_ROLES_BY_ID = {r.id: r for r in DEFAULT_ROLES}
PROFESSOR_WEIGHT = DEFAULT_ROLES_BY_ID["professor"].weight
ASSISTANT_WEIGHT = DEFAULT_ROLES_BY_ID["assistant"].weight

# What the UI's "Generate" button gives the full example.
SEED_DEMO_BUDGET_SECONDS = 30


def solve(payload):
    """Every test goes through here, so the request is always validated the way
    the HTTP layer would validate it."""
    return solve_timetable(SolveRequest(**payload))


def required_sessions(payload):
    """How many sessions this problem's хорариум asks for, by series key."""
    req = SolveRequest(**payload)
    return {s.key: s.count for s in build_series(req, req.semester)}


def dated_slot(a):
    """The dated period a session occupies -- what everything clashes on."""
    return a.slot


# ---------------------------------------------------------------------------
# 1. The seed dataset solves, and what comes back is a valid timetable
# ---------------------------------------------------------------------------


def test_seed_dataset_solves(seed):
    result = solve(seed)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.stats.numPlaced == result.stats.numSessions
    assert result.stats.numSlots > 0


def test_seed_schedule_passes_self_validation(seed):
    result = solve(seed)
    assert result.validation is not None
    assert result.validation.ok, result.validation.errors


def test_seed_schedule_has_no_double_bookings(seed):
    """Re-derived here rather than trusting validate_assignments, which is the
    solver's own homework: two independent checks of the same claim."""
    result = solve(seed)
    teachers_seen, rooms_seen, groups_seen = {}, defaultdict(int), {}
    for a in result.assignments:
        key = (a.teacherId, dated_slot(a))
        assert key not in teachers_seen, f"{a.teacherName} twice in {key}"
        teachers_seen[key] = a
        rooms_seen[(a.roomId, dated_slot(a))] += 1
        # Only group-level sessions claim a group exclusively; подгрупи of the
        # same group are allowed to run side by side, and test_hierarchy.py is
        # where that is checked.
        if a.subgroupId is None:
            for gid in a.groupIds:
                gkey = (gid, dated_slot(a))
                assert gkey not in groups_seen, f"group {gid} twice in {gkey}"
                groups_seen[gkey] = a
    assert max(rooms_seen.values()) == 1


def test_seed_schedule_respects_room_type_and_capacity(seed):
    result = solve(seed)
    rooms = {r["id"]: r for r in seed["rooms"]}
    groups = {g["id"]: g for g in seed["groups"]}
    subgroups = {s["id"]: s for s in seed["subgroups"]}
    offerings = {o["id"]: o for o in seed["offerings"]}
    for a in result.assignments:
        r = rooms[a.roomId]
        o = offerings[a.offeringId]
        allowed = (
            o["lectureRoomTypes"]
            if a.activity is ActivityKind.lektsiya
            else o["exerciseRoomTypes"]
        )
        assert r["type"] in allowed, f"{a.subjectName} in {r['name']}"
        head = (
            subgroups[a.subgroupId]["size"]
            if a.subgroupId
            else sum(groups[g]["size"] for g in a.groupIds)
        )
        assert r["capacity"] >= head


def test_seed_schedules_every_series_its_horarium(seed):
    result = solve(seed)
    counted = Counter()
    for a in result.assignments:
        if a.activity is ActivityKind.lektsiya:
            counted[f"{a.offeringId}:л"] += 1
        else:
            counted[f"{a.offeringId}:у:{a.subgroupId or a.groupIds[0]}"] += 1
    assert dict(counted) == required_sessions(seed)


def test_seed_potok_lecture_busies_every_group_in_the_stream(seed):
    """A поток лекция merges both специалности, and every group in it is busy --
    which is what stops one of them being scheduled elsewhere in that period."""
    result = solve(seed)
    lectures = [a for a in result.assignments if a.activity is ActivityKind.lektsiya]
    assert lectures, "the small seed ships поток лекции"
    multi = [a for a in lectures if len(a.groupIds) > 1]
    assert multi, "at least one лекция spans more than one group"
    for a in multi:
        for other in result.assignments:
            if other is a or dated_slot(other) != dated_slot(a):
                continue
            assert not set(other.groupIds) & set(a.groupIds), (
                f"{other.subjectName} runs against {a.subjectName} for a shared group"
            )


# ---------------------------------------------------------------------------
# 2. Impossible problems come back INFEASIBLE, with a hint that names the reason
# ---------------------------------------------------------------------------


def test_more_sessions_than_periods_is_infeasible(seed):
    """A хорариум no calendar can hold."""
    payload = dict(
        seed,
        offerings=[
            offering(
                "over",
                exerciseHours=600,
                exerciseRoomTypes=["зала"],
                exerciseTeacherIds=["t1"],
                exerciseUnitIds=["g1"],
            )
        ],
    )
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert result.hints


def test_capacity_impossible_is_infeasible_with_capacity_hint(seed):
    """Shrink every стрелбище below one подгрупа and СП has nowhere to go."""
    rooms = [
        dict(r, capacity=1) if r["type"] == "стрелбище" else r for r in seed["rooms"]
    ]
    result = solve(dict(seed, rooms=rooms))
    assert result.status == "INFEASIBLE"
    assert any("does not fit any room" in h.title for h in result.hints), [
        h.title for h in result.hints
    ]


def test_blocking_every_period_is_infeasible(seed):
    """Blocking is weekday-keyed, so blocking every period leaves nothing."""
    cfg = json.loads(SMALL_SEED_PATH.read_text())["slotConfig"]
    everything = [
        f"{d.lower()}-{p}"
        for d in cfg["days"]
        for p in range(1, cfg["periods"] + 1)
    ]
    payload = dict(
        seed,
        slots=build_slots(
            cfg["days"], cfg["periods"], set(everything), "2025-09-15", "2025-09-27"
        ),
    )
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert any("period" in h.title.lower() for h in result.hints), [
        h.title for h in result.hints
    ]


def test_missing_room_type_is_infeasible_with_hint(seed):
    """Delete the стрелбища and СП names a type that does not exist."""
    rooms = [r for r in seed["rooms"] if r["type"] != "стрелбище"]
    result = solve(dict(seed, rooms=rooms))
    assert result.status == "INFEASIBLE"
    assert any("No стрелбище room exists" in h.title for h in result.hints), [
        h.title for h in result.hints
    ]


def test_dangling_teacher_reference_is_reported_not_crashed(seed):
    offerings = [dict(o) for o in seed["offerings"]]
    offerings[0] = dict(
        offerings[0],
        exerciseTeacherIds=["ghost"],
        exerciseHours=4,
        exerciseRoomTypes=["малка зала"],
        exerciseUnitIds=["g1"],
    )
    result = solve(dict(seed, offerings=offerings))
    assert result.status == "MODEL_INVALID"
    assert any("ghost" in h.detail for h in result.hints)


def test_an_offering_with_hours_but_no_teacher_is_reported(seed):
    """Hours with nobody to teach them would silently vanish from the план."""
    payload = dict(
        seed,
        offerings=[
            offering("o", exerciseHours=4, exerciseRoomTypes=["зала"],
                     exerciseUnitIds=["g1"])
        ],
    )
    result = solve(payload)
    assert result.status == "MODEL_INVALID"
    assert any("no candidate teachers" in h.detail for h in result.hints)


# ---------------------------------------------------------------------------
# 3. Room-type sets and teacher pools are really choices
# ---------------------------------------------------------------------------


def test_assigned_teacher_and_room_come_from_the_offerings_own_options(seed):
    result = solve(seed)
    offerings = {o["id"]: o for o in seed["offerings"]}
    rooms = {r["id"]: r for r in seed["rooms"]}
    for a in result.assignments:
        o = offerings[a.offeringId]
        if a.activity is ActivityKind.lektsiya:
            assert a.teacherId == o["leadTeacherId"]
            assert rooms[a.roomId]["type"] in o["lectureRoomTypes"]
        else:
            assert a.teacherId in o["exerciseTeacherIds"]
            assert rooms[a.roomId]["type"] in o["exerciseRoomTypes"]


def test_a_teacher_pool_is_actually_used():
    """Two candidates and more sessions than either can carry alone: six sessions
    in a five-period day cannot be one person's, so the solver has to split them --
    which is the pool doing something."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "зала", 100), room("r2", "зала", 100)],
        teachers=[teacher("t1"), teacher("t2")],
        groups=[
            {"id": "g1", "name": "гр. 1", "size": 10, "courseInstanceId": "c1"},
            {"id": "g2", "name": "гр. 2", "size": 10, "courseInstanceId": "c1"},
        ],
        offerings=[
            offering("o1", exerciseHours=6, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["t1", "t2"], exerciseUnitIds=["g1", "g2"])
        ],
    )
    result = solve(payload)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert len(result.assignments) == 6
    assert {a.teacherId for a in result.assignments} == {"t1", "t2"}


def test_pool_relieves_an_over_commitment_one_teacher_cannot_carry():
    """Ten sessions, six periods in the day: one teacher cannot, two can."""
    base = dict(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "зала", 100), room("r2", "зала", 100)],
        teachers=[teacher("t1"), teacher("t2")],
        groups=[
            {"id": f"g{i}", "name": f"гр. {i}", "size": 10, "courseInstanceId": "c1"}
            for i in (1, 2)
        ],
    )
    alone = problem(
        offerings=[offering("o1", exerciseHours=10, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1", "g2"])],
        **base,
    )
    assert solve(alone).status == "INFEASIBLE"

    shared = problem(
        offerings=[offering("o1", exerciseHours=10, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1", "t2"],
                            exerciseUnitIds=["g1", "g2"])],
        **base,
    )
    assert solve(shared).status in ("OPTIMAL", "FEASIBLE")


def test_second_room_type_saves_an_offering_when_its_first_choice_is_gone(seed):
    """ЛЗФП accepts спортен комплекс or тренажорна зала; delete the halls and it
    still runs in the gym."""
    rooms = [r for r in seed["rooms"] if r["type"] != "спортен комплекс"]
    result = solve(dict(seed, rooms=rooms))
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    gym = [a for a in result.assignments if a.subjectCode == "ЛЗФП"]
    assert gym and all(a.roomName == "Тренажорна зала" for a in gym)


def test_pooled_teachers_are_blamed_collectively_not_individually():
    """A pool shares its load, so the hint has to name the pool, not a member."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        teachers=[teacher("t1", "Първи"), teacher("t2", "Втори")],
        offerings=[
            offering("o1", exerciseHours=40, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["t1", "t2"], exerciseUnitIds=["g1"])
        ],
    )
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert any("collectively over-committed" in h.title for h in result.hints), [
        h.title for h in result.hints
    ]


# ---------------------------------------------------------------------------
# 4. Soft constraints behave softly
# ---------------------------------------------------------------------------


def test_soft_preferences_are_optimised_not_enforced(seed):
    """A preference nobody can meet costs penalty; it never refuses to schedule.
    This is the line between preferredSlots and hardAvailability."""
    teachers = [dict(t, preferredSlots=["mon-1-2"]) for t in seed["teachers"]]
    result = solve(dict(seed, teachers=teachers))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.stats.numPlaced == result.stats.numSessions
    assert result.stats.preferenceViolations > 0


def test_impossible_preferences_cost_penalty_but_stay_solvable(seed):
    """The same preference, on a weekday the grid does not have."""
    teachers = [dict(t, preferredSlots=["sun-1-2"]) for t in seed["teachers"]]
    result = solve(dict(seed, teachers=teachers))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.stats.numPlaced == result.stats.numSessions


def test_a_request_that_names_no_time_limit_gets_no_deadline(seed):
    """The default is unlimited, not a demo-sized budget.

    A faculty-sized semester needs about ninety seconds just to find its first
    legal timetable, so any default short enough to feel quick would hand back
    UNKNOWN with nothing placed -- a worse answer than a slow one.
    """
    payload = dict(seed)
    payload.pop("maxTimeInSeconds")
    assert DEFAULT_SOLVE_SECONDS is None
    assert SolveRequest(**payload).maxTimeInSeconds is None


def test_no_time_limit_runs_to_completion():
    """`null` is not "zero seconds": it is no deadline at all."""
    payload = problem(
        offerings=[offering("o1", exerciseHours=6, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])]
    )
    payload["maxTimeInSeconds"] = None
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert result.settingsUsed.maxTimeInSeconds is None


def test_an_unlimited_run_that_finds_nothing_does_not_blame_the_clock():
    """An unlimited run never ran out of time, so its message must not say it did.

    This covers the INFEASIBLE half. The UNKNOWN half -- where the solver gives up
    for its own reasons -- takes the branch above it in `solve_timetable`, and is
    not reachable on demand from a test: with no deadline CP-SAT returns OPTIMAL
    or INFEASIBLE on any problem small enough to run here.
    """
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        offerings=[offering("o1", exerciseHours=40, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    payload["maxTimeInSeconds"] = None
    result = solve(payload)
    assert result.status == "INFEASIBLE"
    assert "within" not in result.message


# ---------------------------------------------------------------------------
# 5. The solver settings are wired through and do what they say
# ---------------------------------------------------------------------------


def test_stop_after_first_solution_returns_the_first_timetable_not_the_best(seed):
    fast = solve(dict(seed, stopAfterFirstSolution=True))
    best = solve(seed)
    assert fast.status in ("OPTIMAL", "FEASIBLE")
    assert fast.stats.numPlaced == fast.stats.numSessions
    assert fast.stats.objectiveValue >= best.stats.objectiveValue
    assert fast.settingsUsed.stopAfterFirstSolution is True


def test_disabling_our_symmetry_breaking_still_reaches_the_same_optimum(seed):
    with_it = solve(seed)
    without = solve(dict(seed, useSymmetryBreaking=False))
    assert without.status == with_it.status
    assert without.stats.objectiveValue == with_it.stats.objectiveValue


def test_search_parameters_do_not_change_the_answer(seed):
    base = solve(seed)
    for params in (
        {"numWorkers": 1, "randomSeed": 7, "presolve": True,
         "symmetryLevel": None, "linearizationLevel": None},
        {"numWorkers": 4, "randomSeed": 0, "presolve": False,
         "symmetryLevel": 0, "linearizationLevel": 2},
    ):
        other = solve(dict(seed, search=params))
        assert other.status == base.status
        assert other.stats.objectiveValue == base.stats.objectiveValue
        assert other.validation.ok


def test_single_worker_with_a_fixed_seed_is_reproducible(seed):
    params = {"numWorkers": 1, "randomSeed": 42, "presolve": True,
              "symmetryLevel": None, "linearizationLevel": None}
    shape = lambda r: [
        (a.offeringId, a.slot, a.roomId, a.teacherId) for a in r.assignments
    ]
    assert shape(solve(dict(seed, search=params))) == shape(
        solve(dict(seed, search=params))
    )


def test_search_parameters_are_bounded_by_the_schema():
    with pytest.raises(Exception):
        SearchParams(numWorkers=99)
    with pytest.raises(Exception):
        SearchParams(symmetryLevel=9)


def test_settings_used_is_echoed_back(seed):
    result = solve(dict(seed, preferenceWeight=17, roomPreferenceWeight=3, gapWeight=0))
    used = result.settingsUsed
    assert (used.preferenceWeight, used.roomPreferenceWeight, used.gapWeight) == (17, 3, 0)


def test_gap_weight_can_no_longer_buy_gaps_with_teacher_preferences(seed):
    """Gaps are the last rung of the ladder, so by the time they are scored every
    teacher rank is frozen. Raising gapWeight can only scale the number it
    reports -- it can never trade a preference away for a compact day."""
    low = solve(dict(seed, gapWeight=1))
    high = solve(dict(seed, gapWeight=10))
    assert low.stats.preferenceViolations == high.stats.preferenceViolations
    assert low.stats.gapPenalty == high.stats.gapPenalty


def test_zero_weights_still_produce_a_valid_timetable(seed):
    result = solve(dict(seed, preferenceWeight=0, roomPreferenceWeight=0, gapWeight=0))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.validation.ok
    assert result.stats.numPlaced == result.stats.numSessions


def test_full_seed_produces_a_valid_timetable_within_the_demo_budget(full_seed):
    """The instance the UI's "Full example" button sends. It is hard enough that
    OPTIMAL is not promised -- but every session placed and every hard rule
    verified is."""
    result = solve(dict(full_seed, maxTimeInSeconds=SEED_DEMO_BUDGET_SECONDS))
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.stats.numPlaced == result.stats.numSessions
    assert result.validation.ok, result.validation.errors[:5]


# ---------------------------------------------------------------------------
# 6. Rank, ranked rooms, and the priority ladder
# ---------------------------------------------------------------------------


def test_effective_weight_prefers_override_then_role_then_unranked():
    roles = DEFAULT_ROLES_BY_ID
    assert effective_weight(Teacher(id="a", name="A", role="professor"), roles) == (
        PROFESSOR_WEIGHT
    )
    assert effective_weight(
        Teacher(id="b", name="B", role="professor", priorityWeight=0), roles
    ) == 0
    assert effective_weight(Teacher(id="c", name="C"), roles) == UNRANKED_WEIGHT
    # A role id naming no role is a demotion, not a crash.
    assert effective_weight(Teacher(id="d", name="D", role="ghost"), roles) == (
        UNRANKED_WEIGHT
    )


def test_weights_come_from_the_request_not_from_the_code(seed):
    """Invert the ladder in the request and the tiers come back inverted.

    The fixture deliberately sends no `roles` -- see the fallback test below --
    so the ranks come from the seed file itself.
    """
    shipped = json.loads(SMALL_SEED_PATH.read_text())["roles"]
    roles = [dict(r, weight=100 - r["weight"]) for r in shipped]
    result = solve(dict(seed, roles=roles))
    weights = [t.weight for t in result.stats.tiers]
    assert weights == sorted(weights, reverse=True)
    assert max(weights) == 100 - min(r["weight"] for r in shipped)


def test_a_request_naming_no_roles_falls_back_to_the_built_in_ranks(seed):
    payload = dict(seed)
    payload.pop("roles", None)
    assert "roles" not in payload
    result = solve(payload)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert {t.weight for t in result.stats.tiers} <= {r.weight for r in DEFAULT_ROLES}


def test_the_seed_ships_roles_that_match_the_built_in_ranks():
    shipped = json.loads(SMALL_SEED_PATH.read_text())["roles"]
    assert [(r["id"], r["weight"]) for r in shipped] == [
        (r.id, r.weight) for r in DEFAULT_ROLES
    ]


def test_duplicate_role_ids_are_reported(seed):
    shipped = json.loads(SMALL_SEED_PATH.read_text())["roles"]
    roles = shipped + [dict(shipped[0])]
    result = solve(dict(seed, roles=roles))
    assert result.status == "MODEL_INVALID"
    assert any("Duplicate role id" in h.detail for h in result.hints)


def test_a_problem_with_no_roles_has_exactly_one_tier(seed):
    """No ranks at all is the single-objective behaviour that predates the
    ladder, and it still has to work."""
    teachers = [
        {k: v for k, v in t.items() if k not in ("role", "priorityWeight")}
        for t in seed["teachers"]
    ]
    result = solve(dict(seed, roles=[], teachers=teachers))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert len(result.stats.tiers) == 1
    assert result.stats.tiers[0].weight == UNRANKED_WEIGHT


def test_tiers_are_reported_top_down_and_cover_every_teacher(seed):
    result = solve(seed)
    weights = [t.weight for t in result.stats.tiers]
    assert weights == sorted(weights, reverse=True)
    assert sum(t.teacherCount for t in result.stats.tiers) == len(seed["teachers"])


def test_a_teacher_ranking_no_rooms_is_never_charged_for_one(seed):
    teachers = [dict(t, preferredRooms=[]) for t in seed["teachers"]]
    result = solve(dict(seed, teachers=teachers))
    assert result.stats.roomPreferencePenalty == 0
    assert all(a.roomPreferenceRank is None for a in result.assignments)


def test_room_rank_is_scoped_to_the_rooms_type():
    """Ranking two зали says nothing about which стрелбище you get: which room a
    session may use at all is hard, so a teacher is never billed for a type they
    expressed no opinion about."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-15",
        rooms=[room("r1", "зала", 100), room("r2", "зала", 100),
               room("r3", "стрелбище", 30)],
        teachers=[teacher("t1", preferredRooms=["r1", "r2"])],
        offerings=[offering("o1", exerciseHours=2, exerciseRoomTypes=["стрелбище"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert result.stats.roomPreferencePenalty == 0
    assert all(a.roomPreferenceRank is None for a in result.assignments)


def test_a_dangling_or_duplicated_ranked_room_is_tolerated(seed):
    """Deleting a room must not invalidate every teacher who ranked it."""
    teachers = [dict(t, preferredRooms=["ghost", "r1", "r1"]) for t in seed["teachers"]]
    result = solve(dict(seed, teachers=teachers))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.validation.ok


# ---- the ladder, head to head ---------------------------------------------


def _duel(period_count=2, teachers=None, offerings=None, groups=None):
    """Two ranks, one day, and fewer periods than they both want.

    Everything is on one date so the only thing left to decide is *which period*,
    which is what makes the outcome legible: the winner takes period 1.
    """
    groups = groups or [
        {"id": "g1", "name": "гр. 1", "size": 10, "courseInstanceId": "c1"}
    ]
    return problem(
        start="2025-09-15",
        end="2025-09-15",
        periods=period_count,
        rooms=[room(f"r{i}", "зала", 100) for i in range(1, period_count + 2)],
        teachers=teachers or [],
        groups=groups,
        subjects=[
            {"id": f"s{i}", "code": f"S{i}", "name": f"Дисциплина {i}", "katedraId": "k1"}
            for i in range(1, 7)
        ],
        offerings=offerings or [],
    )


def _period_of(result, teacher_id):
    return next(a.period for a in result.assignments if a.teacherId == teacher_id)


def test_the_higher_rank_wins_a_contested_period():
    payload = _duel(
        teachers=[
            teacher("prof", "проф.", role="professor", preferredSlots=["mon-1"]),
            teacher("asis", "ас.", role="assistant", preferredSlots=["mon-1"]),
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
    assert _period_of(result, "prof") == 1
    assert _period_of(result, "asis") != 1


def test_one_professor_outranks_any_number_of_assistants():
    """The claim no choice of weights can express: a rank is never sold, however
    many juniors would gain by it."""
    assistants = [
        teacher(f"a{i}", f"ас. {i}", role="assistant", preferredSlots=["mon-1"])
        for i in range(1, 5)
    ]
    groups = [
        {"id": f"g{i}", "name": f"гр. {i}", "size": 10, "courseInstanceId": "c1"}
        for i in range(1, 6)
    ]
    payload = _duel(
        period_count=5,
        teachers=[teacher("prof", "проф.", role="professor",
                          preferredSlots=["mon-1"])] + assistants,
        groups=groups,
        offerings=[
            offering("o0", "s1", exerciseHours=2, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["prof"], exerciseUnitIds=["g1"])
        ] + [
            offering(f"o{i}", "s2", exerciseHours=2, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=[f"a{i}"], exerciseUnitIds=[f"g{i + 1}"])
            for i in range(1, 5)
        ],
    )
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert _period_of(result, "prof") == 1
    top = next(t for t in result.stats.tiers if t.weight == PROFESSOR_WEIGHT)
    assert top.penalty == 0


def test_a_lower_tier_can_never_improve_at_a_higher_tiers_expense():
    payload = _duel(
        teachers=[
            teacher("prof", "проф.", role="professor", preferredSlots=["mon-1"]),
            teacher("asis", "ас.", role="assistant", preferredSlots=["mon-1"]),
        ],
        offerings=[
            offering("o1", "s1", exerciseHours=2, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["prof"], exerciseUnitIds=["g1"]),
            offering("o2", "s2", exerciseHours=2, exerciseRoomTypes=["зала"],
                     exerciseTeacherIds=["asis"], exerciseUnitIds=["g1"]),
        ],
    )
    result = solve(payload)
    tiers = {t.weight: t for t in result.stats.tiers}
    assert tiers[PROFESSOR_WEIGHT].penalty == 0
    assert tiers[ASSISTANT_WEIGHT].penalty > 0


# ---------------------------------------------------------------------------
# 7. Dated semesters: terms, non-teaching periods, spread, semester scoping
# ---------------------------------------------------------------------------


def _dated(start, end, non_teaching=(), hours=12, spread="whole", window=None,
           days=None, semester=None):
    """One group, one teacher, one room, one offering, over a real date span."""
    over = {}
    if window is not None:
        over["window"] = {"start": window[0], "end": window[1]}
    payload = problem(
        start=start,
        end=end,
        days=days,
        non_teaching=non_teaching,
        seconds=20.0,
        offerings=[offering("o1", exerciseHours=hours, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"],
                            spread=spread, **over)],
    )
    if semester is not None:
        payload["semester"] = semester
    return payload


def _weeks_of(result):
    return Counter(a.date.isocalendar()[:2] for a in result.assignments)


def test_sessions_land_on_real_dates_inside_the_term():
    result = solve(_dated("2025-09-15", "2025-10-11"))
    assert result.status == "OPTIMAL"
    assert all(
        "2025-09-15" <= a.date.isoformat() <= "2025-10-11" for a in result.assignments
    )


def test_nothing_is_ever_scheduled_in_a_non_teaching_period():
    closed = [{"start": "2025-09-22", "end": "2025-09-27", "kind": "стаж",
               "label": "Учебен стаж"}]
    result = solve(_dated("2025-09-15", "2025-10-11", non_teaching=closed))
    assert result.status == "OPTIMAL"
    assert not any(
        "2025-09-22" <= a.date.isoformat() <= "2025-09-27" for a in result.assignments
    )


def test_every_kind_of_non_teaching_period_closes_the_calendar():
    """ваканция, стаж, изпитна сесия and празник are equally unusable -- they are
    kept apart so the разписание can print them, not so the solver can."""
    for kind in ("ваканция", "стаж", "изпитна сесия", "празник"):
        closed = [{"start": "2025-09-22", "end": "2025-09-27", "kind": kind}]
        result = solve(_dated("2025-09-15", "2025-10-11", non_teaching=closed))
        assert result.status == "OPTIMAL", kind
        assert not any(
            "2025-09-22" <= a.date.isoformat() <= "2025-09-27"
            for a in result.assignments
        ), kind


def test_sessions_are_spread_evenly_across_the_teaching_weeks():
    result = solve(_dated("2025-09-15", "2025-10-11", hours=8))
    assert result.status == "OPTIMAL"
    assert set(_weeks_of(result).values()) == {1}


def test_an_uneven_total_still_spreads_as_evenly_as_it_can():
    result = solve(_dated("2025-09-15", "2025-10-11", hours=12))
    assert result.status == "OPTIMAL"
    assert set(_weeks_of(result).values()) <= {1, 2}


def test_a_spread_window_confines_sessions_to_the_period_chosen():
    result = solve(
        _dated("2025-09-15", "2025-10-11", hours=4, spread="range",
               window=("2025-10-01", "2025-10-11"))
    )
    assert result.status == "OPTIMAL"
    assert all(
        "2025-10-01" <= a.date.isoformat() <= "2025-10-11" for a in result.assignments
    )


def test_a_course_out_of_term_takes_no_part():
    result = solve(
        _dated("2025-09-15", "2025-10-11",
               semester={"academicYear": "2025/2026", "index": 2})
    )
    assert result.status == "OPTIMAL"
    assert result.assignments == []
    assert result.stats.numSessions == 0


def test_teacher_period_preferences_recur_every_week():
    """'mon-1' means that period every Monday, not one Monday in September."""
    payload = _dated("2025-09-15", "2025-10-11", hours=8)
    payload["teachers"] = [teacher("t1", preferredSlots=["mon-1"])]
    result = solve(payload)
    assert result.status == "OPTIMAL"
    assert result.stats.preferenceViolations == 0
    assert {(a.day, a.period) for a in result.assignments} == {("Mon", 1)}


def test_progress_events_report_the_ladder_without_changing_the_answer(seed):
    events = []
    quiet = solve_timetable(SolveRequest(**seed))
    loud = solve_timetable(SolveRequest(**seed), events.append)
    assert quiet.stats.objectiveValue == loud.stats.objectiveValue

    kinds = [e["type"] for e in events]
    assert kinds[0] == "building"
    assert kinds[1] == "built"
    assert "phase" in kinds and "phase_done" in kinds
    built = events[1]
    assert built["total"] == 1 + len(built["phases"])
    starts = [e for e in events if e["type"] == "phase"]
    assert starts[0]["label"] == "warmup"
    assert [e["index"] for e in starts] == list(range(1, len(starts) + 1))
