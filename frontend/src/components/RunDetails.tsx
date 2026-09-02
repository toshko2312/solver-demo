import { Button } from './ds/Button';
import { formatLimit } from '../settings';
import type { RunState, SolveResponse, SolverSettings } from '../types';

interface Props {
  run: RunState;
  result: SolveResponse | null;
  error: string | null;
  /** The settings the run was actually solved with, not the ones on screen now. */
  used: SolverSettings;
  onGoResult: () => void;
  onGoData: () => void;
}

/** Everything one finished run has to say: the headline stats, the independent
 *  re-check, the priority ladder, the soft-preference misses, and the reasons a
 *  failed run gives.
 *
 *  Lifted out of GenerateScreen unchanged when that screen went from showing one
 *  run to listing every run -- this is the body of each accordion row.
 */
export function RunDetails({ run, result, error, used, onGoResult, onGoData }: Props) {
  const stats = result?.stats ?? null;
  return (
    <>
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
                {stats.preferenceViolations} preference miss(es) · {stats.roomPreferencePenalty}{' '}
                room cost · {stats.gapPenalty} group gap(s)
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

          {stats.tiers.length > 0 && (
            <div className="ladder" style={{ marginTop: 14 }}>
              <div className="eyebrow">Priority ladder — highest rank settled first</div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th className="right">Teachers</th>
                    <th className="right">Penalty</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.tiers.map((tier) => (
                    <tr key={tier.weight}>
                      <td className="name">
                        {tier.roles.length > 0 ? tier.roles.join(' · ') : 'unranked'}{' '}
                        <span className="muted-sm">w{tier.weight}</span>
                      </td>
                      <td className="right">{tier.teacherCount}</td>
                      <td className="right">{tier.penalty}</td>
                      <td>
                        {tier.status === 'OPTIMAL' ? (
                          <span className="muted-sm">best possible · {tier.solveTimeSeconds}s</span>
                        ) : (
                          <span className="badge badge--warn">
                            {tier.status} — ran out of time, so the ranks below it were held to a
                            number this one might have improved on
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
    </>
  );
}
