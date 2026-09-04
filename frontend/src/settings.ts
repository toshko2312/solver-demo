import type { SolverSettings } from './types';

/** Mirrors DEFAULT_SOLVE_SECONDS in solver/app/models.py: no deadline at all.
 *
 *  A faculty-sized semester takes about ninety seconds just to find its first
 *  legal timetable, so any budget short enough to feel like a demo comes back
 *  UNKNOWN with nothing placed — a worse answer than a slow one. An unlimited
 *  run always returns the best timetable it found. The cost is that the request
 *  stays open for the whole run; set a limit in Settings when that matters. */
export const DEFAULT_SOLVE_SECONDS: number | null = null;

/** Mirrors DEMO_SOLVE_SECONDS: the "quick look" preset, and what the small
 *  example finishes comfortably inside. */
export const DEMO_SOLVE_SECONDS = 30;

/** Must match the field defaults in solver/app/models.py. */
export function defaultSettings(): SolverSettings {
  return {
    maxTimeInSeconds: DEFAULT_SOLVE_SECONDS,
    preferenceWeight: 10,
    roomPreferenceWeight: 5,
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

/** 1200 -> "20 min", 60 -> "1 min", 10 -> "10 s", null -> "Unlimited". */
export function formatLimit(seconds: number | null): string {
  if (seconds === null) return 'Unlimited';
  if (seconds % 60 === 0 && seconds >= 60) return `${seconds / 60} min`;
  return `${seconds} s`;
}
