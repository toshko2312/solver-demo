"""End-to-end checks on the CP-SAT model.

These are the checks the brief calls for before the PoC can be called done:
the seed dataset must produce a valid conflict-free timetable, and an
over-constrained dataset must come back INFEASIBLE rather than hanging.
"""

import json
from collections import Counter, defaultdict

import pytest

from pydantic import ValidationError

from app.models import (
    DEFAULT_ROLES,
    DEFAULT_SOLVE_SECONDS,
    UNRANKED_WEIGHT,
    SearchParams,
    SolveRequest,
    Teacher,
    effective_weight,
)

# The built-in ranks, by id, for tests that assert on a specific rank's weight.
DEFAULT_ROLES_BY_ID = {r.id: r for r in DEFAULT_ROLES}
PROFESSOR_WEIGHT = DEFAULT_ROLES_BY_ID["professor"].weight
ASSISTANT_WEIGHT = DEFAULT_ROLES_BY_ID["assistant"].weight

# What "Load example -> Generate" is allowed to take.
SEED_DEMO_BUDGET_SECONDS = 30
from app.timetable_solver import solve_timetable
from conftest import SEED_SEMESTER, SMALL_SEED_PATH, build_slots


def _seed_total(subject) -> int:
    """Sessions a seed subject runs in the semester the fixtures generate for."""
    return sum(
        x["totalSessions"]
        for x in subject["semesters"]
        if x["academicYear"] == SEED_SEMESTER["academicYear"]
        and x["index"] == SEED_SEMESTER["index"]
    )


def solve(payload):
    return solve_timetable(SolveRequest(**payload))


# --------------------------------------------------------------------------- #
# 1. The seed dataset solves, and the schedule it returns is actually valid.
# --------------------------------------------------------------------------- #


def test_seed_dataset_solves(seed):
    result = solve(seed)
    expected = sum(_seed_total(s) for s in seed["subjects"])
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.stats.numPlaced == result.stats.numSessions == expected


def test_seed_schedule_passes_self_validation(seed):
    result = solve(seed)
    assert result.validation is not None
    assert result.validation.ok, result.validation.errors


def test_seed_schedule_has_no_double_bookings(seed):
    """Checked here independently of validate_assignments, so a bug in the
    validator cannot hide a bug in the model."""
    result = solve(seed)

    teacher_slots = defaultdict(list)
    group_slots = defaultdict(list)
    room_slots = defaultdict(list)
    for a in result.assignments:
        teacher_slots[(a.teacherId, a.slot)].append(a.subjectName)
        room_slots[(a.roomId, a.slot)].append(a.subjectName)
        for gid in a.groupIds:
            group_slots[(gid, a.slot)].append(a.subjectName)

    for key, subjects in teacher_slots.items():
        assert len(subjects) == 1, f"teacher double-booked at {key}: {subjects}"
    for key, subjects in group_slots.items():
        assert len(subjects) == 1, f"group double-booked at {key}: {subjects}"
    for key, subjects in room_slots.items():
        assert len(subjects) == 1, f"room double-booked at {key}: {subjects}"


def test_seed_schedule_respects_room_type_and_capacity(seed):
    result = solve(seed)
    rooms = {r["id"]: r for r in seed["rooms"]}
    groups = {g["id"]: g for g in seed["groups"]}
    subjects = {s["id"]: s for s in seed["subjects"]}

    for a in result.assignments:
        room = rooms[a.roomId]
        assert room["type"] in subjects[a.subjectId]["allowedRoomTypes"], a.subjectName
        head_count = sum(groups[g]["size"] for g in a.groupIds)
        assert room["capacity"] >= head_count, f"{a.subjectName} overflows {room['name']}"


def test_seed_schedules_each_subject_the_right_number_of_times(seed):
    result = solve(seed)
    placed = defaultdict(int)
    for a in result.assignments:
        placed[a.subjectId] += 1
    for subject in seed["subjects"]:
        assert placed[subject["id"]] == _seed_total(subject), subject["name"]


def test_seed_multi_group_subject_busies_every_group(seed):
    """A lecture delivered to a whole поток blocks every one of its groups.
    Selected by role rather than by id, so regenerating the dataset cannot
    quietly turn this into a test of nothing."""
    shared = next(s for s in seed["subjects"] if len(s["semesters"][0]["groupIds"]) > 1)
    result = solve(seed)

    shared_slots = {a.slot for a in result.assignments if a.subjectId == shared["id"]}
    assert shared_slots, f"{shared['name']} was not scheduled"
    for a in result.assignments:
        if a.subjectId == shared["id"] or a.slot not in shared_slots:
            continue
        clash = set(a.groupIds) & set(shared["semesters"][0]["groupIds"])
        assert not clash, f"{a.subjectName} clashes with {shared['name']} at {a.slot}"


# --------------------------------------------------------------------------- #
# 2. Impossible problems come back INFEASIBLE, fast, with a usable hint.
# --------------------------------------------------------------------------- #


def test_more_sessions_than_slots_is_infeasible(seed):
    """One period per day = 5 slots, but Recruit Class A attends 7 sessions a week."""
    over = dict(seed, slots=build_slots(["Mon", "Tue", "Wed", "Thu", "Fri"], 1))
    result = solve(over)

    assert result.status == "INFEASIBLE"
    assert result.assignments == []
    assert result.hints, "an infeasible problem should come with a hint"
    assert result.stats.solveTimeSeconds < 5.0, "should fail fast, not hang"
    assert any("too many sessions" in h.title for h in result.hints), result.hints


def test_capacity_impossible_is_infeasible_with_capacity_hint(seed):
    """Grow the group that needs the firing range past its capacity."""
    firing = next(s for s in seed["subjects"] if "firing_range" in s["allowedRoomTypes"])
    biggest = max(r["capacity"] for r in seed["rooms"] if r["type"] == "firing_range")
    groups = [
        dict(g, size=biggest + 50) if g["id"] in firing["semesters"][0]["groupIds"] else dict(g)
        for g in seed["groups"]
    ]
    result = solve(dict(seed, groups=groups))

    assert result.status == "INFEASIBLE"
    assert any("does not fit any room" in h.title for h in result.hints), result.hints


def test_blocking_every_firing_range_slot_is_infeasible(seed):
    """The UI's 'break it' path: block slots until a required room type has none
    left. Firearms Qualification still needs one."""
    result = solve(dict(seed, slots=[]))
    assert result.status == "INFEASIBLE"
    assert result.hints


def test_missing_room_type_is_infeasible_with_hint(seed):
    rooms = [r for r in seed["rooms"] if r["type"] != "firing_range"]
    result = solve(dict(seed, rooms=rooms))
    assert result.status == "INFEASIBLE"
    assert any("No firing_range room exists" in h.title for h in result.hints), result.hints


def test_dangling_teacher_reference_is_reported_not_crashed(seed):
    subjects = [dict(s) for s in seed["subjects"]]
    subjects[0]["teacherIds"] = ["nobody"]
    result = solve(dict(seed, subjects=subjects))
    assert result.status == "MODEL_INVALID"
    assert result.hints


# --------------------------------------------------------------------------- #
# 3. A subject may accept several room types and several candidate teachers.
# --------------------------------------------------------------------------- #


def test_assigned_teacher_and_room_come_from_the_subjects_own_options(seed):
    """The solver picks one teacher out of the pool and one room out of the
    accepted types -- never something the subject did not offer."""
    result = solve(seed)
    subjects = {s["id"]: s for s in seed["subjects"]}
    rooms = {r["id"]: r for r in seed["rooms"]}

    for a in result.assignments:
        subject = subjects[a.subjectId]
        assert a.teacherId in subject["teacherIds"], f"{a.subjectName}: {a.teacherName}"
        assert rooms[a.roomId]["type"] in subject["allowedRoomTypes"], a.subjectName


def test_a_teacher_pool_is_actually_used(seed):
    """Not a tautology check: saturate the pool so a single teacher provably
    cannot cover the load, and confirm the sessions land on both candidates."""
    slots = build_slots(["Mon"], 5)  # 5 slots; a pool of 2 offers 10 teaching slots
    groups = [dict(g, size=10) for g in seed["groups"]]
    pair = [t["id"] for t in seed["teachers"][:2]]
    subjects = [
        {
            "id": f"x{i}",
            "name": f"Патрулна дейност {i}",
            "allowedRoomTypes": ["lecture"],
            "semesters": [dict(SEED_SEMESTER, totalSessions=5, spread="whole",
                              groupIds=[g["id"]])],
            "teacherIds": pair,
        }
        for i, g in enumerate(groups[:2], start=1)
    ]
    # 10 sessions, 5 slots: every slot runs both subjects at once, so each slot
    # needs two distinct teachers. Neither candidate can be idle.
    result = solve(dict(seed, slots=slots, subjects=subjects, groups=groups))

    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.validation.ok, result.validation.errors
    used = {a.teacherId for a in result.assignments}
    assert used == set(pair), f"pool not shared, only {used} used"
    per_teacher = Counter(a.teacherId for a in result.assignments)
    assert per_teacher[pair[0]] == per_teacher[pair[1]] == 5


def test_pool_relieves_an_over_commitment_that_one_teacher_cannot_carry(seed):
    """The point of the feature, as a test: the same load is INFEASIBLE for one
    teacher and solvable once a second candidate is added."""
    slots = build_slots(["Mon", "Tue"], 5)  # 10 slots
    groups = [dict(g, size=10) for g in seed["groups"]]
    pair = [t["id"] for t in seed["teachers"][:2]]
    subjects = [
        {
            "id": "x1",
            "name": "Патрулна дейност",
            "allowedRoomTypes": ["lecture"],
            # > 10 slots, so one teacher cannot do it
            "semesters": [dict(SEED_SEMESTER, totalSessions=12, spread="whole",
                              groupIds=[groups[0]["id"]])],
            "teacherIds": [pair[0]],
        }
    ]

    alone = solve(dict(seed, slots=slots, subjects=subjects, groups=groups))
    assert alone.status == "INFEASIBLE"
    assert any("over-committed" in h.title for h in alone.hints), alone.hints

    # Same problem, two candidate teachers -- but one group still cannot attend
    # 12 sessions in 10 slots, so split the load across two groups as well.
    shared_subjects = [
        dict(subjects[0], id=f"x{i}",
             semesters=[dict(SEED_SEMESTER, totalSessions=6, spread="whole",
                             groupIds=[g["id"]])],
             teacherIds=pair)
        for i, g in enumerate(groups[:2], start=1)
    ]
    shared = solve(dict(seed, slots=slots, subjects=shared_subjects, groups=groups))
    assert shared.status in ("OPTIMAL", "FEASIBLE"), shared.message
    assert shared.validation.ok, shared.validation.errors


def test_second_room_type_saves_a_subject_when_its_first_choice_is_gone(seed):
    """Digital Evidence Handling accepts a lab or a lecture hall. Delete every
    lab and it should still be scheduled -- in a lecture hall."""
    subjects = [
        dict(s, allowedRoomTypes=["lab", "lecture"])
        for s in seed["subjects"]
        if "lab" in s["allowedRoomTypes"]
    ][:1]
    rooms = [r for r in seed["rooms"] if r["type"] != "lab"]
    result = solve(dict(seed, subjects=subjects, rooms=rooms))

    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.validation.ok, result.validation.errors
    room_types = {
        next(r["type"] for r in rooms if r["id"] == a.roomId) for a in result.assignments
    }
    assert room_types == {"lecture"}

    # With the second type removed as well, the same problem is impossible.
    single = [dict(subjects[0], allowedRoomTypes=["lab"])]
    assert solve(dict(seed, subjects=single, rooms=rooms)).status == "INFEASIBLE"


def test_pooled_teachers_are_blamed_collectively_not_individually(seed):
    """Two teachers sharing an impossible load should be named together, rather
    than one of them being blamed for work the other could take."""
    slots = build_slots(["Mon"], 5)  # 5 slots, pool of 2 -> 10 teaching slots
    subjects = [
        {
            "id": "x1",
            "name": "Овладяване на масови безредици",
            "allowedRoomTypes": ["lecture"],
            "semesters": [dict(SEED_SEMESTER, totalSessions=11, spread="whole",
                              groupIds=[seed["groups"][0]["id"]])],
            "teacherIds": [t["id"] for t in seed["teachers"][:2]],
        }
    ]
    result = solve(dict(seed, slots=slots, subjects=subjects))

    assert result.status == "INFEASIBLE"
    assert any("collectively over-committed" in h.title for h in result.hints), result.hints


# --------------------------------------------------------------------------- #
# 4. Soft constraints behave like soft constraints.
# --------------------------------------------------------------------------- #


def test_soft_preferences_are_optimised_not_enforced(seed):
    result = solve(seed)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    # Every violation is flagged and explained, and the objective accounts for it.
    for a in result.assignments:
        if a.softViolated:
            assert a.softReason
    assert result.stats.preferenceViolations == sum(
        1 for a in result.assignments if a.softViolated
    )


def test_impossible_preferences_cost_penalty_but_stay_solvable(seed):
    """Give every teacher the same single preferred slot: they cannot all have it,
    but a timetable must still come back."""
    teachers = [dict(t, preferredSlots=["mon-1"]) for t in seed["teachers"]]
    result = solve(dict(seed, teachers=teachers))

    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.validation.ok, result.validation.errors
    assert result.stats.preferenceViolations > 0
    assert result.stats.objectiveValue > 0


def test_time_limit_defaults_to_a_demo_sized_budget(seed):
    """A solve carries a default budget that keeps the demo responsive. There is
    no ceiling: proving a faculty-sized timetable optimal takes longer than any
    cap worth setting, so a caller may ask for as long as it wants -- or for no
    limit at all."""
    request = SolveRequest(**{k: v for k, v in seed.items() if k != "maxTimeInSeconds"})
    assert request.maxTimeInSeconds == DEFAULT_SOLVE_SECONDS == 30

    assert SolveRequest(**dict(seed, maxTimeInSeconds=10 * 60 * 60)).maxTimeInSeconds == 36000
    with pytest.raises(ValidationError):
        SolveRequest(**dict(seed, maxTimeInSeconds=0))


def test_no_time_limit_runs_to_completion():
    """maxTimeInSeconds=None means CP-SAT is given no deadline at all. Checked on
    a problem small enough to finish instantly -- pointing an unlimited run at a
    real instance is exactly what this suite must not do."""
    payload = _dated("2025-09-15", "2025-09-19", total=2)
    payload["maxTimeInSeconds"] = None
    result = solve(payload)

    assert result.status == "OPTIMAL", result.message
    assert result.validation.ok, result.validation.errors
    assert len(result.assignments) == 2
    # The echo has to carry it, or the UI would show a budget the run never had.
    assert result.settingsUsed.maxTimeInSeconds is None


# --------------------------------------------------------------------------- #
# 5. Solver settings are wired through and actually take effect.
# --------------------------------------------------------------------------- #


def test_stop_after_first_solution_returns_the_first_timetable_not_the_best(seed):
    """The whole value of optimising, as a test: the first legal timetable is far
    worse than the optimum, and this setting stops there."""
    best = solve(seed)
    first = solve(dict(seed, stopAfterFirstSolution=True))

    assert best.status == "OPTIMAL"
    assert first.status == "FEASIBLE"
    # The point of the setting: what you get without optimising is worse than the
    # optimum, whatever the optimum happens to be for this dataset.
    assert first.stats.objectiveValue > best.stats.objectiveValue
    # Still a legal timetable -- just an unpolished one.
    assert first.validation.ok, first.validation.errors


def test_disabling_our_symmetry_breaking_still_reaches_the_same_optimum(seed):
    """If CP-SAT's own symmetry handling covers ours, switching ours off must not
    change the answer -- only the work needed to reach it."""
    with_ours = solve(seed)
    without = solve(dict(seed, useSymmetryBreaking=False))

    assert without.status == "OPTIMAL"
    assert without.stats.objectiveValue == with_ours.stats.objectiveValue
    assert without.validation.ok, without.validation.errors


def test_search_parameters_do_not_change_the_answer(seed):
    """Tier B settings change how hard the solver works, never what is legal."""
    baseline = solve(seed)
    assert baseline.status == "OPTIMAL"

    for search in (
        {"numWorkers": 1},
        {"presolve": False},
        {"symmetryLevel": 0},
        {"linearizationLevel": 0},
    ):
        result = solve(dict(seed, search=search))
        # A slower configuration may run out of budget before *proving* the
        # optimum -- that is the setting doing exactly what it says. What it must
        # never do is change which timetables are legal, or find one better than
        # the proven optimum.
        assert result.status in ("OPTIMAL", "FEASIBLE"), (search, result.message)
        assert result.stats.numPlaced == result.stats.numSessions, search
        assert result.validation.ok, (search, result.validation.errors)
        assert result.stats.objectiveValue >= baseline.stats.objectiveValue, search
        if result.status == "OPTIMAL":
            assert result.stats.objectiveValue == baseline.stats.objectiveValue, search


def test_single_worker_with_a_fixed_seed_is_reproducible(seed):
    payload = dict(seed, search={"numWorkers": 1, "randomSeed": 12345})
    first, second = solve(payload), solve(payload)
    assert first.stats.objectiveValue == second.stats.objectiveValue
    assert [(a.subjectId, a.slot, a.roomId, a.teacherId) for a in first.assignments] == [
        (a.subjectId, a.slot, a.roomId, a.teacherId) for a in second.assignments
    ]


def test_search_parameters_are_bounded_by_the_schema(seed):
    """The typed model is the whitelist: out-of-range values never reach CP-SAT."""
    for bad in ({"numWorkers": 0}, {"numWorkers": 17}, {"symmetryLevel": 9},
                {"linearizationLevel": 3}, {"randomSeed": -1}):
        with pytest.raises(ValidationError):
            SearchParams(**bad)


def test_settings_used_is_echoed_back(seed):
    result = solve(dict(seed, preferenceWeight=3, gapWeight=7, useSymmetryBreaking=False,
                        search={"numWorkers": 2, "presolve": False}))
    used = result.settingsUsed
    assert used is not None
    assert (used.preferenceWeight, used.gapWeight) == (3, 7)
    assert used.useSymmetryBreaking is False
    assert (used.search.numWorkers, used.search.presolve) == (2, False)


def test_small_example_is_fast_and_leaves_visible_gaps_by_default(seed):
    """The small example exists to be the good first click: quick, provably
    optimal, and -- crucially -- *not* free of soft cost. At the default weights
    it should come back with holes in the middle of group days, because honouring
    a teacher preference is cheaper than closing one. A dataset that scores zero
    penalty renders the soft-constraint half of the UI blank, so a future edit
    that flattens it should fail here.

    The time bound is 20s, not the 8s it was before sessions were dated. That is
    a real cost, not a slipped standard: the fixture's two compressed weeks are
    60 dated slots and 43 sessions against the single week's 30 and 23, and the
    ladder re-solves for every rank. Measured at ~14s; the bound leaves headroom
    without letting a genuine regression through.
    """
    result = solve(seed)

    assert result.status == "OPTIMAL", result.message
    assert result.stats.solveTimeSeconds < 20.0
    assert result.validation.ok, result.validation.errors
    assert result.stats.gapPenalty > 0, "no gaps -- turning up gap weight would demonstrate nothing"
    assert result.stats.objectiveValue > 0


def test_gap_weight_can_no_longer_buy_gaps_with_teacher_preferences(seed):
    """The trade this used to assert is gone, on purpose, and that is worth pinning.

    Before the priority ladder, gaps and preferences shared one weighted objective,
    so raising gapWeight to 10 compacted the days and paid for it with three
    teacher preferences. Now group gaps are the last rung: every teacher tier is
    already frozen at its best by the time gaps are considered, so no gap can ever
    be closed at a teacher's expense. gapWeight still orders solutions *within*
    the gap phase -- it just cannot outbid a rank any more.

    This is the visible cost of hard lexicographic priority, so it gets a test
    rather than a footnote."""
    lax = solve(seed)
    strict = solve(dict(seed, gapWeight=10))

    assert strict.status == "OPTIMAL", strict.message
    assert strict.validation.ok, strict.validation.errors
    # The teacher half is untouchable whatever the gap weight says.
    assert strict.stats.preferenceViolations == lax.stats.preferenceViolations
    assert strict.stats.roomPreferencePenalty == lax.stats.roomPreferencePenalty
    # And gaps are already minimal at the default, because nothing competes with
    # them once the tiers are frozen -- so raising the weight changes nothing.
    assert strict.stats.gapPenalty == lax.stats.gapPenalty


def test_full_seed_produces_a_valid_timetable_within_the_demo_budget(full_seed):
    """The whole four-year faculty -- what "Load example" actually loads.

    It is a genuinely hard instance: CP-SAT returns a good schedule but does not
    prove optimality in this budget, which is the honest behaviour of real
    timetabling and exactly the OPTIMAL/FEASIBLE distinction the app surfaces.
    What must hold is that every session is placed and the result is valid."""
    result = solve(full_seed)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.stats.numPlaced == result.stats.numSessions
    assert result.validation.ok, result.validation.errors
    assert result.stats.solveTimeSeconds <= SEED_DEMO_BUDGET_SECONDS + 3


def test_zero_weights_still_produce_a_valid_timetable(seed):
    result = solve(dict(seed, preferenceWeight=0, gapWeight=0))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.validation.ok, result.validation.errors


# --------------------------------------------------------------------------- #
# 6. Teacher rank, ranked room preferences, and the priority ladder.
# --------------------------------------------------------------------------- #


def test_effective_weight_prefers_override_then_role_then_unranked():
    """The four ways a teacher's tier can be decided, in precedence order."""
    by_id = DEFAULT_ROLES_BY_ID
    plain = Teacher(id="t", name="x")
    ranked = Teacher(id="t", name="x", role="professor")
    overridden = Teacher(id="t", name="x", role="assistant", priorityWeight=6)
    dangling = Teacher(id="t", name="x", role="no-such-role")

    assert effective_weight(plain, by_id) == UNRANKED_WEIGHT
    assert effective_weight(ranked, by_id) == PROFESSOR_WEIGHT
    # The override is the only way to lift one person out of their rank's tier.
    assert effective_weight(overridden, by_id) == 6
    assert effective_weight(overridden, by_id) > effective_weight(
        Teacher(id="t", name="x", role="assistant"), by_id
    )
    # A role that is not in the table demotes rather than raising: the UI cascades
    # on delete, but the solver must survive one slipping through.
    assert effective_weight(dangling, by_id) == UNRANKED_WEIGHT


def test_weights_come_from_the_request_not_from_the_code():
    """The point of making roles data: a caller can reorder the hierarchy.

    Same two teachers, same ranks by name -- but a role table that says an
    assistant outranks a professor. The ladder must follow the request.
    """
    payload = _duel(
        teachers=[
            {"id": "prof", "name": "Professor", "role": "professor",
             "preferredSlots": ["mon-1"]},
            {"id": "asst", "name": "Assistant", "role": "assistant",
             "preferredSlots": ["mon-1"]},
        ],
        subjects=[
            {"id": "s1", "name": "S1", "allowedRoomTypes": ["lecture"],
             "semesters": [dict(SEED_SEMESTER, totalSessions=1, spread="whole",
                                groupIds=["g1"])], "teacherIds": ["prof"]},
            {"id": "s2", "name": "S2", "allowedRoomTypes": ["lecture"],
             "semesters": [dict(SEED_SEMESTER, totalSessions=1, spread="whole",
                                groupIds=["g2"])], "teacherIds": ["asst"]},
        ],
    )
    # Default table: the professor wins.
    assert _slot_of(solve(payload), "prof") == "1"

    inverted = dict(payload, roles=[
        {"id": "professor", "name": "Professor", "short": "prof", "weight": 1},
        {"id": "assistant", "name": "Assistant", "short": "asst", "weight": 9},
    ])
    result = solve(inverted)

    assert result.validation.ok, result.validation.errors
    assert _slot_of(result, "asst") == "1"
    assert _slot_of(result, "prof") == "2"
    # And the ladder reports the ranks by the short labels the request supplied.
    assert [t.roles for t in result.stats.tiers] == [["asst"], ["prof"]]


def test_a_request_naming_no_roles_falls_back_to_the_built_in_ranks(seed):
    """Every seed file and every pre-existing caller omits `roles` entirely.

    The default ids are the values the old enum used, so those requests must keep
    ranking exactly as they did -- this is the whole backwards-compatibility
    guarantee that let roles become data without a migration.
    """
    assert "roles" not in seed
    result = solve(seed)

    assert result.validation.ok, result.validation.errors
    weights = [t.weight for t in result.stats.tiers]
    assert weights == [
        DEFAULT_ROLES_BY_ID[r].weight
        for r in ("professor", "associate_professor", "chief_assistant", "senior_lecturer")
    ]


def test_the_seed_ships_roles_that_match_the_built_in_ranks(seed):
    """The seed files now carry a `roles` array, and the UI sends it.

    Sending it must produce exactly what omitting it does, or the seed and the
    solver's own defaults have drifted apart -- which would be invisible until a
    timetable came back ranked differently in the app than in the tests.
    """
    shipped = json.loads(SMALL_SEED_PATH.read_text())["roles"]
    assert "roles" not in seed  # the fixture omits it, exercising the fallback

    fallback = solve(seed)
    explicit = solve(dict(seed, roles=shipped))

    assert [(t.weight, t.roles) for t in explicit.stats.tiers] == [
        (t.weight, t.roles) for t in fallback.stats.tiers
    ]


def test_duplicate_role_ids_are_reported(seed):
    duped = dict(seed, roles=[
        {"id": "professor", "name": "A", "short": "a", "weight": 5},
        {"id": "professor", "name": "B", "short": "b", "weight": 4},
    ])
    result = solve(duped)

    assert result.status == "MODEL_INVALID"
    assert any("Duplicate role id" in h.detail for h in result.hints), result.hints


def test_a_problem_with_no_roles_has_exactly_one_tier(seed):
    """Backwards compatibility: roles are optional, and a problem without any must
    behave as it did before the ladder existed -- one tier, everybody equal."""
    unranked = dict(
        seed,
        teachers=[
            {k: v for k, v in t.items() if k not in ("role", "priorityWeight")}
            for t in seed["teachers"]
        ],
    )
    result = solve(unranked)

    assert result.validation.ok, result.validation.errors
    assert len(result.stats.tiers) == 1
    assert result.stats.tiers[0].weight == UNRANKED_WEIGHT
    assert result.stats.tiers[0].teacherCount == len(seed["teachers"])


def test_tiers_are_reported_top_down_and_cover_every_teacher(seed):
    result = solve(seed)

    weights = [t.weight for t in result.stats.tiers]
    assert weights == sorted(weights, reverse=True), "ladder must read top rank first"
    assert sum(t.teacherCount for t in result.stats.tiers) == len(seed["teachers"])


def test_a_teacher_ranking_no_rooms_is_never_charged_for_one(seed):
    """An empty preferredRooms means "no opinion", which cannot be violated."""
    indifferent = dict(
        seed,
        teachers=[dict(t, preferredRooms=[]) for t in seed["teachers"]],
    )
    result = solve(indifferent)

    assert result.validation.ok, result.validation.errors
    assert result.stats.roomPreferencePenalty == 0
    assert all(a.roomPreferenceRank is None for a in result.assignments)


def test_room_rank_is_scoped_to_the_rooms_type(seed):
    """Ranking two labs says nothing about which sports hall you get.

    Which room types a session may use is a hard constraint, so charging a teacher
    the unlisted price for a type they never ranked would bill them for a choice
    they were never offered."""
    lab_ids = [r["id"] for r in seed["rooms"] if r["type"] == "lab"]
    # Every teacher ranks only labs, and nothing else.
    lab_only = dict(
        seed,
        teachers=[dict(t, preferredRooms=lab_ids[:1]) for t in seed["teachers"]],
    )
    result = solve(lab_only)

    assert result.validation.ok, result.validation.errors
    non_lab = {r["id"] for r in seed["rooms"] if r["type"] != "lab"}
    for a in result.assignments:
        if a.roomId in non_lab:
            assert a.roomPreferenceRank is None, (
                f"{a.teacherName} was charged for {a.roomName}, a type they never ranked"
            )


def test_a_dangling_or_duplicated_ranked_room_is_tolerated(seed):
    """Deleting a room must not invalidate the problem.

    preferredRooms is positional, so dropping a dangling id genuinely does shift
    the rooms below it up a place. Rejecting the problem instead would mean that
    deleting a single room breaks every teacher who ranked it until each one is
    hand-edited -- and deleting a room is an ordinary edit. So: unknown ids are
    dropped, repeats keep only their first position, and the solve goes ahead.
    """
    dangling = dict(
        seed,
        teachers=[dict(t, preferredRooms=["nope"]) for t in seed["teachers"][:1]]
        + [dict(t) for t in seed["teachers"][1:]],
    )
    result = solve(dangling)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.validation.ok, result.validation.errors
    # The teacher whose only ranked room does not exist has no opinion left.
    first_id = seed["teachers"][0]["id"]
    assert all(
        a.roomPreferenceRank is None for a in result.assignments if a.teacherId == first_id
    )

    room_id = seed["rooms"][0]["id"]
    duplicated = dict(
        seed,
        teachers=[dict(t, preferredRooms=[room_id, room_id]) for t in seed["teachers"][:1]]
        + [dict(t) for t in seed["teachers"][1:]],
    )
    result = solve(duplicated)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.validation.ok, result.validation.errors


def _duel(slot_count=2, teachers=None, subjects=None):
    """A minimal head-to-head: one room, N slots, one session per teacher.

    One room means every session serialises, so the teachers are forced to compete
    for the same slots and somebody must lose. Groups are distinct so the only
    contention is the room.
    """
    # A single Monday, so "which slot did they get" stays a one-dimensional
    # question and the rank duel is not confounded by a choice of week.
    day = "2025-09-15"
    return {
        "semester": SEED_SEMESTER,
        "slots": [
            {"id": f"{day}-{i}", "date": day, "day": "Mon", "period": i}
            for i in range(1, slot_count + 1)
        ],
        "rooms": [{"id": "r1", "name": "Room", "capacity": 30, "type": "lecture"}],
        "groups": [
            {
                "id": f"g{i}", "name": f"G{i}", "size": 10,
                "semesters": [dict(SEED_SEMESTER, start=day, end=day, breaks=[])],
            }
            for i in range(1, len(subjects) + 1)
        ],
        "teachers": teachers,
        "subjects": subjects,
        "maxTimeInSeconds": 10.0,
    }


def _period_of(result, teacher_id) -> int:
    """Which period this teacher's session landed in. Slot ids are dated now, so
    the duel tests ask about the period rather than a weekday-keyed id."""
    return next(a.slot for a in result.assignments if a.teacherId == teacher_id).split("-")[-1]


def _slot_of(result, teacher_id):
    return _period_of(result, teacher_id)


def test_the_higher_rank_wins_a_contested_slot():
    """The requirement, as a test: two teachers want the same slot, one room, and
    rank decides -- not luck, and not whichever the search happened to reach."""
    payload = _duel(
        teachers=[
            {"id": "prof", "name": "Professor", "role": "professor",
             "preferredSlots": ["mon-1"], "preferredRooms": ["r1"]},
            {"id": "asst", "name": "Assistant", "role": "assistant",
             "preferredSlots": ["mon-1"], "preferredRooms": ["r1"]},
        ],
        subjects=[
            {"id": "s1", "name": "S1", "allowedRoomTypes": ["lecture"],
             "semesters": [dict(SEED_SEMESTER, totalSessions=1, spread="whole",
                                groupIds=["g1"])], "teacherIds": ["prof"]},
            {"id": "s2", "name": "S2", "allowedRoomTypes": ["lecture"],
             "semesters": [dict(SEED_SEMESTER, totalSessions=1, spread="whole",
                                groupIds=["g2"])], "teacherIds": ["asst"]},
        ],
    )
    result = solve(payload)

    assert result.validation.ok, result.validation.errors
    assert _slot_of(result, "prof") == "1"
    assert _slot_of(result, "asst") == "2"

    # And the override is what makes priorityWeight more than decoration: lift the
    # assistant above the professor and the outcome must flip.
    flipped = dict(payload, teachers=[
        dict(payload["teachers"][0]),
        dict(payload["teachers"][1], priorityWeight=PROFESSOR_WEIGHT + 1),
    ])
    result = solve(flipped)

    assert result.validation.ok, result.validation.errors
    assert _slot_of(result, "asst") == "1"
    assert _slot_of(result, "prof") == "2"


def test_one_professor_outranks_any_number_of_assistants():
    """The property a weighted objective cannot express.

    Three sessions, three slots, one room, and everybody wants mon-1. Exactly one
    of them can have it, so the total number of disappointed teachers is 2 either
    way -- the two outcomes are *tied* on any weighted sum, and only a strict
    ranking picks between them. The professor must win every time.
    """
    payload = _duel(
        slot_count=3,
        teachers=[
            {"id": "prof", "name": "Professor", "role": "professor",
             "preferredSlots": ["mon-1"]},
            {"id": "a1", "name": "Assistant One", "role": "assistant",
             "preferredSlots": ["mon-1"]},
            {"id": "a2", "name": "Assistant Two", "role": "assistant",
             "preferredSlots": ["mon-1"]},
        ],
        subjects=[
            {"id": f"s{i}", "name": f"S{i}", "allowedRoomTypes": ["lecture"],
             "semesters": [dict(SEED_SEMESTER, totalSessions=1, spread="whole",
                                groupIds=[f"g{i}"])], "teacherIds": [tid]}
            for i, tid in enumerate(["prof", "a1", "a2"], start=1)
        ],
    )
    result = solve(payload)

    assert result.validation.ok, result.validation.errors
    assert _slot_of(result, "prof") == "1"
    # The professor's tier is satisfied; the assistants' tier pays the whole bill.
    by_weight = {t.weight: t for t in result.stats.tiers}
    assert by_weight[PROFESSOR_WEIGHT].penalty == 0
    assert by_weight[ASSISTANT_WEIGHT].penalty > 0


def test_a_lower_tier_can_never_improve_at_a_higher_tiers_expense():
    """Adding work for a junior rank must not cost a senior one anything."""
    base = _duel(
        slot_count=3,
        teachers=[
            {"id": "prof", "name": "Professor", "role": "professor",
             "preferredSlots": ["mon-1"]},
            {"id": "a1", "name": "Assistant One", "role": "assistant",
             "preferredSlots": ["mon-1"]},
        ],
        subjects=[
            {"id": "s1", "name": "S1", "allowedRoomTypes": ["lecture"],
             "semesters": [dict(SEED_SEMESTER, totalSessions=1, spread="whole",
                                groupIds=["g1"])], "teacherIds": ["prof"]},
            {"id": "s2", "name": "S2", "allowedRoomTypes": ["lecture"],
             "semesters": [dict(SEED_SEMESTER, totalSessions=1, spread="whole",
                                groupIds=["g2"])], "teacherIds": ["a1"]},
        ],
    )
    alone = solve(base)
    prof_weight = PROFESSOR_WEIGHT
    assert {t.weight: t for t in alone.stats.tiers}[prof_weight].penalty == 0

    # Same problem, but the assistant now has two sessions competing for mon-1.
    busier = dict(base)
    busier["subjects"] = [
        base["subjects"][0],
        dict(base["subjects"][1],
             semesters=[dict(SEED_SEMESTER, totalSessions=2, spread="whole",
                             groupIds=["g2"])]),
    ]
    crowded = solve(busier)

    assert crowded.validation.ok, crowded.validation.errors
    assert _slot_of(crowded, "prof") == "1"
    assert {t.weight: t for t in crowded.stats.tiers}[prof_weight].penalty == 0


# --------------------------------------------------------------------------- #
# 7. Dated semesters: windows, breaks, even spread, and semester scoping.
# --------------------------------------------------------------------------- #


def _dated(start, end, periods=3, breaks=(), total=6, spread="whole", window=None,
           semester=None, days=("Mon", "Tue", "Wed", "Thu", "Fri")):
    """One group, one teacher, one room, over a real date span."""
    semester = semester or SEED_SEMESTER
    spec = dict(semester, totalSessions=total, spread=spread)
    if window:
        spec["window"] = {"start": window[0], "end": window[1]}
    return {
        "semester": semester,
        "slots": build_slots(list(days), periods, set(), start, end),
        "teachers": [{"id": "t1", "name": "T"}],
        "rooms": [{"id": "r1", "name": "Room", "capacity": 30, "type": "lecture"}],
        "groups": [
            {
                "id": "g1", "name": "G1", "size": 10,
                "semesters": [
                    dict(semester, start=start, end=end,
                         breaks=[{"start": a, "end": b} for a, b in breaks])
                ],
            }
        ],
        "subjects": [
            {"id": "s1", "name": "Subj", "allowedRoomTypes": ["lecture"],
             "teacherIds": ["t1"], "semesters": [dict(spec, groupIds=["g1"])]}
        ],
        "maxTimeInSeconds": 20.0,
    }


def _weeks_of(result):
    return Counter(a.date.isocalendar()[:2] for a in result.assignments)


def test_sessions_land_on_real_dates_inside_the_term():
    result = solve(_dated("2025-09-15", "2025-10-10", total=8))

    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.validation.ok, result.validation.errors
    assert len(result.assignments) == 8
    for a in result.assignments:
        assert "2025-09-15" <= a.date.isoformat() <= "2025-10-10"
        # The slot id carries the date, which is what the multi-week grid keys on.
        assert a.slot.startswith(a.date.isoformat())


def test_nothing_is_ever_scheduled_on_a_break():
    """A break is excluded from teaching entirely, not merely discouraged."""
    result = solve(
        _dated("2025-09-15", "2025-10-10", total=8,
               breaks=[("2025-09-22", "2025-09-26")])
    )

    assert result.validation.ok, result.validation.errors
    dates = {a.date.isoformat() for a in result.assignments}
    assert not any("2025-09-22" <= d <= "2025-09-26" for d in dates), sorted(dates)


def test_sessions_are_spread_evenly_across_the_teaching_weeks():
    """Four weeks, eight sessions: two a week, not eight in one week."""
    result = solve(_dated("2025-09-15", "2025-10-10", total=8))

    per_week = _weeks_of(result)
    assert len(per_week) == 4, dict(per_week)
    assert set(per_week.values()) == {2}, dict(per_week)


def test_an_uneven_total_still_spreads_as_evenly_as_it_can():
    """Nine sessions over four weeks cannot be equal; it must still not bunch."""
    result = solve(_dated("2025-09-15", "2025-10-10", total=9))

    per_week = _weeks_of(result)
    assert min(per_week.values()) >= 2 and max(per_week.values()) <= 3, dict(per_week)


def test_a_spread_window_confines_sessions_to_the_period_chosen():
    """The other half of 'spread evenly': across a period picked in the semester."""
    result = solve(
        _dated("2025-09-15", "2025-10-10", total=4,
               spread="range", window=("2025-09-29", "2025-10-10"))
    )

    assert result.validation.ok, result.validation.errors
    for a in result.assignments:
        assert "2025-09-29" <= a.date.isoformat() <= "2025-10-10", a.date


def test_a_subject_whose_groups_are_never_both_in_term_is_explained():
    """Intersection, not union: the two groups' terms do not overlap at all."""
    payload = _dated("2025-09-15", "2025-10-10", total=2)
    payload["groups"].append(
        {
            "id": "g2", "name": "G2", "size": 10,
            "semesters": [dict(SEED_SEMESTER, start="2025-11-03", end="2025-11-28", breaks=[])],
        }
    )
    payload["subjects"][0]["semesters"][0]["groupIds"] = ["g1", "g2"]
    payload["slots"] = build_slots(
        ["Mon", "Tue", "Wed", "Thu", "Fri"], 3, set(), "2025-09-15", "2025-11-28"
    )
    result = solve(payload)

    assert result.status in ("INFEASIBLE", "UNKNOWN"), result.status
    assert any("no usable dates" in h.title for h in result.hints), result.hints


def test_only_the_requested_semesters_subjects_are_scheduled():
    """A solve is scoped to one semester: everything else sits it out."""
    other = {"academicYear": "2025/2026", "index": 2}
    payload = _dated("2025-09-15", "2025-10-10", total=4)
    # A second subject that runs in semester 2 only.
    payload["subjects"].append(
        {"id": "s2", "name": "Next term", "allowedRoomTypes": ["lecture"],
         "teacherIds": ["t1"],
         "semesters": [dict(other, totalSessions=4, spread="whole", groupIds=["g1"])]}
    )
    result = solve(payload)

    assert result.validation.ok, result.validation.errors
    assert {a.subjectId for a in result.assignments} == {"s1"}
    assert len(result.assignments) == 4


def test_a_group_with_no_dates_for_the_semester_takes_no_part():
    payload = _dated("2025-09-15", "2025-10-10", total=4)
    payload["groups"][0]["semesters"] = [
        dict({"academicYear": "2026/2027", "index": 1},
             start="2026-09-14", end="2026-10-09", breaks=[])
    ]
    result = solve(payload)

    # Its only subject cannot run, so there is nothing to place.
    assert result.status in ("INFEASIBLE", "UNKNOWN"), result.status


def test_teacher_slot_preferences_recur_every_week():
    """preferredSlots is weekday-keyed, not dated: 'mon-1' means that period every
    week of the term, the same way a blocked slot does."""
    payload = _dated("2025-09-15", "2025-10-10", total=4)
    payload["teachers"] = [dict(payload["teachers"][0], preferredSlots=["mon-1"])]
    result = solve(payload)

    assert result.validation.ok, result.validation.errors
    # Four weeks, four sessions, one Monday-period-1 each: every one satisfiable.
    assert result.stats.preferenceViolations == 0, [a.softReason for a in result.assignments]
    for a in result.assignments:
        assert a.day == "Mon" if hasattr(a, "day") else True
        assert a.slot.endswith("-1")


def test_a_subject_can_be_taught_to_a_different_cohort_each_semester():
    """Groups belong to the semester entry, not to the subject.

    The same subject runs for G1 in semester 1 and for G2 in semester 2. Solving
    one term must schedule that term's cohort and no other -- the case the old
    flat `Subject.groupIds` could not express at all.
    """
    first = SEED_SEMESTER
    second = {"academicYear": SEED_SEMESTER["academicYear"], "index": 2}
    payload = _dated("2025-09-15", "2025-10-10", total=4)
    payload["groups"].append(
        {
            "id": "g2", "name": "G2", "size": 10,
            "semesters": [
                dict(second, start="2026-02-09", end="2026-03-06", breaks=[]),
            ],
        }
    )
    payload["groups"][0]["semesters"].append(
        dict(second, start="2026-02-09", end="2026-03-06", breaks=[])
    )
    payload["subjects"][0]["semesters"].append(
        dict(second, totalSessions=4, spread="whole", groupIds=["g2"])
    )

    autumn = solve(payload)
    assert autumn.validation.ok, autumn.validation.errors
    assert len(autumn.assignments) == 4
    assert {gid for a in autumn.assignments for gid in a.groupIds} == {"g1"}

    spring = solve(
        dict(
            payload,
            semester=second,
            slots=build_slots(
                ["Mon", "Tue", "Wed", "Thu", "Fri"], 3, set(), "2026-02-09", "2026-03-06"
            ),
        )
    )
    assert spring.validation.ok, spring.validation.errors
    assert len(spring.assignments) == 4
    # G1 is in term this semester too, and is deliberately *not* scheduled: the
    # cohort comes from the semester entry, not from the subject.
    assert {gid for a in spring.assignments for gid in a.groupIds} == {"g2"}


def test_progress_events_report_the_ladder_without_changing_the_answer():
    """The streaming endpoint's hook is instrumentation, not a second code path.

    It reports the milestones the run already passes -- the model being built,
    then each rung starting and settling -- and the answer must be identical to
    the same request solved with no hook at all.
    """
    payload = _dated("2025-09-15", "2025-10-10", total=4)
    events = []
    plain = solve_timetable(SolveRequest(**dict(payload, maxTimeInSeconds=20.0)))
    watched = solve_timetable(
        SolveRequest(**dict(payload, maxTimeInSeconds=20.0)), events.append
    )

    assert watched.status == plain.status
    assert watched.stats.objectiveValue == plain.stats.objectiveValue
    assert len(watched.assignments) == len(plain.assignments)

    kinds = [e["type"] for e in events]
    assert kinds[0] == "building"
    assert kinds[1] == "built"
    assert "phase" in kinds and "phase_done" in kinds

    built = events[1]
    # Warm-up plus every rung, fixed before the first second of search -- this is
    # what lets the UI draw a bar that only moves forwards.
    assert built["total"] == 1 + len(built["phases"])

    starts = [e for e in events if e["type"] == "phase"]
    assert [e["index"] for e in starts] == list(range(1, len(starts) + 1))
    assert starts[0]["label"] == "warmup"
    for event in starts:
        assert event["total"] == built["total"]
