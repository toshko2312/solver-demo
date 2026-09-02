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
Sessions, not subjects, are what we place. A subject running 36 sessions in the
semester becomes 36 interchangeable session instances, each landing on a real
date somewhere inside that subject's window.

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
from collections import Counter, defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from .diagnostics import build_hints, check_references
from .models import (
    Assignment,
    SpreadMode,
    Hint,
    SettingsUsed,
    SolveRequest,
    SolveResponse,
    Stats,
    TierResult,
    Validation,
    effective_weight,
)


def _settings_used(req: SolveRequest) -> SettingsUsed:
    """Echo the knobs this run was solved with, so a result can never be read
    against settings that have since changed."""
    return SettingsUsed(
        maxTimeInSeconds=req.maxTimeInSeconds,
        preferenceWeight=req.preferenceWeight,
        roomPreferenceWeight=req.roomPreferenceWeight,
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


# A floor under any phase's slice. The real floor is this model's presolve cost,
# which is measured at run time (see the warm-up in step 6) because it scales with
# the instance -- on the full seed CP-SAT spends ~6s in presolve before the search
# starts, so a 4s slice returns UNKNOWN having never searched at all. This constant
# only guards the degenerate case of a tiny budget on a tiny model.
MIN_PHASE_SECONDS = 1.0


class _Session:
    """One instance of a subject that has to be placed exactly once."""

    def __init__(self, key: int, subject, index: int, slot_indices):
        self.key = key            # position in the sessions list
        self.subject = subject
        self.index = index        # 0-based occurrence within its subject
        self.slots = slot_indices  # the slot indices this instance may occupy


def solve_timetable(req: SolveRequest, on_event: Optional[Callable] = None) -> SolveResponse:
    """Build and solve the model. Never raises on an unsatisfiable problem --
    infeasibility is a result, not an error.

    `on_event` is an optional progress hook. It is called with plain dicts as the
    run passes its own milestones -- the model being built, then each rung of the
    ladder starting, improving and settling -- which is what `POST /solve/stream`
    turns into server-sent events. It changes nothing about the answer: with no
    hook the solve is exactly what it was, and the callback that reports improving
    solutions is only attached when there is somewhere to report them to.
    """

    def emit(kind: str, **payload) -> None:
        if on_event is not None:
            on_event({"type": kind, **payload})

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
    roles_by_id = {r.id: r for r in req.roles}
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

    # ---- 1. Which dates each subject may use --------------------------------
    # Everything about this solve is scoped to one semester. A group with no entry
    # for it is not in term and takes no part; a subject with no entry runs no
    # sessions.
    ref = req.semester
    group_semester = {g.id: g.semester(ref) for g in req.groups}
    all_dates = sorted({slot.date for slot in slots})

    def _usable_dates(subject) -> set:
        """Dates on which this subject may be taught.

        The *intersection* of its groups' teaching dates, not the union: every
        listed group is busy for the whole session, so a session cannot run while
        any one of them is out of term or on a break. Then narrowed to the
        subject's own spread window when it has one.
        """
        spec = subject.semester(ref)
        if spec is None:
            return set()
        usable: Optional[set] = None
        for gid in spec.groupIds:
            gs = group_semester.get(gid)
            if gs is None:
                return set()
            teaching = {d for d in all_dates if gs.teaches_on(d)}
            usable = teaching if usable is None else (usable & teaching)
        if usable is None:
            return set()
        if spec.spread == SpreadMode.range and spec.window is not None:
            usable = {d for d in usable if spec.window.contains(d)}
        return usable

    # subject id -> the slot indices it may occupy. This is what keeps the cube
    # from exploding across a whole semester: a session never gets a variable for
    # a slot outside its own window, exactly as it never gets one for a room of
    # the wrong type (step 3).
    subject_slots: Dict[str, List[int]] = {}
    subject_weeks: Dict[str, List[tuple]] = {}
    # subject id -> the groups attending it *this* semester. Groups live on the
    # semester entry, and everything below is already scoped to `ref`, so this is
    # resolved once here rather than at every use.
    subject_groups: Dict[str, List[str]] = {s.id: s.groups_for(ref) for s in req.subjects}
    iso_week_of = {ti: slot.date.isocalendar()[:2] for ti, slot in enumerate(slots)}
    for subject in req.subjects:
        dates = _usable_dates(subject)
        usable = [ti for ti, slot in enumerate(slots) if slot.date in dates]
        subject_slots[subject.id] = usable
        subject_weeks[subject.id] = sorted({iso_week_of[ti] for ti in usable})

    def _session_slots(subject, index: int, total: int) -> List[int]:
        """The slots one session instance may occupy.

        Two constraints already in this model pin a session to a narrow band of
        weeks, and applying them here -- at construction, where they cost nothing
        -- rather than only as constraints is what makes a semester-wide search
        affordable at all:

          * even spread (HARD 7) caps every week at `ceiling` sessions, and
          * symmetry breaking (step 4) forces a subject's sessions into strictly
            increasing slot order.

        Together they mean session `index` has at least `index` siblings before it
        and `total - 1 - index` after, so it cannot be earlier than
        `index // ceiling` weeks in, nor later than the mirror of that from the
        end. A subject running one session a week collapses to exactly one week
        per session -- which is the difference between ~40k booleans and ~10M.

        Only sound while symmetry breaking is on; without it the ordering
        assumption goes away and every usable slot has to stay in play.
        """
        weeks = subject_weeks[subject.id]
        usable = subject_slots[subject.id]
        if not req.useSymmetryBreaking or total == 0 or len(weeks) < 2:
            return usable
        ceiling = -(-total // len(weeks))          # ceil(total / weeks)
        first = min(index // ceiling, len(weeks) - 1)
        last = max(len(weeks) - 1 - (total - 1 - index) // ceiling, 0)
        if last < first:
            return usable                          # bounds crossed: do not prune
        window = set(weeks[first : last + 1])
        return [ti for ti in usable if iso_week_of[ti] in window]

    # ---- 2. Expand subjects into session instances --------------------------
    sessions: List[_Session] = []
    for subject in req.subjects:
        spec = subject.semester(ref)
        if spec is None:
            continue
        for k in range(spec.totalSessions):
            sessions.append(
                _Session(
                    len(sessions), subject, k,
                    _session_slots(subject, k, spec.totalSessions),
                )
            )

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
                roomPreferencePenalty=0,
                gapPenalty=0,
            ),
            validation=Validation(ok=True),
        )

    emit(
        "building",
        sessions=len(sessions),
        slots=len(slots),
        rooms=len(req.rooms),
        teachers=len(req.teachers),
    )
    model = cp_model.CpModel()

    # ---- 2. Decision variables ---------------------------------------------
    # One boolean per (session, slot, room, teacher) -- created only for rooms that
    # could legally host this session, so HARD CONSTRAINT 5 (room type) and HARD
    # CONSTRAINT 6 (capacity >= total group size) are enforced here by omission.
    #
    # What a literal *means* -- symmetry breaking, the preference objective and the
    # solution read-back all need it. Held as four parallel lists per session
    # rather than a list of 4-tuples: on the full seed that is 718k tuples not
    # allocated, and every consumer walks them with zip(). Nothing indexes the cube
    # by key, so no dict of the variables is kept either -- only the count, which
    # is what the stats report.
    session_vars: Dict[int, List[cp_model.IntVar]] = defaultdict(list)
    session_slots_of: Dict[int, List[int]] = defaultdict(list)
    session_rooms_of: Dict[int, List[str]] = defaultdict(list)
    session_teachers_of: Dict[int, List[str]] = defaultdict(list)
    num_literals = 0
    by_room_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    by_teacher_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    by_group_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)

    # Which rooms can host a session of a given (room types, head count) is the
    # same question for every session of a subject, so it is answered once per
    # subject rather than once per session instance.
    rooms_for_subject: Dict[str, List] = {}
    for subject in req.subjects:
        allowed_types = set(subject.allowedRoomTypes)
        size = sum(groups_by_id[gid].size for gid in subject_groups[subject.id])
        rooms_for_subject[subject.id] = [
            room
            for room in req.rooms
            if room.type in allowed_types and room.capacity >= size
        ]

    # Variables are created unnamed. A name is debug-only, and at this scale the
    # f-strings alone cost seconds while the names themselves inflate the proto
    # that every phase then has to presolve.
    new_bool = model.NewBoolVar
    for session in sessions:
        subject = session.subject
        key = session.key
        session_rooms = rooms_for_subject[subject.id]
        groups = subject_groups[subject.id]
        # Local aliases: these lists are appended to once per literal, and on the
        # full seed that is 718k times through this loop.
        session_list = session_vars[key]
        session_tis = session_slots_of[key]
        session_rids = session_rooms_of[key]
        session_kids = session_teachers_of[key]
        for ti in session.slots:
            for room in session_rooms:
                room_id = room.id
                room_slot = by_room_slot[(room_id, ti)]
                for teacher_id in subject.teacherIds:
                    var = new_bool("")
                    num_literals += 1
                    session_list.append(var)
                    session_tis.append(ti)
                    session_rids.append(room_id)
                    session_kids.append(teacher_id)
                    room_slot.append(var)
                    # Keyed on the literal's own candidate, not on a fixed teacher:
                    # only the teacher this variable would actually assign is busy.
                    by_teacher_slot[(teacher_id, ti)].append(var)
                    for gid in groups:
                        by_group_slot[(gid, ti)].append(var)

    # ---- 3. Hard constraints ------------------------------------------------

    # HARD 1: every session happens exactly once -- in one slot, in one room, with
    # one teacher. Summed over a subject's instances this is "scheduled exactly
    # its semester total", and because the literals carry a teacher index it is
    # also what picks a single teacher out of the subject's candidate pool.
    # Note: if a session has no legal (slot, room) at all, this is AddExactlyOne
    # over an empty list, which makes the model infeasible -- the correct answer,
    # and diagnostics.py explains why.
    for session in sessions:
        model.AddExactlyOne(session_vars[session.key])

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

    # A subject's own session instances. Built once: both the even-spread
    # constraint and the symmetry-breaking chain want it, and finding them by
    # scanning every session per subject is quadratic (158 x 3060 on the full
    # seed).
    sessions_by_subject: Dict[str, List[_Session]] = defaultdict(list)
    for session in sessions:
        sessions_by_subject[session.subject.id].append(session)

    # HARD 7: even spread. A subject's sessions are distributed across the
    # teaching weeks of its window, each week carrying between floor(N/W) and
    # ceil(N/W) of them. This is what "spread evenly" means once sessions land on
    # real dates, and it is also the constraint that makes a semester-wide search
    # affordable: without it a session roams every week of the term.
    for subject in req.subjects:
        spec = subject.semester(ref)
        if spec is None or spec.totalSessions == 0:
            continue
        weeks = subject_weeks[subject.id]
        if len(weeks) < 2:
            continue  # one week or none: nothing to spread across
        per_week: Dict[tuple, List[cp_model.IntVar]] = defaultdict(list)
        for session in sessions_by_subject[subject.id]:
            key = session.key
            for var, ti in zip(session_vars[key], session_slots_of[key]):
                per_week[iso_week_of[ti]].append(var)
        low, high = divmod(spec.totalSessions, len(weeks))
        ceiling = low + (1 if high else 0)
        for week in weeks:
            lits = per_week.get(week, [])
            if not lits:
                continue
            # LinearExpr.sum accumulates in C++; the builtin sum() would build one
            # throwaway expression object per literal.
            total = cp_model.LinearExpr.sum(lits)
            model.Add(total <= ceiling)
            if low:
                model.Add(total >= low)

    # ---- 4. Symmetry breaking (optional) -----------------------------------
    # The sessions of one subject are interchangeable, so every solution has
    # N! equivalent permutations and the search re-explores all of
    # them. Channel each session's slot into an integer and force a subject's
    # sessions to run in strictly increasing slot order. Strict "<" also encodes
    # "not twice in the same slot", which the group constraint already implies.
    #
    # Switchable, because CP-SAT's own presolve detects symmetry too (the search
    # log reports dozens of generators and an orbitope on this model). Whether our
    # constraint still earns its place is an empirical question, and the Settings
    # tab exists so it can be answered by measurement rather than assumption.
    # Built only when the chain below will use it: nothing else reads these
    # integers, and channelling them costs one linear constraint per session over
    # every literal that session has.
    slot_of: Dict[int, cp_model.IntVar] = {}
    if req.useSymmetryBreaking:
        for session in sessions:
            sv = model.NewIntVar(0, len(slots) - 1, "")
            key = session.key
            if session_vars[key]:
                model.Add(
                    sv
                    == cp_model.LinearExpr.weighted_sum(
                        session_vars[key], session_slots_of[key]
                    )
                )
            slot_of[key] = sv

        for subject_sessions in sessions_by_subject.values():
            ordered = sorted(subject_sessions, key=lambda s: s.index)
            for a, b in zip(ordered, ordered[1:]):
                model.Add(slot_of[a.key] < slot_of[b.key])

    # ---- 5. Soft constraints -> one penalty expression per priority tier ----
    # Teachers are sorted into tiers by rank weight, and each tier gets its own
    # objective. Step 6 then optimises them top down, freezing each before moving
    # on -- so a professor's preference is never sold to buy an assistant's.
    weight_of = {t.id: effective_weight(t, roles_by_id) for t in req.teachers}

    # SOFT 1: a session placed outside its teacher's preferred slots costs
    # preferenceWeight. Teachers with no stated preference contribute nothing.
    # Which teacher is now itself a decision, so the penalty is a property of the
    # literal, not of the session: picking a candidate who likes that slot is
    # cheaper, and that trade-off is exactly what the objective is here to make.
    # preferredSlots is weekday-keyed ('mon-1'), not dated, and deliberately so: a
    # teacher prefers Monday first period *every* week, not one Monday in October.
    # Same shape as blockedSlots, and what the weekday x period picker in the UI
    # produces. So a preference matches every slot sharing its weekday and period.
    weekday_key = {ti: f"{slot.day.lower()}-{slot.period}" for ti, slot in enumerate(slots)}
    preferred_by_teacher = {}
    for teacher in req.teachers:
        if not teacher.preferredSlots:
            continue
        # Hoisted: building the set inside the comprehension rebuilt it once per
        # slot, and there are 600 of them in a real semester.
        wanted = set(teacher.preferredSlots)
        preferred_by_teacher[teacher.id] = {
            ti for ti in range(len(slots)) if weekday_key[ti] in wanted
        }

    # SOFT 2: preferredRooms is *ranked*, so the cost is the room's position in
    # the list rather than a flat miss/hit. A room the teacher did not list at all
    # costs len(list): worse than every ranked choice, never infinitely worse.
    # Ids naming no live room are dropped before ranking -- the same silent
    # treatment preferredSlots entries already get (see diagnostics.py).
    # Ranking is scoped *per room type*, and that scoping is load-bearing. Which
    # room a session can use at all is a hard constraint (step 2), so a teacher who
    # ranks two полигона has expressed no opinion about which стрелбище they get --
    # and charging them the unlisted price for a firing-range session they are
    # required to teach would bill them for a choice they never had. Within a type
    # they did rank, an unlisted room still costs one step worse than their last
    # named choice, which is the whole point of ranking.
    room_type_of = {r.id: r.type for r in req.rooms}
    room_rank: Dict[str, Dict[str, int]] = {}       # teacher -> room -> position
    unlisted_rank: Dict[str, Dict[object, int]] = {}  # teacher -> room type -> cost

    for teacher in req.teachers:
        # Drop ids naming no live room, and keep only the first mention of a
        # repeated one, so a room cannot hold two positions at once. Both are
        # tolerated rather than rejected: see check_references in diagnostics.py.
        ranked: List[str] = []
        for rid in teacher.preferredRooms:
            if rid in room_type_of and rid not in ranked:
                ranked.append(rid)
        if not ranked:
            continue
        by_type: Dict[object, List[str]] = defaultdict(list)
        for rid in ranked:
            by_type[room_type_of[rid]].append(rid)
        room_rank[teacher.id] = {
            rid: i for rids in by_type.values() for i, rid in enumerate(rids)
        }
        unlisted_rank[teacher.id] = {t: len(rids) for t, rids in by_type.items()}

    def _room_rank_of(teacher_id: str, room_id: str) -> Optional[int]:
        """Position of a room among the rooms this teacher ranked *of that type*.

        None when they ranked nothing at all, or nothing of this room's type --
        both mean "no opinion", which can never be violated.
        """
        ranks = room_rank.get(teacher_id)
        if ranks is None:
            return None
        if room_id in ranks:
            return ranks[room_id]
        return unlisted_rank[teacher_id].get(room_type_of[room_id])

    # The cost of a literal is a function of (teacher, slot) and (teacher, room)
    # only, and both halves have a handful of distinct values -- so they are
    # tabulated once instead of being recomputed for each of the 718k literals on
    # the full seed.
    room_cost_by_teacher: Dict[str, Dict[str, int]] = {}
    for teacher in req.teachers:
        table = {}
        for room in req.rooms:
            rank = _room_rank_of(teacher.id, room.id)
            table[room.id] = req.roomPreferenceWeight * rank if rank else 0
        room_cost_by_teacher[teacher.id] = table

    tier_terms: Dict[int, List[Tuple[int, cp_model.IntVar]]] = defaultdict(list)
    for session in sessions:
        key = session.key
        for var, ti, room_id, teacher_id in zip(
            session_vars[key],
            session_slots_of[key],
            session_rooms_of[key],
            session_teachers_of[key],
        ):
            prefs = preferred_by_teacher.get(teacher_id)
            cost = req.preferenceWeight if prefs is not None and ti not in prefs else 0
            cost += room_cost_by_teacher[teacher_id][room_id]
            if cost:
                tier_terms[weight_of[teacher_id]].append((cost, var))

    # SOFT 3: gaps in a group's day. busy[g][day][period] is true when group g has
    # anything in that slot; a gap is a free period with teaching on both sides.
    # This is the last rung of the ladder: student compaction is settled only once
    # every rank has had its say.
    # Keyed by the real date: a gap is a hole in one actual day, and two Mondays
    # three weeks apart are different days with different holes.
    slots_by_day: Dict[object, List[Tuple[int, int]]] = defaultdict(list)  # date -> [(period, slot_index)]
    for ti, slot in enumerate(slots):
        slots_by_day[slot.date].append((slot.period, ti))

    # Days are ordered once, not once per group.
    ordered_by_day = {
        day: [ti for _p, ti in sorted(day_slots)]
        for day, day_slots in slots_by_day.items()
        if len(day_slots) >= 3
    }

    gap_vars: List[cp_model.IntVar] = []
    for group in req.groups:
        group_id = group.id
        for ordered in ordered_by_day.values():
            # Slots this group could actually occupy. Everywhere else its busy
            # literal is the constant 0, so no variable is created for it -- but
            # the period still counts as a gap candidate, because a period the
            # group can never occupy is exactly the kind of hole this penalises.
            busy: Dict[int, cp_model.IntVar] = {}
            for ti in ordered:
                lits = by_group_slot.get((group_id, ti))
                if lits:
                    b = model.NewBoolVar("")
                    # busy == OR(lits). AddMaxEquality takes the literals as they
                    # are; posting it as a linear equality instead measured worse,
                    # because model.Add flattens the expression into a var->coeff
                    # map first and these lists are long.
                    model.AddMaxEquality(b, lits)
                    busy[ti] = b
            if len(busy) < 2:
                continue  # nothing can bracket a hole: every gap here is a constant 0
            positions = {ti: j for j, ti in enumerate(ordered)}
            first = min(positions[ti] for ti in busy)
            last = max(positions[ti] for ti in busy)
            # A middle period is a gap if it is free while some earlier and some
            # later period on the same day are busy. Aggregating "anything
            # before" and "anything after" into one literal each keeps this linear
            # in the number of periods; the pairwise family it replaces was cubic
            # and has the same solutions, because g is boolean and
            # max_i(b_i) + max_k(b_k) - b_mid - 1 is the tightest of those pairs.
            for j in range(max(first + 1, 1), min(last, len(ordered) - 1)):
                mid = ordered[j]
                earlier = [busy[ti] for ti in ordered[:j] if ti in busy]
                later = [busy[ti] for ti in ordered[j + 1:] if ti in busy]
                if not earlier or not later:
                    continue  # nothing to bracket it: this gap is always 0
                before = model.NewBoolVar("")
                model.AddMaxEquality(before, earlier)
                after = model.NewBoolVar("")
                model.AddMaxEquality(after, later)
                g = model.NewBoolVar("")
                mid_busy = busy.get(mid)
                # g is defined both ways, not just lower-bounded. Minimising it
                # would pin it to its lower bound either way, so the optimum is
                # the same -- but the reverse implication lets CP-SAT fix g the
                # moment the surrounding periods are decided, which is what the
                # gap phase spends its time proving.
                free = [before, after] if mid_busy is None else [before, after, ~mid_busy]
                model.AddBoolAnd(free).OnlyEnforceIf(g)
                model.AddBoolOr([~lit for lit in free]).OnlyEnforceIf(~g)
                gap_vars.append(g)

    # ---- 6. Solve, one phase per tier, highest rank first -------------------
    # Set once the phase list is known, and read by _new_solver below.
    ladder_mode = False

    def _new_solver(budget: Optional[float]) -> cp_model.CpSolver:
        """A fresh solver per phase: each gets its own slice of the time budget,
        and the engine knobs are re-applied identically every time.

        A budget of None is an unlimited run -- CP-SAT is handed no deadline and
        stops only when it has finished or proved optimality."""
        s = cp_model.CpSolver()
        if budget is not None:
            s.parameters.max_time_in_seconds = max(budget, 0.01)
        s.parameters.num_search_workers = req.search.numWorkers
        s.parameters.random_seed = req.search.randomSeed
        s.parameters.cp_model_presolve = req.search.presolve
        # Left unset means "whatever this OR-Tools version defaults to" -- except in
        # ladder mode, where it must be 0. CP-SAT's symmetry presolve fixes literals
        # in each orbit, which turns the previous phase's solution hint from
        # "complete and feasible" into "infeasible, we will try to repair it". The
        # hint is what stops every rung re-discovering feasibility from scratch, so
        # on a hard instance the hint matters far more than the symmetry detection.
        # Our own slot_of symmetry breaking (step 4) still applies. An explicit
        # setting from the caller always wins.
        if req.search.symmetryLevel is not None:
            s.parameters.symmetry_level = req.search.symmetryLevel
        elif ladder_mode:
            s.parameters.symmetry_level = 0
        if req.search.linearizationLevel is not None:
            s.parameters.linearization_level = req.search.linearizationLevel
        s.parameters.stop_after_first_solution = req.stopAfterFirstSolution
        return s

    tier_weights = sorted({weight_of[t.id] for t in req.teachers}, reverse=True)
    roles_by_weight: Dict[int, set] = defaultdict(set)
    teachers_by_weight: Counter = Counter()
    for teacher in req.teachers:
        w = weight_of[teacher.id]
        teachers_by_weight[w] += 1
        role = roles_by_id.get(teacher.role) if teacher.role else None
        if role is not None:
            roles_by_weight[w].add(role.short)

    # (label, weight, expression). A tier with no costed literal has nothing to
    # decide, so it is recorded as a free win rather than burning a solve on a
    # constant-zero objective.
    # weighted_sum builds the expression in C++. The builtin sum() over
    # `c * v` terms allocates one intermediate expression per literal, which on
    # the full seed is ~600k allocations per objective.
    def _penalty(terms) -> object:
        return cp_model.LinearExpr.weighted_sum(
            [v for _c, v in terms], [c for c, _v in terms]
        )

    phases: List[Tuple[str, int, Optional[object]]] = []
    for w in tier_weights:
        terms = tier_terms.get(w)
        phases.append(("tier", w, _penalty(terms) if terms else None))
    if gap_vars and req.gapWeight:
        phases.append(
            ("gap", 0, cp_model.LinearExpr.weighted_sum(gap_vars, [req.gapWeight] * len(gap_vars)))
        )

    # Stopping at the first solution is a request for *an* answer, not the best
    # one; running a five-rung optimisation ladder that abandons each rung
    # immediately would be neither. Collapse to the single combined objective.
    if req.stopAfterFirstSolution:
        combined_vars = [v for terms in tier_terms.values() for _c, v in terms]
        combined_coeffs = [c for terms in tier_terms.values() for c, _v in terms]
        if gap_vars and req.gapWeight:
            combined_vars += gap_vars
            combined_coeffs += [req.gapWeight] * len(gap_vars)
        phases = [
            (
                "combined",
                0,
                cp_model.LinearExpr.weighted_sum(combined_vars, combined_coeffs)
                if combined_vars
                else None,
            )
        ]

    active = [ph for ph in phases if ph[2] is not None]
    ladder_mode = len(active) > 1

    # The warm-up plus every rung. Fixed before a single second of search, which
    # is what lets the client draw a bar that only ever moves forwards.
    total_phases = 1 + len(active) if active else 1
    emit(
        "built",
        numBooleanVariables=num_literals,
        total=total_phases,
        phases=[
            {
                "label": label,
                "weight": weight,
                "roles": sorted(roles_by_weight.get(weight, ())),
            }
            for label, weight, _expr in active
        ],
    )

    wall_start = time.perf_counter()

    def _hint_from(source: cp_model.CpSolver) -> None:
        """Hand the next solve the timetable this one found.

        ClearHints first is mandatory, not tidiness: AddHint appends, and
        duplicate entries make the model MODEL_INVALID on the next solve.

        Only the true literals are hinted -- one per session -- rather than all
        718k cube variables. The false ones carry no information CP-SAT cannot
        derive: HARD 1 makes each session's literals exactly-one, so fixing the
        true one determines its siblings. slot_of is included because those
        integers are not implied by any single literal.
        """
        model.ClearHints()
        for session in sessions:
            for var in session_vars[session.key]:
                if source.Value(var):
                    model.AddHint(var, 1)
                    break
        for var in slot_of.values():
            model.AddHint(var, source.Value(var))

    class _Reporter(cp_model.CpSolverSolutionCallback):
        """Forwards every improving solution of the phase in flight.

        The phase objective *is* the tier's penalty, so `best` is the number the
        UI shows, and `bound` against it is how much of the rung is left to prove.
        Only attached when there is a hook to report to -- an ordinary solve never
        pays for it.
        """

        def __init__(self, index: int):
            super().__init__()
            self.index = index

        def on_solution_callback(self) -> None:
            emit(
                "improved",
                index=self.index,
                best=self.ObjectiveValue(),
                bound=self.BestObjectiveBound(),
            )

    def _solve(solver_: cp_model.CpSolver, index: Optional[int]) -> int:
        """Solve, reporting improvements when a progress hook is listening."""
        if on_event is None or index is None:
            return solver_.Solve(model)
        return solver_.Solve(model, _Reporter(index))

    # weight -> (status, seconds) for the phase that settled that tier.
    tier_outcome: Dict[int, Tuple[str, float]] = {}
    solver: Optional[cp_model.CpSolver] = None
    all_optimal = True
    last_status = cp_model.UNKNOWN

    if not active:
        # No soft constraint has any bite: this is a pure feasibility question.
        solver = _new_solver(req.maxTimeInSeconds)
        last_status = solver.Solve(model)
        if last_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver = None
        all_optimal = last_status == cp_model.OPTIMAL
    else:
        # None all the way down: an unlimited run has nothing to ration, so every
        # phase simply runs to completion in turn.
        unlimited = req.maxTimeInSeconds is None
        remaining = req.maxTimeInSeconds if not unlimited else 0.0
        # A warm-up solve with no objective at all, purely to find *a* legal
        # timetable, whose solution is then hinted into the first rung. Without it
        # the top tier pays the whole cost of finding feasibility out of its own
        # slice -- on the full seed that is ~10s against a 5s slice, so the ladder
        # returned UNKNOWN having never placed a single session. Every later rung
        # is warm-started by its predecessor; this is what warm-starts the first.
        phases_left = len(active)
        # The warm-up is not rationed. It carries no objective, so CP-SAT returns
        # the moment it finds any legal timetable -- giving it the whole budget
        # costs nothing when the instance is easy, and on a hard one it is the
        # difference between answering and not. Rationing it to a share of the
        # budget is what made the full seed return UNKNOWN with nothing at all:
        # the run has to *have* a timetable before optimising one is meaningful,
        # and once it has one, every later rung can only improve on it.
        warmup_budget = None if unlimited else remaining
        model.ClearObjective()
        warmup = _new_solver(warmup_budget)
        warm_start = time.perf_counter()
        emit("phase", index=1, total=total_phases, label="warmup", weight=0, roles=[])
        # No objective, so nothing to improve on: the reporter would only repeat
        # the one solution that ends this phase.
        warm_status = warmup.Solve(model)
        warm_seconds = time.perf_counter() - warm_start
        emit(
            "phase_done",
            index=1,
            total=total_phases,
            label="warmup",
            status=_STATUS_NAMES.get(warm_status, "UNKNOWN"),
            penalty=None,
            seconds=round(warm_seconds, 3),
        )
        if not unlimited:
            remaining = max(remaining - warm_seconds, 0.0)
        # What the warm-up cost is the best estimate available of what any phase
        # costs before it can produce anything: the same presolve, on the same
        # model. A rung given less than that will burn its whole slice inside
        # presolve and return UNKNOWN, so it is better not to start it.
        phase_floor = max(warm_seconds, MIN_PHASE_SECONDS)
        if warm_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver = warmup
            last_status = warm_status
            _hint_from(warmup)

        for phase_index, (label, weight, expr) in enumerate(active, start=2):
            if not unlimited and remaining <= 0:
                all_optimal = False
                break
            # An even share, but never less than the floor and never more than what
            # is left. The floor is what stops a tight budget being sliced so thin
            # that every rung dies in presolve; the clamp means the senior ranks
            # simply spend what there is and the junior ones go unrun, which is the
            # right way round. Attempting a rung is never a gamble: the warm-up
            # solution is already banked, so a rung that finds nothing costs only
            # its own slice.
            budget = (
                None if unlimited
                else min(max(remaining / phases_left, phase_floor), remaining)
            )
            model.Minimize(expr)
            phase_start = time.perf_counter()
            emit(
                "phase",
                index=phase_index,
                total=total_phases,
                label=label,
                weight=weight,
                roles=sorted(roles_by_weight.get(weight, ())),
            )
            phase_solver = _new_solver(budget)
            status = _solve(phase_solver, phase_index)

            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                # Its slice was not enough. Rather than move down the ladder --
                # or stop with time still on the clock -- give this rung
                # everything that is left. It is the most senior rank still
                # unsettled, so it has the strongest claim on the remainder, and
                # the rungs beneath it were going to be starved either way.
                # An unlimited rung already had every second there is, so there
                # is nothing to retry it with -- it failed for some other reason.
                spent = time.perf_counter() - phase_start
                retry_budget = 0.0 if unlimited else max(remaining - spent, 0.0)
                if retry_budget > 0:
                    phase_solver = _new_solver(retry_budget)
                    status = _solve(phase_solver, phase_index)

            phase_seconds = time.perf_counter() - phase_start
            if not unlimited:
                remaining = max(remaining - phase_seconds, 0.0)
            phases_left -= 1

            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                # Ran out of road even with the whole remainder. Whatever earlier
                # phases achieved still stands, so keep it rather than discarding
                # the run -- the warm-up timetable is already banked.
                all_optimal = False
                if solver is None:
                    last_status = status
                emit(
                    "phase_done",
                    index=phase_index,
                    total=total_phases,
                    label=label,
                    status=_STATUS_NAMES.get(status, "UNKNOWN"),
                    penalty=None,
                    seconds=round(phase_seconds, 3),
                )
                break

            solver = phase_solver
            last_status = status
            if status != cp_model.OPTIMAL:
                all_optimal = False
            achieved = int(round(phase_solver.ObjectiveValue()))
            emit(
                "phase_done",
                index=phase_index,
                total=total_phases,
                label=label,
                status=_STATUS_NAMES.get(status, "UNKNOWN"),
                penalty=achieved,
                seconds=round(phase_seconds, 3),
            )

            if label == "tier":
                tier_outcome[weight] = (
                    _STATUS_NAMES.get(status, "UNKNOWN"),
                    round(phase_seconds, 3),
                )

            # Freeze this rung before the next one bargains. The bound comes from
            # a solution that demonstrably exists, so the model stays feasible.
            # When the phase only reached FEASIBLE the bound is a value this tier
            # settled for rather than its true optimum -- the ladder still holds,
            # but the claim is weaker, which is why the status is reported per tier.
            #
            model.Add(expr <= achieved)

            # Hand the next rung the solution this one just found. Without it every
            # phase re-discovers feasibility from scratch, which on the full seed
            # costs ~10s a rung against a 30s budget for the whole ladder.
            _hint_from(phase_solver)

    # Every tier is reported, including ones that never got a phase of their own --
    # either free (no costed literal to decide) or never reached before the budget
    # ran out. Penalties are read back off the solution rather than taken from the
    # phase objective, so they are right whichever route produced it: the ladder,
    # the collapsed stopAfterFirstSolution solve, or no objective at all.
    def _build_tiers() -> List[TierResult]:
        out: List[TierResult] = []
        for w in tier_weights:
            terms = tier_terms.get(w) or []
            if solver is not None:
                penalty = sum(c * solver.Value(v) for c, v in terms)
                # A tier with no costed literal had nothing to decide, so it is
                # satisfied by definition. One that had something to decide but
                # never got a phase ran out of budget: its penalty is whatever the
                # timetable happens to give it, NOT a number it agreed to.
                default_status = "OPTIMAL" if not terms else "NOT REACHED"
            else:
                penalty = 0
                default_status = "UNKNOWN"
            status_str, seconds = tier_outcome.get(w, (default_status, 0.0))
            out.append(
                TierResult(
                    weight=w,
                    roles=sorted(roles_by_weight.get(w, ())),
                    teacherCount=teachers_by_weight[w],
                    penalty=int(penalty),
                    status=status_str,
                    solveTimeSeconds=seconds,
                )
            )
        return out

    tier_results = _build_tiers()

    wall_seconds = time.perf_counter() - wall_start
    status_name = _STATUS_NAMES.get(last_status, "UNKNOWN")
    if solver is not None:
        status_name = "OPTIMAL" if all_optimal else "FEASIBLE"

    if solver is None:
        hints = build_hints(req)
        if last_status == cp_model.INFEASIBLE:
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
                numBooleanVariables=num_literals,
                preferenceViolations=0,
                roomPreferencePenalty=0,
                gapPenalty=0,
                tiers=tier_results,
            ),
        )

    # ---- 7. Read the solution back ------------------------------------------
    assignments: List[Assignment] = []
    for session in sessions:
        subject = session.subject
        # Exactly one literal is true (HARD 1), and it carries the whole answer:
        # when, where, and which of the candidate teachers got the session.
        value = solver.BooleanValue
        placed: Optional[Tuple[int, str, str]] = next(
            (
                (ti, room_id, teacher_id)
                for var, ti, room_id, teacher_id in zip(
                    session_vars[session.key],
                    session_slots_of[session.key],
                    session_rooms_of[session.key],
                    session_teachers_of[session.key],
                )
                if value(var)
            ),
            None,
        )
        if placed is None:
            continue  # unreachable: HARD 1 forces exactly one true literal
        ti, room_id, teacher_id = placed
        teacher = teachers_by_id[teacher_id]
        slot = slots[ti]
        rank = _room_rank_of(teacher_id, room_id)
        slot_missed = (
            bool(teacher.preferredSlots)
            and f"{slot.day.lower()}-{slot.period}" not in teacher.preferredSlots
        )
        room_missed = bool(rank)
        violated = slot_missed or room_missed
        # Both halves are reported, because "wrong room" and "wrong time" are
        # different complaints and the card in the UI has to say which.
        reasons = []
        if slot_missed:
            reasons.append(
                f"{teacher.name} prefers {len(teacher.preferredSlots)} other slot(s); "
                f"this session sits in {slot.day} period {slot.period}."
            )
        if room_missed:
            if room_id in room_rank[teacher_id]:
                reasons.append(
                    f"{rooms_by_id[room_id].name} is {teacher.name}'s "
                    f"#{rank + 1} choice of room of this type, not their first."
                )
            else:
                reasons.append(
                    f"{rooms_by_id[room_id].name} is not among the {rank} room(s) "
                    f"of this type {teacher.name} ranked."
                )
        reason = " ".join(reasons) if reasons else None
        assignments.append(
            Assignment(
                subjectId=subject.id,
                subjectName=subject.name,
                slot=slot.id,
                date=slot.date,
                roomId=room_id,
                roomName=rooms_by_id[room_id].name,
                teacherId=teacher.id,
                teacherName=teacher.name,
                groupIds=list(subject_groups[subject.id]),
                groupNames=[groups_by_id[g].name for g in subject_groups[subject.id]],
                softViolated=violated,
                softReason=reason,
                roomPreferenceRank=rank,
            )
        )

    gap_penalty = sum(solver.Value(g) for g in gap_vars)
    violations = sum(1 for a in assignments if a.softViolated)
    room_penalty = sum(
        req.roomPreferenceWeight * a.roomPreferenceRank
        for a in assignments
        if a.roomPreferenceRank
    )
    # The whole ladder in one number, recomputed rather than read off the solver:
    # after the phases CP-SAT's own ObjectiveValue() is only the final rung, which
    # would price a timetable that broke every professor's preference at zero.
    total_penalty = sum(t.penalty for t in tier_results) + req.gapWeight * int(gap_penalty)

    # ---- 8. Check the solver's homework -------------------------------------
    # Re-derive every hard constraint from the returned assignments alone. If the
    # model above is wrong, this is what catches it.
    validation = validate_assignments(assignments, req)

    return SolveResponse(
        settingsUsed=_settings_used(req),
        status=status_name,
        message=(
            "Optimal timetable: every priority tier reached its best possible outcome."
            if status_name == "OPTIMAL"
            else "Feasible timetable found within the time limit (not proven optimal)."
        ),
        assignments=assignments,
        stats=Stats(
            status=status_name,
            solveTimeSeconds=round(wall_seconds, 3),
            objectiveValue=float(total_penalty),
            # A bound on the last rung is not a bound on the ladder, so it is only
            # meaningful when a single objective was solved.
            # Only one phase ran, so its bound is a bound on the whole answer.
            bestObjectiveBound=solver.BestObjectiveBound() if len(active) == 1 else None,
            numSessions=len(sessions),
            numPlaced=len(assignments),
            numSlots=len(slots),
            numBooleanVariables=num_literals,
            preferenceViolations=violations,
            roomPreferencePenalty=int(room_penalty),
            gapPenalty=int(gap_penalty),
            tiers=tier_results,
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
    subjects_by_id = {s.id: s for s in req.subjects}
    slot_ids = {s.id for s in req.slots}

    # Every subject scheduled exactly its semester total.
    counts: Dict[str, int] = defaultdict(int)
    for a in assignments:
        counts[a.subjectId] += 1
    for subject in req.subjects:
        spec = subject.semester(req.semester)
        required = spec.totalSessions if spec is not None else 0
        if counts[subject.id] != required:
            errors.append(
                f"{subject.name}: scheduled {counts[subject.id]} time(s) this "
                f"semester, requires {required}."
            )

    seen_teacher: Dict[Tuple[str, str], str] = {}
    seen_group: Dict[Tuple[str, str], str] = {}
    seen_room: Dict[Tuple[str, str], str] = {}

    groups_semester = {g.id: g.semester(req.semester) for g in req.groups}

    for a in assignments:
        if a.slot not in slot_ids:
            errors.append(f"{a.subjectName}: placed in unknown/blocked slot {a.slot}.")

        # Re-derive the date window from the raw problem, without reference to the
        # model that produced it: every group of the session must be in term and
        # off break on this date.
        for gid in a.groupIds:
            gs = groups_semester.get(gid)
            name = groups_by_id[gid].name if gid in groups_by_id else gid
            if gs is None:
                errors.append(f"{a.subjectName}: group {name} is not in term this semester.")
            elif not gs.teaches_on(a.date):
                errors.append(
                    f"{a.subjectName} on {a.date}: group {name} is not teaching that "
                    "day (outside its semester, or on a break)."
                )

        room = rooms_by_id.get(a.roomId)
        subject = subjects_by_id.get(a.subjectId)
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
