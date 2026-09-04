"""Why is this problem impossible?

CP-SAT tells you a model is INFEASIBLE; it does not tell you which of your
requirements you should relax. These are cheap counting checks -- run before the
solve, reported when it fails -- that catch the over-subscription cases that
account for nearly every hand-built impossible timetable.

They are necessary conditions only: passing every check does not make a problem
solvable, so when none of them fires we say so rather than inventing a reason.
"""

from collections import defaultdict
from typing import Dict, List

from .models import Hint, SolveRequest
from .sessions import build_series, courses_in_term


def check_references(req: SolveRequest) -> List[str]:
    """Dangling ids and malformed grids are data bugs, not infeasibilities --
    report them separately, as MODEL_INVALID."""

    errors: List[str] = []
    faculty_ids = {f.id for f in req.faculties}
    katedra_ids = {k.id for k in req.katedri}
    specialty_ids = {s.id for s in req.specialties}
    course_ids = {c.id for c in req.courseInstances}
    teacher_ids = {t.id for t in req.teachers}
    room_ids = {r.id for r in req.rooms}
    group_ids = {g.id for g in req.groups}
    subgroup_ids = {sg.id for sg in req.subgroups}
    subject_ids = {s.id for s in req.subjects}

    for katedra in req.katedri:
        if katedra.facultyId is not None and katedra.facultyId not in faculty_ids:
            errors.append(
                f"Катедра '{katedra.name}' names faculty '{katedra.facultyId}', "
                "which does not exist."
            )
    for specialty in req.specialties:
        if specialty.facultyId not in faculty_ids:
            errors.append(
                f"Specialty '{specialty.name}' names faculty '{specialty.facultyId}', "
                "which does not exist."
            )
    for course in req.courseInstances:
        if course.specialtyId not in specialty_ids:
            errors.append(
                f"Course '{course.id}' names specialty '{course.specialtyId}', "
                "which does not exist."
            )
        if course.start > course.end:
            errors.append(f"Course '{course.id}' ends before it starts.")
    for group in req.groups:
        if group.courseInstanceId not in course_ids:
            errors.append(
                f"Group '{group.name}' names course '{group.courseInstanceId}', "
                "which does not exist."
            )
    for subgroup in req.subgroups:
        if subgroup.groupId not in group_ids:
            errors.append(
                f"Subgroup '{subgroup.name}' names group '{subgroup.groupId}', "
                "which does not exist."
            )
    for subject in req.subjects:
        if subject.katedraId is not None and subject.katedraId not in katedra_ids:
            errors.append(
                f"Subject '{subject.name}' names катедра '{subject.katedraId}', "
                "which does not exist."
            )
    for teacher in req.teachers:
        if teacher.katedraId is not None and teacher.katedraId not in katedra_ids:
            errors.append(
                f"Teacher '{teacher.name}' names катедра '{teacher.katedraId}', "
                "which does not exist."
            )

    # An offering is where almost every reference lives, and where a missing one
    # would silently drop sessions rather than fail loudly.
    for offering in req.offerings:
        where = f"Offering '{offering.id}'"
        if offering.subjectId not in subject_ids:
            errors.append(f"{where} names subject '{offering.subjectId}', which does not exist.")
        if offering.courseInstanceId not in course_ids:
            errors.append(
                f"{where} names course '{offering.courseInstanceId}', which does not exist."
            )
        for gid in offering.streamGroupIds:
            if gid not in group_ids:
                errors.append(f"{where} names group '{gid}' in its поток, which does not exist.")
        for tid in offering.exerciseTeacherIds:
            if tid not in teacher_ids:
                errors.append(f"{where} names teacher '{tid}', who does not exist.")
        if offering.leadTeacherId is not None and offering.leadTeacherId not in teacher_ids:
            errors.append(
                f"{where} names водещ преподавател '{offering.leadTeacherId}', who does not exist."
            )
        for unit in offering.exerciseUnitIds:
            known = subgroup_ids if offering.exerciseAudience.value == "subgroup" else group_ids
            if unit not in known:
                errors.append(
                    f"{where} names {offering.exerciseAudience.value} '{unit}' for its "
                    "упражнения, which does not exist."
                )

        # Consistency: hours without the things needed to place them would be a
        # silently unscheduled part of the учебен план.
        if offering.lectureHours:
            if not offering.leadTeacherId:
                errors.append(f"{where} has лекционни часа but no водещ преподавател.")
            if not offering.streamGroupIds:
                errors.append(f"{where} has лекционни часа but no groups in its поток.")
            if not offering.lectureRoomTypes:
                errors.append(f"{where} has лекционни часа but no allowed room type.")
        if offering.exerciseHours:
            if not offering.exerciseTeacherIds:
                errors.append(f"{where} has упражнителни часа but no candidate teachers.")
            if not offering.exerciseUnitIds:
                errors.append(f"{where} has упражнителни часа but no groups or подгрупи.")
            if not offering.exerciseRoomTypes:
                errors.append(f"{where} has упражнителни часа but no allowed room type.")
        if offering.spread.value in ("range", "block") and offering.window is None:
            errors.append(f"{where} is spread '{offering.spread.value}' but names no window.")

    # A teacher whose preferred slots have all been blocked is not an error: the
    # preference simply becomes unsatisfiable and gets paid for in the objective.
    # preferredRooms gets the same treatment, and deliberately so. It is
    # positional, so dropping a dangling id does shift the rooms below it up a
    # place -- but making that fatal would mean deleting one room invalidates the
    # whole problem until every teacher who ranked it has been hand-edited, and
    # deleting a room is an ordinary thing to do in the UI. The solver drops
    # unknown ids and re-ranks what is left. hardAvailability is left alone for
    # the same reason -- an entry naming a period that no longer exists narrows
    # nothing.
    del room_ids

    for kind, items in (
        ("role", req.roles),
        ("faculty", req.faculties),
        ("катедра", req.katedri),
        ("specialty", req.specialties),
        ("course", req.courseInstances),
        ("teacher", req.teachers),
        ("room", req.rooms),
        ("group", req.groups),
        ("subgroup", req.subgroups),
        ("subject", req.subjects),
        ("offering", req.offerings),
        ("slot", req.slots),
    ):
        ids = set()
        for item in items:
            if item.id in ids:
                errors.append(f"Duplicate {kind} id '{item.id}'.")
            ids.add(item.id)

    return errors


def build_hints(req: SolveRequest) -> List[Hint]:
    """Best-effort explanation of an INFEASIBLE (or timed-out) problem."""

    hints: List[Hint] = []
    ref = req.semester
    in_term = courses_in_term(req, ref)
    groups_by_id = {g.id: g for g in req.groups}
    subjects_by_id = {s.id: s for s in req.subjects}
    teacher_names = {t.id: t.name for t in req.teachers}
    slots = req.slots
    n_slots = len(slots)
    # What preferredSlots and hardAvailability are keyed on: this period, that
    # weekday, every week.
    weekday_key = {s.id: f"{s.day.lower()}-{s.period}" for s in slots}
    series = [s for s in build_series(req, ref) if s.count]

    def name_of(s) -> str:
        subject = subjects_by_id.get(s.offering.subjectId)
        label = subject.name if subject else s.offering.subjectId
        return f"{label} ({s.label})"

    if not n_slots:
        hints.append(
            Hint(
                title="No teachable periods",
                detail=(
                    "There is no dated period to schedule into: every period is "
                    "blocked, or no course is in term on any day of the grid."
                ),
            )
        )
        return hints

    # 0. A series whose groups are never in term together, or whose spread window
    # misses their term entirely. Its sessions have nowhere legal to go, which
    # reads as a flat INFEASIBLE without this.
    dates = sorted({s.date for s in slots})
    for s in series:
        usable = None
        missing = []
        for gid in s.group_ids:
            group = groups_by_id.get(gid)
            course = in_term.get(group.courseInstanceId) if group else None
            if course is None:
                missing.append(group.name if group else gid)
                continue
            teaching = {d for d in dates if course.teaches_on(d)}
            usable = teaching if usable is None else (usable & teaching)
        if missing:
            hints.append(
                Hint(
                    title=f"{name_of(s)} has groups out of term",
                    detail=(
                        f"{', '.join(missing)} are not in term this semester, so the "
                        "session has no day on which all of its groups are present."
                    ),
                )
            )
            continue
        window = s.offering.window
        if usable is not None and window is not None and s.offering.spread.value != "whole":
            usable = {d for d in usable if window.contains(d)}
        if usable is not None and not usable:
            hints.append(
                Hint(
                    title=f"{name_of(s)} has no usable dates",
                    detail=(
                        "Its groups are never all in term on the same teaching day"
                        + (" inside the period it is spread across." if window else ".")
                    ),
                )
            )

    # 1. A series with no room that both matches one of its accepted types and
    #    fits its students. This one is always fatal, so it goes early.
    for s in series:
        allowed = set(s.room_types)
        label = " or ".join(sorted(t.value for t in allowed))
        matching = [r for r in req.rooms if r.type in allowed]
        fitting = [r for r in matching if r.capacity >= s.head_count]
        if not matching:
            hints.append(
                Hint(
                    title=f"No {label} room exists",
                    detail=f"'{name_of(s)}' requires a {label} room and none is defined.",
                )
            )
        elif not fitting:
            largest = max(r.capacity for r in matching)
            hints.append(
                Hint(
                    title=f"{name_of(s)} does not fit any room",
                    detail=(
                        f"It needs a {label} room for {s.head_count} student(s); the "
                        f"largest such room holds {largest}."
                    ),
                )
            )

    # 2. Room-type contention. A series accepts a *set* of types, so counting per
    #    single type would miss the real bottleneck. This is Hall's condition
    #    restricted to the type-sets that actually appear in the data: for each
    #    such set S, every session whose accepted types all lie inside S can only
    #    be placed in rooms of a type in S, so their number may not exceed the
    #    placements those rooms offer. Also checked per distinct head-count, so a
    #    big поток competing for the one large аудитория is visible, not averaged
    #    away. A room that takes several groups at once offers that many
    #    placements per period.
    type_sets = {frozenset(s.room_types) for s in series}
    for type_set in sorted(type_sets, key=lambda ts: sorted(t.value for t in ts)):
        sizes = [
            s.head_count
            for s in series
            if set(s.room_types) <= type_set
            for _ in range(s.count)
        ]
        if not sizes:
            continue
        label = " or ".join(sorted(t.value for t in type_set))
        for threshold in sorted(set(sizes)):
            needed = sum(1 for s in sizes if s >= threshold)
            usable_rooms = [
                r for r in req.rooms if r.type in type_set and r.capacity >= threshold
            ]
            available = sum(r.maxConcurrentGroups for r in usable_rooms) * n_slots
            if needed > available:
                qualifier = "" if threshold == min(sizes) else f" for {threshold}+ students"
                hints.append(
                    Hint(
                        title=f"{label} rooms over-subscribed{qualifier}",
                        detail=(
                            f"{needed} session(s) need a {label} room{qualifier}, but "
                            f"{len(usable_rooms)} such room(s) offer {available} "
                            f"placement(s) across {n_slots} period(s)."
                        ),
                    )
                )
                break  # the tightest failing threshold is the informative one

    # 3. Teacher over-commitment. Same Hall-style reasoning as the rooms: a pool
    #    shares its load, so blaming one teacher for sessions their colleague
    #    could take would be wrong. For each candidate pool P present in the data,
    #    the sessions whose own pool fits inside P can only be taught by P's
    #    members. A водещ преподавател is a pool of one, so this covers лекции too.
    #    Availability narrows the count: a хон. преп. does not have n_slots to
    #    give.
    supply: Dict[str, int] = {}
    for teacher in req.teachers:
        if teacher.hardAvailability:
            wanted = set(teacher.hardAvailability)
            reachable = sum(1 for s in slots if weekday_key[s.id] in wanted)
        else:
            reachable = n_slots
        if teacher.maxWeeklyPeriods is not None:
            weeks = len({s.date.isocalendar()[:2] for s in slots})
            reachable = min(reachable, teacher.maxWeeklyPeriods * weeks)
        supply[teacher.id] = reachable

    pools = {frozenset(s.teacher_ids) for s in series}
    for pool in sorted(pools, key=lambda p: sorted(p)):
        load = sum(s.count for s in series if set(s.teacher_ids) <= pool)
        capacity = sum(supply.get(t, n_slots) for t in pool)
        if load > capacity:
            names = ", ".join(sorted(teacher_names.get(t, t) for t in pool))
            hints.append(
                Hint(
                    title=(
                        f"{names} is over-committed"
                        if len(pool) == 1
                        else f"{names} are collectively over-committed"
                    ),
                    detail=(
                        f"{load} session(s) can only be taught by {names}, who between "
                        f"them can reach {capacity} period(s) -- counting availability "
                        "windows and weekly caps."
                    ),
                )
            )

    # 4. A group with more sessions to attend than it has periods to attend them
    #    in. A подгрупа session busies its parent group, so it counts here; two
    #    подгрупи taught side by side count once, which makes this a lower bound
    #    and therefore safe as a necessary condition.
    per_group: Dict[str, int] = defaultdict(int)
    for s in series:
        for gid in s.group_ids:
            per_group[gid] += s.count
    for group in req.groups:
        load = per_group.get(group.id, 0)
        course = in_term.get(group.courseInstanceId)
        if course is None:
            continue
        teaching_days = len({s.date for s in slots if course.teaches_on(s.date)})
        ceiling = min(n_slots, teaching_days * course.maxPeriodsPerDay)
        if load > ceiling:
            hints.append(
                Hint(
                    title=f"{group.name} has too many sessions",
                    detail=(
                        f"{load} session(s) to attend, against {ceiling} available: "
                        f"{teaching_days} teaching day(s) x {course.maxPeriodsPerDay} "
                        "period(s) a day."
                    ),
                )
            )

    # 5. Total placements against total room-periods, ignoring type entirely.
    total_sessions = sum(s.count for s in series)
    total_capacity = sum(r.maxConcurrentGroups for r in req.rooms) * n_slots
    if total_sessions > total_capacity:
        hints.append(
            Hint(
                title="More sessions than room-periods",
                detail=(
                    f"{total_sessions} session(s) must fit into {len(req.rooms)} room(s) "
                    f"across {n_slots} period(s) = {total_capacity} placements."
                ),
            )
        )

    if not hints:
        hints.append(
            Hint(
                title="No single constraint class is over-subscribed",
                detail=(
                    "Every resource has enough capacity on its own; the conflict is in "
                    "the interaction between them. Try unblocking periods, adding a room, "
                    "raising the daily cap, or splitting a teacher's load."
                ),
            )
        )

    return hints
