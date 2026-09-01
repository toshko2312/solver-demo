/** Domain model. Mirrors solver/app/models.py -- this is the whole wire format. */

export type RoomType = 'lecture' | 'lab' | 'sports' | 'firing_range' | 'training_ground';

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

export interface Teacher {
  id: string;
  name: string;
  department?: string;
  /** Soft preference: slot ids the solver should aim for, but may trade away. */
  preferredSlots: string[];
  /** Soft preference, and ORDERED: [0] is the room this teacher most wants.
   *  Ranking is scoped per room type -- ranking labs says nothing about which
   *  sports hall you get. */
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
}

export interface Group {
  id: string;
  name: string;
  size: number;
  programme?: string;
  /** At most two per academic year. A group with no entry for the semester being
   *  generated is not in term and takes no part in that solve. */
  semesters: GroupSemester[];
}

export interface Subject {
  id: string;
  name: string;
  /** Any room of one of these types will do; the solver picks. */
  allowedRoomTypes: RoomType[];
  /** One entry per semester this subject runs in. */
  semesters: SubjectSemester[];
  /** Candidate teachers. The solver assigns exactly one per session. */
  teacherIds: string[];
}

export interface SlotConfig {
  days: string[];
  periods: number;
  periodTimes: string[];
  /** Slot ids the user has switched off; these are never sent to the solver. */
  blockedSlots: string[];
}

/** A cell of the weekly template: what the preference grid and the blocking UI
 *  work in. Undated on purpose -- 'mon-1' means that period every week. */
export interface WeekdaySlot {
  id: string;
  day: string;
  period: number;
}

export interface Slot {
  /** '<ISO date>-<period>', e.g. '2025-09-15-1'. */
  id: string;
  /** ISO date. The weekday is kept alongside it because columns and
   *  `blockedSlots` are both weekday-keyed. */
  date: string;
  day: string;
  period: number;
}

/** Identity of a semester. The *dates* live per group. */
export interface SemesterRef {
  academicYear: string; // '2025/2026'
  index: 1 | 2;
}

export function semesterKey(ref: SemesterRef): string {
  return `${ref.academicYear}-${ref.index}`;
}

/** A closed interval of dates: a break, or a subject's spread window. */
export interface DateRange {
  start: string;
  end: string;
  label?: string;
}

/** One group's dates for one semester. Breaks are excluded from teaching
 *  entirely and do not count towards the weeks an even spread is measured on. */
export interface GroupSemester extends SemesterRef {
  start: string;
  end: string;
  breaks: DateRange[];
}

export type SpreadMode = 'whole' | 'range';

/** How much of a subject runs in one semester. A total, not a weekly rate:
 *  sessions land on real dates, so nothing has to divide evenly. */
export interface SubjectSemester extends SemesterRef {
  totalSessions: number;
  spread: SpreadMode;
  /** Required when spread is 'range'. */
  window?: DateRange;
  /** Who attends this subject in this semester. Every listed group is busy for
   *  the whole session. Groups live here rather than on the subject because a
   *  subject can run for different cohorts in each semester. */
  groupIds: string[];
}

export interface Problem {
  slotConfig: SlotConfig;
  roles: Role[];
  teachers: Teacher[];
  rooms: Room[];
  groups: Group[];
  subjects: Subject[];
}

export interface Assignment {
  subjectId: string;
  subjectName: string;
  slot: string;
  /** The real date this session lands on. */
  date: string;
  roomId: string;
  roomName: string;
  teacherId: string;
  teacherName: string;
  groupIds: string[];
  groupNames: string[];
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
  maxTimeInSeconds: number;
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

export type RunState = 'empty' | 'solving' | 'solved' | 'failed' | 'error';
export type Lens = 'group' | 'teacher' | 'room';
