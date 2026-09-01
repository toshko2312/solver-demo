/** Slot ids are derived, never stored: '<lowercased day>-<period>', e.g. mon-1.
 *  The solver's tests build them the same way (solver/tests/conftest.py). */

import { semesterKey } from './types';
import type {
  DateRange,
  Group,
  GroupSemester,
  SemesterRef,
  Slot,
  SlotConfig,
  Subject,
  SubjectSemester,
  WeekdaySlot,
} from './types';

export function slotId(day: string, period: number): string {
  return `${day.toLowerCase()}-${period}`;
}

/** Every cell of the weekly template, blocked ones included. Undated: this is
 *  what the preference grid and the blocking UI work in. */
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

export function slotLabel(config: SlotConfig, id: string): string {
  const slot = allSlots(config).find((s) => s.id === id);
  return slot ? `${slot.day} · Period ${slot.period}` : id;
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

export function inRange(iso: string, range: DateRange): boolean {
  return iso >= range.start && iso <= range.end;
}

/** Teaching dates of one group's semester: inside the term, off every break. */
export function teachingDates(sem: GroupSemester, config: SlotConfig): string[] {
  const days = new Set(config.days);
  const out: string[] = [];
  for (let d = sem.start; d <= sem.end; d = addDays(d, 1)) {
    if (!days.has(weekdayName(d))) continue;
    if (sem.breaks.some((b) => inRange(d, b))) continue;
    out.push(d);
  }
  return out;
}

export function groupSemester(group: Group, ref: SemesterRef): GroupSemester | undefined {
  return group.semesters.find(
    (s) => s.academicYear === ref.academicYear && s.index === ref.index,
  );
}

/** Every semester any group is in term for, newest year first. */
export function knownSemesters(groups: Group[]): SemesterRef[] {
  const seen = new Map<string, SemesterRef>();
  for (const g of groups) {
    for (const s of g.semesters) {
      const ref = { academicYear: s.academicYear, index: s.index };
      seen.set(semesterKey(ref), ref);
    }
  }
  // Chronological: a calendar reads forwards, and the first entry is what the
  // pickers default to.
  return [...seen.values()].sort(
    (a, b) => a.academicYear.localeCompare(b.academicYear) || a.index - b.index,
  );
}

/** The dated slots sent to the solver for one semester: the weekday template
 *  expanded across every date any group in term teaches on, blocked
 *  weekday-periods omitted. A date no group teaches on is simply not a slot. */
export function semesterSlots(
  config: SlotConfig,
  groups: Group[],
  ref: SemesterRef,
): Slot[] {
  const blocked = new Set(config.blockedSlots);
  const dates = new Set<string>();
  for (const g of groups) {
    const sem = groupSemester(g, ref);
    if (sem) for (const d of teachingDates(sem, config)) dates.add(d);
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
  groups: Group[],
  ref: SemesterRef,
): { week: string; dates: string[] }[] {
  const byWeek = new Map<string, string[]>();
  for (const slot of semesterSlots(config, groups, ref)) {
    const w = isoWeek(slot.date);
    if (!byWeek.has(w)) byWeek.set(w, []);
    const list = byWeek.get(w)!;
    if (!list.includes(slot.date)) list.push(slot.date);
  }
  return [...byWeek.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([week, dates]) => ({ week, dates: dates.sort() }));
}

export function subjectSemester(
  subject: Subject,
  ref: SemesterRef,
): SubjectSemester | undefined {
  return subject.semesters.find(
    (x) => x.academicYear === ref.academicYear && x.index === ref.index,
  );
}

/** Sessions a subject runs in one semester, 0 when it does not run then. */
export function sessionsIn(subject: Subject, ref: SemesterRef): number {
  return subjectSemester(subject, ref)?.totalSessions ?? 0;
}

/** Groups attending a subject in one semester; empty when it does not run then.
 *  Mirrors Subject.groups_for() in solver/app/models.py. */
export function subjectGroupIds(subject: Subject, ref: SemesterRef): string[] {
  return subjectSemester(subject, ref)?.groupIds ?? [];
}

/** Every group across every semester, deduped -- for the views and the delete
 *  cascade, which are not about one term. */
export function subjectAllGroupIds(subject: Subject): string[] {
  const seen: string[] = [];
  for (const spec of subject.semesters) {
    for (const gid of spec.groupIds) if (!seen.includes(gid)) seen.push(gid);
  }
  return seen;
}

/** The dates a subject may actually be taught on: the intersection of its
 *  groups' teaching dates, narrowed to its own spread window. Mirrors
 *  _usable_dates() in solver/app/timetable_solver.py. */
export function subjectDates(
  subject: Subject,
  groups: Group[],
  config: SlotConfig,
  ref: SemesterRef,
): string[] {
  const spec = subjectSemester(subject, ref);
  if (!spec) return [];
  let usable: string[] | null = null;
  for (const gid of spec.groupIds) {
    const group = groups.find((g) => g.id === gid);
    const sem = group && groupSemester(group, ref);
    if (!sem) return [];
    const teaching = teachingDates(sem, config);
    // Intersection, not union: every listed group is busy for the whole session,
    // so a date only counts while all of them are in term.
    usable = usable === null ? teaching : usable.filter((d) => teaching.includes(d));
  }
  if (usable === null) return [];
  let out = usable;
  if (spec.spread === 'range' && spec.window) {
    out = out.filter((d) => inRange(d, spec.window!));
  }
  return out.sort();
}
