/** Domain model. Mirrors solver/app/models.py -- this is the whole wire format.
 *
 *  The hierarchy is the academy's: Faculty -> Specialty -> CourseInstance ->
 *  Group -> Subgroup. A разписание is issued per CourseInstance, and teaching is
 *  placed in periods of two academic hours. */

export type RoomType =
  | 'зала'
  | 'малка зала'
  | 'компютърна зала'
  | 'стрелбище'
  | 'полигон'
  | 'спортен комплекс'
  | 'тренажорна зала';

/** ОКС. */
export type Degree = 'бакалавър' | 'магистър' | 'доктор';
export type StudyForm = 'редовна' | 'задочна';
export type StudentKind = 'курсант' | 'студент';

/** Why a stretch of the term carries no teaching. All four are equally unusable;
 *  they stay distinct because the разписание prints them apart. */
export type NonTeachingKind = 'ваканция' | 'стаж' | 'изпитна сесия' | 'празник';
export type ExamSessionKind = 'редовна' | 'поправителна' | 'ликвидационна';

/** What a session is. The разписание grid marks cells with the first letter. */
export type ActivityKind = 'лекция' | 'упражнение' | 'практика';
export type ControlForm = 'изпит' | 'КТО' | 'зачет';
/** Who attends an offering's упражнения. */
export type Audience = 'group' | 'subgroup';

/** An academic rank. Mirrors Role in solver/app/models.py.
 *  Ranks are problem data, edited on the Data setup screen like everything else. */
export interface Role {
  /** Stable: teachers point at this, so renaming a rank is free. */
  id: string;
  /** Full label, for the dropdown and the roles table. */
  name: string;
  /** Narrow-column label, for the teachers table and the ladder panel. */
  short: string;
  /** Tier key, not a multiplier: only the ordering and the ties matter. */
  weight: number;
}

export interface Faculty {
  id: string;
  name: string;
}

/** A катедра. Owns subjects and teachers. */
export interface Katedra {
  id: string;
  name: string;
  facultyId?: string | null;
}

export interface Specialty {
  id: string;
  facultyId: string;
  /** 'ППООР', 'ГП'. */
  code: string;
  name: string;
  degree: Degree;
  form: StudyForm;
  studentKind: StudentKind;
  durationYears: number;
}

/** A closed interval of dates: an offering's spread window. */
export interface DateRange {
  start: string;
  end: string;
  label?: string;
}

/** A stretch of the term with no teaching in it, and why. Replaces the old
 *  untyped `breaks`. `session` is set only when kind is 'изпитна сесия'. */
export interface NonTeachingPeriod {
  start: string;
  end: string;
  kind: NonTeachingKind;
  session?: ExamSessionKind | null;
  label?: string | null;
}

/** One курс of one специалност in one semester: the scheduling unit, and the
 *  unit a printed разписание is emitted for. Term dates live here rather than on
 *  the group, because year 1 routinely runs a different calendar from years 2-4
 *  of the same специалност. */
export interface CourseInstance {
  id: string;
  specialtyId: string;
  year: number;
  academicYear: string;
  semester: 1 | 2;
  start: string;
  end: string;
  nonTeaching: NonTeachingPeriod[];
  /** Hard cap on periods taught to one of its groups in a day. */
  maxPeriodsPerDay: number;
  /** Разписание header. Descriptive only -- the solver never reads these. */
  regNumber?: string | null;
  approvedBy?: string | null;
  approvalDate?: string | null;
  administrativenOtgovornik?: string | null;
}

export interface Teacher {
  id: string;
  name: string;
  katedraId?: string | null;
  /** Soft preference: weekday keys ('mon-1') the solver aims for but may trade
   *  away. */
  preferredSlots: string[];
  /** HARD availability, same key shape. Empty means always available. A literal
   *  is never created outside this list, so it cannot be bought at any price --
   *  unlike a preference, an impossible availability is INFEASIBLE. */
  hardAvailability: string[];
  /** Hard cap on periods taught in one ISO week. null means uncapped. */
  maxWeeklyPeriods?: number | null;
  /** Soft preference, and ORDERED: [0] is the room this teacher most wants.
   *  Ranking is scoped per room type -- ranking полигони says nothing about
   *  which стрелбище you get. */
  preferredRooms: string[];
  /** Id of a Role. Absent, or naming a role that is gone, means unranked --
   *  which shares the bottom priority tier. */
  role?: string | null;
  /** Overrides the weight the role implies; the only way to lift one person out
   *  of their rank's tier. */
  priorityWeight?: number | null;
}

export interface Room {
  id: string;
  name: string;
  capacity: number;
  type: RoomType;
  building?: string;
  /** How many sessions may share this room in one period. 1 for everything by
   *  default, and emphatically 1 for стрелбище and малка зала. */
  maxConcurrentGroups: number;
}

/** Учебна група. Belongs to exactly one CourseInstance, which owns its dates. */
export interface Group {
  id: string;
  name: string;
  size: number;
  courseInstanceId: string;
}

/** Подгрупа: a group split for стрелкова подготовка, ЛЗФП or чуждоезиково
 *  обучение -- language подгрупи split by level, so sizes are uneven on purpose.
 *  Two subgroups of one group may be taught at the same time; a group-level
 *  session excludes every one of them. */
export interface Subgroup {
  id: string;
  groupId: string;
  name: string;
  size: number;
}

/** A catalogue entry. What is *taught* is a SubjectOffering. */
export interface Subject {
  id: string;
  /** 'ОИД', 'УППС', 'ЛЗФП', 'СП', 'АЕ'. */
  code: string;
  name: string;
  katedraId?: string | null;
}

export type SpreadMode = 'whole' | 'range' | 'block';

/** One subject as taught to one курс: the хорариум and everything around it.
 *  Hours, not session counts -- '30/15' is 30 лекционни and 15 упражнителни
 *  часа, and the solver divides by hoursPerSession. */
export interface SubjectOffering {
  id: string;
  subjectId: string;
  courseInstanceId: string;
  lectureHours: number;
  exerciseHours: number;
  /** Academic hours in one session. One period, so 2. */
  hoursPerSession: number;
  controlForm: ControlForm;
  /** Allowed room types per activity kind. */
  lectureRoomTypes: RoomType[];
  exerciseRoomTypes: RoomType[];
  /** The ПОТОК: groups merged for this offering's lectures. A join, not an
   *  attribute of the course -- общообразователните merge across специалности
   *  and специалните do not. Exercises ignore it entirely. */
  streamGroupIds: string[];
  /** Водещ преподавател. A лекция has one named lecturer, not a pool. */
  leadTeacherId?: string | null;
  /** Упражнения keep the pool: exactly one takes each session, per session. */
  exerciseTeacherIds: string[];
  exerciseAudience: Audience;
  /** Group ids when audience is 'group', subgroup ids when 'subgroup'. Each unit
   *  gets its own full exerciseHours -- the хорариум is per student. */
  exerciseUnitIds: string[];
  spread: SpreadMode;
  /** Required when spread is 'range' or 'block'. */
  window?: DateRange;
  examDate?: string | null;
}

export interface SlotConfig {
  days: string[];
  periods: number;
  /** 'HH:MM-HH:MM' per period. The обедна почивка is the gap these leave between
   *  two of them -- it needs no field of its own, and no rule. */
  periodTimes: string[];
  /** Weekday-keyed slot ids the user has switched off; these are never sent to
   *  the solver. */
  blockedSlots: string[];
}

/** A cell of the weekly template: what the preference grid, the availability
 *  grid and the blocking UI all work in. Undated on purpose -- 'mon-1' means
 *  that period every week. */
export interface WeekdaySlot {
  id: string;
  day: string;
  period: number;
}

export interface Slot {
  /** '<ISO date>-<period>', e.g. '2025-09-15-1'. */
  id: string;
  /** ISO date. The weekday is kept alongside it because columns and the
   *  blocking keys are both weekday-keyed. */
  date: string;
  day: string;
  period: number;
}

/** Identity of a semester. The *dates* live on the CourseInstance. */
export interface SemesterRef {
  academicYear: string; // '2025/2026'
  index: 1 | 2;
}

export function semesterKey(ref: SemesterRef): string {
  return `${ref.academicYear}-${ref.index}`;
}

export interface Problem {
  slotConfig: SlotConfig;
  roles: Role[];
  faculties: Faculty[];
  katedri: Katedra[];
  specialties: Specialty[];
  courseInstances: CourseInstance[];
  teachers: Teacher[];
  rooms: Room[];
  groups: Group[];
  subgroups: Subgroup[];
  subjects: Subject[];
  offerings: SubjectOffering[];
}

export interface Assignment {
  offeringId: string;
  subjectId: string;
  subjectCode: string;
  subjectName: string;
  activity: ActivityKind;
  /** The dated period this session occupies, and its number on the day. */
  slot: string;
  period: number;
  /** The real date this session lands on. */
  date: string;
  day: string;
  roomId: string;
  roomName: string;
  teacherId: string;
  teacherName: string;
  /** Every group busy for this session: the whole поток for a лекция, the
   *  subgroup's parent group for a подгрупа упражнение. */
  groupIds: string[];
  groupNames: string[];
  subgroupId: string | null;
  subgroupName: string | null;
  softViolated: boolean;
  softReason: string | null;
  /** Position of the assigned room among the rooms this teacher ranked *of that
   *  type*: 0 is their first choice. null means they expressed no opinion. */
  roomPreferenceRank: number | null;
}

/** One rung of the priority ladder. Mirrors TierResult in solver/app/models.py. */
export interface TierResult {
  weight: number;
  /** Short labels of the ranks in this tier, rendered as-is. */
  roles: string[];
  teacherCount: number;
  penalty: number;
  /** FEASIBLE here means the rung ran out of time, and the tiers below it were
   *  frozen against a number it might have improved on. */
  status: string;
  solveTimeSeconds: number;
}

export interface Stats {
  status: string;
  solveTimeSeconds: number;
  objectiveValue: number | null;
  bestObjectiveBound: number | null;
  numSessions: number;
  numPlaced: number;
  /** Dated periods on offer -- what the solver places into. */
  numSlots: number;
  numBooleanVariables: number;
  preferenceViolations: number;
  roomPreferencePenalty: number;
  gapPenalty: number;
  /** Top-down, one entry per distinct teacher weight in the problem. */
  tiers: TierResult[];
}

export interface Hint {
  title: string;
  detail: string;
}

/** CP-SAT engine parameters. Mirrors SearchParams in solver/app/models.py.
 *  null means "leave the library default alone". */
export interface SearchParams {
  numWorkers: number;
  randomSeed: number;
  presolve: boolean;
  symmetryLevel: number | null;
  linearizationLevel: number | null;
}

export interface SolverSettings {
  /** null means no limit at all: the solver runs until it finishes. */
  maxTimeInSeconds: number | null;
  preferenceWeight: number;
  roomPreferenceWeight: number;
  gapWeight: number;
  stopAfterFirstSolution: boolean;
  useSymmetryBreaking: boolean;
  search: SearchParams;
}

export interface SolveResponse {
  status: 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE' | 'UNKNOWN' | 'MODEL_INVALID';
  message: string;
  assignments: Assignment[];
  stats: Stats | null;
  validation: { ok: boolean; errors: string[] } | null;
  hints: Hint[];
  /** What the run was actually solved with -- not necessarily what is on screen now. */
  settingsUsed: SolverSettings | null;
}

// ---------------------------------------------------------------------------
// The разписание document. Built server-side by solver/app/razpisanie.py; the
// JSON above stays the machine-readable form and this is a renderer on top.
// ---------------------------------------------------------------------------

export interface RazpisanieHeader {
  facultyName: string;
  regNumber: string | null;
  approvedBy: string | null;
  approvalDate: string | null;
  specialtyCode: string;
  specialtyName: string;
  degree: Degree;
  form: StudyForm;
  studentKind: StudentKind;
  year: number;
  semester: number;
  start: string;
  end: string;
  administrativenOtgovornik: string | null;
}

/** One numbered line of section I. `number` is what the grid cells print. */
export interface RazpisanieSubject {
  number: number;
  code: string;
  name: string;
  lectureHours: number;
  exerciseHours: number;
  katedra: string | null;
  leadTeacher: string | null;
  exerciseTeachers: string[];
  rooms: string[];
  controlForm: ControlForm;
}

/** One line of section II -- разпределение на учебното време. */
export interface RazpisanieTimeBlock {
  label: string;
  start: string;
  end: string;
  weeks: number;
}

/** One line of section III. */
export interface RazpisanieExam {
  number: number;
  code: string;
  name: string;
  controlForm: ControlForm;
  examDate: string | null;
}

/** One (day, period) cell of the month grid. Empty cells are simply absent. */
export interface RazpisanieCell {
  date: string;
  period: number;
  /** Usually one entry; more than one when подгрупи run in parallel. */
  entries: string[];
}

export interface RazpisanieMonth {
  label: string;
  year: number;
  month: number;
  dates: string[];
  cells: RazpisanieCell[];
}

export interface Razpisanie {
  courseInstanceId: string;
  header: RazpisanieHeader;
  subjects: RazpisanieSubject[];
  timeBlocks: RazpisanieTimeBlock[];
  exams: RazpisanieExam[];
  /** The grid's columns: 1..periods, with their clock times. */
  periods: number[];
  periodTimes: Record<number, string>;
  months: RazpisanieMonth[];
}

/** Live progress of a solve in flight, assembled from the solver's own events.
 *  The ladder runs a fixed sequence -- model build, warm-up, one phase per rank
 *  tier, then gaps -- so `phase of total` only ever moves forwards. */
export interface SolveProgress {
  /** 0 while the model is still being built, then 1..total. */
  phase: number;
  total: number;
  /** 'building' | 'warmup' | 'tier' | 'gap' | 'combined'. */
  label: string;
  /** Rank short-names this phase is settling; empty for warm-up and gaps. */
  roles: string[];
  /** Best penalty this phase has found so far, and the bound it is proving
   *  against. Both null until CP-SAT reports its first improvement. */
  best: number | null;
  bound: number | null;
  /** Penalties the phases that already settled agreed to, newest last. */
  settled: { label: string; roles: string[]; penalty: number | null; status: string }[];
}

export type RunState = 'empty' | 'solving' | 'solved' | 'failed' | 'error';
export type Lens = 'group' | 'teacher' | 'room';
