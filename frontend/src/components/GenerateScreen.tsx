import { useEffect, useState } from 'react';

import { Button } from './ds/Button';
import { countNonDefault, formatLimit } from '../settings';
import { openSlots } from '../slots';
import type { Problem, RunState, SolveResponse, SolverSettings } from '../types';

interface Props {
  problem: Problem;
  run: RunState;
  result: SolveResponse | null;
  error: string | null;
  settings: SolverSettings;
  onOpenSettings: () => void;
  onGenerate: () => void;
  onGoResult: () => void;
  onGoData: () => void;
}

export function GenerateScreen({
  problem,
  run,
  result,
  error,
  settings,
  onOpenSettings,
  onGenerate,
  onGoResult,
  onGoData,
}: Props) {
  // With no time limit a solve can run for a while; a ticking clock is the
  // difference between "working" and "hung" as far as the user can tell.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (run !== 'solving') return;
    setElapsed(0);
    const started = Date.now();
    const id = setInterval(() => setElapsed((Date.now() - started) / 1000), 100);
    return () => clearInterval(id);
  }, [run]);

  const changedCount = countNonDefault(settings);
  const open = openSlots(problem.slotConfig).length;
  const sessions = problem.subjects.reduce((n, s) => n + s.sessionsPerWeek, 0);
  const stats = result?.stats ?? null;
  // Always describe the run by the settings it was solved with, never by the ones
  // currently on screen -- those may have been changed since.
  const used = result?.settingsUsed ?? settings;

  const summary = [
    { value: problem.teachers.length, label: 'Teachers' },
    { value: problem.rooms.length, label: 'Rooms' },
    { value: problem.groups.length, label: 'Groups' },
    { value: problem.subjects.length, label: 'Subjects' },
    { value: open, label: 'Open slots' },
    { value: sessions, label: 'Sessions needed' },
  ];

  const headline =
    run === 'solving'
      ? 'Solving'
      : run === 'solved'
        ? result?.status === 'OPTIMAL'
          ? 'Optimal'
          : 'Feasible'
        : run === 'failed'
          ? result?.status === 'MODEL_INVALID'
            ? 'Invalid problem'
            : 'No solution found'
          : run === 'error'
            ? 'Solver unreachable'
            : 'Idle';

  return (
    <div className="screen gen">
      <section className="card card--pad">
        <div className="gen__runrow">
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div className="display-md">Run the scheduler</div>
            <div className="muted" style={{ marginTop: 4, maxWidth: 620 }}>
              Hard rules: no teacher, group or room double-booked; the room type must match the
              subject and hold every student; blocked slots are excluded. Teacher slot preferences
              and compact group days are optimised, not guaranteed.
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div className="muted-sm" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>
                {formatLimit(settings.maxTimeInSeconds)} · {settings.search.numWorkers} worker
                {settings.search.numWorkers === 1 ? '' : 's'} · presolve{' '}
                {settings.search.presolve ? 'on' : 'off'}
              </span>
              {changedCount > 0 && (
                <span className="badge badge--warn">{changedCount} non-default</span>
              )}
              <button className="microbtn" onClick={onOpenSettings}>
                Settings
              </button>
            </div>
            <Button variant="primary" large onClick={onGenerate} disabled={run === 'solving'}>
              {run === 'solving' ? 'Solving…' : 'Generate timetable'}
            </Button>
          </div>
        </div>

        <div className="summary">
          {summary.map((s) => (
            <div key={s.label} className="summary__tile">
              <div className="summary__value">{s.value}</div>
              <div className="summary__label">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="card card--pad">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span
            className={`statusdot ${
              run === 'solved'
                ? 'statusdot--ok'
                : run === 'failed' || run === 'error'
                  ? 'statusdot--fail'
                  : run === 'solving'
                    ? 'statusdot--busy'
                    : ''
            }`}
          />
          <span className="display-sm">{headline}</span>
          <span className="muted-sm">{result?.message ?? error ?? 'No run in this session yet.'}</span>
        </div>

        {run === 'solving' && (
          <div style={{ marginTop: 16 }}>
            <div className="sweep">
              <div className="sweep__bar" />
            </div>
            <div className="muted-sm" style={{ marginTop: 10 }}>
              CP-SAT is propagating hard constraints and minimising the soft penalty. The result
              arrives as soon as the search finishes; if it hits the{' '}
              {formatLimit(settings.maxTimeInSeconds)} limit first, the best schedule found so far is
              returned.{' '}
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{elapsed.toFixed(1)}s elapsed</span>
            </div>
          </div>
        )}

        {run === 'error' && (
          <div className="failbox" style={{ marginTop: 16 }}>
            <div className="hint__title">Could not reach the solver service</div>
            <div className="hint__detail">{error}</div>
            <div className="hint__detail" style={{ marginTop: 6 }}>
              Check that it is running on port 8000 (<code>curl localhost:8000/health</code>).
            </div>
          </div>
        )}

        {run === 'solved' && stats && (
          <>
            <div className="statgrid" style={{ marginTop: 16 }}>
              <div className="statgrid__tile">
                <div className="eyebrow">Time taken</div>
                <div className="statgrid__value">{stats.solveTimeSeconds.toFixed(2)} s</div>
                <div className="statgrid__note">
                  limit {formatLimit(used.maxTimeInSeconds)} · {used.search.numWorkers}w ·{' '}
                  {stats.numBooleanVariables} booleans
                </div>
              </div>
              <div className="statgrid__tile">
                <div className="eyebrow">Result</div>
                <div className="statgrid__value">{stats.status}</div>
                <div className="statgrid__note">
                  {stats.status === 'OPTIMAL'
                    ? 'Proven minimum penalty'
                    : 'Best found in the time limit'}
                </div>
              </div>
              <div className="statgrid__tile">
                <div className="eyebrow">Soft penalty</div>
                <div className="statgrid__value">{stats.objectiveValue ?? 0}</div>
                <div className="statgrid__note">
                  {stats.preferenceViolations} preference miss(es) · {stats.gapPenalty} group gap(s)
                </div>
              </div>
              <div className="statgrid__tile">
                <div className="eyebrow">Sessions placed</div>
                <div className="statgrid__value">
                  {stats.numPlaced} / {stats.numSessions}
                </div>
                <div className="statgrid__note">across {stats.numSlots} open slots</div>
              </div>
            </div>

            <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span className={`badge ${result?.validation?.ok ? 'badge--ok' : 'badge--bad'}`}>
                {result?.validation?.ok
                  ? 'Independent re-check: all hard rules hold'
                  : 'Independent re-check FAILED'}
              </span>
              {stats.preferenceViolations > 0 && (
                <span className="badge badge--warn">
                  {stats.preferenceViolations} soft preference(s) not met
                </span>
              )}
            </div>

            {result?.validation && !result.validation.ok && (
              <div className="failbox" style={{ marginTop: 14 }}>
                {result.validation.errors.map((e) => (
                  <div key={e} className="hint__detail">
                    {e}
                  </div>
                ))}
              </div>
            )}

            {result && result.assignments.some((a) => a.softViolated) && (
              <div className="penalty">
                {result.assignments
                  .filter((a) => a.softViolated)
                  .map((a) => (
                    <div key={`${a.subjectId}-${a.slot}`} style={{ marginBottom: 4 }}>
                      <strong>{a.teacherName}</strong> — {a.softReason}
                    </div>
                  ))}
              </div>
            )}

            <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button variant="primary" onClick={onGoResult}>
                View timetable
              </Button>
            </div>
          </>
        )}

        {run === 'failed' && result && (
          <>
            <div className="failbox" style={{ marginTop: 16 }}>
              <div className="hint__title" style={{ marginBottom: 10 }}>
                {result.status === 'MODEL_INVALID'
                  ? 'The problem definition is inconsistent'
                  : 'Hard constraints cannot all be satisfied'}
              </div>
              {result.hints.map((h) => (
                <div key={h.title} className="hint">
                  <span className="hint__marker" />
                  <div>
                    <div className="hint__title">{h.title}</div>
                    <div className="hint__detail">{h.detail}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="muted-sm" style={{ marginTop: 10 }}>
              The solver ran and proved this — it did not crash. Solve time{' '}
              {stats ? stats.solveTimeSeconds.toFixed(2) : '0.00'} s.
            </div>
            <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button variant="primary" onClick={onGoData}>
                Review input data
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
