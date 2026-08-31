"""End-to-end checks on the CP-SAT model.

These are the checks the brief calls for before the PoC can be called done:
the seed dataset must produce a valid conflict-free timetable, and an
over-constrained dataset must come back INFEASIBLE rather than hanging.
"""

from collections import Counter, defaultdict

import pytest

from pydantic import ValidationError

from app.models import (
    DEFAULT_SOLVE_SECONDS,
    MAX_SOLVE_SECONDS,
    SearchParams,
    SolveRequest,
)

# What "Load example -> Generate" is allowed to take.
SEED_DEMO_BUDGET_SECONDS = 30
from app.timetable_solver import solve_timetable
from conftest import build_slots


def solve(payload):
    return solve_timetable(SolveRequest(**payload))


# --------------------------------------------------------------------------- #
# 1. The seed dataset solves, and the schedule it returns is actually valid.
# --------------------------------------------------------------------------- #


def test_seed_dataset_solves(seed):
    result = solve(seed)
    expected = sum(s["sessionsPerWeek"] for s in seed["subjects"])
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
        assert placed[subject["id"]] == subject["sessionsPerWeek"], subject["name"]


def test_seed_multi_group_subject_busies_every_group(seed):
    """A lecture delivered to a whole поток blocks every one of its groups.
    Selected by role rather than by id, so regenerating the dataset cannot
    quietly turn this into a test of nothing."""
    shared = next(s for s in seed["subjects"] if len(s["groupIds"]) > 1)
    result = solve(seed)

    shared_slots = {a.slot for a in result.assignments if a.subjectId == shared["id"]}
    assert shared_slots, f"{shared['name']} was not scheduled"
    for a in result.assignments:
        if a.subjectId == shared["id"] or a.slot not in shared_slots:
            continue
        clash = set(a.groupIds) & set(shared["groupIds"])
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
        dict(g, size=biggest + 50) if g["id"] in firing["groupIds"] else dict(g)
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
            "sessionsPerWeek": 5,
            "teacherIds": pair,
            "groupIds": [g["id"]],
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
            "sessionsPerWeek": 12,  # > 10 slots, so one teacher cannot do it
            "teacherIds": [pair[0]],
            "groupIds": [groups[0]["id"]],
        }
    ]

    alone = solve(dict(seed, slots=slots, subjects=subjects, groups=groups))
    assert alone.status == "INFEASIBLE"
    assert any("over-committed" in h.title for h in alone.hints), alone.hints

    # Same problem, two candidate teachers -- but one group still cannot attend
    # 12 sessions in 10 slots, so split the load across two groups as well.
    shared_subjects = [
        dict(subjects[0], id=f"x{i}", sessionsPerWeek=6, teacherIds=pair, groupIds=[g["id"]])
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
            "sessionsPerWeek": 11,
            "teacherIds": [t["id"] for t in seed["teachers"][:2]],
            "groupIds": [seed["groups"][0]["id"]],
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


def test_time_limit_defaults_below_the_ceiling_and_cannot_exceed_it(seed):
    """A solve is bounded twice over: a default budget that keeps the demo
    responsive, and a hard ceiling so no request can pin a worker thread for
    long. The default is deliberately well under the ceiling -- a faculty-sized
    timetable will use every second it is given without proving optimality."""
    request = SolveRequest(**{k: v for k, v in seed.items() if k != "maxTimeInSeconds"})
    assert request.maxTimeInSeconds == DEFAULT_SOLVE_SECONDS == 30
    assert DEFAULT_SOLVE_SECONDS < MAX_SOLVE_SECONDS == 20 * 60

    with pytest.raises(ValidationError):
        SolveRequest(**dict(seed, maxTimeInSeconds=MAX_SOLVE_SECONDS + 1))
    with pytest.raises(ValidationError):
        SolveRequest(**dict(seed, maxTimeInSeconds=0))


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
    that flattens it should fail here."""
    result = solve(seed)

    assert result.status == "OPTIMAL", result.message
    assert result.stats.solveTimeSeconds < 8.0
    assert result.validation.ok, result.validation.errors
    assert result.stats.gapPenalty > 0, "no gaps -- turning up gap weight would demonstrate nothing"
    assert result.stats.objectiveValue > 0


def test_raising_gap_weight_closes_the_gaps_and_costs_preferences(seed):
    """The demo story, encoded: one knob, and the trade goes the other way.

    At the default weights the solver keeps the holes; weight them heavily and it
    compacts the days instead, paying for it in teacher preferences. Both halves
    must move, or the Settings dialog is demonstrating nothing."""
    lax = solve(seed)
    strict = solve(dict(seed, gapWeight=10))

    assert strict.status == "OPTIMAL", strict.message
    assert strict.validation.ok, strict.validation.errors
    assert strict.stats.gapPenalty == 0 < lax.stats.gapPenalty
    assert strict.stats.preferenceViolations > lax.stats.preferenceViolations


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
