import { Accordion } from './ds/Accordion';
import { Button } from './ds/Button';
import { RunDetails } from './RunDetails';
import { RunProgress } from './RunProgress';
import { StaleBanner } from './StaleBanner';
import { Select } from './ds/Select';
import { countNonDefault, formatLimit } from '../settings';
import { offeringSessions, offeringsIn, semesterSlots } from '../slots';
import { semesterKey } from '../types';
import type {
  Problem,
  RunState,
  SemesterRef,
  SolveProgress,
  SolveResponse,
  SolverSettings,
} from '../types';

interface Props {
  problem: Problem;
  semester: SemesterRef | null;
  semesters: SemesterRef[];
  onPickSemester: (next: SemesterRef) => void;
  /** Every semester's run state, result, live progress and start time: the screen
   *  lists them all, not just the one on screen. */
  runs: Record<string, RunState>;
  results: Record<string, SolveResponse>;
  progress: Record<string, SolveProgress>;
  starts: Record<string, number>;
  errors: Record<string, string | null>;
  run: RunState;
  result: SolveResponse | null;
  error: string | null;
  /** This semester's timetable predates the current input data. */
  stale: boolean;
  settings: SolverSettings;
  onOpenSettings: () => void;
  onGenerate: () => void;
  onGoResult: () => void;
  onGoData: () => void;
}

export function GenerateScreen({
  problem,
  semester,
  semesters,
  onPickSemester,
  runs,
  results,
  progress,
  starts,
  errors,
  run,
  result,
  error,
  stale,
  settings,
  onOpenSettings,
  onGenerate,
  onGoResult,
  onGoData,
}: Props) {
  const changedCount = countNonDefault(settings);
  // The dated periods this semester actually has, not the weekday template's 36
  // -- a semester is weeks of them, and the template count would badly
  // understate it.
  const open = semester
    ? semesterSlots(problem.slotConfig, problem.courseInstances, semester).length
    : 0;
  const sessions = semester
    ? offeringsIn(problem.offerings, problem.courseInstances, semester).reduce(
        (n, o) => n + offeringSessions(o),
        0,
      )
    : 0;
  const summary = [
    { value: problem.teachers.length, label: 'Teachers' },
    { value: problem.rooms.length, label: 'Rooms' },
    { value: problem.groups.length, label: 'Групи' },
    { value: problem.subgroups.length, label: 'Подгрупи' },
    { value: problem.offerings.length, label: 'Offerings' },
    { value: open, label: 'Open periods' },
    { value: sessions, label: 'Sessions needed' },
  ];

  const headlineFor = (state: RunState, r: SolveResponse | null) =>
    state === 'solving'
      ? 'Solving'
      : state === 'solved'
        ? r?.status === 'OPTIMAL'
          ? 'Optimal'
          : 'Feasible'
        : state === 'failed'
          ? r?.status === 'MODEL_INVALID'
            ? 'Invalid problem'
            : 'No solution found'
          : state === 'error'
            ? 'Solver unreachable'
            : 'Idle';

  const dotFor = (state: RunState) =>
    state === 'solved'
      ? 'statusdot--ok'
      : state === 'failed' || state === 'error'
        ? 'statusdot--fail'
        : state === 'solving'
          ? 'statusdot--busy'
          : '';

  // Every semester that has been run, or is running, in the order the calendar
  // puts them. A run that is still going is listed alongside the finished ones,
  // so a background solve is never off-screen.
  const rows = semesters
    .map((x) => ({ semester: x, key: semesterKey(x) }))
    .filter(({ key }) => runs[key] !== undefined || results[key] !== undefined);

  return (
    <div className="screen gen">
      {stale && <StaleBanner onRegenerate={onGenerate} />}
      <section className="card card--pad">
        <div className="gen__runrow">
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div className="display-md">Run the scheduler</div>
            <div className="muted" style={{ marginTop: 4, maxWidth: 620 }}>
              Hard rules: no teacher, група, подгрупа or room double-booked; a група-level
              session excludes every подгрупа of that група; the room type must match the activity
              and hold every student; хонорувани преподаватели are only scheduled inside their
              availability; no група exceeds its курс's periods a day. Teacher period preferences,
              ranked rooms and compact group days are optimised, not guaranteed.
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              {semesters.length > 0 && (
                <div className="muted-sm" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span>Semester</span>
                  <Select
                    size="sm"
                    aria-label="Semester"
                    value={semester ? semesterKey(semester) : ''}
                    options={semesters.map((x) => ({
                      value: semesterKey(x),
                      label: `${x.academicYear} · Semester ${x.index}`,
                    }))}
                    onChange={(key) => {
                      const next = semesters.find((x) => semesterKey(x) === key);
                      if (next) onPickSemester(next);
                    }}
                  />
                </div>
              )}
              <Button
                variant="primary"
                large
                onClick={onGenerate}
                disabled={run === 'solving' || !semester || sessions === 0}
              >
                {run === 'solving' ? 'Solving…' : 'Generate timetable'}
              </Button>
            </div>
          </div>
        </div>

        {semester && (
          <div className="muted-sm" style={{ marginTop: 8 }}>
            {sessions === 0 ? (
              <>
                No subject runs in {semester.academicYear} · Semester {semester.index}, so there is
                nothing to schedule. Give a subject sessions in this semester under Data setup →
                Subjects.
              </>
            ) : (
              <>
                Generating replaces the timetable stored for {semester.academicYear} · Semester{' '}
                {semester.index}. Other semesters are left as they are.
              </>
            )}
          </div>
        )}

        <div className="summary">
          {summary.map((s) => (
            <div key={s.label} className="summary__tile">
              <div className="summary__value">{s.value}</div>
              <div className="summary__label">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {rows.length === 0 ? (
        <section className="card card--pad">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <span className="statusdot" />
            <span className="display-sm">Idle</span>
            <span className="muted-sm">No run in this session yet.</span>
          </div>
        </section>
      ) : (
        <div className="runlist">
          {rows.map(({ semester: x, key }) => {
            const rowRun = runs[key] ?? 'empty';
            const rowResult = results[key] ?? null;
            const rowProgress = progress[key] ?? null;
            const isActive = semester !== null && semesterKey(semester) === key;
            return (
              <Accordion
                key={key}
                defaultOpen={isActive}
                onToggle={(open) => open && !isActive && onPickSemester(x)}
                title={
                  <>
                    <span className={`statusdot ${dotFor(rowRun)}`} style={{ marginRight: 8 }} />
                    {x.academicYear} · Semester {x.index}
                  </>
                }
                subtitle={
                  <>
                    {headlineFor(rowRun, rowResult)}
                    {rowResult?.stats && rowRun === 'solved'
                      ? ` · penalty ${rowResult.stats.objectiveValue ?? 0}`
                      : ''}
                    {rowRun === 'error' ? ` · ${errors[key] ?? ''}` : ''}
                  </>
                }
                aside={
                  rowRun === 'solving' ? (
                    <RunProgress
                      progress={rowProgress}
                      startedAt={starts[key] ?? null}
                      limit={settings.maxTimeInSeconds}
                    />
                  ) : null
                }
              >
                <RunDetails
                  run={rowRun}
                  result={rowResult}
                  error={errors[key] ?? null}
                  used={rowResult?.settingsUsed ?? settings}
                  onGoResult={() => {
                    if (!isActive) onPickSemester(x);
                    onGoResult();
                  }}
                  onGoData={onGoData}
                />
              </Accordion>
            );
          })}
        </div>
      )}
    </div>
  );
}
