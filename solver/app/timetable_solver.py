"""Timetable scheduling for Академия на МВР as a CP-SAT model.

This is the file worth reading: it is the whole scheduling model, and the rest of
the service is plumbing around it.

THE PROBLEM
-----------
Place every session of every учебен план into a (period, room, teacher) triple
such that nobody and nothing is double-booked, every room fits and suits its
session, and -- as far as the hard constraints allow -- teachers get the periods
they asked for and student groups get compact days.

THE ENCODING
------------
Sessions, not offerings, are what we place. An offering carries a хорариум, which
`sessions.build_series` turns into series of interchangeable sessions: one series
for its лекции (attended by the whole поток) and one per group or подгрупа for its
упражнения. Each session lands on a real dated period.

One boolean per (session, period, room, teacher) quadruple:

    x[s, t, r, k] == 1  <=>  session s happens in period t, in room r, taught by k

An offering names a *set* of acceptable room types per activity kind and, for
упражнения, a *pool* of candidate teachers, so where and who are both decisions.
The teacher index is what makes the pool work: the session's "happens exactly
once" constraint already ranges over teacher-tagged variables, so "exactly one
teacher from the pool" needs no constraint of its own -- it falls out of HARD 1.
A лекция has a single водещ преподавател, which is simply a pool of one, so the
same machinery covers both.

The cube is pruned when it is built. A room only gets a variable for a session if
its type is one the activity accepts and its capacity fits; a teacher only gets
one for a period inside their hard availability. Three hard constraints therefore
never appear as constraints at all -- they are structural. That is the first
question a reader has ("where is the capacity constraint?"), hence this paragraph.

THE TEACHING DAY
----------------
A period is a block of two academic hours, and it is the atomic unit: every clash
constraint below is keyed on the dated period. The обедна почивка needs no rule of
its own -- it is the stretch of clock between two periods that no period covers,
so nothing can be scheduled across it.
"""

import time
from collections import Counter, defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from .diagnostics import build_hints, check_references
from .models import (
    ActivityKind,
    Assignment,
    Hint,
    SettingsUsed,
    SolveRequest,
    SolveResponse,
    SpreadMode,
    Stats,
    TierResult,
    Validation,
    effective_weight,
)
from .sessions import build_series, courses_in_term


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
# the instance -- on the full seed CP-SAT spends several seconds in presolve
# before the search starts, so a 4s slice returns UNKNOWN having never searched at
# all. This constant only guards the degenerate case of a tiny budget on a tiny
# model.
MIN_PHASE_SECONDS = 1.0


class _Session:
    """One instance of a series that has to be placed exactly once."""

    __slots__ = ("key", "series", "index", "slots")

    def __init__(self, key: int, series, index: int, slot_indices):
        self.key = key             # position in the sessions list
        self.series = series       # the Series it belongs to
        self.index = index         # 0-based occurrence within its series
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

    ref = req.semester
    rooms_by_id = {r.id: r for r in req.rooms}
    groups_by_id = {g.id: g for g in req.groups}
    subgroups_by_id = {sg.id: sg for sg in req.subgroups}
    teachers_by_id = {t.id: t for t in req.teachers}
    roles_by_id = {r.id: r for r in req.roles}
    subjects_by_id = {s.id: s for s in req.subjects}
    in_term = courses_in_term(req, ref)

    # ---- 1. The dated grid ---------------------------------------------------
    # Every dated period on offer, which is what the solver places into. A period
    # the user blocked, or one inside a non-teaching stretch, is simply not here.
    slots = req.slots
    if not slots:
        return SolveResponse(
            settingsUsed=_settings_used(req),
            status="INFEASIBLE",
            message="There are no teaching periods to schedule into.",
            hints=[
                Hint(
                    title="No teachable periods",
                    detail=(
                        "There is no dated period to schedule into: every period is "
                        "blocked, or no курс is in term on any day of the grid."
                    ),
                )
            ],
        )

    all_dates = sorted({slot.date for slot in slots})
    week_of = {ti: slot.date.isocalendar()[:2] for ti, slot in enumerate(slots)}
    # What preferredSlots and hardAvailability are keyed on: this period, that
    # weekday, every week.
    weekday_key = {
        ti: f"{slot.day.lower()}-{slot.period}" for ti, slot in enumerate(slots)
    }

    # ---- 2. Which periods each series may use -------------------------------
    series_list = build_series(req, ref)

    def _usable_dates(series) -> set:
        """Dates on which this series may be taught.

        The *intersection* of its groups' teaching dates, not the union: every
        listed group is busy for the whole session, so a лекция cannot run while
        any one поток group is out of term or on a стаж. Then narrowed to the
        offering's own spread window when it has one.
        """
        usable: Optional[set] = None
        for gid in series.group_ids:
            group = groups_by_id.get(gid)
            course = in_term.get(group.courseInstanceId) if group else None
            if course is None:
                return set()
            teaching = {d for d in all_dates if course.teaches_on(d)}
            usable = teaching if usable is None else (usable & teaching)
        if usable is None:
            return set()
        window = series.offering.window
        if series.offering.spread is not SpreadMode.whole and window is not None:
            usable = {d for d in usable if window.contains(d)}
        return usable

    # series key -> the slot indices it may occupy. This is what keeps the cube
    # from exploding across a whole semester: a session never gets a variable for
    # a period outside its own window, exactly as it never gets one for a room of
    # the wrong type.
    series_slots: Dict[str, List[int]] = {}
    series_weeks: Dict[str, List[tuple]] = {}
    for series in series_list:
        dates = _usable_dates(series)
        usable = [ti for ti, slot in enumerate(slots) if slot.date in dates]
        series_slots[series.key] = usable
        series_weeks[series.key] = sorted({week_of[ti] for ti in usable})

    def _session_slots(series, index: int, total: int) -> List[int]:
        """The periods one session instance may occupy.

        Two constraints already in this model pin a session to a narrow band of
        weeks, and applying them here -- at construction, where they cost nothing
        -- rather than only as constraints is what makes a semester-wide search
        affordable at all:

          * even spread (HARD 7) caps every week at `ceiling` sessions, and
          * symmetry breaking (step 5) forces a series' sessions into strictly
            increasing period order.

        Together they mean session `index` has at least `index` siblings before it
        and `total - 1 - index` after, so it cannot be earlier than
        `index // ceiling` weeks in, nor later than the mirror of that from the
        end. A series running one session a week collapses to exactly one week per
        session -- which is the difference between a model that solves and one
        that does not.

        Only sound while symmetry breaking is on AND the series is evenly spread.
        `block` deliberately has no weekly ceiling, so the arithmetic above has no
        basis and every usable period has to stay in play.
        """
        weeks = series_weeks[series.key]
        usable = series_slots[series.key]
        if (
            not req.useSymmetryBreaking
            or series.offering.spread is SpreadMode.block
            or total == 0
            or len(weeks) < 2
        ):
            return usable
        ceiling = -(-total // len(weeks))          # ceil(total / weeks)
        first = min(index // ceiling, len(weeks) - 1)
        last = max(len(weeks) - 1 - (total - 1 - index) // ceiling, 0)
        if last < first:
            return usable                          # bounds crossed: do not prune
        window = set(weeks[first : last + 1])
        return [ti for ti in usable if week_of[ti] in window]

    # ---- 3. Expand series into session instances ----------------------------
    sessions: List[_Session] = []
    for series in series_list:
        for k in range(series.count):
            sessions.append(
                _Session(len(sessions), series, k, _session_slots(series, k, series.count))
            )

    if not sessions:
        return SolveResponse(
            settingsUsed=_settings_used(req),
            status="OPTIMAL",
            message="Nothing to schedule: no offering requires any session.",
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

    # ---- 4. Decision variables ----------------------------------------------
    # One boolean per (session, period, room, teacher) -- created only for rooms
    # that could legally host this session and teachers who could legally be
    # there, so HARD 5 (room type), HARD 6 (capacity) and HARD 10 (hard
    # availability) are all enforced here by omission.
    #
    # What a literal *means* -- symmetry breaking, the preference objective and
    # the solution read-back all need it. Held as four parallel lists per session
    # rather than a list of 4-tuples: on a faculty-sized problem that is hundreds
    # of thousands of tuples not allocated, and every consumer walks them with
    # zip(). Nothing indexes the cube by key, so no dict of the variables is kept
    # either -- only the count, which is what the stats report.
    session_vars: Dict[int, List[cp_model.IntVar]] = defaultdict(list)
    session_slots_of: Dict[int, List[int]] = defaultdict(list)
    session_rooms_of: Dict[int, List[str]] = defaultdict(list)
    session_teachers_of: Dict[int, List[str]] = defaultdict(list)
    num_literals = 0
    by_room_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    by_teacher_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    # Group-level sessions (лекции, and упражнения taught to a whole group) and
    # подгрупа sessions are collected apart, because they are constrained
    # differently: a group-level session excludes every подгрупа of that group,
    # while two подгрупи may be taught side by side. Keeping them in one bucket
    # would forbid exactly the parallelism the split exists to create.
    by_group_level_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    by_subgroup_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)
    # Everything that makes a group busy, subgroups included. What the gap
    # objective and the daily cap both read.
    by_group_busy_slot: Dict[Tuple[str, int], List[cp_model.IntVar]] = defaultdict(list)

    # Which rooms can host a session of a given (room types, head count) is the
    # same question for every session of a series, so it is answered once per
    # series rather than once per session instance.
    rooms_for_series: Dict[str, List] = {}
    for series in series_list:
        allowed_types = set(series.room_types)
        rooms_for_series[series.key] = [
            room
            for room in req.rooms
            if room.type in allowed_types and room.capacity >= series.head_count
        ]

    # Hard availability, resolved once per teacher into the set of slot indices
    # they can actually attend. Empty availability means "always", which is why
    # the value is None rather than the full set -- a membership test we can skip.
    available_slots: Dict[str, Optional[set]] = {}
    for teacher in req.teachers:
        if not teacher.hardAvailability:
            available_slots[teacher.id] = None
            continue
        wanted = set(teacher.hardAvailability)
        available_slots[teacher.id] = {
            ti for ti in range(len(slots)) if weekday_key[ti] in wanted
        }

    # Variables are created unnamed. A name is debug-only, and at this scale the
    # f-strings alone cost seconds while the names themselves inflate the proto
    # that every phase then has to presolve.
    new_bool = model.NewBoolVar
    for session in sessions:
        series = session.series
        key = session.key
        series_rooms = rooms_for_series[series.key]
        groups = series.group_ids
        subgroup_id = series.subgroup_id
        # Local aliases: these lists are appended to once per literal.
        session_list = session_vars[key]
        session_tis = session_slots_of[key]
        session_rids = session_rooms_of[key]
        session_kids = session_teachers_of[key]
        for ti in session.slots:
            for room in series_rooms:
                room_id = room.id
                room_slot = by_room_slot[(room_id, ti)]
                for teacher_id in series.teacher_ids:
                    reachable = available_slots[teacher_id]
                    if reachable is not None and ti not in reachable:
                        continue      # HARD 10: outside a hard window, no literal
                    var = new_bool("")
                    num_literals += 1
                    session_list.append(var)
                    session_tis.append(ti)
                    session_rids.append(room_id)
                    session_kids.append(teacher_id)
                    room_slot.append(var)
                    # Keyed on the literal's own candidate, not on a fixed
                    # teacher: only the teacher this variable would actually
                    # assign is busy.
                    by_teacher_slot[(teacher_id, ti)].append(var)
                    if subgroup_id is None:
                        for gid in groups:
                            by_group_level_slot[(gid, ti)].append(var)
                    else:
                        by_subgroup_slot[(subgroup_id, ti)].append(var)
                    for gid in groups:
                        by_group_busy_slot[(gid, ti)].append(var)

    # ---- 5. Hard constraints ------------------------------------------------

    # HARD 1: every session happens exactly once -- in one period, in one room, with
    # one teacher. Summed over a series' instances this is "scheduled exactly its
    # хорариум", and because the literals carry a teacher index it is also what
    # picks a single teacher out of the candidate pool.
    # Note: if a session has no legal (period, room, teacher) at all, this is
    # AddExactlyOne over an empty list, which makes the model infeasible -- the
    # correct answer, and diagnostics.py explains why.
    for session in sessions:
        model.AddExactlyOne(session_vars[session.key])

    # HARD 2: no teacher teaches two sessions in the same period.
    for (_teacher_id, _ti), lits in by_teacher_slot.items():
        if len(lits) > 1:
            model.AddAtMostOne(lits)

    # HARD 3: no group attends two sessions in the same period, and a group-level
    # session excludes every one of that group's подгрупи.
    #
    # Posted as one AtMostOne per (group, period, subgroup) rather than one over
    # everything the group could be doing: the union form would also forbid two
    # подгрупи running side by side, which is the entire point of splitting a
    # group for стрелкова подготовка. Each of these constraints already implies
    # "at most one group-level session", so the standalone version is only needed
    # for a group with no подгрупи at all.
    subgroups_of: Dict[str, List[str]] = defaultdict(list)
    for subgroup in req.subgroups:
        subgroups_of[subgroup.groupId].append(subgroup.id)

    for (group_id, ti), group_lits in by_group_level_slot.items():
        children = subgroups_of.get(group_id)
        if not children:
            if len(group_lits) > 1:
                model.AddAtMostOne(group_lits)
            continue
        for sub_id in children:
            lits = group_lits + by_subgroup_slot.get((sub_id, ti), [])
            if len(lits) > 1:
                model.AddAtMostOne(lits)

    # HARD 4: no подгрупа attends two sessions in the same period. The loop above
    # covers every period a group-level session could occupy; a period where only
    # подгрупи are busy still needs this.
    for (_sub_id, _ti), lits in by_subgroup_slot.items():
        if len(lits) > 1:
            model.AddAtMostOne(lits)

    # HARD 5: a room hosts at most `maxConcurrentGroups` sessions in one period.
    # One for everything by default -- and emphatically one for стрелбище and
    # малка зала, which take a single group or подгрупа at a time. AddAtMostOne
    # rather than a counting constraint in that case: CP-SAT propagates it better.
    for (room_id, _ti), lits in by_room_slot.items():
        if len(lits) < 2:
            continue
        limit = rooms_by_id[room_id].maxConcurrentGroups
        if limit == 1:
            model.AddAtMostOne(lits)
        else:
            model.Add(cp_model.LinearExpr.sum(lits) <= limit)

    # HARD 6 (room type) and HARD 7 (capacity): structural, see step 4.
    # HARD 10 (teacher hard availability): structural, see step 4.

    # A series' own session instances. Built once: both the even-spread constraint
    # and the symmetry-breaking chain want it, and finding them by scanning every
    # session per series is quadratic.
    sessions_by_series: Dict[str, List[_Session]] = defaultdict(list)
    for session in sessions:
        sessions_by_series[session.series.key].append(session)

    # HARD 8: even spread. A series' sessions are distributed across the teaching
    # weeks of its window, each week carrying between floor(N/W) and ceil(N/W) of
    # them. This is what "spread evenly" means once sessions land on real dates,
    # and it is also the constraint that makes a semester-wide search affordable:
    # without it a session roams every week of the term.
    #
    # Задочна форма is the exception. A block offering compresses a whole semester
    # into a two- or three-week присъствен period, where balancing weeks is not
    # what anybody wants: the window is meant to be saturated. So `block` gets no
    # weekly floor and no ceiling -- and, correspondingly, no week-band pruning in
    # `_session_slots`, which is only sound because of the ceiling.
    for series in series_list:
        if not series.count or series.offering.spread is SpreadMode.block:
            continue
        weeks = series_weeks[series.key]
        if len(weeks) < 2:
            continue  # one week or none: nothing to spread across
        per_week: Dict[tuple, List[cp_model.IntVar]] = defaultdict(list)
        for session in sessions_by_series[series.key]:
            key = session.key
            for var, ti in zip(session_vars[key], session_slots_of[key]):
                per_week[week_of[ti]].append(var)
        low, high = divmod(series.count, len(weeks))
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

    # HARD 9: a teacher's weekly load. Only posted for teachers who declared a
    # cap -- most have none, and an unposted constraint is the cheapest kind.
    capped = [t for t in req.teachers if t.maxWeeklyPeriods is not None]
    if capped:
        by_teacher_week: Dict[Tuple[str, tuple], List[cp_model.IntVar]] = defaultdict(list)
        for (teacher_id, ti), lits in by_teacher_slot.items():
            by_teacher_week[(teacher_id, week_of[ti])].extend(lits)
        for teacher in capped:
            for week in set(week_of.values()):
                lits = by_teacher_week.get((teacher.id, week))
                if lits:
                    model.Add(cp_model.LinearExpr.sum(lits) <= teacher.maxWeeklyPeriods)

    # ---- 6. Symmetry breaking (optional) ------------------------------------
    # The sessions of one series are interchangeable, so every solution has N!
    # equivalent permutations and the search re-explores all of them. Channel each
    # session's period into an integer and force a series' sessions to run in
    # strictly increasing period order. Strict "<" also encodes "not twice in the
    # same period", which the group constraint already implies.
    #
    # Switchable, because CP-SAT's own presolve detects symmetry too. Whether our
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

        for series_sessions in sessions_by_series.values():
            ordered = sorted(series_sessions, key=lambda s: s.index)
            for a, b in zip(ordered, ordered[1:]):
                model.Add(slot_of[a.key] < slot_of[b.key])

    # ---- 7. Soft constraints -> one penalty expression per priority tier -----
    # Teachers are sorted into tiers by rank weight, and each tier gets its own
    # objective. Step 8 then optimises them top down, freezing each before moving
    # on -- so a професор's preference is never sold to buy an асистент's.
    weight_of = {t.id: effective_weight(t, roles_by_id) for t in req.teachers}

    # SOFT 1: a session placed outside its teacher's preferred periods costs
    # preferenceWeight. Teachers with no stated preference contribute nothing.
    # Which teacher is now itself a decision, so the penalty is a property of the
    # literal, not of the session: picking a candidate who likes that period is
    # cheaper, and that trade-off is exactly what the objective is here to make.
    # preferredSlots is weekday-keyed ('mon-1'), not dated, and deliberately so:
    # a teacher prefers Monday's first period *every* week, not one Monday in
    # October.
    preferred_by_teacher = {}
    for teacher in req.teachers:
        if not teacher.preferredSlots:
            continue
        # Hoisted: building the set inside the comprehension rebuilt it once per
        # period, and there are hundreds of them in a real semester.
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
    # room a session can use at all is a hard constraint (step 4), so a teacher
    # who ranks two полигона has expressed no opinion about which стрелбище they
    # get -- and charging them the unlisted price for a стрелбище session they are
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

    # The cost of a literal is a function of (teacher, period) and (teacher, room)
    # only, and both halves have a handful of distinct values -- so they are
    # tabulated once instead of being recomputed for each of the many literals.
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

    # `busy[group][date][period]` is true when the group has anything in that period
    # -- its own sessions and every one of its подгрупи, because a group is busy
    # when any подгрупа of it is. Two things read this: the daily cap (HARD 11,
    # below) and the gap objective (SOFT 3). Built once for both.
    slots_by_day: Dict[object, List[Tuple[int, int]]] = defaultdict(list)
    for ti, slot in enumerate(slots):
        slots_by_day[slot.date].append((slot.period, ti))

    # Days are ordered once, not once per group.
    ordered_by_day = {
        day: [ti for _period, ti in sorted(day_slots)]
        for day, day_slots in slots_by_day.items()
    }

    busy_by_group_day: Dict[Tuple[str, object], Dict[int, cp_model.IntVar]] = {}
    for group in req.groups:
        for day, ordered in ordered_by_day.items():
            busy: Dict[int, cp_model.IntVar] = {}
            for ti in ordered:
                lits = by_group_busy_slot.get((group.id, ti))
                if lits:
                    b = model.NewBoolVar("")
                    # busy == OR(lits). AddMaxEquality takes the literals as they
                    # are; posting it as a linear equality instead measured worse,
                    # because model.Add flattens the expression into a var->coeff
                    # map first and these lists are long.
                    model.AddMaxEquality(b, lits)
                    busy[ti] = b
            if busy:
                busy_by_group_day[(group.id, day)] = busy

    # HARD 11: no group is taught more than its course allows in one day. Counted
    # over `busy`, so two подгрупи running side by side cost the group one period of
    # its day, not two -- which is what the cap means to the курсанти living it.
    for group in req.groups:
        course = in_term.get(group.courseInstanceId)
        if course is None:
            continue
        for day in ordered_by_day:
            busy = busy_by_group_day.get((group.id, day))
            if busy and len(busy) > course.maxPeriodsPerDay:
                model.Add(
                    cp_model.LinearExpr.sum(list(busy.values())) <= course.maxPeriodsPerDay
                )

    # SOFT 3: gaps in a group's day. A gap is a free period with teaching on both
    # sides of it. This is the last rung of the ladder: student compaction is
    # settled only once every rank has had its say. Keyed by the real date: a gap
    # is a hole in one actual day, and two Mondays three weeks apart are different
    # days with different holes.
    gap_vars: List[cp_model.IntVar] = []
    for group in req.groups:
        for day, ordered in ordered_by_day.items():
            if len(ordered) < 3:
                continue  # nothing can bracket a hole
            busy = busy_by_group_day.get((group.id, day))
            if not busy or len(busy) < 2:
                continue  # every gap here is a constant 0
            positions = {ti: j for j, ti in enumerate(ordered)}
            first = min(positions[ti] for ti in busy)
            last = max(positions[ti] for ti in busy)
            # A middle period is a gap if it is free while some earlier and some
            # later period on the same day are busy. Aggregating "anything before"
            # and "anything after" into one literal each keeps this linear in the
            # number of periods; the pairwise family it replaces was cubic and has
            # the same solutions, because g is boolean and
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
                # moment the surrounding periods are decided, which is what the gap
                # phase spends its time proving.
                free = [before, after] if mid_busy is None else [before, after, ~mid_busy]
                model.AddBoolAnd(free).OnlyEnforceIf(g)
                model.AddBoolOr([~lit for lit in free]).OnlyEnforceIf(~g)
                gap_vars.append(g)

    # ---- 8. Solve, one phase per tier, highest rank first --------------------
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
        # Left unset means "whatever this OR-Tools version defaults to" -- except
        # in ladder mode, where it must be 0. CP-SAT's symmetry presolve fixes
        # literals in each orbit, which turns the previous phase's solution hint
        # from "complete and feasible" into "infeasible, we will try to repair
        # it". The hint is what stops every rung re-discovering feasibility from
        # scratch, so on a hard instance the hint matters far more than the
        # symmetry detection. Our own slot_of symmetry breaking (step 6) still
        # applies. An explicit setting from the caller always wins.
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
    # weighted_sum builds the expression in C++. The builtin sum() over `c * v`
    # terms allocates one intermediate expression per literal.
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

    total_phases = 1 + len(active) if active else 1
    emit(
        "built",
        numBooleanVariables=num_literals,
        total=total_phases,
        phases=[
            {"label": label, "weight": weight, "roles": sorted(roles_by_weight.get(weight, ()))}
            for label, weight, _expr in active
        ],
    )

    solver: Optional[cp_model.CpSolver] = None
    last_status = cp_model.UNKNOWN
    all_optimal = True
    tier_outcome: Dict[int, Tuple[str, float]] = {}
    wall_start = time.perf_counter()

    def _hint_from(source: cp_model.CpSolver) -> None:
        """Warm-start the next phase from the solution this one just found.

        ClearHints first is mandatory: AddHint appends, and hinting the same
        variable twice makes the model invalid.
        """
        model.ClearHints()
        for session in sessions:
            key = session.key
            for var in session_vars[key]:
                if source.BooleanValue(var):
                    model.AddHint(var, 1)
                    break
        for sv in slot_of.values():
            model.AddHint(sv, source.Value(sv))

    class _Reporter(cp_model.CpSolverSolutionCallback):
        """Reports improving solutions as the phase finds them."""

        def __init__(self, index: int):
            super().__init__()
            self._index = index

        def on_solution_callback(self) -> None:
            emit(
                "improved",
                index=self._index,
                best=self.ObjectiveValue(),
                bound=self.BestObjectiveBound(),
            )

    def _solve(solver_: cp_model.CpSolver, index: Optional[int]) -> int:
        if on_event is not None and index is not None:
            return solver_.Solve(model, _Reporter(index))
        return solver_.Solve(model)

    if not active:
        single = _new_solver(req.maxTimeInSeconds)
        last_status = _solve(single, None)
        if last_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver = single
        all_optimal = last_status == cp_model.OPTIMAL
    else:
        unlimited = req.maxTimeInSeconds is None
        remaining = 0.0 if unlimited else float(req.maxTimeInSeconds)
        phases_left = len(active)

        # The warm-up is deliberately NOT rationed: a run has to *have* a
        # timetable before optimising one means anything, and once it has one
        # every later rung can only improve on it. That is what guarantees a solve
        # always returns the best timetable it found, however little time it was
        # given.
        model.ClearObjective()
        emit("phase", index=1, total=total_phases, label="warmup", weight=0, roles=[])
        warmup = _new_solver(None if unlimited else remaining)
        warm_start = time.perf_counter()
        warm_status = _solve(warmup, None)
        warm_seconds = time.perf_counter() - warm_start
        remaining -= warm_seconds
        phase_floor = max(warm_seconds, MIN_PHASE_SECONDS)
        emit(
            "phase_done",
            index=1,
            total=total_phases,
            label="warmup",
            status=_STATUS_NAMES.get(warm_status, "UNKNOWN"),
            penalty=None,
            seconds=round(warm_seconds, 3),
        )
        if warm_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver = warmup
            _hint_from(warmup)
        else:
            all_optimal = False
        last_status = warm_status

        if solver is not None:
            for phase_index, (label, weight, expr) in enumerate(active, start=2):
                if not unlimited and remaining <= 0:
                    all_optimal = False
                    break

                # Each rung gets an even share of what is left, floored at the
                # warm-up's own measured cost -- the best available estimate of
                # what this model's presolve costs, since a rung given less than
                # that spends its whole slice in presolve and returns UNKNOWN
                # having never searched. When the remaining budget cannot afford
                # another real rung the ladder stops there, which starves the
                # *junior* ranks: the right way round.
                budget = (
                    None
                    if unlimited
                    else min(max(remaining / phases_left, phase_floor), remaining)
                )
                model.Minimize(expr)
                emit(
                    "phase",
                    index=phase_index,
                    total=total_phases,
                    label=label,
                    weight=weight,
                    roles=sorted(roles_by_weight.get(weight, ())),
                )
                phase_start = time.perf_counter()
                phase_solver = _new_solver(budget)
                status = _solve(phase_solver, phase_index)
                spent = time.perf_counter() - phase_start

                if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    # One retry with everything that is left: a rung that returned
                    # nothing at all is worth more time than its even share.
                    retry_budget = 0.0 if unlimited else max(remaining - spent, 0.0)
                    if unlimited or retry_budget > 0:
                        phase_solver = _new_solver(None if unlimited else retry_budget)
                        status = _solve(phase_solver, phase_index)
                        spent = time.perf_counter() - phase_start

                phase_seconds = spent
                remaining -= phase_seconds
                phases_left -= 1

                if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
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

                # Freeze this rung before the next one bargains. The bound comes
                # from a solution that demonstrably exists, so the model stays
                # feasible. When the phase only reached FEASIBLE the bound is a
                # value this tier settled for rather than its true optimum -- the
                # ladder still holds, but the claim is weaker, which is why the
                # status is reported per tier.
                model.Add(expr <= achieved)

                # Hand the next rung the solution this one just found. Without it
                # every phase re-discovers feasibility from scratch.
                _hint_from(phase_solver)

    # Every tier is reported, including ones that never got a phase of their own
    # -- either free (no costed literal to decide) or never reached before the
    # budget ran out. Penalties are read back off the solution rather than taken
    # from the phase objective, so they are right whichever route produced it: the
    # ladder, the collapsed stopAfterFirstSolution solve, or no objective at all.
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
        elif req.maxTimeInSeconds is None:
            # No deadline was set, so running out of time is not what happened.
            # CP-SAT gave up for its own reasons, or the run was interrupted.
            message = (
                "The search ended without a timetable and without proving there is "
                "none. Nothing here can say why."
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

    # ---- 9. Read the solution back ------------------------------------------
    assignments: List[Assignment] = []
    value = solver.BooleanValue
    for session in sessions:
        series = session.series
        offering = series.offering
        subject = subjects_by_id[offering.subjectId]
        # Exactly one literal is true (HARD 1), and it carries the whole answer:
        # when, where, and which of the candidate teachers got the session.
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
            bool(teacher.preferredSlots) and weekday_key[ti] not in teacher.preferredSlots
        )
        room_missed = bool(rank)
        violated = slot_missed or room_missed
        # Both halves are reported, because "wrong room" and "wrong time" are
        # different complaints and the card in the UI has to say which.
        reasons = []
        if slot_missed:
            reasons.append(
                f"{teacher.name} prefers {len(teacher.preferredSlots)} other period(s); "
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
        subgroup = subgroups_by_id.get(series.subgroup_id) if series.subgroup_id else None
        assignments.append(
            Assignment(
                offeringId=offering.id,
                subjectId=subject.id,
                subjectCode=subject.code,
                subjectName=subject.name,
                activity=series.activity,
                slot=slot.id,
                period=slot.period,
                date=slot.date,
                day=slot.day,
                roomId=room_id,
                roomName=rooms_by_id[room_id].name,
                teacherId=teacher.id,
                teacherName=teacher.name,
                groupIds=list(series.group_ids),
                groupNames=[
                    groups_by_id[g].name if g in groups_by_id else g
                    for g in series.group_ids
                ],
                subgroupId=subgroup.id if subgroup else None,
                subgroupName=subgroup.name if subgroup else None,
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

    # ---- 10. Check the solver's homework ------------------------------------
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
    returned assignments and re-checks them from the raw problem data. This is
    what makes "the solver produced a valid timetable" a checkable claim.
    """

    errors: List[str] = []
    ref = req.semester
    rooms_by_id = {r.id: r for r in req.rooms}
    groups_by_id = {g.id: g for g in req.groups}
    subgroups_by_id = {sg.id: sg for sg in req.subgroups}
    offerings_by_id = {o.id: o for o in req.offerings}
    in_term = courses_in_term(req, ref)
    slot_ids = {s.id for s in req.slots}

    # Every series scheduled exactly the sessions its хорариум asks for.
    required = {s.key: s for s in build_series(req, ref)}
    counts: Dict[str, int] = defaultdict(int)
    for a in assignments:
        unit = a.subgroupId or (a.groupIds[0] if a.activity is not ActivityKind.lektsiya and a.groupIds else None)
        key = f"{a.offeringId}:л" if a.activity is ActivityKind.lektsiya else f"{a.offeringId}:у:{unit}"
        counts[key] += 1
    for key, series in required.items():
        if counts[key] != series.count:
            offering = series.offering
            errors.append(
                f"{offering.id} ({series.label}): scheduled {counts[key]} time(s), "
                f"requires {series.count} for its хорариум."
            )
    for key in counts:
        if key not in required:
            errors.append(f"Scheduled sessions for '{key}', which this semester does not run.")

    seen_teacher: Dict[Tuple[str, str], str] = {}
    seen_group: Dict[Tuple[str, str], str] = {}
    seen_subgroup: Dict[Tuple[str, str], str] = {}
    room_load: Dict[Tuple[str, str], int] = defaultdict(int)
    day_load: Dict[Tuple[str, object], set] = defaultdict(set)
    week_load: Dict[Tuple[str, tuple], int] = defaultdict(int)

    for a in assignments:
        where = f"{a.subjectName} ({a.activity.value})"

        # The slot id is derived from the date and the period, so a card whose
        # three fields disagree is a bug in whatever produced or moved it.
        if a.slot != f"{a.date.isoformat()}-{a.period}":
            errors.append(
                f"{where}: slot id {a.slot} does not match its date and period."
            )
        if a.slot not in slot_ids:
            errors.append(f"{where}: placed in unknown or blocked slot {a.slot}.")

        # Re-derive the date window from the raw problem, without reference to the
        # model that produced it: every group of the session must be in term and
        # teaching on this date.
        for gid in a.groupIds:
            group = groups_by_id.get(gid)
            name = group.name if group else gid
            course = in_term.get(group.courseInstanceId) if group else None
            if course is None:
                errors.append(f"{where}: group {name} is not in term this semester.")
            elif not course.teaches_on(a.date):
                errors.append(
                    f"{where} on {a.date}: group {name} is not teaching that day "
                    "(outside its term, or in a non-teaching period)."
                )

        offering = offerings_by_id.get(a.offeringId)
        room = rooms_by_id.get(a.roomId)
        if room is None:
            errors.append(f"{where}: placed in unknown room {a.roomId}.")
        elif offering is not None:
            allowed = offering.room_types_for(a.activity)
            if room.type not in allowed:
                names = ", ".join(t.value for t in allowed)
                errors.append(
                    f"{where} in {room.name}: room type {room.type.value} is not "
                    f"among the allowed types ({names})."
                )
            if a.subgroupId is not None:
                subgroup = subgroups_by_id.get(a.subgroupId)
                head_count = subgroup.size if subgroup else 0
            else:
                head_count = sum(
                    groups_by_id[g].size for g in a.groupIds if g in groups_by_id
                )
            if room.capacity < head_count:
                errors.append(
                    f"{where} in {room.name}: capacity {room.capacity} "
                    f"< {head_count} student(s)."
                )

        if offering is not None:
            if a.activity is ActivityKind.lektsiya:
                if a.teacherId != offering.leadTeacherId:
                    errors.append(
                        f"{where}: taught by {a.teacherName}, who is not the водещ "
                        "преподавател."
                    )
            elif a.teacherId not in offering.exerciseTeacherIds:
                errors.append(
                    f"{where}: assigned to {a.teacherName}, who is not one of its "
                    "candidate teachers."
                )
            window = offering.window
            if offering.spread.value != "whole" and window is not None:
                if not window.contains(a.date):
                    errors.append(
                        f"{where} on {a.date}: outside the period it is spread across."
                    )

        teacher = next((t for t in req.teachers if t.id == a.teacherId), None)
        if teacher is not None and teacher.hardAvailability:
            key = f"{a.day.lower()}-{a.period}"
            if key not in teacher.hardAvailability:
                errors.append(
                    f"{where}: {a.teacherName} is not available in {key}, which is a "
                    "hard constraint."
                )

        key = (a.teacherId, a.slot)
        if key in seen_teacher:
            errors.append(
                f"{a.teacherName} double-booked in {a.slot}: "
                f"{seen_teacher[key]} and {where}."
            )
        else:
            seen_teacher[key] = where

        if a.subgroupId is not None:
            skey = (a.subgroupId, a.slot)
            if skey in seen_subgroup:
                errors.append(
                    f"Subgroup {a.subgroupName} double-booked in {a.slot}: "
                    f"{seen_subgroup[skey]} and {where}."
                )
            else:
                seen_subgroup[skey] = where
        else:
            # Only group-level sessions claim the group exclusively. A подгрупа
            # session busies its parent group for the daily cap and the gaps, but
            # two подгрупи may share a period -- so it is not a double booking.
            for gid in a.groupIds:
                gkey = (gid, a.slot)
                name = groups_by_id[gid].name if gid in groups_by_id else gid
                if gkey in seen_group:
                    errors.append(
                        f"Group {name} double-booked in {a.slot}: "
                        f"{seen_group[gkey]} and {where}."
                    )
                else:
                    seen_group[gkey] = where

        room_load[(a.roomId, a.slot)] += 1
        for gid in a.groupIds:
            day_load[(gid, a.date)].add(a.period)
        week_load[(a.teacherId, a.date.isocalendar()[:2])] += 1

    # A group-level session and a подгрупа session of the same group in the same
    # period is a clash, even though neither map above catches it on its own.
    for a in assignments:
        if a.subgroupId is None:
            continue
        subgroup = subgroups_by_id.get(a.subgroupId)
        if subgroup is None:
            errors.append(f"{a.subjectName}: names unknown subgroup {a.subgroupId}.")
            continue
        other = seen_group.get((subgroup.groupId, a.slot))
        if other is not None:
            name = groups_by_id[subgroup.groupId].name if subgroup.groupId in groups_by_id else subgroup.groupId
            errors.append(
                f"Subgroup {a.subgroupName} is taught in {a.slot} while its group "
                f"{name} is in {other}."
            )

    for (room_id, slot_id), load in room_load.items():
        room = rooms_by_id.get(room_id)
        limit = room.maxConcurrentGroups if room else 1
        if load > limit:
            name = room.name if room else room_id
            errors.append(
                f"Room {name} hosts {load} session(s) in {slot_id}, above its "
                f"limit of {limit}."
            )

    for (group_id, date), periods_used in day_load.items():
        group = groups_by_id.get(group_id)
        course = in_term.get(group.courseInstanceId) if group else None
        if course is None:
            continue
        if len(periods_used) > course.maxPeriodsPerDay:
            errors.append(
                f"Group {group.name} is taught {len(periods_used)} period(s) on {date}, "
                f"above its cap of {course.maxPeriodsPerDay}."
            )

    for (teacher_id, week), load in week_load.items():
        teacher = next((t for t in req.teachers if t.id == teacher_id), None)
        if teacher is None or teacher.maxWeeklyPeriods is None:
            continue
        if load > teacher.maxWeeklyPeriods:
            errors.append(
                f"{teacher.name} teaches {load} period(s) in week {week[1]} of {week[0]}, "
                f"above their cap of {teacher.maxWeeklyPeriods}."
            )

    return Validation(ok=not errors, errors=errors)
