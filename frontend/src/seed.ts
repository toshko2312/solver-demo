/** The two one-click example datasets.
 *  They live in ../../shared/ so the solver's tests and this UI exercise
 *  byte-identical numbers. */

import seedFullData from '../../shared/seed-full.json';
import seedSmallData from '../../shared/seed-small.json';
import { DEFAULT_ROLES } from './theme';
import type { Problem } from './types';

/** The academy's day: six periods of 90 minutes, each two academic hours -- so a
 *  full day is the twelve academic hours a учебен план counts in. The обедна
 *  почивка is the 13:00-13:45 gap between period 3 and period 4: a break defined
 *  by absence, which needs no field and no rule because no period covers it. */
export const ACADEMY_PERIOD_TIMES = [
  '08:00-09:30',
  '09:45-11:15',
  '11:30-13:00',
  '13:45-15:15',
  '15:30-17:00',
  '17:15-18:45',
];

export function emptyProblem(): Problem {
  return {
    slotConfig: {
      // Saturday included: курсанти have Saturday classes.
      days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
      periods: ACADEMY_PERIOD_TIMES.length,
      periodTimes: [...ACADEMY_PERIOD_TIMES],
      blockedSlots: [],
    },
    // A blank project still starts with the seven ranks; they are ordinary data
    // from here on, editable under Data setup -> Roles.
    roles: DEFAULT_ROLES.map((r) => ({ ...r })),
    faculties: [],
    katedri: [],
    specialties: [],
    courseInstances: [],
    teachers: [],
    rooms: [],
    groups: [],
    subgroups: [],
    subjects: [],
    offerings: [],
  };
}

const KEYS = [
  'slotConfig',
  'roles',
  'faculties',
  'katedri',
  'specialties',
  'courseInstances',
  'teachers',
  'rooms',
  'groups',
  'subgroups',
  'subjects',
  'offerings',
] as const;

function load(data: unknown): Problem {
  const source = data as Record<string, unknown>;
  const picked: Record<string, unknown> = {};
  for (const key of KEYS) picked[key] = source[key];
  // Deep copy: the UI mutates the loaded problem freely.
  return JSON.parse(JSON.stringify(picked)) as Problem;
}

/** One курс of Факултет "Полиция", both semesters of 2025/2026: solves quickly
 *  and stays readable. A solve covers one semester; the picker on the Generate
 *  screen chooses which. */
export function seedSmall(): Problem {
  return load(seedSmallData);
}

/** All four курса plus a задочен, in both semesters of 2025/2026 -- realistic,
 *  and a hard instance in either term. */
export function seedFull(): Problem {
  return load(seedFullData);
}

export function nextId(prefix: string, existing: { id: string }[]): string {
  let n = existing.length + 1;
  const taken = new Set(existing.map((e) => e.id));
  while (taken.has(`${prefix}${n}`)) n++;
  return `${prefix}${n}`;
}
