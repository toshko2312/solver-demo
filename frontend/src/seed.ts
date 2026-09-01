/** The two one-click example datasets.
 *  They live in ../../shared/ so the solver's tests and this UI exercise
 *  byte-identical numbers. */

import seedFullData from '../../shared/seed-full.json';
import seedSmallData from '../../shared/seed-small.json';
import { DEFAULT_ROLES } from './theme';
import type { Problem } from './types';

export function emptyProblem(): Problem {
  return {
    // The six-period academy day, so a blank project matches the examples.
    slotConfig: {
      days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
      periods: 6,
      periodTimes: [
        '08:00-09:30',
        '09:45-11:15',
        '11:30-13:00',
        '13:45-15:15',
        '15:30-17:00',
        '17:15-18:45',
      ],
      blockedSlots: [],
    },
    // A blank project still starts with the six ranks; they are ordinary data
    // from here on, editable under Data setup -> Roles.
    roles: DEFAULT_ROLES.map((r) => ({ ...r })),
    teachers: [],
    rooms: [],
    groups: [],
    subjects: [],
  };
}

function load(data: unknown): Problem {
  const { slotConfig, roles, teachers, rooms, groups, subjects } = data as Problem;
  // Deep copy: the UI mutates the loaded problem freely.
  return JSON.parse(
    JSON.stringify({ slotConfig, roles, teachers, rooms, groups, subjects }),
  ) as Problem;
}

/** One курс: solves in a fraction of a second and stays readable in the grid. */
export function seedSmall(): Problem {
  return load(seedSmallData);
}

/** All four years of Факултет "Полиция" -- realistic, and a hard instance. */
export function seedFull(): Problem {
  return load(seedFullData);
}

export function nextId(prefix: string, existing: { id: string }[]): string {
  let n = existing.length + 1;
  const taken = new Set(existing.map((e) => e.id));
  while (taken.has(`${prefix}${n}`)) n++;
  return `${prefix}${n}`;
}
