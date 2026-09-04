import { useEffect, type ReactNode } from 'react';

import { Accordion } from './ds/Accordion';
import { Button } from './ds/Button';
import { HelpTip } from './ds/HelpTip';
import { useBodyScrollLock } from './ds/useBodyScrollLock';
import { DEFAULT_SOLVE_SECONDS, DEMO_SOLVE_SECONDS, defaultSettings, formatLimit } from '../settings';
import type { SearchParams, SolverSettings } from '../types';

interface Props {
  settings: SolverSettings;
  onChange: (settings: SolverSettings) => void;
  onClose: () => void;
}

function Setting({
  label,
  help,
  meta,
  children,
}: {
  label: string;
  help: string;
  meta?: string;
  children: ReactNode;
}) {
  return (
    <div className="setting">
      <div style={{ minWidth: 0 }}>
        <div className="setting__label">
          {label}
          <HelpTip text={help} label={`What does "${label}" do?`} />
        </div>
        {meta && <div className="setting__meta">{meta}</div>}
      </div>
      <div className="setting__control">{children}</div>
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <>
      <button className={`microbtn${value ? ' microbtn--active' : ''}`} onClick={() => onChange(true)}>
        On
      </button>
      <button className={`microbtn${!value ? ' microbtn--active' : ''}`} onClick={() => onChange(false)}>
        Off
      </button>
    </>
  );
}

function Choice<T extends string | number | null>({
  options,
  value,
  onChange,
}: {
  options: [string, T][];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <>
      {options.map(([label, option]) => (
        <button
          key={label}
          className={`microbtn${value === option ? ' microbtn--active' : ''}`}
          onClick={() => onChange(option)}
        >
          {label}
        </button>
      ))}
    </>
  );
}

export function SettingsDialog({ settings, onChange, onClose }: Props) {
  useBodyScrollLock(true);
  const set = (patch: Partial<SolverSettings>) => onChange({ ...settings, ...patch });
  const setSearch = (patch: Partial<SearchParams>) =>
    onChange({ ...settings, search: { ...settings.search, ...patch } });

  // Escape closes, the way a dialog is expected to.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal__backdrop" onClick={onClose}>
      <div
        className="modal modal--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__head">
          <div>
            <div className="display-sm" id="settings-dialog-title">
              Solver settings
            </div>
            <div className="muted-sm" style={{ marginTop: 2 }}>
              Applied on the next run.
            </div>
          </div>
          <button className="linkbtn linkbtn--quiet" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="settings">
      <Accordion
        title="A · Objective"
        subtitle="Changes which timetable you get back."
        defaultOpen
      >
        <Setting
          label="Time limit"
          help="How long the scheduler is allowed to think. Given a limit it stops there and hands back the best timetable it has found so far; with no limit it runs until it proves it can do no better. A full faculty timetable will use every second you give it, so more time buys a better schedule rather than a faster answer."
          meta={`Default ${formatLimit(
            DEFAULT_SOLVE_SECONDS,
          )} — a faculty-sized semester needs about ninety seconds just to find its first legal timetable, so a short budget comes back with nothing placed. Unlimited can take hours on a hard problem, and the run cannot be stopped from here.`}
        >
          <Choice
            options={[
              ['10 s', 10],
              ['30 s', DEMO_SOLVE_SECONDS],
              ['2 min', 120],
              ['20 min', 20 * 60],
              ['Unlimited', null],
            ]}
            value={settings.maxTimeInSeconds}
            onChange={(v) => set({ maxTimeInSeconds: v })}
          />
          <input
            className="setting__number"
            type="number"
            min={1}
            disabled={settings.maxTimeInSeconds === null}
            value={settings.maxTimeInSeconds ?? ''}
            onChange={(e) => set({ maxTimeInSeconds: Math.max(1, Number(e.target.value)) })}
          />
          <span className="muted-sm">s</span>
        </Setting>

        <Setting
          label="Teacher preference weight"
          help="How much the scheduler cares about giving teachers the slots they asked for. Higher means it tries harder to keep them happy, even if students' days get more scattered."
          meta="Cost charged for each session placed outside its teacher's preferred slots."
        >
          <input
            className="setting__number"
            type="number"
            min={0}
            max={1000}
            value={settings.preferenceWeight}
            onChange={(e) =>
              set({ preferenceWeight: Math.min(1000, Math.max(0, Number(e.target.value))) })
            }
          />
        </Setting>

        <Setting
          label="Room preference weight"
          help="How much the scheduler cares about giving teachers the rooms they ranked. First choice is free; each place further down the list costs this much again. Ranking is scored per room type, so ranking labs says nothing about which sports hall you get."
          meta="Cost per rank step away from a teacher's first-choice room of that type. Below the slot weight by default: when both cannot be met, the slot is the one worth keeping."
        >
          <input
            className="setting__number"
            type="number"
            min={0}
            max={1000}
            value={settings.roomPreferenceWeight}
            onChange={(e) =>
              set({ roomPreferenceWeight: Math.min(1000, Math.max(0, Number(e.target.value))) })
            }
          />
        </Setting>

        <Setting
          label="Gap weight"
          help="How much the scheduler cares about avoiding free periods in the middle of a class's day. It orders solutions within the gap stage only: group gaps are settled last, after every teacher rank, so raising this can no longer buy a compact day at the price of a teacher preference."
          meta="Gaps are the final rung of the priority ladder. By the time they are considered every teacher tier is frozen at its best, so this weight cannot outbid a rank."
        >
          <input
            className="setting__number"
            type="number"
            min={0}
            max={1000}
            value={settings.gapWeight}
            onChange={(e) => set({ gapWeight: Math.min(1000, Math.max(0, Number(e.target.value))) })}
          />
        </Setting>

        <Setting
          label="Stop at first solution"
          help="Take the first workable timetable instead of the best one. Good for seeing the difference: the first one it finds breaks a dozen or so preferences, and improving it takes a fraction of a second."
          meta="On this dataset: penalty of roughly 115-140 with it on, 0 with it off."
        >
          <Toggle
            value={settings.stopAfterFirstSolution}
            onChange={(v) => set({ stopAfterFirstSolution: v })}
          />
        </Setting>
      </Accordion>

      <Accordion title="B · Search" subtitle="Same answer, different amount of work to reach it.">
        <p className="settings__warn">
          These do not change which timetables are legal — only how the solver looks for one. Some
          combinations are much slower; the time limit above still applies.
        </p>

        <Setting
          label="Parallel workers"
          help="How many different strategies the scheduler tries at once. More is usually faster. Setting it to 1 makes runs repeatable, which helps when comparing settings."
          meta="8 workers: ~520 branches. 1 worker: ~18,600 branches for the same answer."
        >
          <Choice
            options={[
              ['1', 1],
              ['2', 2],
              ['4', 4],
              ['8', 8],
              ['16', 16],
            ]}
            value={settings.search.numWorkers}
            onChange={(v) => setSearch({ numWorkers: v })}
          />
        </Setting>

        <Setting
          label="Random seed"
          help="Changes the scheduler's coin flips. With one worker the same seed always produces the same timetable; a different seed may produce a different but equally good one."
          meta="Only meaningful alongside a single worker — with several, timing decides the winner."
        >
          <input
            className="setting__number"
            type="number"
            min={0}
            value={settings.search.randomSeed}
            onChange={(e) => setSearch({ randomSeed: Math.max(0, Number(e.target.value)) })}
          />
        </Setting>

        <Setting
          label="Presolve"
          help="Lets the scheduler tidy up and simplify the problem before solving it. Usually a big win, though on a problem this small it sometimes costs more time than it saves."
          meta="On this dataset it is measurably faster with presolve off."
        >
          <Toggle value={settings.search.presolve} onChange={(v) => setSearch({ presolve: v })} />
        </Setting>

        <Setting
          label="Symmetry detection"
          help="How hard the scheduler looks for interchangeable pieces — like two identical lessons — so it doesn't waste time trying the same timetable twice in different clothes."
          meta="Auto leaves the solver's own default alone."
        >
          <Choice
            options={[
              ['Auto', null],
              ['0', 0],
              ['1', 1],
              ['2', 2],
              ['3', 3],
              ['4', 4],
            ]}
            value={settings.search.symmetryLevel}
            onChange={(v) => setSearch({ symmetryLevel: v })}
          />
        </Setting>

        <Setting
          label="Arithmetic reasoning"
          help="How much the scheduler leans on arithmetic-style reasoning alongside its logical reasoning. Higher can help when balancing numeric goals, but takes longer to set up."
          meta="CP-SAT calls this the linearization level."
        >
          <Choice
            options={[
              ['Auto', null],
              ['0', 0],
              ['1', 1],
              ['2', 2],
            ]}
            value={settings.search.linearizationLevel}
            onChange={(v) => setSearch({ linearizationLevel: v })}
          />
        </Setting>

        <Setting
          label="Our own symmetry shortcut"
          help="Our own shortcut: it tells the scheduler that a subject's lessons must be placed in time order, so it never tries every reshuffle of the same lessons. Turn it off to see whether the scheduler's built-in version already covers it."
          meta="A constraint we add by hand, not a solver setting."
        >
          <Toggle
            value={settings.useSymmetryBreaking}
            onChange={(v) => set({ useSymmetryBreaking: v })}
          />
        </Setting>
      </Accordion>

        </div>
        <div className="modal__foot">
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
          <Button variant="secondary-pill" onClick={() => onChange(defaultSettings())}>
            Reset to defaults
          </Button>
        </div>
      </div>
    </div>
  );
}
