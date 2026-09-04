/** Hard-rule re-check for a timetable that has been edited by hand.
 *
 *  The solver guarantees its own output, and `validate_assignments()` in
 *  solver/app/timetable_solver.py re-proves it independently. Moving a session
 *  in the grid bypasses both: the move is accepted whatever it breaks, so the
 *  breach has to be found here and shown.
 *
 *  Only the rules a *period* move can break are checked. The room, the teacher and
 *  the audience never change in a move, so room type, room capacity, whether the
 *  teacher is a candidate for the offering, and the per-series session count are
 *  all still guaranteed by the solve they came from.
 */

import {
  coursesIn,
  isoWeek,
  offeringDates,
  offeringsIn,
  semesterSlots,
  sessionsOf,
  teachesOn,
} from './slots';
import type { Assignment, Problem, SemesterRef } from './types';

/** The dated period a session occupies -- the unit everything clashes on. */
function cell(a: Assignment): string {
  return a.slot;
}

/** Hard-rule breaches introduced by hand, keyed by index into `assignments`.
 *
 *  The double-booking scans run over every assignment, never over the grid's
 *  lens-filtered view: a clash with a session the current filter hides is still
 *  a clash. */
export function findConflicts(
  assignments: Assignment[],
  problem: Problem,
  ref: SemesterRef,
): Map<number, string[]> {
  const out = new Map<number, string[]>();
  const add = (index: number, message: string) => {
    const list = out.get(index);
    if (list) list.push(message);
    else out.set(index, [message]);
  };

  // The exact slot universe the solver was given -- blocked periods and dates
  // nobody teaches on are simply not in it, which is how the solver learns they
  // are unusable.
  const legal = new Set(
    semesterSlots(problem.slotConfig, problem.courseInstances, ref).map((s) => s.id),
  );
  const groupById = new Map(problem.groups.map((g) => [g.id, g]));
  const subgroupById = new Map(problem.subgroups.map((s) => [s.id, s]));
  const courseById = new Map(problem.courseInstances.map((c) => [c.id, c]));
  const inTerm = new Set(coursesIn(problem.courseInstances, ref).map((c) => c.id));
  const roomById = new Map(problem.rooms.map((r) => [r.id, r]));

  // First occupant wins the cell and the second is the one flagged -- but both
  // cards have to show the clash, so the winner is recorded and marked too.
  const teacherAt = new Map<string, number>();
  const groupAt = new Map<string, number>();
  const subgroupAt = new Map<string, number>();
  const roomAt = new Map<string, number[]>();

  const clash = (
    seen: Map<string, number>,
    key: string,
    index: number,
    message: (other: Assignment) => string,
  ) => {
    const first = seen.get(key);
    if (first === undefined) {
      seen.set(key, index);
      return;
    }
    add(index, message(assignments[first]));
    add(first, message(assignments[index]));
  };

  assignments.forEach((a, i) => {
    if (!legal.has(a.slot)) {
      add(
        i,
        `${a.slot} is not an open period this semester — blocked, or nobody teaches then.`,
      );
    }

    for (const gid of a.groupIds) {
      const group = groupById.get(gid);
      const course = group && courseById.get(group.courseInstanceId);
      const name = group?.name ?? gid;
      if (!course || !inTerm.has(course.id)) {
        add(i, `${name} is not in term this semester.`);
      } else if (!teachesOn(course, a.date)) {
        add(
          i,
          `${name} is not teaching on ${a.date} — outside its term, or in a non-teaching period.`,
        );
      }
    }

    clash(teacherAt, `${a.teacherId}|${cell(a)}`, i, (o) =>
      `${a.teacherName} is already teaching ${o.subjectName} in this period.`,
    );

    if (a.subgroupId) {
      // Подгрупите of one група may run side by side, so a подгрупа clashes only
      // with itself -- and, below, with anything its parent група is doing.
      clash(subgroupAt, `${a.subgroupId}|${cell(a)}`, i, (o) =>
        `${a.subgroupName} is already in ${o.subjectName} in this period.`,
      );
    } else {
      for (const gid of a.groupIds) {
        clash(groupAt, `${gid}|${cell(a)}`, i, (o) => {
          const name = groupById.get(gid)?.name ?? gid;
          return `${name} is already in ${o.subjectName} in this period.`;
        });
      }
    }

    // Rooms count rather than clash: maxConcurrentGroups is 1 for almost
    // everything, but a hall that takes two подгрупи says so.
    const key = `${a.roomId}|${cell(a)}`;
    const here = roomAt.get(key);
    if (here) here.push(i);
    else roomAt.set(key, [i]);
  });

  for (const [key, indices] of roomAt) {
    const roomId = key.split('|')[0];
    const limit = roomById.get(roomId)?.maxConcurrentGroups ?? 1;
    if (indices.length <= limit) continue;
    for (const i of indices) {
      const a = assignments[i];
      add(
        i,
        `${a.roomName} now holds ${indices.length} session(s) in this period; it takes ${limit}.`,
      );
    }
  }

  // A група-level session and a подгрупа session of that група in the same period
  // is a clash even though neither scan above catches it.
  assignments.forEach((a, i) => {
    if (!a.subgroupId) return;
    const parent = subgroupById.get(a.subgroupId)?.groupId;
    if (!parent) return;
    const other = groupAt.get(`${parent}|${cell(a)}`);
    if (other === undefined) return;
    const name = groupById.get(parent)?.name ?? parent;
    add(i, `${name} is in ${assignments[other].subjectName} in this period.`);
    add(other, `${a.subgroupName} is in ${a.subjectName} in this period.`);
  });

  // The daily cap. A подгрупа session busies its parent група, and two подгрупи
  // side by side cost the група one period of its day, not two -- so this counts
  // distinct periods, exactly as the solver does.
  const dayPeriods = new Map<string, Set<number>>();
  const dayIndices = new Map<string, number[]>();
  assignments.forEach((a, i) => {
    for (const gid of a.groupIds) {
      const key = `${gid}|${a.date}`;
      const periods = dayPeriods.get(key) ?? new Set<number>();
      periods.add(a.period);
      dayPeriods.set(key, periods);
      dayIndices.set(key, [...(dayIndices.get(key) ?? []), i]);
    }
  });
  for (const [key, periods] of dayPeriods) {
    const [gid, date] = key.split('|');
    const group = groupById.get(gid);
    const course = group && courseById.get(group.courseInstanceId);
    if (!course || periods.size <= course.maxPeriodsPerDay) continue;
    for (const i of dayIndices.get(key) ?? []) {
      add(
        i,
        `${group?.name ?? gid} now has ${periods.size} period(s) on ${date}; its курс allows ` +
          `${course.maxPeriodsPerDay}.`,
      );
    }
  }

  // Hard availability. Unlike a preference, this one a move can genuinely break.
  const teacherById = new Map(problem.teachers.map((t) => [t.id, t]));
  assignments.forEach((a, i) => {
    const t = teacherById.get(a.teacherId);
    if (!t || !t.hardAvailability.length) return;
    const key = `${a.day.toLowerCase()}-${a.period}`;
    if (!t.hardAvailability.includes(key)) {
      add(i, `${a.teacherName} is not available in ${key} — a hard constraint, not a preference.`);
    }
  });

  // The offering's own window. `validate_assignments` re-checks it too, but the
  // solver enforces it by never generating a variable outside the window, so a
  // hand move is the only way to land outside one.
  const datesFor = new Map<string, Set<string>>();
  for (const offering of offeringsIn(problem.offerings, problem.courseInstances, ref)) {
    datesFor.set(
      offering.id,
      new Set(
        offeringDates(
          offering,
          problem.groups,
          problem.subgroups,
          problem.courseInstances,
          problem.slotConfig,
          ref,
        ),
      ),
    );
  }
  assignments.forEach((a, i) => {
    const dates = datesFor.get(a.offeringId);
    if (dates && !dates.has(a.date)) {
      add(i, `${a.subjectName} cannot run on ${a.date} — outside the dates it is spread across.`);
    }
  });

  return out;
}

/** Even spread, as grid-level notices rather than per-card flags.
 *
 *  HARD 8 caps a series at ceil(N/W) sessions in any one teaching week, and
 *  "move to another week" is exactly the gesture that breaks it -- but the
 *  breach belongs to the week, not to any one of the sessions in it, so there is
 *  no single card to mark. `block` offerings are exempt, as they are in the
 *  solver: saturating a window is what задочна форма asks for. */
export function spreadNotices(
  assignments: Assignment[],
  problem: Problem,
  ref: SemesterRef,
): string[] {
  const notices: string[] = [];
  const subjectName = new Map(problem.subjects.map((s) => [s.id, s.name]));
  for (const offering of offeringsIn(problem.offerings, problem.courseInstances, ref)) {
    if (offering.spread === 'block') continue;
    const weeks = new Set(
      offeringDates(
        offering,
        problem.groups,
        problem.subgroups,
        problem.courseInstances,
        problem.slotConfig,
        ref,
      ).map(isoWeek),
    );
    // The solver skips the constraint entirely below two weeks, and so must this.
    if (weeks.size < 2) continue;
    const name = subjectName.get(offering.subjectId) ?? offering.subjectId;

    // Per series, not per offering: each група's упражнения are spread on their
    // own, and so are the поток's лекции.
    const bySeries = new Map<string, Map<string, string[]>>();
    const counts = new Map<string, number>();
    for (const a of assignments) {
      if (a.offeringId !== offering.id) continue;
      const series =
        a.activity === 'лекция' ? 'лекция' : `${a.subgroupName ?? a.groupNames[0] ?? ''}`;
      counts.set(series, sessionsOf(offering, a.activity === 'лекция' ? 'лекция' : 'упражнение'));
      const perWeek = bySeries.get(series) ?? new Map<string, string[]>();
      const week = isoWeek(a.date);
      perWeek.set(week, [...(perWeek.get(week) ?? []), a.date]);
      bySeries.set(series, perWeek);
    }

    for (const [series, perWeek] of bySeries) {
      const ceiling = Math.ceil((counts.get(series) ?? 0) / weeks.size);
      for (const [, dates] of [...perWeek.entries()].sort(([a], [b]) => a.localeCompare(b))) {
        if (dates.length > ceiling) {
          notices.push(
            `${name} (${series}) now has ${dates.length} session(s) in the week of ` +
              `${dates.sort()[0]}; an even spread allows at most ${ceiling}.`,
          );
        }
      }
    }
  }
  return notices;
}
