import { openSlots } from './slots';
import { defaultSettings } from './settings';
import type { Problem, SolveResponse, SolverSettings } from './types';

// Same-origin '/api' by default (Vite proxies it to the solver); override with
// VITE_API_URL to talk to a solver on another host.
const BASE = import.meta.env.VITE_API_URL ?? '/api';

export async function solve(
  problem: Problem,
  settings: SolverSettings = defaultSettings(),
): Promise<SolveResponse> {
  const response = await fetch(`${BASE}/solve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      slots: openSlots(problem.slotConfig),
      teachers: problem.teachers,
      rooms: problem.rooms,
      groups: problem.groups,
      subjects: problem.subjects,
      ...settings,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Solver returned ${response.status}: ${body.slice(0, 400)}`);
  }
  return (await response.json()) as SolveResponse;
}
