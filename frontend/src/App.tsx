import { useState } from 'react';

import { DataScreen } from './components/DataScreen';
import { GenerateScreen } from './components/GenerateScreen';
import { ResultScreen } from './components/ResultScreen';
import { Button } from './components/ds/Button';
import { solve } from './api';
import { SettingsDialog } from './components/SettingsDialog';
import { emptyProblem, seedFull, seedSmall } from './seed';
import { defaultSettings } from './settings';
import type { Problem, RunState, SolveResponse } from './types';

type Screen = 'data' | 'generate' | 'result';

export function App() {
  // The whole problem lives here: no database, no server-side session. It is
  // POSTed to the solver in full every time you press Generate.
  const [problem, setProblem] = useState<Problem>(emptyProblem);
  const [screen, setScreen] = useState<Screen>('data');
  const [run, setRun] = useState<RunState>('empty');
  const [result, setResult] = useState<SolveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Solver knobs live here alongside the problem, and are sent with every solve.
  const [settings, setSettings] = useState(defaultSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const generate = async () => {
    if (run === 'solving') return;
    setRun('solving');
    setError(null);
    setScreen('generate');
    try {
      const response = await solve(problem, settings);
      setResult(response);
      if (response.status === 'OPTIMAL' || response.status === 'FEASIBLE') {
        setRun('solved');
        setScreen('result');
      } else {
        // INFEASIBLE / UNKNOWN / MODEL_INVALID: the solver ran and reported back.
        setRun('failed');
      }
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
      setRun('error');
    }
  };

  const loadSeed = (build: () => Problem) => {
    setProblem(build());
    setResult(null);
    setRun('empty');
    setError(null);
    setScreen('data');
  };

  const editProblem = (next: Problem) => {
    setProblem(next);
    // Any edit invalidates the result: the grid on screen no longer matches the
    // data it was generated from.
    if (run === 'solved' || run === 'failed') {
      setRun('empty');
      setResult(null);
    }
  };

  const statusLabel =
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
      ? 'Input data — edits require a re-run'
      : screen === 'result'
        ? 'Generated result — read-only until re-run'
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
            {run === 'solving' ? 'Solving…' : 'Generate'}
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
          run={run}
          result={result}
          error={error}
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
          run={run}
          result={result}
          onGenerate={generate}
          onGoData={() => setScreen('data')}
          onGoGenerate={() => setScreen('generate')}
        />
      )}
    </div>
  );
}
