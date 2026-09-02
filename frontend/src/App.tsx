import { useState } from 'react';

import { DataScreen } from './components/DataScreen';
import { GenerateScreen } from './components/GenerateScreen';
import { ResultScreen } from './components/ResultScreen';
import { Button } from './components/ds/Button';
import { solveStream } from './api';
import { SettingsDialog } from './components/SettingsDialog';
import { emptyProblem, seedFull, seedSmall } from './seed';
import { defaultSettings } from './settings';
import { knownSemesters, sessionsIn } from './slots';
import { semesterKey } from './types';
import type { Problem, RunState, SemesterRef, SolveProgress, SolveResponse } from './types';

type Screen = 'data' | 'generate' | 'result';

export function App() {
  // The whole problem lives here: no database, no server-side session. It is
  // POSTed to the solver in full every time you press Generate.
  const [problem, setProblem] = useState<Problem>(emptyProblem);
  const [screen, setScreen] = useState<Screen>('data');
  // One timetable per semester, and one run state per semester alongside it:
  // several semesters can be solving at once, and each has to report its own
  // progress, its own error and its own clock.
  const [results, setResults] = useState<Record<string, SolveResponse>>({});
  const [runs, setRuns] = useState<Record<string, RunState>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [startedAt, setStartedAt] = useState<Record<string, number>>({});
  // Live phase progress for the runs in flight, streamed from the solver.
  const [progress, setProgress] = useState<Record<string, SolveProgress>>({});
  const [semester, setSemester] = useState<SemesterRef | null>(null);
  // Bumped by every edit to the input data. A result records the version it was
  // solved from, so "does this grid still match the data?" is one comparison
  // rather than a dependency analysis that would be quietly wrong.
  const [dataVersion, setDataVersion] = useState(0);
  const [resultVersions, setResultVersions] = useState<Record<string, number>>({});

  const semesters = knownSemesters(problem.groups);
  // Default to the first semester that actually has sessions to place, not just
  // the first on the calendar: a group can carry dates for a future year long
  // before any subject runs in it, and defaulting there offers a solve of nothing.
  const firstWithWork =
    semesters.find((x) => problem.subjects.some((s) => sessionsIn(s, x) > 0)) ?? semesters[0];
  const active = semester ?? firstWithWork ?? null;
  const activeKey = active ? semesterKey(active) : null;
  const result = activeKey ? (results[activeKey] ?? null) : null;
  const run: RunState = activeKey ? (runs[activeKey] ?? 'empty') : 'empty';
  const error = activeKey ? (errors[activeKey] ?? null) : null;
  const stale =
    activeKey !== null &&
    results[activeKey] !== undefined &&
    resultVersions[activeKey] !== dataVersion;
  // How many *other* semesters are still solving -- a background run must never
  // be invisible just because you are looking at a different semester.
  const solvingElsewhere = Object.entries(runs).filter(
    ([key, state]) => state === 'solving' && key !== activeKey,
  ).length;

  /** Move one session of the semester on screen to another slot.
   *
   *  A hand edit, not a data change: it must not go through `editProblem`, whose
   *  version bump would mark every semester's timetable stale, and it leaves
   *  `resultVersions` alone -- the input data has not moved, so the grid is not
   *  out of date with it. Regenerating is the reset; nothing here is undoable.
   */
  const moveSession = (index: number, slot: string, date: string) => {
    if (!activeKey) return;
    setResults((prev) => {
      const stored = prev[activeKey];
      if (!stored) return prev;
      return {
        ...prev,
        [activeKey]: {
          ...stored,
          assignments: stored.assignments.map((a, i) => (i === index ? { ...a, slot, date } : a)),
        },
      };
    });
  };

  const pickSemester = (next: SemesterRef) => setSemester(next);

  // Solver knobs live here alongside the problem, and are sent with every solve.
  const [settings, setSettings] = useState(defaultSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const generate = async () => {
    if (!active) return;
    // Captured before the await: several runs can be in flight at once, and the
    // semester on screen may have changed by the time this one lands. Every write
    // below is keyed on the semester this run was started for.
    const key = semesterKey(active);
    const version = dataVersion;
    if (runs[key] === 'solving') return;

    setRuns((prev) => ({ ...prev, [key]: 'solving' }));
    setErrors((prev) => ({ ...prev, [key]: null }));
    setStartedAt((prev) => ({ ...prev, [key]: Date.now() }));
    setProgress((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setScreen('generate');
    try {
      const response = await solveStream(problem, active, settings, (p) =>
        setProgress((prev) => ({ ...prev, [key]: p })),
      );
      // Replaces whatever this semester had; the others are left alone. The
      // version is the one captured at the top, so a run that overlapped an edit
      // arrives already marked stale -- which is the truth about it.
      setResults((prev) => ({ ...prev, [key]: response }));
      setResultVersions((prev) => ({ ...prev, [key]: version }));
      const ok = response.status === 'OPTIMAL' || response.status === 'FEASIBLE';
      // INFEASIBLE / UNKNOWN / MODEL_INVALID: the solver ran and reported back.
      setRuns((prev) => ({ ...prev, [key]: ok ? 'solved' : 'failed' }));
      setProgress((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    } catch (e) {
      setResults((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setErrors((prev) => ({ ...prev, [key]: e instanceof Error ? e.message : String(e) }));
      setRuns((prev) => ({ ...prev, [key]: 'error' }));
      setProgress((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const loadSeed = (build: () => Problem) => {
    setProblem(build());
    setResults({});
    setResultVersions({});
    setRuns({});
    setErrors({});
    setStartedAt({});
    setProgress({});
    setSemester(null);
    setScreen('data');
  };

  const editProblem = (next: Problem) => {
    setProblem(next);
    // Timetables are kept, not discarded: one can take minutes to prove optimal,
    // and an edit is not a reason to throw that away. Bumping the version is what
    // marks every existing grid as generated from data that has since moved.
    setDataVersion((v) => v + 1);
  };

  const baseStatus =
    run === 'solving'
      ? 'Solving…'
      : run === 'solved'
        ? `${result?.status === 'OPTIMAL' ? 'Optimal' : 'Feasible'} · penalty ${result?.stats?.objectiveValue ?? 0}`
        : run === 'failed'
          ? result?.status === 'MODEL_INVALID'
            ? 'Invalid problem'
            : 'No solution found'
          : run === 'error'
            ? 'Solver unreachable'
            : 'Not generated';

  // The pill describes the semester on screen, then says what is happening off it.
  const statusLabel =
    baseStatus +
    (stale ? ' · stale' : '') +
    (solvingElsewhere ? ` · ${solvingElsewhere} solving` : '');

  const statusDot =
    run === 'solved'
      ? 'statusdot--ok'
      : run === 'failed' || run === 'error'
        ? 'statusdot--fail'
        : run === 'solving'
          ? 'statusdot--busy'
          : '';

  const contextNote =
    screen === 'data'
      ? 'Input data — edits mark existing timetables stale'
      : screen === 'result'
        ? 'Generated result — regenerate to pick up data changes'
        : 'Solver';

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__title">Timetable Generator</span>
          <span className="topbar__sub">OR-Tools CP-SAT · proof of concept</span>
        </div>
        <div className="topbar__right">
          <div className="statuspill">
            <span className={`statusdot ${statusDot}`} />
            <span>{statusLabel}</span>
          </div>
          <Button variant="secondary-pill" onClick={() => loadSeed(seedSmall)}>
            Small example
          </Button>
          <Button variant="secondary-pill" onClick={() => loadSeed(seedFull)}>
            Full example
          </Button>
          <Button variant="primary" onClick={generate} disabled={run === 'solving'}>
            {run === 'solving' ? 'Solving…' : stale ? 'Regenerate' : 'Generate'}
          </Button>
        </div>
      </header>

      <nav className="tabbar">
        {(
          [
            ['data', 'Data setup'],
            ['generate', 'Generate'],
            ['result', 'Timetable'],
          ] as [Screen, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            className={`tabbar__tab${screen === key ? ' tabbar__tab--active' : ''}`}
            onClick={() => setScreen(key)}
          >
            {label}
          </button>
        ))}
        <span className="tabbar__note">{contextNote}</span>
      </nav>

      {screen === 'data' && <DataScreen problem={problem} onChange={editProblem} />}

      {screen === 'generate' && (
        <GenerateScreen
          problem={problem}
          semester={active}
          semesters={semesters}
          onPickSemester={pickSemester}
          runs={runs}
          results={results}
          progress={progress}
          starts={startedAt}
          errors={errors}
          run={run}
          result={result}
          error={error}
          stale={stale}
          settings={settings}
          onOpenSettings={() => setSettingsOpen(true)}
          onGenerate={generate}
          onGoResult={() => setScreen('result')}
          onGoData={() => setScreen('data')}
        />
      )}

      {settingsOpen && (
        <SettingsDialog
          settings={settings}
          onChange={setSettings}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {screen === 'result' && (
        <ResultScreen
          problem={problem}
          semester={active}
          semesters={semesters}
          results={results}
          runs={runs}
          staleKeys={Object.keys(results).filter((k) => resultVersions[k] !== dataVersion)}
          onPickSemester={pickSemester}
          run={run}
          result={result}
          stale={stale}
          onGenerate={generate}
          onMoveSession={moveSession}
          onGoData={() => setScreen('data')}
          onGoGenerate={() => setScreen('generate')}
        />
      )}
    </div>
  );
}
