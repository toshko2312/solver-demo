"""University timetable scheduling as a CP-SAT model.

This is the file worth reading: it is the whole scheduling model, and the rest of
the service is plumbing around it.

THE PROBLEM
-----------
Place every session of every subject into a (time slot, room) pair such that
nobody and nothing is double-booked, every room fits and suits its session, and
-- as far as the hard constraints allow -- teachers get the slots they asked for
and student groups get compact days.

THE ENCODING
------------
Sessions, not subjects, are what we place. A subject with sessionsPerWeek=3
becomes three interchangeable session instances.

One boolean per (session, slot, room, teacher) quadruple:

    x[s, t, r, k] == 1  <=>  session s happens in slot t, in room r, taught by k

A subject names a *set* of acceptable room types and a *pool* of candidate
teachers, so where and who are both decisions, not given constants. The teacher
index is what makes the pool work: the session's "happens exactly once"
constraint already ranges over teacher-tagged variables, so "exactly one teacher
from the pool" needs no constraint of its own -- it falls out of HARD 1.

The alternative -- an IntVar for the slot plus an IntVar for the room per session
-- needs reified channelling constraints to express "no two sessions in the same
room at the same time", which is the bulk of the model. With booleans every
resource conflict is a plain AtMostOne over a slice of the cube, which is both
shorter to write and what CP-SAT propagates best.

The cube is pruned when it is built: a room only gets a variable for a session if
the room's type is one the subject accepts and its capacity fits. Two of the six
hard constraints therefore never appear as constraints at all -- they are
structural. That is the first question a reader has ("where is the capacity
constraint?"), hence this paragraph.
"""

import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from .diagnostics import build_hints, check_references
from .models import (
    Assignment,
    Hint,
    SettingsUsed,
    SolveRequest,
    SolveResponse,
    Stats,
    Validation,
)


def _settings_used(req: SolveRequest) -> SettingsUsed:
    """Echo the knobs this run was solved with, so a result can never be read
    against settings that have since changed."""
    return SettingsUsed(
        maxTimeInSeconds=req.maxTimeInSeconds,
        preferenceWeight=req.preferenceWeight,
        gapWeight=req.gapWeight,
        stopAfterFirstSolution=req.stopAfterFirstSolution,
        useSymmetryBreaking=req.useSymmetryBreaking,
        search=req.search,
    )


# CP-SAT status code -> the strings we put on the wire. FEASIBLE and OPTIMAL are
# deliberately kept distinct: "we found a schedule" and "we proved no better
# schedule exists" are different claims and the UI shows them differently.
_STATUS_NAMES = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


class _Session:
    """One instance of a subject that has to be placed exactly once."""

    def __init__(self, key: int, subject, index: int, size: int):
        self.key = key            # position in the sessions list
        self.subject = subject
        self.index = index        # 0-based occurrence within its subject
        self.size = size          # total head-count of all its groups


def solve_timetable(req: SolveRequest) -> SolveResponse:
    """Build and solve the model. Never raises on an unsatisfiable problem --
    infeasibility is a result, not an error."""

    # ---- 0. Sanity: dangling ids would silently drop constraints ------------
    reference_errors = check_references(req)
    if reference_errors:
        return SolveResponse(
            settingsUsed=_settings_used(req),
            status="MODEL_INVALID",
            message="The problem references entities that do not exist.",
            hints=[Hint(title="Broken reference", detail=e) for e in reference_errors],
        )

    rooms_by_id = {r.id: r for r in req.rooms}
    groups_by_id = {g.id: g for g in req.groups}
    teachers_by_id = {t.id: t for t in req.teachers}
    slot_index = {s.id: i for i, s in enumerate(req.slots)}
    slots = req.slots

    if not slots:
        return SolveResponse(
            settingsUsed=_settings_used(req),
            status="INFEASIBLE",
            message="There are no teaching slots to schedule into.",
            hints=[
                Hint(
                    title="No slots available",
                    detail="Every slot is blocked, or the day/period grid is empty.",
                )
            ],
        )

    # ---- 1. Expand subjects into session instances --------------------------
    sessions: List[_Session] = []
    for subject in req.subjects:
        size = sum(groups_by_id[gid].size for gid in subject.groupIds)
        for k in range(subject.sessionsPerWeek):
            sessions.append(_Session(len(sessions), subject, k, size))

    if not sessions:
        return SolveResponse(
            settingsUsed=_settings_used(req),
            status="OPTIMAL",
            message="Nothing to schedule: no subject requires any session.",
            stats=Stats(
                status="OPTIMAL",
                solveTimeSeconds=0.0,
                objectiveValue=0.0,
                numSessions=0,
                numPlaced=0,
                numSlots=len(slots),
                numBooleanVariables=0,
                preferenceViolations=0,
                gapPenalty=0,
            ),
            validation=Validation(ok=True),
        )

    model = cp_model.CpModel()

    # ---- 2. Decision variables ---------------------------------------------
    # x[(session_key, slot_index, room_id)] -- only for rooms that could legally
    # host this session. HARD CONSTRAINT 5 (room type) and HARD CONSTRAINT 6
    # (capacity >= total group size) are enforced right here, by omission.
    x: Dict[Tuple[int, int, str, str], cp_model.IntVar] = {}
    # Handy slices, built alongside the cube so we never scan the dict later.
    by_session: Dict[int, List[cp_model.IntVar]] = defaultdict(list)
    # (variable, slot index, room id, teacher id) per session. Symmetry breaking,
    # the preference objective and the solution read-back all need to know what a
    # literal *means*, and this is the only list any of them has to walk.
    session_terms: Dict[int, List[Tuple[cp_model.IntVar, int, str, str]]] = defaultdict(list)
    by_room_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    by_teacher_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    by_group_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)

    for session in sessions:
        subject = session.subject
        allowed_types = set(subject.allowedRoomTypes)
        for ti, _slot in enumerate(slots):
            for room in req.rooms:
                if room.type not in allowed_types:
                    continue
                if room.capacity < session.size:
                    continue
                for teacher_id in subject.teacherIds:
                    var = model.NewBoolVar(f"x_s{session.key}_t{ti}_r{room.id}_k{teacher_id}")
                    x[(session.key, ti, room.id, teacher_id)] = var
                    by_session[session.key].append(var)
                    session_terms[session.key].append((var, ti, room.id, teacher_id))
                    by_room_slot[(room.id, ti)].append(var)
                    # Keyed on the literal's own candidate, not on a fixed teacher:
                    # only the teacher this variable would actually assign is busy.
                    by_teacher_slot[(teacher_id, ti)].append(var)
                    for gid in subject.groupIds:
                        by_group_slot[(gid, ti)].append(var)

    # ---- 3. Hard constraints ------------------------------------------------

    # HARD 1: every session happens exactly once -- in one slot, in one room, with
    # one teacher. Summed over a subject's instances this is "scheduled exactly
    # sessionsPerWeek times", and because the literals carry a teacher index it is
    # also what picks a single teacher out of the subject's candidate pool.
    # Note: if a session has no legal (slot, room) at all, this is AddExactlyOne
    # over an empty list, which makes the model infeasible -- the correct answer,
    # and diagnostics.py explains why.
    for session in sessions:
        model.AddExactlyOne(by_session[session.key])

    # HARD 2: no teacher teaches two sessions in the same slot.
    for (_teacher_id, _ti), lits in by_teacher_slot.items():
        if len(lits) > 1:
            model.AddAtMostOne(lits)

    # HARD 3: no group attends two sessions in the same slot. A subject can link
    # several groups; each of them is busy, which is why by_group_slot fans a
    # single variable out to every group on the subject.
    for (_group_id, _ti), lits in by_group_slot.items():
        if len(lits) > 1:
            model.AddAtMostOne(lits)

    # HARD 4: no room hosts two sessions in the same slot.
    for (_room_id, _ti), lits in by_room_slot.items():
        if len(lits) > 1:
            model.AddAtMostOne(lits)

    # HARD 5 (room type) and HARD 6 (capacity): structural, see step 2.

    # ---- 4. Symmetry breaking (optional) -----------------------------------
    # The sessions of one subject are interchangeable, so every solution has
    # sessionsPerWeek! equivalent permutations and the search re-explores all of
    # them. Channel each session's slot into an integer and force a subject's
    # sessions to run in strictly increasing slot order. Strict "<" also encodes
    # "not twice in the same slot", which the group constraint already implies.
    #
    # Switchable, because CP-SAT's own presolve detects symmetry too (the search
    # log reports dozens of generators and an orbitope on this model). Whether our
    # constraint still earns its place is an empirical question, and the Settings
    # tab exists so it can be answered by measurement rather than assumption.
    slot_of: Dict[int, cp_model.IntVar] = {}
    for session in sessions:
        sv = model.NewIntVar(0, len(slots) - 1, f"slot_of_s{session.key}")
        terms = session_terms[session.key]
        if terms:
            model.Add(sv == sum(int(ti) * var for var, ti, _rid, _kid in terms))
        slot_of[session.key] = sv

    if req.useSymmetryBreaking:
        by_subject: Dict[str, List[_Session]] = defaultdict(list)
        for session in sessions:
            by_subject[session.subject.id].append(session)
        for subject_sessions in by_subject.values():
            ordered = sorted(subject_sessions, key=lambda s: s.index)
            for a, b in zip(ordered, ordered[1:]):
                model.Add(slot_of[a.key] < slot_of[b.key])

    # ---- 5. Soft constraints -> objective -----------------------------------
    objective_terms = []

    # SOFT 1: a session placed outside its teacher's preferred slots costs
    # preferenceWeight. Teachers with no stated preference contribute nothing.
    # Which teacher is now itself a decision, so the penalty is a property of the
    # literal, not of the session: picking a candidate who likes that slot is
    # cheaper, and that trade-off is exactly what the objective is here to make.
    preferred_by_teacher = {
        teacher.id: {slot_index[s] for s in teacher.preferredSlots if s in slot_index}
        for teacher in req.teachers
        if teacher.preferredSlots
    }
    preference_literals: List[cp_model.IntVar] = [
        var
        for session in sessions
        for var, ti, _rid, teacher_id in session_terms[session.key]
        if teacher_id in preferred_by_teacher and ti not in preferred_by_teacher[teacher_id]
    ]
    if req.preferenceWeight:
        objective_terms.extend(req.preferenceWeight * v for v in preference_literals)

    # SOFT 2: gaps in a group's day. busy[g][day][period] is true when group g has
    # anything in that slot; a gap is a free period with teaching on both sides.
    slots_by_day: Dict[str, List[Tuple[int, int]]] = defaultdict(list)  # day -> [(period, slot_index)]
    for ti, slot in enumerate(slots):
        slots_by_day[slot.day].append((slot.period, ti))

    gap_vars: List[cp_model.IntVar] = []
    for group in req.groups:
        for day, day_slots in slots_by_day.items():
            ordered = [ti for _p, ti in sorted(day_slots)]
            if len(ordered) < 3:
                continue
            busy: Dict[int, cp_model.IntVar] = {}
            for ti in ordered:
                b = model.NewBoolVar(f"busy_{group.id}_{day}_{ti}")
                lits = by_group_slot.get((group.id, ti), [])
                if lits:
                    # busy == OR(lits). AtMostOne above guarantees the sum is 0 or 1.
                    model.AddMaxEquality(b, lits)
                else:
                    model.Add(b == 0)
                busy[ti] = b
            # A middle period is a gap if it is free while some earlier and some
            # later period on the same day are busy. One variable per candidate
            # period, constrained by every surrounding pair -- not one variable
            # per pair, which would charge a single free period once for each
            # pair that brackets it.
            for j in range(1, len(ordered) - 1):
                mid = ordered[j]
                g = model.NewBoolVar(f"gap_{group.id}_{day}_{mid}")
                for i in range(j):
                    for k in range(j + 1, len(ordered)):
                        model.Add(g >= busy[ordered[i]] + busy[ordered[k]] - busy[mid] - 1)
                gap_vars.append(g)
    if req.gapWeight:
        objective_terms.extend(req.gapWeight * v for v in gap_vars)

    if objective_terms:
        model.Minimize(sum(objective_terms))

    # ---- 6. Solve -----------------------------------------------------------
    solver = cp_model.CpSolver()
    # Always bounded, defaulting to the 20-minute ceiling in models.py. On expiry
    # we return the best solution found so far and say so via FEASIBLE (or
    # UNKNOWN when nothing was found at all).
    solver.parameters.max_time_in_seconds = req.maxTimeInSeconds
    solver.parameters.num_search_workers = req.search.numWorkers
    solver.parameters.random_seed = req.search.randomSeed
    solver.parameters.cp_model_presolve = req.search.presolve
    # Left unset means "whatever this OR-Tools version defaults to".
    if req.search.symmetryLevel is not None:
        solver.parameters.symmetry_level = req.search.symmetryLevel
    if req.search.linearizationLevel is not None:
        solver.parameters.linearization_level = req.search.linearizationLevel
    # Stops at the first legal timetable. The result is then FEASIBLE by
    # definition, however good it happens to be.
    solver.parameters.stop_after_first_solution = req.stopAfterFirstSolution

    wall_start = time.perf_counter()
    status = solver.Solve(model)
    wall_seconds = time.perf_counter() - wall_start

    status_name = _STATUS_NAMES.get(status, "UNKNOWN")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        hints = build_hints(req)
        if status == cp_model.INFEASIBLE:
            message = (
                "No timetable exists: the hard constraints cannot all be satisfied "
                "at the same time."
            )
        else:
            message = (
                f"No solution found within {req.maxTimeInSeconds:g}s. The problem may "
                "still be solvable -- try a longer time limit."
            )
        return SolveResponse(
            settingsUsed=_settings_used(req),
            status=status_name,
            message=message,
            hints=hints,
            stats=Stats(
                status=status_name,
                solveTimeSeconds=round(wall_seconds, 3),
                objectiveValue=None,
                bestObjectiveBound=None,
                numSessions=len(sessions),
                numPlaced=0,
                numSlots=len(slots),
                numBooleanVariables=len(x),
                preferenceViolations=0,
                gapPenalty=0,
            ),
        )

    # ---- 7. Read the solution back ------------------------------------------
    assignments: List[Assignment] = []
    for session in sessions:
        subject = session.subject
        # Exactly one literal is true (HARD 1), and it carries the whole answer:
        # when, where, and which of the candidate teachers got the session.
        placed: Optional[Tuple[int, str, str]] = next(
            (
                (ti, room_id, teacher_id)
                for var, ti, room_id, teacher_id in session_terms[session.key]
                if solver.Value(var)
            ),
            None,
        )
        if placed is None:
            continue  # unreachable: HARD 1 forces exactly one true literal
        ti, room_id, teacher_id = placed
        teacher = teachers_by_id[teacher_id]
        slot = slots[ti]
        violated = bool(teacher.preferredSlots) and slot.id not in teacher.preferredSlots
        reason = None
        if violated:
            reason = (
                f"{teacher.name} prefers {len(teacher.preferredSlots)} other slot(s); "
                f"this session sits in {slot.day} period {slot.period}."
            )
        assignments.append(
            Assignment(
                subjectId=subject.id,
                subjectName=subject.name,
                slot=slot.id,
                roomId=room_id,
                roomName=rooms_by_id[room_id].name,
                teacherId=teacher.id,
                teacherName=teacher.name,
                groupIds=list(subject.groupIds),
                groupNames=[groups_by_id[g].name for g in subject.groupIds],
                softViolated=violated,
                softReason=reason,
            )
        )

    gap_penalty = sum(solver.Value(g) for g in gap_vars)
    violations = sum(1 for a in assignments if a.softViolated)

    # ---- 8. Check the solver's homework -------------------------------------
    # Re-derive every hard constraint from the returned assignments alone. If the
    # model above is wrong, this is what catches it.
    validation = validate_assignments(assignments, req)

    return SolveResponse(
        settingsUsed=_settings_used(req),
        status=status_name,
        message=(
            "Optimal timetable: no lower-penalty schedule exists."
            if status == cp_model.OPTIMAL
            else "Feasible timetable found within the time limit (not proven optimal)."
        ),
        assignments=assignments,
        stats=Stats(
            status=status_name,
            solveTimeSeconds=round(wall_seconds, 3),
            objectiveValue=solver.ObjectiveValue() if objective_terms else 0.0,
            bestObjectiveBound=solver.BestObjectiveBound() if objective_terms else 0.0,
            numSessions=len(sessions),
            numPlaced=len(assignments),
            numSlots=len(slots),
            numBooleanVariables=len(x),
            preferenceViolations=violations,
            gapPenalty=int(gap_penalty),
        ),
        validation=validation,
    )


def validate_assignments(assignments: List[Assignment], req: SolveRequest) -> Validation:
    """Independently verify a timetable against every hard constraint.

    Deliberately written without reference to the CP-SAT model above: it walks the
    returned assignments and re-checks them from the raw problem data. This is what
    makes "the solver produced a valid timetable" a checkable claim.
    """

    errors: List[str] = []
    rooms_by_id = {r.id: r for r in req.rooms}
    groups_by_id = {g.id: g for g in req.groups}
    slot_ids = {s.id for s in req.slots}

    # Every subject scheduled exactly sessionsPerWeek times.
    counts: Dict[str, int] = defaultdict(int)
    for a in assignments:
        counts[a.subjectId] += 1
    for subject in req.subjects:
        if counts[subject.id] != subject.sessionsPerWeek:
            errors.append(
                f"{subject.name}: scheduled {counts[subject.id]} time(s), "
                f"requires {subject.sessionsPerWeek}."
            )

    seen_teacher: Dict[Tuple[str, str], str] = {}
    seen_group: Dict[Tuple[str, str], str] = {}
    seen_room: Dict[Tuple[str, str], str] = {}

    for a in assignments:
        if a.slot not in slot_ids:
            errors.append(f"{a.subjectName}: placed in unknown/blocked slot {a.slot}.")

        room = rooms_by_id.get(a.roomId)
        subject = next((s for s in req.subjects if s.id == a.subjectId), None)
        if room is None:
            errors.append(f"{a.subjectName}: placed in unknown room {a.roomId}.")
        elif subject is not None:
            if room.type not in subject.allowedRoomTypes:
                allowed = ", ".join(t.value for t in subject.allowedRoomTypes)
                errors.append(
                    f"{a.subjectName} in {room.name}: room type {room.type.value} "
                    f"is not among the allowed types ({allowed})."
                )
            head_count = sum(groups_by_id[g].size for g in a.groupIds if g in groups_by_id)
            if room.capacity < head_count:
                errors.append(
                    f"{a.subjectName} in {room.name}: capacity {room.capacity} "
                    f"< {head_count} student(s)."
                )

        if subject is not None and a.teacherId not in subject.teacherIds:
            errors.append(
                f"{a.subjectName}: assigned to {a.teacherName}, who is not one of "
                "its candidate teachers."
            )

        key = (a.teacherId, a.slot)
        if key in seen_teacher:
            errors.append(
                f"{a.teacherName} double-booked in {a.slot}: "
                f"{seen_teacher[key]} and {a.subjectName}."
            )
        else:
            seen_teacher[key] = a.subjectName

        for gid in a.groupIds:
            gkey = (gid, a.slot)
            name = groups_by_id[gid].name if gid in groups_by_id else gid
            if gkey in seen_group:
                errors.append(
                    f"Group {name} double-booked in {a.slot}: "
                    f"{seen_group[gkey]} and {a.subjectName}."
                )
            else:
                seen_group[gkey] = a.subjectName

        rkey = (a.roomId, a.slot)
        if rkey in seen_room:
            errors.append(
                f"Room {a.roomName} double-booked in {a.slot}: "
                f"{seen_room[rkey]} and {a.subjectName}."
            )
        else:
            seen_room[rkey] = a.subjectName

    return Validation(ok=not errors, errors=errors)
