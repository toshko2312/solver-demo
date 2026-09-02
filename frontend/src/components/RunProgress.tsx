import { useEffect, useState } from 'react';

import { formatLimit } from '../settings';
import type { SolveProgress } from '../types';

interface Props {
  /** null until the solver's first event arrives, or when the stream is unavailable. */
  progress: SolveProgress | null;
  startedAt: number | null;
  limit: number | null;
}

/** What a solve in flight is actually doing.
 *
 *  The bar is driven by the solver's own phase boundaries, not by elapsed time:
 *  the priority ladder runs a fixed sequence -- build the model, find any legal
 *  timetable, then settle one rank tier at a time, then the gaps -- and the count
 *  is known before the first second of search. So the bar only ever moves
 *  forwards, and each step means a rank has been settled.
 *
 *  Before the first event, and against a server with no streaming endpoint, it
 *  falls back to the indeterminate sweep -- which is the honest thing to show
 *  when there is nothing to count.
 */
export function RunProgress({ progress, startedAt, limit }: Props) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (startedAt === null) return;
    // Counted from when this semester's run started, not from when the clock was
    // mounted: several runs can be in flight, each with its own start.
    const tick = () => setElapsed((Date.now() - startedAt) / 1000);
    tick();
    const id = setInterval(tick, 100);
    return () => clearInterval(id);
  }, [startedAt]);

  const phases = progress && progress.total > 0 ? progress.total : 0;
  const done = progress ? progress.phase : 0;

  const label = !progress
    ? 'starting'
    : progress.phase === 0
      ? 'building the model'
      : progress.label === 'warmup'
        ? 'finding a first timetable'
        : progress.label === 'gap'
          ? 'compacting group days'
          : progress.roles.length > 0
            ? `settling ${progress.roles.join(' · ')}`
            : 'settling preferences';

  return (
    <>
      <span className="runrow__meta">
        <span>{label}</span>
        {progress?.best != null && <span>· penalty {Math.round(progress.best)}</span>}
      </span>
      {phases > 0 ? (
        <span className="progress" title={`Phase ${done} of ${phases}`}>
          {/* Half a step of credit for the phase in flight: it has started, and a
              bar that only moves when a rung *finishes* looks stuck for minutes. */}
          <span
            className="progress__fill"
            style={{ width: `${Math.min(100, ((done - 0.5) / phases) * 100)}%` }}
          />
        </span>
      ) : (
        <span className="sweep" style={{ width: 180 }}>
          <span className="sweep__bar" />
        </span>
      )}
      <span className="runrow__count">
        {phases > 0 ? `${done} of ${phases} · ` : ''}
        {elapsed.toFixed(1)}s
        {limit !== null ? ` of ${formatLimit(limit)}` : ''}
      </span>
    </>
  );
}
