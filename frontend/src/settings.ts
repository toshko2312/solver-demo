import type { SolverSettings } from './types';

/** The solver hard-caps a single solve at this (MAX_SOLVE_SECONDS in
 *  solver/app/models.py); the API rejects anything larger. */
export const MAX_SOLVE_SECONDS = 20 * 60;

/** Mirrors DEFAULT_SOLVE_SECONDS in solver/app/models.py. The full seed is a hard
 *  instance that would otherwise run to the ceiling every time. */
export const DEFAULT_SOLVE_SECONDS = 30;

/** Must match the field defaults in solver/app/models.py. */
export function defaultSettings(): SolverSettings {
  return {
    maxTimeInSeconds: DEFAULT_SOLVE_SECONDS,
    preferenceWeight: 10,
    gapWeight: 1,
    stopAfterFirstSolution: false,
    useSymmetryBreaking: true,
    search: {
      numWorkers: 8,
      randomSeed: 0,
      presolve: true,
      symmetryLevel: null,
      linearizationLevel: null,
    },
  };
}

/** How many knobs differ from the defaults. Drives the "settings changed" chip,
 *  so a surprising result is never a mystery. */
export function countNonDefault(settings: SolverSettings): number {
  const base = defaultSettings();
  let n = 0;
  for (const key of Object.keys(base) as (keyof SolverSettings)[]) {
    if (key === 'search') continue;
    if (settings[key] !== base[key]) n++;
  }
  for (const key of Object.keys(base.search) as (keyof SolverSettings['search'])[]) {
    if (settings.search[key] !== base.search[key]) n++;
  }
  return n;
}

/** 1200 -> "20 min", 60 -> "1 min", 10 -> "10 s". */
export function formatLimit(seconds: number): string {
  if (seconds % 60 === 0 && seconds >= 60) return `${seconds / 60} min`;
  return `${seconds} s`;
}
