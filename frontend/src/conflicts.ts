/** Hard-rule re-check for a timetable that has been edited by hand.
 *
 *  The solver guarantees its own output, and `validate_assignments()` in
 *  solver/app/timetable_solver.py re-proves it independently. Moving a session
 *  in the grid bypasses both: the move is accepted whatever it breaks, so the
 *  breach has to be found here and shown.
 *
 *  Only the rules a *slot* move can break are checked. The room, the teacher and
 *  the groups never change in a move, so room type, room capacity, whether the
 *  teacher is a candidate for the subject, and the per-subject session count are
 *  all still guaranteed by the solve they came from.
 */

import { groupSemester, isoWeek, semesterSlots, subjectDates, subjectSemester } from './slots';
import type { Assignment, Problem, SemesterRef } from './types';

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

  // The exact slot universe the solver was given -- blocked cells and dates
  // nobody teaches on are simply not in it, which is how the solver learns they
  // are unusable. Mirrors the `a.slot not in slot_ids` check.
  const legal = new Set(semesterSlots(problem.slotConfig, problem.groups, ref).map((s) => s.id));
  const groupById = new Map(problem.groups.map((g) => [g.id, g]));

  // First occupant wins the slot and the second is the one flagged -- but both
  // cards have to show the clash, so the winner is recorded and marked too.
  const teacherAt = new Map<string, number>();
  const groupAt = new Map<string, number>();
  const roomAt = new Map<string, number>();

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
      add(i, `${a.slot} is not an open slot this semester — blocked, or nobody teaches then.`);
    }

    for (const gid of a.groupIds) {
      const group = groupById.get(gid);
      const sem = group && groupSemester(group, ref);
      const name = group?.name ?? gid;
      if (!sem) {
        add(i, `${name} is not in term this semester.`);
      } else if (!(a.date >= sem.start && a.date <= sem.end)) {
        add(i, `${name} is not teaching on ${a.date} — outside its semester.`);
      } else if (sem.breaks.some((b) => a.date >= b.start && a.date <= b.end)) {
        add(i, `${name} is not teaching on ${a.date} — on a break.`);
      }
    }

    clash(teacherAt, `${a.teacherId}|${a.slot}`, i, (o) =>
      `${a.teacherName} is already teaching ${o.subjectName} in this slot.`,
    );
    clash(roomAt, `${a.roomId}|${a.slot}`, i, (o) =>
      `${a.roomName} is already taken by ${o.subjectName} in this slot.`,
    );
    for (const gid of a.groupIds) {
      clash(groupAt, `${gid}|${a.slot}`, i, (o) => {
        const name = groupById.get(gid)?.name ?? gid;
        return `${name} is already in ${o.subjectName} in this slot.`;
      });
    }
  });

  // The subject's own window. `validate_assignments` does not re-check this --
  // the solver enforces it by never generating a variable outside the window --
  // so a hand move is the only way to land outside it, and the only place it can
  // be caught.
  const datesFor = new Map<string, Set<string>>();
  for (const subject of problem.subjects) {
    if (subjectSemester(subject, ref)) {
      datesFor.set(
        subject.id,
        new Set(subjectDates(subject, problem.groups, problem.slotConfig, ref)),
      );
    }
  }
  assignments.forEach((a, i) => {
    const dates = datesFor.get(a.subjectId);
    if (dates && !dates.has(a.date)) {
      add(i, `${a.subjectName} cannot run on ${a.date} — outside the dates it is spread across.`);
    }
  });

  return out;
}

/** Even spread, as grid-level notices rather than per-card flags.
 *
 *  HARD 7 caps a subject at ceil(N/W) sessions in any one teaching week, and
 *  "move to another week" is exactly the gesture that breaks it -- but the
 *  breach belongs to the week, not to any one of the sessions in it, so there is
 *  no single card to mark. */
export function spreadNotices(
  assignments: Assignment[],
  problem: Problem,
  ref: SemesterRef,
): string[] {
  const notices: string[] = [];
  for (const subject of problem.subjects) {
    const spec = subjectSemester(subject, ref);
    if (!spec) continue;
    const weeks = new Set(
      subjectDates(subject, problem.groups, problem.slotConfig, ref).map(isoWeek),
    );
    // The solver skips the constraint entirely below two weeks, and so must this.
    if (weeks.size < 2) continue;
    const ceiling = Math.ceil(spec.totalSessions / weeks.size);
    const perWeek = new Map<string, string[]>();
    for (const a of assignments) {
      if (a.subjectId !== subject.id) continue;
      const week = isoWeek(a.date);
      const dates = perWeek.get(week);
      if (dates) dates.push(a.date);
      else perWeek.set(week, [a.date]);
    }
    for (const [, dates] of [...perWeek.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      if (dates.length > ceiling) {
        notices.push(
          `${subject.name} now has ${dates.length} session(s) in the week of ` +
            `${dates.sort()[0]}; an even spread allows at most ${ceiling}.`,
        );
      }
    }
  }
  return notices;
}
