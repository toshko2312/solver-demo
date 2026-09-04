/** Slot ids are derived, never stored: '<lowercased day>-<period>', e.g. mon-1.
 *  The solver's tests build them the same way (solver/tests/conftest.py).
 *
 *  A period is a block of two academic hours and it is the atomic unit -- there
 *  is no finer thing to schedule. The обедна почивка needs no representation at
 *  all: it is the stretch of clock between two periods that no period covers, so
 *  nothing can be placed across it. */

import { semesterKey } from './types';
import type {
  CourseInstance,
  Group,
  SemesterRef,
  Slot,
  SlotConfig,
  SubjectOffering,
  Subgroup,
  WeekdaySlot,
} from './types';

export function slotId(day: string, period: number): string {
  return `${day.toLowerCase()}-${period}`;
}

/** Every cell of the weekly template, blocked ones included. Undated: this is
 *  what the preference grid, the availability grid and the blocking UI work in. */
export function allSlots(config: SlotConfig): WeekdaySlot[] {
  const out: WeekdaySlot[] = [];
  for (const day of config.days) {
    for (let period = 1; period <= config.periods; period++) {
      out.push({ id: slotId(day, period), day, period });
    }
  }
  return out;
}

/** Template cells that are not blocked. The dated slots actually sent to the
 *  solver come from semesterSlots() below. */
export function openSlots(config: SlotConfig): WeekdaySlot[] {
  const blocked = new Set(config.blockedSlots);
  return allSlots(config).filter((s) => !blocked.has(s.id));
}

export function periodTime(config: SlotConfig, period: number): string {
  return config.periodTimes[period - 1] ?? '';
}

// ---------------------------------------------------------------------------
// Period clock times. Stored as the canonical 'HH:MM-HH:MM' string the seeds
// already use, so nothing outside the editor -- or on the wire, which never sees
// slotConfig at all -- has to know these are now structured values.
// ---------------------------------------------------------------------------

export interface PeriodSpan {
  /** 'HH:MM', 24-hour. */
  start: string;
  end: string;
}

const SPAN = /^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/;

/** Minutes since midnight. '09:45' -> 585. */
export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(':');
  return Number(h) * 60 + Number(m);
}

/** The inverse, for deriving a new period from the one before it. */
export function clockTime(minutes: number): string {
  const clamped = Math.max(0, Math.min(24 * 60 - 1, Math.round(minutes)));
  const h = Math.floor(clamped / 60);
  return `${String(h).padStart(2, '0')}:${String(clamped - h * 60).padStart(2, '0')}`;
}

/** null for anything that is not 'HH:MM-HH:MM' -- a problem stored before times
 *  were editable can hold free text, since 'Add period' used to write 'Period 7'. */
export function parsePeriodTime(text: string): PeriodSpan | null {
  const m = SPAN.exec(text.trim());
  if (!m) return null;
  const [, h1, m1, h2, m2] = m;
  if (Number(h1) > 23 || Number(h2) > 23 || Number(m1) > 59 || Number(m2) > 59) return null;
  return { start: `${h1.padStart(2, '0')}:${m1}`, end: `${h2.padStart(2, '0')}:${m2}` };
}

export function formatPeriodTime(span: PeriodSpan): string {
  return `${span.start}-${span.end}`;
}

/** Why each period's times are unusable, keyed by period number.
 *
 *  Periods must not overlap, and must run in period *order*: the gap objective
 *  in the solver treats consecutive period numbers as adjacent within a day, so
 *  a Period 3 sitting earlier on the clock than Period 2 would compact the wrong
 *  thing. Touching is not overlapping -- one period may end exactly when the next
 *  begins. A row with no readable time is reported but never blamed on, or for,
 *  its neighbours.
 */
export function periodTimeErrors(times: string[]): Map<number, string> {
  const out = new Map<number, string>();
  let prev: { period: number; span: PeriodSpan } | null = null;
  for (let i = 0; i < times.length; i++) {
    const period = i + 1;
    const span = parsePeriodTime(times[i]);
    if (!span) {
      out.set(period, 'No time set.');
      continue;
    }
    if (minutesOf(span.start) >= minutesOf(span.end)) {
      out.set(period, `Period ${period} ends before it starts.`);
    } else if (prev && minutesOf(span.start) < minutesOf(prev.span.end)) {
      out.set(
        period,
        `Period ${period} must start at or after ${prev.span.end}, when Period ${prev.period} ends.`,
      );
    }
    prev = { period, span };
  }
  return out;
}

export function slotLabel(config: SlotConfig, id: string): string {
  const cell = allSlots(config).find((s) => s.id === id);
  return cell ? `${cell.day} · Period ${cell.period}` : id;
}

// ---------------------------------------------------------------------------
// Dates. A semester is a real span of days, so the weekday x period template
// above gets expanded across it. Deliberately dependency-free: this is a handful
// of day arithmetic, not a reason to take on a date library.
// ---------------------------------------------------------------------------

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function parseDate(iso: string): Date {
  // Midday UTC, so a timezone offset can never roll the date across midnight.
  return new Date(`${iso}T12:00:00Z`);
}

export function addDays(iso: string, days: number): string {
  const d = parseDate(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return isoDate(d);
}

export function weekdayName(iso: string): string {
  return DAY_NAMES[parseDate(iso).getUTCDay()];
}

/** ISO year-week, as 'YYYY-Www'. Mirrors date.isocalendar() on the solver side. */
export function isoWeek(iso: string): string {
  const d = parseDate(iso);
  // Thursday of this week decides the ISO year.
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day + 3);
  const year = d.getUTCFullYear();
  const firstThursday = new Date(Date.UTC(year, 0, 4, 12));
  const offset = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - offset + 3);
  const week = 1 + Math.round((d.getTime() - firstThursday.getTime()) / (7 * 86400000));
  return `${year}-W${String(week).padStart(2, '0')}`;
}

/** Any closed date interval: a spread window, or a non-teaching period. */
export function inRange(iso: string, range: { start: string; end: string }): boolean {
  return iso >= range.start && iso <= range.end;
}

/** Teaching dates of one курс: inside the term, off every non-teaching period.
 *  Term dates live on the CourseInstance, not on the група -- year 1 routinely
 *  runs a different calendar from years 2-4 of the same специалност. */
export function teachingDates(course: CourseInstance, config: SlotConfig): string[] {
  const days = new Set(config.days);
  const out: string[] = [];
  for (let d = course.start; d <= course.end; d = addDays(d, 1)) {
    if (!days.has(weekdayName(d))) continue;
    if (course.nonTeaching.some((p) => inRange(d, p))) continue;
    out.push(d);
  }
  return out;
}

/** Whether a курс teaches on one date. Mirrors CourseInstance.teaches_on(). */
export function teachesOn(course: CourseInstance, date: string): boolean {
  if (date < course.start || date > course.end) return false;
  return !course.nonTeaching.some((p) => inRange(date, p));
}

export function courseOf(
  group: Group | undefined,
  courses: CourseInstance[],
): CourseInstance | undefined {
  return group && courses.find((c) => c.id === group.courseInstanceId);
}

/** The курсове in term for one semester. */
export function coursesIn(courses: CourseInstance[], ref: SemesterRef): CourseInstance[] {
  return courses.filter(
    (c) => c.academicYear === ref.academicYear && c.semester === ref.index,
  );
}

/** Every semester any курс is in term for, chronologically. */
export function knownSemesters(courses: CourseInstance[]): SemesterRef[] {
  const seen = new Map<string, SemesterRef>();
  for (const c of courses) {
    const ref: SemesterRef = { academicYear: c.academicYear, index: c.semester };
    seen.set(semesterKey(ref), ref);
  }
  // Chronological: a calendar reads forwards, and the first entry is what the
  // pickers default to.
  return [...seen.values()].sort(
    (a, b) => a.academicYear.localeCompare(b.academicYear) || a.index - b.index,
  );
}

/** The dated slots sent to the solver for one semester: every period of every
 *  date any курс in term teaches on, minus the ones blocked in the template. A
 *  date no курс teaches on is simply not a slot. */
export function semesterSlots(
  config: SlotConfig,
  courses: CourseInstance[],
  ref: SemesterRef,
): Slot[] {
  const blocked = new Set(config.blockedSlots);
  const dates = new Set<string>();
  for (const course of coursesIn(courses, ref)) {
    for (const d of teachingDates(course, config)) dates.add(d);
  }
  const out: Slot[] = [];
  for (const date of [...dates].sort()) {
    const day = weekdayName(date);
    for (let period = 1; period <= config.periods; period++) {
      if (blocked.has(slotId(day, period))) continue;
      out.push({ id: `${date}-${period}`, date, day, period });
    }
  }
  return out;
}

/** Teaching weeks of a semester, as ISO week keys with their dates. */
export function semesterWeeks(
  config: SlotConfig,
  courses: CourseInstance[],
  ref: SemesterRef,
): { week: string; dates: string[] }[] {
  const byWeek = new Map<string, string[]>();
  for (const slot of semesterSlots(config, courses, ref)) {
    const w = isoWeek(slot.date);
    if (!byWeek.has(w)) byWeek.set(w, []);
    const list = byWeek.get(w)!;
    if (!list.includes(slot.date)) list.push(slot.date);
  }
  return [...byWeek.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([week, dates]) => ({ week, dates: dates.sort() }));
}

// ---------------------------------------------------------------------------
// Offerings. A хорариум is hours, not sessions; the solver divides, and so does
// this. Mirrors SubjectOffering.sessions_for() and sessions.build_series().
// ---------------------------------------------------------------------------

/** Sessions one audience unit gets of one activity kind. Ceil, not floor:
 *  rounding down would silently under-deliver the хорариум. */
export function sessionsOf(offering: SubjectOffering, kind: 'лекция' | 'упражнение'): number {
  const hours = kind === 'лекция' ? offering.lectureHours : offering.exerciseHours;
  if (hours <= 0) return 0;
  return Math.ceil(hours / Math.max(1, offering.hoursPerSession));
}

/** Everything this offering contributes to a semester: лекции once for the
 *  поток, упражнения once per unit. */
export function offeringSessions(offering: SubjectOffering): number {
  const lectures = offering.leadTeacherId ? sessionsOf(offering, 'лекция') : 0;
  const exercises = offering.exerciseTeacherIds.length
    ? sessionsOf(offering, 'упражнение') * offering.exerciseUnitIds.length
    : 0;
  return lectures + exercises;
}

export function offeringsIn(
  offerings: SubjectOffering[],
  courses: CourseInstance[],
  ref: SemesterRef,
): SubjectOffering[] {
  const ids = new Set(coursesIn(courses, ref).map((c) => c.id));
  return offerings.filter((o) => ids.has(o.courseInstanceId));
}

/** Every група busy for an offering, поток and подгрупа parents alike. */
export function offeringGroupIds(
  offering: SubjectOffering,
  subgroups: Subgroup[],
): string[] {
  const out = new Set(offering.streamGroupIds);
  for (const unit of offering.exerciseUnitIds) {
    const sub = subgroups.find((s) => s.id === unit);
    out.add(sub ? sub.groupId : unit);
  }
  return [...out];
}

/** The dates an offering may actually be taught on: the intersection of its
 *  групи's teaching dates, narrowed to its own spread window. Mirrors
 *  _usable_dates() in solver/app/timetable_solver.py. */
export function offeringDates(
  offering: SubjectOffering,
  groups: Group[],
  subgroups: Subgroup[],
  courses: CourseInstance[],
  config: SlotConfig,
  ref: SemesterRef,
): string[] {
  const inTerm = new Set(coursesIn(courses, ref).map((c) => c.id));
  let usable: string[] | null = null;
  for (const gid of offeringGroupIds(offering, subgroups)) {
    const group = groups.find((g) => g.id === gid);
    const course = courseOf(group, courses);
    if (!course || !inTerm.has(course.id)) return [];
    const teaching = teachingDates(course, config);
    // Intersection, not union: every listed група is busy for the whole session,
    // so a date only counts while all of them are in term.
    usable = usable === null ? teaching : usable.filter((d) => teaching.includes(d));
  }
  if (usable === null) return [];
  let out = usable;
  if (offering.spread !== 'whole' && offering.window) {
    out = out.filter((d) => inRange(d, offering.window!));
  }
  return out.sort();
}
