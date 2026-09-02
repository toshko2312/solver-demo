import { semesterSlots } from './slots';
import { defaultSettings } from './settings';
import type {
  Problem,
  SemesterRef,
  SolveProgress,
  SolveResponse,
  SolverSettings,
} from './types';

// Same-origin '/api' by default (Vite proxies it to the solver); override with
// VITE_API_URL to talk to a solver on another host.
const BASE = import.meta.env.VITE_API_URL ?? '/api';

function requestBody(
  problem: Problem,
  semester: SemesterRef,
  settings: SolverSettings,
): string {
  return JSON.stringify({
    semester,
    // The weekday template expanded across this semester's real dates.
    slots: semesterSlots(problem.slotConfig, problem.groups, semester),
    roles: problem.roles,
    teachers: problem.teachers,
    rooms: problem.rooms,
    groups: problem.groups,
    subjects: problem.subjects,
    ...settings,
  });
}

export async function solve(
  problem: Problem,
  semester: SemesterRef,
  settings: SolverSettings = defaultSettings(),
): Promise<SolveResponse> {
  const response = await fetch(`${BASE}/solve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: requestBody(problem, semester, settings),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Solver returned ${response.status}: ${body.slice(0, 400)}`);
  }
  return (await response.json()) as SolveResponse;
}

/** One event from `POST /solve/stream`, mirroring what solve_timetable emits. */
type SolveEvent =
  | { type: 'building'; sessions: number; slots: number; rooms: number; teachers: number }
  | { type: 'built'; numBooleanVariables: number; total: number; phases: unknown[] }
  | { type: 'phase'; index: number; total: number; label: string; roles: string[] }
  | { type: 'improved'; index: number; best: number; bound: number }
  | {
      type: 'phase_done';
      index: number;
      total: number;
      label: string;
      status: string;
      penalty: number | null;
      seconds: number;
    }
  | { type: 'done'; result: SolveResponse }
  | { type: 'error'; message: string };

/** The same solve as `solve()`, reporting progress as it goes.
 *
 *  EventSource cannot POST and the whole problem travels in the body, so this
 *  reads the server-sent stream off `fetch` by hand. A server without the
 *  streaming endpoint -- an older build behind the same proxy -- falls back to
 *  the plain call, which simply produces no progress.
 */
export async function solveStream(
  problem: Problem,
  semester: SemesterRef,
  settings: SolverSettings = defaultSettings(),
  onProgress?: (progress: SolveProgress) => void,
): Promise<SolveResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/solve/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: requestBody(problem, semester, settings),
    });
  } catch {
    return solve(problem, semester, settings);
  }
  if (response.status === 404 || response.status === 405 || !response.body) {
    return solve(problem, semester, settings);
  }
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Solver returned ${response.status}: ${body.slice(0, 400)}`);
  }

  const progress: SolveProgress = {
    phase: 0,
    total: 0,
    label: 'building',
    roles: [],
    best: null,
    bound: null,
    settled: [],
  };
  const report = () => onProgress?.({ ...progress, settled: [...progress.settled] });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: SolveResponse | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line; whatever trails is a partial
    // frame and waits for the next chunk.
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      const event = JSON.parse(line.slice(6)) as SolveEvent;
      switch (event.type) {
        case 'built':
          progress.total = event.total;
          report();
          break;
        case 'phase':
          progress.phase = event.index;
          progress.total = event.total;
          progress.label = event.label;
          progress.roles = event.roles;
          // A new phase optimises a different objective, so the last one's
          // numbers say nothing about this one.
          progress.best = null;
          progress.bound = null;
          report();
          break;
        case 'improved':
          progress.best = event.best;
          progress.bound = event.bound;
          report();
          break;
        case 'phase_done':
          progress.settled.push({
            label: event.label,
            roles: progress.roles,
            penalty: event.penalty,
            status: event.status,
          });
          report();
          break;
        case 'done':
          result = event.result;
          break;
        case 'error':
          throw new Error(event.message);
      }
    }
  }

  if (!result) throw new Error('The solver stream ended without a result.');
  return result;
}
