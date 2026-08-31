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


def check_references(req: SolveRequest) -> List[str]:
    """Dangling ids are a data bug, not an infeasibility -- report them separately."""

    errors: List[str] = []
    teacher_ids = {t.id for t in req.teachers}
    group_ids = {g.id for g in req.groups}

    for subject in req.subjects:
        for tid in subject.teacherIds:
            if tid not in teacher_ids:
                errors.append(
                    f"Subject '{subject.name}' names teacher '{tid}', "
                    "who does not exist."
                )
        for gid in subject.groupIds:
            if gid not in group_ids:
                errors.append(
                    f"Subject '{subject.name}' names group '{gid}', which does not exist."
                )

    # A teacher whose preferred slots have all been blocked is not an error: the
    # preference simply becomes unsatisfiable and gets paid for in the objective.

    for kind, items in (
        ("teacher", req.teachers),
        ("room", req.rooms),
        ("group", req.groups),
        ("subject", req.subjects),
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
    n_slots = len(req.slots)
    groups_by_id = {g.id: g for g in req.groups}

    def head_count(subject) -> int:
        return sum(groups_by_id[g].size for g in subject.groupIds if g in groups_by_id)

    # 1. A subject with no room that both matches one of its accepted types and
    #    fits its students. This one is always fatal, so it goes first.
    for subject in req.subjects:
        if subject.sessionsPerWeek == 0:
            continue
        size = head_count(subject)
        allowed = set(subject.allowedRoomTypes)
        label = " or ".join(sorted(t.value for t in allowed))
        matching = [r for r in req.rooms if r.type in allowed]
        fitting = [r for r in matching if r.capacity >= size]
        if not matching:
            hints.append(
                Hint(
                    title=f"No {label} room exists",
                    detail=(
                        f"'{subject.name}' requires a {label} room and none is defined."
                    ),
                )
            )
        elif not fitting:
            largest = max(r.capacity for r in matching)
            hints.append(
                Hint(
                    title=f"{subject.name} does not fit any room",
                    detail=(
                        f"It needs a {label} room for {size} student(s); the largest "
                        f"such room holds {largest}."
                    ),
                )
            )

    # 2. Room-type contention. A subject now accepts a *set* of types, so counting
    #    per single type would miss the real bottleneck. This is Hall's condition
    #    restricted to the type-sets that actually appear in the data: for each such
    #    set S, every session whose accepted types all lie inside S can only be
    #    placed in rooms of a type in S, so their number may not exceed the
    #    placements those rooms offer. Also checked per distinct head-count, so a big
    #    session competing for the one large room is visible, not averaged away.
    type_sets = {
        frozenset(subject.allowedRoomTypes)
        for subject in req.subjects
        if subject.sessionsPerWeek
    }
    for type_set in sorted(type_sets, key=lambda ts: sorted(t.value for t in ts)):
        sizes = [
            head_count(subject)
            for subject in req.subjects
            if set(subject.allowedRoomTypes) <= type_set
            for _ in range(subject.sessionsPerWeek)
        ]
        if not sizes:
            continue
        label = " or ".join(sorted(t.value for t in type_set))
        for threshold in sorted(set(sizes)):
            needed = sum(1 for s in sizes if s >= threshold)
            usable = [
                r for r in req.rooms if r.type in type_set and r.capacity >= threshold
            ]
            available = len(usable) * n_slots
            if needed > available:
                qualifier = (
                    "" if threshold == min(sizes) else f" for {threshold}+ students"
                )
                hints.append(
                    Hint(
                        title=f"{label} rooms over-subscribed{qualifier}",
                        detail=(
                            f"{needed} session(s) need a {label} room{qualifier}, but "
                            f"{len(usable)} such room(s) x {n_slots} slot(s) = "
                            f"{available} placements are available."
                        ),
                    )
                )
                break  # the tightest failing threshold is the informative one

    # 3. Teacher over-commitment. Same Hall-style reasoning as the rooms: a pool
    #    shares its load, so blaming one teacher for sessions their colleague could
    #    take would be wrong. For each candidate pool P present in the data, the
    #    sessions whose own pool fits inside P can only be taught by P's members.
    teacher_names = {t.id: t.name for t in req.teachers}
    pools = {
        frozenset(subject.teacherIds)
        for subject in req.subjects
        if subject.sessionsPerWeek
    }
    for pool in sorted(pools, key=lambda p: sorted(p)):
        load = sum(
            subject.sessionsPerWeek
            for subject in req.subjects
            if set(subject.teacherIds) <= pool
        )
        capacity = len(pool) * n_slots
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
                        f"them have {len(pool)} teacher(s) x {n_slots} slot(s) = "
                        f"{capacity} teaching slot(s)."
                    ),
                )
            )

    # 4. A group with more sessions to attend than there are slots.
    per_group: Dict[str, int] = defaultdict(int)
    for subject in req.subjects:
        for gid in subject.groupIds:
            per_group[gid] += subject.sessionsPerWeek
    for group in req.groups:
        load = per_group.get(group.id, 0)
        if load > n_slots:
            hints.append(
                Hint(
                    title=f"{group.name} has too many sessions",
                    detail=(
                        f"{load} session(s) to attend across only {n_slots} available "
                        "slot(s)."
                    ),
                )
            )

    # 5. Total placements against total room-slots, ignoring type entirely.
    total_sessions = sum(s.sessionsPerWeek for s in req.subjects)
    total_capacity = len(req.rooms) * n_slots
    if total_sessions > total_capacity:
        hints.append(
            Hint(
                title="More sessions than room-slots",
                detail=(
                    f"{total_sessions} session(s) must fit into {len(req.rooms)} room(s) "
                    f"x {n_slots} slot(s) = {total_capacity} placements."
                ),
            )
        )

    if not hints:
        hints.append(
            Hint(
                title="No single constraint class is over-subscribed",
                detail=(
                    "Every resource has enough capacity on its own; the conflict is in "
                    "the interaction between them. Try relaxing blocked slots, adding a "
                    "room, or splitting a teacher's load."
                ),
            )
        )

    return hints
