/** Domain model. Mirrors solver/app/models.py -- this is the whole wire format. */

export type RoomType = 'lecture' | 'lab' | 'sports' | 'firing_range' | 'training_ground';

export interface Teacher {
  id: string;
  name: string;
  department?: string;
  /** Soft preference: slot ids the solver should aim for, but may trade away. */
  preferredSlots: string[];
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
}

export interface Subject {
  id: string;
  name: string;
  /** Any room of one of these types will do; the solver picks. */
  allowedRoomTypes: RoomType[];
  sessionsPerWeek: number;
  /** Candidate teachers. The solver assigns exactly one per session. */
  teacherIds: string[];
  groupIds: string[];
}

export interface SlotConfig {
  days: string[];
  periods: number;
  periodTimes: string[];
  /** Slot ids the user has switched off; these are never sent to the solver. */
  blockedSlots: string[];
}

export interface Slot {
  id: string;
  day: string;
  period: number;
}

export interface Problem {
  slotConfig: SlotConfig;
  teachers: Teacher[];
  rooms: Room[];
  groups: Group[];
  subjects: Subject[];
}

export interface Assignment {
  subjectId: string;
  subjectName: string;
  slot: string;
  roomId: string;
  roomName: string;
  teacherId: string;
  teacherName: string;
  groupIds: string[];
  groupNames: string[];
  softViolated: boolean;
  softReason: string | null;
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
  gapPenalty: number;
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
