/** Colour vocabulary lifted from the design mock.
 *  Room types get fixed colours; subjects are user-created, so they cycle
 *  through the mock's subject palette in list order. */

import type { Role, RoomType } from './types';

export interface Swatch {
  c: string;
  tint: string;
  ink?: string;
}

export const ROOM_TYPES: RoomType[] = ['lecture', 'lab', 'sports', 'firing_range', 'training_ground'];

export const ROOM_TYPE_LABEL: Record<RoomType, string> = {
  lecture: 'Lecture hall',
  lab: 'Computer lab',
  sports: 'Sports hall',
  firing_range: 'Firing range',
  training_ground: 'Training ground',
};

/** The ranks a blank project starts with. Must stay in step with DEFAULT_ROLES
 *  in solver/app/models.py -- the ids especially, which are what a request
 *  omitting `roles` falls back to on the solver side. */
export const DEFAULT_ROLES: Role[] = [
  { id: 'professor', name: 'проф. — Professor', short: 'проф.', weight: 6 },
  { id: 'associate_professor', name: 'доц. — Assoc. Professor', short: 'доц.', weight: 5 },
  { id: 'chief_assistant', name: 'гл. ас. — Chief Assistant', short: 'гл. ас.', weight: 4 },
  { id: 'senior_lecturer', name: 'ст. преп. — Senior Lecturer', short: 'ст. преп.', weight: 3 },
  { id: 'lecturer', name: 'преп. — Lecturer', short: 'преп.', weight: 2 },
  { id: 'assistant', name: 'ас. — Assistant', short: 'ас.', weight: 1 },
];

/** Mirrors UNRANKED_WEIGHT: a teacher with no stated rank shares the bottom tier. */
export const UNRANKED_WEIGHT = 1;

/** Mirrors effective_weight() in solver/app/models.py. */
export function effectiveWeight(
  t: { role?: string | null; priorityWeight?: number | null },
  roles: Role[],
): number {
  if (t.priorityWeight != null) return t.priorityWeight;
  if (t.role != null) {
    const role = roles.find((r) => r.id === t.role);
    if (role) return role.weight;
  }
  return UNRANKED_WEIGHT;
}

export const ROOM_TYPE_COLOR: Record<RoomType, Swatch> = {
  lecture: { c: '#0066cc', tint: '#e9f1fb', ink: '#0a4f9e' },
  lab: { c: '#0f7b6c', tint: '#e6f3f1', ink: '#0b5c51' },
  sports: { c: '#1f7a3d', tint: '#e8f4ec', ink: '#175c2e' },
  firing_range: { c: '#9a2c2c', tint: '#f9ecec', ink: '#7d1f1f' },
  training_ground: { c: '#7a5c1f', tint: '#f5efe2', ink: '#5f4715' },
};

// Sixteen hues: a faculty timetable runs to dozens of subjects, and eight
// colours would repeat every eight rows of the table.
const SUBJECT_PALETTE: Swatch[] = [
  { c: '#0066cc', tint: '#e9f1fb' },
  { c: '#0f7b6c', tint: '#e6f3f1' },
  { c: '#5e5ce6', tint: '#ecebfd' },
  { c: '#b1560f', tint: '#fbefe4' },
  { c: '#1f7a3d', tint: '#e8f4ec' },
  { c: '#9a2c2c', tint: '#f9ecec' },
  { c: '#4a4a52', tint: '#eeeef1' },
  { c: '#a8327d', tint: '#f9e9f3' },
  { c: '#1d6fa5', tint: '#e7f1f7' },
  { c: '#6b7f1c', tint: '#f1f4e3' },
  { c: '#7a5c1f', tint: '#f5efe2' },
  { c: '#8b3fa0', tint: '#f4eaf7' },
  { c: '#2f6f6a', tint: '#e8f2f1' },
  { c: '#c04b2f', tint: '#fceee9' },
  { c: '#3a5da8', tint: '#eaeff9' },
  { c: '#96631f', tint: '#f8f0e2' },
];

export function subjectColor(subjectIds: string[], subjectId: string): Swatch {
  const i = subjectIds.indexOf(subjectId);
  return SUBJECT_PALETTE[(i < 0 ? 0 : i) % SUBJECT_PALETTE.length];
}
