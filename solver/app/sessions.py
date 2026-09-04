"""Expanding a учебен план into session series.

A `SubjectOffering` carries a хорариум -- hours, not sessions -- and describes
two quite different activities at once. Turning that into "N interchangeable
sessions, attended by these groups, taught by one of these teachers, in a room of
one of these types" is the step both the solver and the diagnostics need, and it
is the only place that knows how a хорариум becomes placements.

A *series* is the unit of interchangeability: one activity of one offering for
one audience. The лекции of an offering are one series (the whole поток attends
together); its упражнения are one series *per unit*, because the хорариум is per
student and every group or подгрупа gets the full count.
"""

from typing import Dict, List, Optional

from .models import (
    ActivityKind,
    CourseInstance,
    Group,
    RoomType,
    SemesterRef,
    SolveRequest,
    Subgroup,
    SubjectOffering,
)


class Series:
    """One offering's sessions of one activity kind for one audience.

    `group_ids` is who is *busy*, which for a подгрупа упражнение is the parent
    group -- the subgroup is named separately in `subgroup_id`, because the two
    are constrained differently: a group-level session excludes every subgroup of
    that group, while two subgroups may run side by side.
    """

    __slots__ = (
        "key", "offering", "activity", "unit_id", "subgroup_id", "group_ids",
        "head_count", "teacher_ids", "room_types", "count", "label",
    )

    def __init__(
        self,
        key: str,
        offering: SubjectOffering,
        activity: ActivityKind,
        unit_id: Optional[str],
        subgroup_id: Optional[str],
        group_ids: List[str],
        head_count: int,
        teacher_ids: List[str],
        room_types: List[RoomType],
        count: int,
        label: str,
    ) -> None:
        self.key = key
        self.offering = offering
        self.activity = activity
        self.unit_id = unit_id
        self.subgroup_id = subgroup_id
        self.group_ids = group_ids
        self.head_count = head_count
        self.teacher_ids = teacher_ids
        self.room_types = room_types
        self.count = count
        self.label = label


def courses_in_term(req: SolveRequest, ref: SemesterRef) -> Dict[str, CourseInstance]:
    """The course instances this solve is about, by id.

    A course with no entry for `ref` is not in term and takes no part -- which is
    how a request carrying all four years of a specialty still solves one
    semester at a time.
    """
    return {ci.id: ci for ci in req.courseInstances if ci.matches(ref)}


def build_series(req: SolveRequest, ref: SemesterRef) -> List[Series]:
    """Every session series this semester runs, in a stable order.

    Offerings whose CourseInstance is not in term this semester contribute
    nothing. An offering that names a group which is out of term is *not* filtered
    here: it goes through with an audience the calendar cannot satisfy, so the
    solve fails and `diagnostics.build_hints` names the group. Silently dropping
    it would schedule a лекция the поток never sees.
    """
    in_term = courses_in_term(req, ref)
    groups_by_id: Dict[str, Group] = {g.id: g for g in req.groups}
    subgroups_by_id: Dict[str, Subgroup] = {sg.id: sg for sg in req.subgroups}

    out: List[Series] = []
    for offering in req.offerings:
        if offering.courseInstanceId not in in_term:
            continue

        lectures = offering.sessions_for(ActivityKind.lektsiya)
        if lectures and offering.leadTeacherId:
            group_ids = list(offering.streamGroupIds)
            out.append(
                Series(
                    key=f"{offering.id}:л",
                    offering=offering,
                    activity=ActivityKind.lektsiya,
                    unit_id=None,
                    subgroup_id=None,
                    group_ids=group_ids,
                    # The whole поток is in the room at once.
                    head_count=sum(
                        groups_by_id[g].size for g in group_ids if g in groups_by_id
                    ),
                    teacher_ids=[offering.leadTeacherId],
                    room_types=list(offering.lectureRoomTypes),
                    count=lectures,
                    label="лекция",
                )
            )

        exercises = offering.sessions_for(ActivityKind.uprazhnenie)
        if exercises and offering.exerciseTeacherIds:
            for unit_id in offering.exerciseUnitIds:
                subgroup = subgroups_by_id.get(unit_id)
                if subgroup is not None:
                    group_ids = [subgroup.groupId]
                    head_count = subgroup.size
                    subgroup_id: Optional[str] = subgroup.id
                else:
                    group_ids = [unit_id]
                    head_count = groups_by_id[unit_id].size if unit_id in groups_by_id else 0
                    subgroup_id = None
                out.append(
                    Series(
                        key=f"{offering.id}:у:{unit_id}",
                        offering=offering,
                        activity=ActivityKind.uprazhnenie,
                        unit_id=unit_id,
                        subgroup_id=subgroup_id,
                        group_ids=group_ids,
                        head_count=head_count,
                        teacher_ids=list(offering.exerciseTeacherIds),
                        room_types=list(offering.exerciseRoomTypes),
                        count=exercises,
                        label="упражнение",
                    )
                )
    return out

