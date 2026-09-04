/** Colour vocabulary lifted from the design mock.
 *  Room types get fixed colours; subjects are user-created, so they cycle
 *  through the mock's subject palette in list order. */

import type { Role, RoomType } from './types';

export interface Swatch {
  c: string;
  tint: string;
  ink?: string;
}

export const ROOM_TYPES: RoomType[] = [
  'зала',
  'малка зала',
  'компютърна зала',
  'стрелбище',
  'полигон',
  'спортен комплекс',
  'тренажорна зала',
];

/** The type *is* its Bulgarian name, so the label is the value. Kept as a map
 *  because every table and legend reads through it, and an English gloss would
 *  have to go somewhere if one were ever wanted. */
export const ROOM_TYPE_LABEL: Record<RoomType, string> = {
  'зала': 'Зала',
  'малка зала': 'Малка зала',
  'компютърна зала': 'Компютърна зала',
  'стрелбище': 'Стрелбище',
  'полигон': 'Полигон',
  'спортен комплекс': 'Спортен комплекс',
  'тренажорна зала': 'Тренажорна зала',
};

/** Room types that take one група or подгрупа at a time. The solver enforces
 *  Room.maxConcurrentGroups, whatever it is set to; this is what a new room of
 *  that type starts at, and what the form warns about raising. */
export const SINGLE_GROUP_ROOM_TYPES: RoomType[] = ['стрелбище', 'малка зала'];

/** The ranks a blank project starts with. Must stay in step with DEFAULT_ROLES
 *  in solver/app/models.py -- the ids especially, which are what a request
 *  omitting `roles` falls back to on the solver side. */
export const DEFAULT_ROLES: Role[] = [
  { id: 'professor', name: 'проф. — Professor', short: 'проф.', weight: 7 },
  { id: 'associate_professor', name: 'доц. — Assoc. Professor', short: 'доц.', weight: 6 },
  { id: 'chief_assistant', name: 'гл. ас. — Chief Assistant', short: 'гл. ас.', weight: 5 },
  { id: 'assistant', name: 'ас. — Assistant', short: 'ас.', weight: 4 },
  { id: 'senior_lecturer', name: 'ст. преп. — Senior Lecturer', short: 'ст. преп.', weight: 3 },
  { id: 'lecturer', name: 'преп. — Lecturer', short: 'преп.', weight: 2 },
  { id: 'honorary_lecturer', name: 'хон. преп. — Honorary Lecturer', short: 'хон. преп.', weight: 1 },
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
  'зала': { c: '#0066cc', tint: '#e9f1fb', ink: '#0a4f9e' },
  'малка зала': { c: '#3a5da8', tint: '#eaeff9', ink: '#2b4780' },
  'компютърна зала': { c: '#0f7b6c', tint: '#e6f3f1', ink: '#0b5c51' },
  'стрелбище': { c: '#9a2c2c', tint: '#f9ecec', ink: '#7d1f1f' },
  'полигон': { c: '#7a5c1f', tint: '#f5efe2', ink: '#5f4715' },
  'спортен комплекс': { c: '#1f7a3d', tint: '#e8f4ec', ink: '#175c2e' },
  'тренажорна зала': { c: '#6b7f1c', tint: '#f1f4e3', ink: '#4f5f15' },
};

/** Лекция / упражнение / практика, for the grid marker and the session card. */
export const ACTIVITY_MARKER: Record<string, string> = {
  'лекция': 'л',
  'упражнение': 'у',
  'практика': 'п',
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
