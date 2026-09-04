"""Wire format for the solver service.

Everything the solver needs arrives in a single POST body: there is no database
and no server-side session. The frontend owns the problem and sends all of it.

The model is the one Академия на МВР actually uses. Above a group sits
Faculty -> Specialty -> CourseInstance, and below it sits Subgroup; a разписание
is issued per CourseInstance (курс + семестър + специалност), which is what the
renderer in `razpisanie.py` emits. Teaching runs on a six-day week in periods of
two academic hours; the обедна почивка is simply a stretch of clock with no period
defined across it.
"""

from datetime import date as date_
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# What a solve is given unless the caller says otherwise: nothing -- no deadline
# at all. CP-SAT runs until it finishes or proves optimality.
#
# This is a deliberate change from the 30s default this service shipped with. A
# faculty-sized semester now takes about ninety seconds just to find its *first*
# legal timetable, so any budget short enough to feel like a demo returns
# UNKNOWN with nothing placed -- which is a worse answer than a slow one. An
# unlimited run always comes back with the best timetable it found.
#
# The cost is real and worth stating: the HTTP request stays open for the whole
# run, holding a worker, and nothing short of restarting the service will stop
# it. Set a limit in the Settings dialog when that matters.
DEFAULT_SOLVE_SECONDS = None

# The budget the Settings dialog offers as its "quick look" preset, and what the
# small example is comfortably inside.
DEMO_SOLVE_SECONDS = 30


class RoomType(str, Enum):
    """Room kinds an offering can require, named as the academy names them.

    A session may only be placed in a room whose type appears in the offering's
    allowed types *for that activity kind* -- лекции and упражнения of the same
    subject routinely want different rooms.
    """

    zala = "зала"                              # аудитория / учебна зала
    malka_zala = "малка зала"                  # seminar room, one group or subgroup
    kompyutarna_zala = "компютърна зала"
    strelbishte = "стрелбище"
    poligon = "полигон"                        # outdoor tactical training ground
    sporten_kompleks = "спортен комплекс"
    trenazhorna_zala = "тренажорна зала"       # gym, for ЛЗФП


class Degree(str, Enum):
    """ОКС -- образователно-квалификационна степен."""

    bakalavur = "бакалавър"
    magistur = "магистър"
    doktor = "доктор"


class StudyForm(str, Enum):
    """Форма на обучение. `zadochna` is what SpreadMode.block exists for."""

    redovna = "редовна"
    zadochna = "задочна"


class StudentKind(str, Enum):
    """Курсанти are cadets on the state order; студенти are civilians. The two
    differ in whether Saturday teaching is normal, which is data, not code."""

    kursant = "курсант"
    student = "студент"


class NonTeachingKind(str, Enum):
    """Why a stretch of the term carries no teaching.

    All four are equally unusable for scheduling; they are kept distinct because
    the разписание prints them separately and section II counts them apart.
    """

    vakantsiya = "ваканция"
    stazh = "стаж"
    izpitna_sesiya = "изпитна сесия"
    praznik = "празник"


class ExamSessionKind(str, Enum):
    """Which exam session an `изпитна сесия` period is. Section II of the
    разписание lists all three separately."""

    redovna = "редовна"
    popravitelna = "поправителна"
    likvidatsionna = "ликвидационна"


class ActivityKind(str, Enum):
    """What a session *is*. The разписание grid marks cells with the first letter."""

    lektsiya = "лекция"
    uprazhnenie = "упражнение"
    praktika = "практика"


# The marker each activity gets in a разписание grid cell.
ACTIVITY_MARKER = {
    ActivityKind.lektsiya: "л",
    ActivityKind.uprazhnenie: "у",
    ActivityKind.praktika: "п",
}


class ControlForm(str, Enum):
    """Форма на контрол, printed in section III beside the exam date."""

    izpit = "изпит"
    kto = "КТО"          # курсова текуща оценка
    zachet = "зачет"


class Audience(str, Enum):
    """Who attends an offering's упражнения: whole groups, or подгрупи."""

    group = "group"
    subgroup = "subgroup"


class Role(BaseModel):
    """An academic rank, as data rather than as a fixed enum.

    Everything else the solver reasons about is edited on the Data setup screen;
    ranks used to be the exception, hardcoded here and mirrored by hand in the
    frontend. They are now an ordinary entity, so a faculty can name the ranks it
    actually has and decide what outranks what.
    """

    # Stable, and what Teacher.role points at -- so renaming a rank is free.
    id: str
    # Full label for the dropdown and the roles table, e.g. 'проф. — Professor'.
    name: str
    # Narrow-column label for the teachers table and the ladder, e.g. 'проф.'.
    short: str
    # Priority of the rank, higher wins. This is a *tier key*, not a multiplier:
    # the solver optimises one tier at a time, top down (see timetable_solver.py
    # step 6), so what matters is the ordering and which ranks share a value.
    weight: int = Field(ge=0, le=100)


# The ranks of Академия на МВР, used when a request names no roles of its own and
# as the starting set for a blank project in the UI. Хонорувани преподаватели sit
# at the bottom: they are external, and what actually protects their timetable is
# Teacher.hardAvailability, which is hard and outranks every preference.
DEFAULT_ROLES = [
    Role(id="professor", name="проф. — Professor", short="проф.", weight=7),
    Role(id="associate_professor", name="доц. — Assoc. Professor", short="доц.", weight=6),
    Role(id="chief_assistant", name="гл. ас. — Chief Assistant", short="гл. ас.", weight=5),
    Role(id="assistant", name="ас. — Assistant", short="ас.", weight=4),
    Role(id="senior_lecturer", name="ст. преп. — Senior Lecturer", short="ст. преп.", weight=3),
    Role(id="lecturer", name="преп. — Lecturer", short="преп.", weight=2),
    Role(id="honorary_lecturer", name="хон. преп. — Honorary Lecturer", short="хон. преп.", weight=1),
]

# A teacher with no stated rank shares the bottom tier. This is what keeps the
# feature backwards compatible: a problem with no roles at all yields exactly one
# tier, which is the single-objective behaviour that existed before the ladder.
UNRANKED_WEIGHT = 1


class Slot(BaseModel):
    """One dated teaching period, e.g. id="2025-09-15-1", date=2025-09-15, period=1.

    Slots are generated by the frontend by expanding its weekday x period template
    across the semester being scheduled. Slots the user has blocked -- and dates
    that fall in a non-teaching period -- are simply omitted from the request, so
    the solver never needs to know about availability rules: a missing slot is an
    unusable slot. `day` is kept alongside `date` because the weekday is what the
    UI labels columns with and what `blockedSlots` is keyed on.

    A period is a teaching block of two academic hours, and it is what the solver
    places into -- there is no finer unit. The обедна почивка needs no rule of its
    own: it is the stretch of clock between two periods that no period covers, so
    nothing can be scheduled across it.
    """

    id: str
    date: date_
    day: str
    period: int


class SemesterRef(BaseModel):
    """Which semester a request is about.

    Identity is the academic year plus the index within it; the *dates* live on
    the CourseInstance, because year 1 routinely runs the same semester on a
    different calendar from years 2-4 of the same специалност.
    """

    academicYear: str            # "2025/2026"
    index: int = Field(ge=1, le=2)

    @property
    def key(self) -> str:
        return f"{self.academicYear}-{self.index}"


class DateRange(BaseModel):
    """A closed interval of dates. Used for spread windows."""

    start: date_
    end: date_
    label: Optional[str] = None

    def contains(self, day: date_) -> bool:
        return self.start <= day <= self.end


class NonTeachingPeriod(BaseModel):
    """A stretch of the term with no teaching in it, and why.

    Replaces the old untyped `breaks`. Every kind is equally unusable -- no
    session is ever placed inside one, and they do not count towards the teaching
    weeks the even spread is measured against -- but the разписание has to name
    them, and section II counts each exam session separately.
    """

    start: date_
    end: date_
    kind: NonTeachingKind
    # Only meaningful when kind is `изпитна сесия`; section II keys on it.
    session: Optional[ExamSessionKind] = None
    label: Optional[str] = None

    def contains(self, day: date_) -> bool:
        return self.start <= day <= self.end


class Faculty(BaseModel):
    """Факултет: Полиция, ПБЗН."""

    id: str
    name: str


class Katedra(BaseModel):
    """A department. Owns subjects and teachers; printed on the разписание."""

    id: str
    name: str
    facultyId: Optional[str] = None


class Specialty(BaseModel):
    """Специалност -- ППООР, Гранична полиция, ... -- with its ОКС and form."""

    id: str
    facultyId: str
    code: str                     # 'ППООР'
    name: str
    degree: Degree = Degree.bakalavur
    form: StudyForm = StudyForm.redovna
    studentKind: StudentKind = StudentKind.kursant
    durationYears: int = Field(default=4, ge=1, le=6)


class CourseInstance(BaseModel):
    """One курс of one специалност in one semester: the scheduling unit.

    This is what a printed разписание is emitted for, and it is where the term
    dates live -- they moved off Group because a specialty's first year regularly
    starts and ends on different dates from its later years.
    """

    id: str
    specialtyId: str
    year: int = Field(ge=1, le=5)
    academicYear: str
    semester: int = Field(ge=1, le=2)
    start: date_
    end: date_
    nonTeaching: List[NonTeachingPeriod] = Field(default_factory=list)
    # Hard cap on how many periods a group of this course may be taught in one day.
    maxPeriodsPerDay: int = Field(default=5, ge=1, le=12)

    # Header of the printed разписание. Purely descriptive: the solver never
    # reads these, but the document is not the document without them.
    regNumber: Optional[str] = None
    approvedBy: Optional[str] = None            # 'ДЕКАН на факултет "Полиция" ...'
    approvalDate: Optional[date_] = None
    administrativenOtgovornik: Optional[str] = None

    def matches(self, ref: SemesterRef) -> bool:
        return self.academicYear == ref.academicYear and self.semester == ref.index

    def teaches_on(self, day: date_) -> bool:
        if not (self.start <= day <= self.end):
            return False
        return not any(p.contains(day) for p in self.nonTeaching)


class Teacher(BaseModel):
    id: str
    name: str
    katedraId: Optional[str] = None
    # Soft: scheduling outside these periods is penalised, never forbidden.
    # Weekday-keyed ('mon-1'), so a preference means that period every week. An
    # empty list means "no preference", which can never be violated.
    preferredSlots: List[str] = Field(default_factory=list)
    # HARD, and the reason it exists: хонорувани преподаватели are external and
    # genuinely cannot attend outside their window. Same 'mon-1-2' key shape as
    # preferredSlots, and empty means "always available". A literal is never
    # created for a period outside this list, so it cannot be traded away at any
    # price -- unlike a preference, an impossible availability is INFEASIBLE.
    hardAvailability: List[str] = Field(default_factory=list)
    # Hard cap on periods taught in one ISO week. None means uncapped.
    maxWeeklyPeriods: Optional[int] = Field(default=None, ge=0, le=100)
    # Soft, and *ranked*: index 0 is the room this teacher most wants, and the
    # cost of a placement is the room's position in the list. A room that is not
    # listed at all costs len(list) -- worse than every ranked choice, but never
    # infinitely worse. Empty means "no preference" and can never be violated.
    preferredRooms: List[str] = Field(default_factory=list)
    # Id of a Role in the request. Optional: absent, or naming a role that is not
    # there, means unranked -- see UNRANKED_WEIGHT.
    role: Optional[str] = None
    # Overrides the weight the role would imply. This is the only way to lift one
    # person out of their rank's tier -- give an assistant a 7 and they negotiate
    # alongside the professors.
    priorityWeight: Optional[int] = Field(default=None, ge=0, le=100)


def effective_weight(teacher: Teacher, roles_by_id: Dict[str, Role]) -> int:
    """Priority tier key for a teacher: explicit override, else rank, else bottom.

    A role id naming no role falls to the bottom tier rather than raising: the UI
    cascades on delete so this should not reach the wire, and quietly demoting a
    teacher is a better failure than refusing to schedule anybody.
    """
    if teacher.priorityWeight is not None:
        return teacher.priorityWeight
    if teacher.role is not None:
        role = roles_by_id.get(teacher.role)
        if role is not None:
            return role.weight
    return UNRANKED_WEIGHT


class Room(BaseModel):
    id: str
    name: str
    capacity: int = Field(ge=0)
    type: RoomType
    building: Optional[str] = None
    # How many sessions may share this room in one period. 1 for everything by
    # default, and emphatically 1 for стрелбище and малка зала, which take one
    # group or подгрупа at a time. Above 1 it becomes a counting constraint.
    maxConcurrentGroups: int = Field(default=1, ge=1, le=10)


class Group(BaseModel):
    """Учебна група. Belongs to exactly one CourseInstance, which owns its dates."""

    id: str
    name: str
    size: int = Field(ge=0)
    courseInstanceId: str


class Subgroup(BaseModel):
    """Подгрупа: a Group split for стрелкова подготовка, ЛЗФП or чуждоезиково
    обучение -- language подгрупи split by level, so sizes are uneven on purpose.

    A subgroup has its own size and its own busy calendar. Two subgroups of the
    same group may be taught at the same time (that is the whole point of the
    split); a group-level session excludes every one of its subgroups.
    """

    id: str
    groupId: str
    name: str
    size: int = Field(ge=0)


class Subject(BaseModel):
    """A catalogue entry. What is *taught* is a SubjectOffering."""

    id: str
    code: str                     # 'ОИД', 'УППС', 'ЛЗФП', 'СП', 'АЕ'
    name: str
    katedraId: Optional[str] = None


class SpreadMode(str, Enum):
    """Where inside the semester an offering's sessions are spread."""

    whole = "whole"    # evenly across every teaching week of the semester
    range = "range"    # evenly across a sub-period chosen inside it
    # Saturate a window instead of balancing weeks. Задочно compresses a whole
    # semester into a 2-3 week присъствен period, where an even weekly spread is
    # simply the wrong shape.
    block = "block"


class SubjectOffering(BaseModel):
    """One subject as taught to one курс: the хорариум and everything around it.

    A учебен план gives hours, not session counts -- '30/15' is 30 лекционни and
    15 упражнителни часа -- so this carries hours and the solver divides. Sessions
    are generated per activity kind, and the two kinds differ in almost every
    respect: who attends, who teaches, and which rooms will do.
    """

    id: str
    subjectId: str
    courseInstanceId: str

    # Хорариум. Either may be 0; an offering with both 0 contributes nothing.
    lectureHours: int = Field(default=0, ge=0, le=600)
    exerciseHours: int = Field(default=0, ge=0, le=600)
    # Academic hours in one session. One period, so 2 -- but a faculty that blocks
    # four hours of полигон at a time can say so.
    hoursPerSession: int = Field(default=2, ge=1, le=12)
    controlForm: ControlForm = ControlForm.izpit

    # Allowed room types per activity kind. Required only for a kind that runs.
    lectureRoomTypes: List[RoomType] = Field(default_factory=list)
    exerciseRoomTypes: List[RoomType] = Field(default_factory=list)

    # The ПОТОК: the groups merged for this offering's lectures. Derived data,
    # modelled as a join here rather than as an attribute of the course, because
    # общообразователните дисциплини merge groups across специалности and
    # специалните do not. Exercise sessions ignore it entirely.
    streamGroupIds: List[str] = Field(default_factory=list)
    # Водещ преподавател. A лекция has one named lecturer, not a pool.
    leadTeacherId: Optional[str] = None

    # Упражнения keep the pool-pick behaviour: exactly one of these takes each
    # session, chosen by the solver, independently per session.
    exerciseTeacherIds: List[str] = Field(default_factory=list)
    exerciseAudience: Audience = Audience.group
    # Group ids when exerciseAudience is `group`, subgroup ids when `subgroup`.
    # Each unit gets its own full exerciseHours -- the хорариум is per student.
    exerciseUnitIds: List[str] = Field(default_factory=list)

    spread: SpreadMode = SpreadMode.whole
    # Required when spread is `range` or `block`; ignored for `whole`.
    window: Optional[DateRange] = None
    # Section III of the разписание.
    examDate: Optional[date_] = None

    def sessions_for(self, kind: ActivityKind) -> int:
        """How many sessions one audience unit gets of this activity kind.

        Ceil, not floor: rounding down would silently under-deliver the хорариум,
        and a leftover hour is a smaller lie than a missing one.
        """
        hours = self.lectureHours if kind is ActivityKind.lektsiya else self.exerciseHours
        if hours <= 0:
            return 0
        return -(-hours // self.hoursPerSession)

    def room_types_for(self, kind: ActivityKind) -> List[RoomType]:
        return (
            self.lectureRoomTypes
            if kind is ActivityKind.lektsiya
            else self.exerciseRoomTypes
        )


class SearchParams(BaseModel):
    """CP-SAT engine parameters exposed to the UI.

    This model *is* the whitelist: there is no passthrough of arbitrary solver
    proto fields. `None` means "leave CP-SAT's own default alone", which is safer
    than hardcoding today's defaults -- they can shift between OR-Tools versions.

    None of these change which timetables are legal; they change how hard, and how
    repeatably, the solver works to find one.
    """

    numWorkers: int = Field(default=8, ge=1, le=16)
    randomSeed: int = Field(default=0, ge=0)
    presolve: bool = True
    symmetryLevel: Optional[int] = Field(default=None, ge=0, le=4)
    linearizationLevel: Optional[int] = Field(default=None, ge=0, le=2)


class SolveRequest(BaseModel):
    # Which semester this solve is for. Everything else is filtered through it:
    # which course instances are in term, which offerings run, and how many
    # sessions each has. One solve covers *every* course instance of that
    # semester, because rooms and teachers are shared across курсове and solving
    # them one at a time would double-book both.
    semester: SemesterRef
    # Every dated period on offer. This is the whole grid: a period the user
    # blocked, or one that falls in a non-teaching stretch, is simply not here.
    slots: List[Slot]

    # Defaults to the built-in ranks, so a caller that never heard of roles still
    # gets the same tiers it always did.
    roles: List[Role] = Field(default_factory=lambda: list(DEFAULT_ROLES))

    faculties: List[Faculty] = Field(default_factory=list)
    katedri: List[Katedra] = Field(default_factory=list)
    specialties: List[Specialty] = Field(default_factory=list)
    courseInstances: List[CourseInstance] = Field(default_factory=list)
    teachers: List[Teacher]
    rooms: List[Room]
    groups: List[Group]
    subgroups: List[Subgroup] = Field(default_factory=list)
    subjects: List[Subject]
    offerings: List[SubjectOffering] = Field(default_factory=list)

    # None -- the default -- means *no* limit: CP-SAT is given no deadline and
    # runs until it finishes or proves optimality. There is deliberately no
    # ceiling either; proving a faculty-sized timetable optimal takes longer than
    # any cap worth setting.
    #
    # Given a number, the best solution found so far is returned on expiry and
    # the status says whether it was proven optimal.
    maxTimeInSeconds: Optional[float] = Field(default=DEFAULT_SOLVE_SECONDS, gt=0.0)
    # Soft-constraint weights. Preference outranks gaps by an order of magnitude
    # so a compact day is never bought at the price of a teacher preference.
    preferenceWeight: int = Field(default=10, ge=0, le=1000)
    # Cost per *rank step* away from a teacher's first-choice room. Below the slot
    # weight on purpose: when the two preferences cannot both be met, the slot is
    # the one worth keeping.
    roomPreferenceWeight: int = Field(default=5, ge=0, le=1000)
    gapWeight: int = Field(default=1, ge=0, le=1000)
    # Take the first legal timetable instead of the best one. The gap between the
    # two is the whole value of optimising, so it is worth being able to see it.
    stopAfterFirstSolution: bool = False
    # Our own symmetry-breaking constraint (see timetable_solver.py step 4).
    # Switchable because CP-SAT's presolve finds symmetry on its own, and whether
    # ours still earns its place is a question this PoC should be able to answer.
    useSymmetryBreaking: bool = True
    search: SearchParams = Field(default_factory=SearchParams)


class Assignment(BaseModel):
    offeringId: str
    subjectId: str
    subjectCode: str
    subjectName: str
    activity: ActivityKind
    # The dated period this session occupies, and its number on the day. Both,
    # because the grid keys cells on the id and labels rows by the number.
    slot: str
    period: int
    # The real date this session lands on, so the multi-week grid can place it
    # without re-deriving anything from a slot id.
    date: date_
    day: str
    roomId: str
    roomName: str
    teacherId: str
    teacherName: str
    # Every group busy for this session. For a лекция that is the whole поток;
    # for a подгрупа упражнение it is the subgroup's parent group.
    groupIds: List[str]
    groupNames: List[str]
    # Set only for a session taught to one подгрупа.
    subgroupId: Optional[str] = None
    subgroupName: Optional[str] = None
    # True when this session missed its teacher's preferred periods or rooms.
    softViolated: bool = False
    softReason: Optional[str] = None
    # Position of the assigned room in the teacher's ranked list: 0 is their first
    # choice, len(list) means the room was not on it. None when they ranked none.
    roomPreferenceRank: Optional[int] = None


class TierResult(BaseModel):
    """What one rung of the priority ladder achieved.

    Without this the ladder is invisible: a single objective number cannot say
    which rank had to give something up, nor whether a rung ran out of time
    before it had finished bargaining.
    """

    weight: int
    # Short labels of the ranks sharing this weight, for the UI to render as-is.
    # Empty when the tier is unranked.
    roles: List[str] = Field(default_factory=list)
    teacherCount: int
    # Weighted slot+room penalty this tier settled for.
    penalty: int
    # OPTIMAL means the tier could do no better; FEASIBLE means it ran out of
    # time and the tiers below were frozen against a possibly-improvable number.
    status: str
    solveTimeSeconds: float


class Stats(BaseModel):
    status: str
    solveTimeSeconds: float
    # Total weighted penalty across every tier plus gaps -- NOT CP-SAT's own
    # ObjectiveValue(), which after the ladder is only the final (gap) phase.
    objectiveValue: Optional[float] = None
    # Only meaningful for a single-objective solve; the ladder leaves it None,
    # because a bound on the last phase is not a bound on the whole.
    bestObjectiveBound: Optional[float] = None
    numSessions: int
    numPlaced: int
    # Dated periods on offer -- what the solver places into.
    numSlots: int
    numBooleanVariables: int
    preferenceViolations: int
    roomPreferencePenalty: int = 0
    gapPenalty: int
    # Top-down, one entry per distinct teacher weight present in the problem.
    tiers: List[TierResult] = Field(default_factory=list)


class Hint(BaseModel):
    """One reason the problem looks over-subscribed. Title + detail mirrors the
    failure panel in the UI design."""

    title: str
    detail: str


class Validation(BaseModel):
    """Independent re-check of the solver's own output (see
    `timetable_solver.validate_assignments`)."""

    ok: bool
    errors: List[str] = Field(default_factory=list)


class SettingsUsed(BaseModel):
    """Echo of the settings a result was actually produced with.

    Without this the UI would show the *current* settings next to a result that
    was solved under the previous ones.
    """

    maxTimeInSeconds: Optional[float]
    preferenceWeight: int
    roomPreferenceWeight: int
    gapWeight: int
    stopAfterFirstSolution: bool
    useSymmetryBreaking: bool
    search: SearchParams


class SolveResponse(BaseModel):
    # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN | MODEL_INVALID
    status: str
    message: str
    assignments: List[Assignment] = Field(default_factory=list)
    stats: Optional[Stats] = None
    validation: Optional[Validation] = None
    hints: List[Hint] = Field(default_factory=list)
    settingsUsed: Optional[SettingsUsed] = None


# ---------------------------------------------------------------------------
# The разписание document. Built by `razpisanie.py` from a request plus its
# response; the JSON above stays the machine-readable form and this is a
# renderer on top of it.
# ---------------------------------------------------------------------------


class RazpisanieHeader(BaseModel):
    facultyName: str
    regNumber: Optional[str] = None
    approvedBy: Optional[str] = None
    approvalDate: Optional[date_] = None
    specialtyCode: str
    specialtyName: str
    degree: Degree
    form: StudyForm
    studentKind: StudentKind
    year: int
    semester: int
    start: date_
    end: date_
    administrativenOtgovornik: Optional[str] = None


class RazpisanieSubject(BaseModel):
    """One numbered line of section I. `number` is what the grid cells print."""

    number: int
    code: str
    name: str
    lectureHours: int
    exerciseHours: int
    katedra: Optional[str] = None
    leadTeacher: Optional[str] = None
    exerciseTeachers: List[str] = Field(default_factory=list)
    rooms: List[str] = Field(default_factory=list)
    controlForm: ControlForm


class RazpisanieTimeBlock(BaseModel):
    """One line of section II -- разпределение на учебното време."""

    label: str                  # 'занятия' | 'редовна сесия' | ...
    start: date_
    end: date_
    weeks: int


class RazpisanieExam(BaseModel):
    """One line of section III."""

    number: int
    code: str
    name: str
    controlForm: ControlForm
    examDate: Optional[date_] = None


class RazpisanieCell(BaseModel):
    """One (day, period) cell of the month grid. Empty cells are simply absent."""

    date: date_
    period: int
    # Usually one entry; more than one when подгрупи run in parallel.
    entries: List[str] = Field(default_factory=list)   # '7 у', '3 л'


class RazpisanieMonth(BaseModel):
    label: str                  # 'септември 2025'
    year: int
    month: int
    dates: List[date_]
    cells: List[RazpisanieCell] = Field(default_factory=list)


class Razpisanie(BaseModel):
    courseInstanceId: str
    header: RazpisanieHeader
    subjects: List[RazpisanieSubject] = Field(default_factory=list)
    timeBlocks: List[RazpisanieTimeBlock] = Field(default_factory=list)
    exams: List[RazpisanieExam] = Field(default_factory=list)
    # The grid's columns: 1..periods, with their clock times.
    periods: List[int] = Field(default_factory=list)
    periodTimes: Dict[int, str] = Field(default_factory=dict)
    months: List[RazpisanieMonth] = Field(default_factory=list)


class RazpisanieRequest(BaseModel):
    """POST /razpisanie -- the problem, its answer, and which курс to print."""

    request: SolveRequest
    response: SolveResponse
    courseInstanceId: str
    # Clock times per period, for the grid's row labels. The solver never sees
    # these; they live in the frontend's slotConfig, so they ride along here.
    periodTimes: Dict[int, str] = Field(default_factory=dict)
