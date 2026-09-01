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
from typing import Dict, List, Optional, Tuple

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

    def __init__(self, key: int, subject, index: int, size: int, slot_indices):
        self.key = key            # position in the sessions list
        self.subject = subject
        self.index = index        # 0-based occurrence within its subject
        self.size = size          # total head-count of all its groups
        self.slots = slot_indices  # the slot indices this instance may occupy


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
        size = sum(groups_by_id[gid].size for gid in spec.groupIds)
        for k in range(spec.totalSessions):
            sessions.append(
                _Session(
                    len(sessions), subject, k, size,
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
        for ti in session.slots:
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
                    for gid in subject_groups[subject.id]:
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
        for session in sessions:
            if session.subject.id != subject.id:
                continue
            for var, ti, _rid, _kid in session_terms[session.key]:
                per_week[iso_week_of[ti]].append(var)
        low, high = divmod(spec.totalSessions, len(weeks))
        ceiling = low + (1 if high else 0)
        for week in weeks:
            lits = per_week.get(week, [])
            if not lits:
                continue
            model.Add(sum(lits) <= ceiling)
            if low:
                model.Add(sum(lits) >= low)

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
    preferred_by_teacher = {
        teacher.id: {ti for ti in range(len(slots)) if weekday_key[ti] in set(teacher.preferredSlots)}
        for teacher in req.teachers
        if teacher.preferredSlots
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

    def _literal_cost(ti: int, room_id: str, teacher_id: str) -> int:
        """What this exact (slot, room, teacher) choice costs its teacher's tier."""
        cost = 0
        prefs = preferred_by_teacher.get(teacher_id)
        if prefs is not None and ti not in prefs:
            cost += req.preferenceWeight
        rank = _room_rank_of(teacher_id, room_id)
        if rank:
            cost += req.roomPreferenceWeight * rank
        return cost

    tier_terms: Dict[int, List[Tuple[int, cp_model.IntVar]]] = defaultdict(list)
    for session in sessions:
        for var, ti, room_id, teacher_id in session_terms[session.key]:
            cost = _literal_cost(ti, room_id, teacher_id)
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

    # ---- 6. Solve, one phase per tier, highest rank first -------------------
    # Set once the phase list is known, and read by _new_solver below.
    ladder_mode = False

    def _new_solver(budget: float) -> cp_model.CpSolver:
        """A fresh solver per phase: each gets its own slice of the time budget,
        and the engine knobs are re-applied identically every time."""
        s = cp_model.CpSolver()
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
    phases: List[Tuple[str, int, Optional[object]]] = []
    for w in tier_weights:
        terms = tier_terms.get(w)
        phases.append(("tier", w, sum(c * v for c, v in terms) if terms else None))
    if gap_vars and req.gapWeight:
        phases.append(("gap", 0, req.gapWeight * sum(gap_vars)))

    # Stopping at the first solution is a request for *an* answer, not the best
    # one; running a five-rung optimisation ladder that abandons each rung
    # immediately would be neither. Collapse to the single combined objective.
    if req.stopAfterFirstSolution:
        combined = [c * v for terms in tier_terms.values() for c, v in terms]
        if gap_vars and req.gapWeight:
            combined.append(req.gapWeight * sum(gap_vars))
        phases = [("combined", 0, sum(combined) if combined else None)]

    active = [ph for ph in phases if ph[2] is not None]
    ladder_mode = len(active) > 1

    wall_start = time.perf_counter()
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
        remaining = req.maxTimeInSeconds
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
        warmup_budget = remaining
        model.ClearObjective()
        warmup = _new_solver(warmup_budget)
        warm_start = time.perf_counter()
        warm_status = warmup.Solve(model)
        warm_seconds = time.perf_counter() - warm_start
        remaining = max(remaining - warm_seconds, 0.0)
        # What the warm-up cost is the best estimate available of what any phase
        # costs before it can produce anything: the same presolve, on the same
        # model. A rung given less than that will burn its whole slice inside
        # presolve and return UNKNOWN, so it is better not to start it.
        phase_floor = max(warm_seconds, MIN_PHASE_SECONDS)
        if warm_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver = warmup
            last_status = warm_status
            model.ClearHints()
            for var in x.values():
                model.AddHint(var, warmup.Value(var))
            for var in slot_of.values():
                model.AddHint(var, warmup.Value(var))

        for label, weight, expr in active:
            if remaining <= 0:
                all_optimal = False
                break
            # An even share, but never less than the floor and never more than what
            # is left. The floor is what stops a tight budget being sliced so thin
            # that every rung dies in presolve; the clamp means the senior ranks
            # simply spend what there is and the junior ones go unrun, which is the
            # right way round. Attempting a rung is never a gamble: the warm-up
            # solution is already banked, so a rung that finds nothing costs only
            # its own slice.
            budget = min(max(remaining / phases_left, phase_floor), remaining)
            model.Minimize(expr)
            phase_start = time.perf_counter()
            phase_solver = _new_solver(budget)
            status = phase_solver.Solve(model)

            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                # Its slice was not enough. Rather than move down the ladder --
                # or stop with time still on the clock -- give this rung
                # everything that is left. It is the most senior rank still
                # unsettled, so it has the strongest claim on the remainder, and
                # the rungs beneath it were going to be starved either way.
                spent = time.perf_counter() - phase_start
                retry_budget = max(remaining - spent, 0.0)
                if retry_budget > 0:
                    phase_solver = _new_solver(retry_budget)
                    status = phase_solver.Solve(model)

            phase_seconds = time.perf_counter() - phase_start
            remaining = max(remaining - phase_seconds, 0.0)
            phases_left -= 1

            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                # Ran out of road even with the whole remainder. Whatever earlier
                # phases achieved still stands, so keep it rather than discarding
                # the run -- the warm-up timetable is already banked.
                all_optimal = False
                if solver is None:
                    last_status = status
                break

            solver = phase_solver
            last_status = status
            if status != cp_model.OPTIMAL:
                all_optimal = False
            achieved = int(round(phase_solver.ObjectiveValue()))

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
            # ClearHints first is mandatory, not tidiness: AddHint appends, and
            # duplicate entries make the model MODEL_INVALID on the next solve.
            # slot_of is included because a hint CP-SAT calls incomplete is worth
            # much less -- the x cube alone leaves those integers unhinted.
            model.ClearHints()
            for var in x.values():
                model.AddHint(var, phase_solver.Value(var))
            for var in slot_of.values():
                model.AddHint(var, phase_solver.Value(var))

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
                numBooleanVariables=len(x),
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
            numBooleanVariables=len(x),
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
