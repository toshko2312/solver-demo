import { useEffect, useMemo, useState } from 'react';

import { Button } from './ds/Button';
import { Select } from './ds/Select';
import { ROOM_TYPES, ROOM_TYPE_COLOR, ROOM_TYPE_LABEL, subjectColor } from '../theme';
import type { Swatch } from '../theme';
import { periodTime, semesterWeeks, slotId, slotLabel, weekdayName } from '../slots';
import { semesterKey } from '../types';
import type {
  Assignment,
  Lens,
  Problem,
  RunState,
  SemesterRef,
  SolveResponse,
} from '../types';

interface Props {
  problem: Problem;
  semester: SemesterRef | null;
  semesters: SemesterRef[];
  results: Record<string, SolveResponse>;
  onPickSemester: (next: SemesterRef) => void;
  run: RunState;
  result: SolveResponse | null;
  onGenerate: () => void;
  onGoData: () => void;
  onGoGenerate: () => void;
}

/** How many session cards a grid cell shows before the rest collapse into a
 *  single "+N more" card. The same in both densities: how much the grid hides
 *  should not depend on a display toggle. */
const SHOWN_PER_CELL = 2;

/** Identity of one placed session. The slot carries the date, so this is unique
 *  across the whole semester, not just the week on screen. */
function sessionKey(a: Assignment): string {
  return `${a.subjectId}-${a.slot}`;
}

/** One placed session. Rendered in the grid cell and, for the sessions a full
 *  cell cannot show, in the overflow dialog -- the same card in both, so a
 *  session does not change appearance depending on where it is read. */
function SessionCard({
  assignment: a,
  color,
  selected,
  onClick,
}: {
  assignment: Assignment;
  color: Swatch;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`sesscard${a.softViolated ? ' sesscard--soft' : ''}${
        selected ? ' sesscard--selected' : ''
      }`}
      style={{ background: color.tint, borderLeftColor: color.c }}
      onClick={onClick}
    >
      <div className="sesscard__top">
        <span className="sesscard__subject">{a.subjectName}</span>
        {a.softViolated && <span className="sesscard__flag" title={a.softReason ?? ''} />}
      </div>
      <div className="sesscard__teacher">{a.teacherName}</div>
      <div className="sesscard__group">{a.groupNames.join(' · ')}</div>
      <div className="sesscard__room">{a.roomName}</div>
    </button>
  );
}

/** The three lenses filter one shared `assignments` array -- there is no
 *  per-lens data path, so the views cannot disagree with each other. */
function matchesLens(a: Assignment, lens: Lens, pick: string): boolean {
  if (pick === 'all') return true;
  if (lens === 'group') return a.groupIds.includes(pick);
  if (lens === 'teacher') return a.teacherId === pick;
  return a.roomId === pick;
}

export function ResultScreen({ problem, semester, semesters, results, onPickSemester, run, result, onGenerate, onGoData, onGoGenerate }: Props) {
  const [lens, setLens] = useState<Lens>('group');
  // A faculty-sized timetable is unreadable with every group shown at once, so
  // large results open focused on a single group instead of "All".
  const [pick, setPick] = useState(() =>
    (result?.assignments.length ?? 0) > 60 ? (problem.groups[0]?.id ?? 'all') : 'all',
  );
  const [colorBy, setColorBy] = useState<'subject' | 'roomType'>('subject');
  const [dense, setDense] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  // Slot id whose overflow dialog is open. A cell shows at most SHOWN_PER_CELL
  // cards; everything past that is only reachable through here.
  const [overflow, setOverflow] = useState<string | null>(null);
  // Which teaching week the grid is showing. Reset whenever the semester changes,
  // since week 12 of one term means nothing in another.
  const [weekIndex, setWeekIndex] = useState(0);

  // A transient viewer, so it closes on Escape. The entity modals do not, and
  // are deliberately left alone.
  useEffect(() => {
    if (!overflow) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOverflow(null);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [overflow]);

  const weeks = useMemo(
    () => (semester ? semesterWeeks(problem.slotConfig, problem.groups, semester) : []),
    [problem.slotConfig, problem.groups, semester],
  );
  const week = weeks[Math.min(weekIndex, Math.max(weeks.length - 1, 0))];
  const weekDates = week?.dates ?? [];

  const assignments = result?.assignments ?? [];
  const subjectIds = problem.subjects.map((s) => s.id);
  const blocked = new Set(problem.slotConfig.blockedSlots);
  const roomTypeOf = (roomId: string) => problem.rooms.find((r) => r.id === roomId)?.type ?? 'lecture';

  const visible = useMemo(
    () => assignments.filter((a) => matchesLens(a, lens, pick)),
    [assignments, lens, pick],
  );

  const colorFor = (a: Assignment) =>
    colorBy === 'roomType' ? ROOM_TYPE_COLOR[roomTypeOf(a.roomId)] : subjectColor(subjectIds, a.subjectId);

  const pickOptions =
    lens === 'group'
      ? problem.groups.map((g) => ({ id: g.id, label: g.name }))
      : lens === 'teacher'
        ? problem.teachers.map((t) => ({ id: t.id, label: t.name }))
        : problem.rooms.map((r) => ({ id: r.id, label: r.name }));

  const legend =
    colorBy === 'roomType'
      ? ROOM_TYPES.map((t) => ({
          label: ROOM_TYPE_LABEL[t],
          c: ROOM_TYPE_COLOR[t].c,
        }))
      : problem.subjects
          .filter((s) => visible.some((a) => a.subjectId === s.id))
          .map((s) => ({ label: s.name, c: subjectColor(subjectIds, s.id).c }));

  const exportCsv = () => {
    const header =
      'date,day,period,subject,teacher,groups,room,soft_preference_violated,room_choice_rank';
    const rows = [...assignments]
      .sort((a, b) => a.slot.localeCompare(b.slot))
      .map((a) => {
        return [
          a.date,
          weekdayName(a.date),
          a.slot.slice(a.date.length + 1),
          a.subjectName,
          a.teacherName,
          a.groupNames.join(' + '),
          a.roomName,
          a.softViolated ? 'yes' : 'no',
          a.roomPreferenceRank == null ? '' : a.roomPreferenceRank + 1,
        ]
          .map((v) => `"${String(v).replace(/"/g, '""')}"`)
          .join(',');
      });
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'timetable.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  if (run !== 'solved' || !result) {
    return (
      <div className="screen">
        <div className="card emptystate">
          <div className="ghostgrid">
            {Array.from({ length: 15 }, (_, i) => (
              <div key={i} />
            ))}
          </div>
          <div className="display-md">
            {run === 'solving' ? 'Solving…' : run === 'failed' ? 'No valid schedule' : 'No timetable yet'}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            {run === 'failed'
              ? 'The solver proved the hard constraints cannot all be satisfied. See the Generate tab for the reasons.'
              : run === 'error'
                ? 'The solver service could not be reached.'
                : `${problem.teachers.length} teachers, ${problem.rooms.length} rooms, ${problem.groups.length} groups, ${problem.subjects.length} subjects. Run the scheduler to produce a weekly grid.`}
          </div>
          <div style={{ marginTop: 18, display: 'flex', gap: 8, justifyContent: 'center' }}>
            <Button variant="primary" onClick={run === 'failed' ? onGoGenerate : onGenerate}>
              {run === 'failed' ? 'See why' : 'Generate timetable'}
            </Button>
            <Button variant="secondary-pill" onClick={onGoData}>
              Check input data
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const columns = `96px repeat(${Math.max(weekDates.length, 1)}, minmax(0,1fr))`;
  // Read off `visible`, not off a copy taken when the card was clicked, so the
  // dialog can never disagree with the cell it came from.
  const overflowSessions = (() => {
    if (!overflow) return null;
    const date = overflow.slice(0, 10);
    const period = Number(overflow.slice(11));
    return {
      title: `${weekdayName(date)} ${date.slice(8, 10)}/${date.slice(5, 7)} · Period ${period}`,
      time: periodTime(problem.slotConfig, period),
      items: visible.filter((a) => a.slot === overflow),
    };
  })();
  const selectedAssignment = assignments.find((a) => sessionKey(a) === selected) ?? null;
  const stats = result.stats!;

  return (
    <div className="screen">
      <div className="result__controls">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <div className="pillgroup">
            {(['group', 'teacher', 'room'] as Lens[]).map((l) => (
              <button
                key={l}
                className={`pill${lens === l ? ' pill--active' : ''}`}
                onClick={() => {
                  setLens(l);
                  setPick('all');
                }}
              >
                By {l}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <button
              className={`chip${pick === 'all' ? ' chip--active' : ''}`}
              onClick={() => setPick('all')}
            >
              All
            </button>
            {pickOptions.map((o) => (
              <button
                key={o.id}
                className={`chip${pick === o.id ? ' chip--active' : ''}`}
                onClick={() => setPick(o.id)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          {semesters.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} className="muted-sm">
              <span>Semester</span>
              <Select
                size="sm"
                aria-label="Semester"
                value={semester ? semesterKey(semester) : ''}
                options={semesters.map((x) => ({
                  value: semesterKey(x),
                  label:
                    `${x.academicYear} · Semester ${x.index}` +
                    (results[semesterKey(x)] ? '' : ' (not generated)'),
                }))}
                onChange={(key) => {
                  const next = semesters.find((x) => semesterKey(x) === key);
                  if (next) {
                    onPickSemester(next);
                    setWeekIndex(0);
                    setSelected(null);
                    setOverflow(null);
                  }
                }}
              />
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} className="muted-sm">
            <span>Colour by</span>
            <button
              className={`microbtn${colorBy === 'subject' ? ' microbtn--active' : ''}`}
              onClick={() => setColorBy('subject')}
            >
              Subject
            </button>
            <button
              className={`microbtn${colorBy === 'roomType' ? ' microbtn--active' : ''}`}
              onClick={() => setColorBy('roomType')}
            >
              Room type
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} className="muted-sm">
            <span>Density</span>
            <button
              className={`microbtn${!dense ? ' microbtn--active' : ''}`}
              onClick={() => setDense(false)}
            >
              Roomy
            </button>
            <button
              className={`microbtn${dense ? ' microbtn--active' : ''}`}
              onClick={() => setDense(true)}
            >
              Compact
            </button>
          </div>
          <Button variant="secondary-pill" onClick={exportCsv}>
            Export CSV
          </Button>
        </div>
      </div>

      <div className="result__body">
        <section className="card">
          <div className="grid__head">
            <div className="display-sm">
              {pick === 'all'
                ? `All ${lens}s`
                : pickOptions.find((o) => o.id === pick)?.label}{' '}
              · {visible.length} session(s)
            </div>
            <div className="grid__legend">
              {legend.map((k) => (
                <span key={k.label} className="grid__legenditem">
                  <span className="swatch" style={{ background: k.c }} />
                  {k.label}
                </span>
              ))}
            </div>
          </div>

          {weeks.length > 0 && (
            <div className="weeknav">
              <button
                className="microbtn"
                disabled={weekIndex <= 0}
                onClick={() => setWeekIndex((i) => Math.max(i - 1, 0))}
              >
                ‹ Previous
              </button>
              <Select
                size="sm"
                aria-label="Week"
                value={week?.week ?? ''}
                options={weeks.map((w, i) => ({
                  value: w.week,
                  label: `Week ${i + 1} of ${weeks.length} · ${w.dates[0]} – ${
                    w.dates[w.dates.length - 1]
                  }`,
                }))}
                onChange={(key) => setWeekIndex(weeks.findIndex((w) => w.week === key))}
              />
              <button
                className="microbtn"
                disabled={weekIndex >= weeks.length - 1}
                onClick={() => setWeekIndex((i) => Math.min(i + 1, weeks.length - 1))}
              >
                Next ›
              </button>
              <span className="muted-sm">
                {visible.filter((a) => weekDates.includes(a.date)).length} session(s) this week
              </span>
            </div>
          )}

          <div className="grid__row grid__row--head" style={{ gridTemplateColumns: columns }}>
            <div className="grid__daycell" />
            {weekDates.map((d) => (
              <div key={d} className="grid__daycell">
                {weekdayName(d)}{' '}
                <span className="muted-sm">
                  {d.slice(8, 10)}/{d.slice(5, 7)}
                </span>
              </div>
            ))}
          </div>

          {Array.from({ length: problem.slotConfig.periods }, (_, i) => i + 1).map((period) => (
            <div key={period} className="grid__row" style={{ gridTemplateColumns: columns }}>
              <div className="grid__rowhead">
                <div className="grid__periodname">Period {period}</div>
                <div className="grid__periodtime">{periodTime(problem.slotConfig, period)}</div>
              </div>
              {weekDates.map((date) => {
                const id = `${date}-${period}`;
                const cell = visible.filter((a) => a.slot === id);
                const hidden = cell.slice(SHOWN_PER_CELL);
                // blockedSlots stays weekday-keyed, so a blocked period is blocked
                // on that weekday every week of the term.
                const isBlocked = blocked.has(slotId(weekdayName(date), period));
                return (
                  <div
                    key={id}
                    className={`grid__cell${isBlocked ? ' grid__cell--blocked' : ''}`}
                    style={{ minHeight: dense ? 62 : 92 }}
                  >
                    {cell.slice(0, SHOWN_PER_CELL).map((a) => {
                      const key = sessionKey(a);
                      return (
                        <SessionCard
                          key={key}
                          assignment={a}
                          color={colorFor(a)}
                          selected={selected === key}
                          onClick={() => setSelected(selected === key ? null : key)}
                        />
                      );
                    })}
                    {hidden.length > 0 && (
                      // Carries the selected ring when the chosen session is one
                      // of the hidden ones, so a selection never looks lost.
                      <button
                        className={`sesscard sesscard--more${
                          hidden.some((a) => sessionKey(a) === selected)
                            ? ' sesscard--selected'
                            : ''
                        }`}
                        onClick={() => setOverflow(id)}
                      >
                        + {hidden.length} more
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </section>

        <aside className="side">
          <div className="card card--pad">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className="eyebrow">Session</span>
              {selectedAssignment && (
                <button className="linkbtn" onClick={() => setSelected(null)}>
                  Clear
                </button>
              )}
            </div>
            {selectedAssignment ? (
              <>
                <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 9 }}>
                  <span
                    style={{
                      width: 11,
                      height: 11,
                      borderRadius: 3,
                      background: colorFor(selectedAssignment).c,
                    }}
                  />
                  <span className="display-sm">{selectedAssignment.subjectName}</span>
                </div>
                <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {[
                    ['Teacher', selectedAssignment.teacherName],
                    ['Groups', selectedAssignment.groupNames.join(', ')],
                    ['Room', selectedAssignment.roomName],
                    ['Slot', slotLabel(problem.slotConfig, selectedAssignment.slot)],
                  ].map(([k, v]) => (
                    <div key={k} className="side__row">
                      <span className="side__k">{k}</span>
                      <span className="side__v">{v}</span>
                    </div>
                  ))}
                </div>
                {selectedAssignment.softViolated && (
                  <div className="penalty">{selectedAssignment.softReason}</div>
                )}
                {selectedAssignment.roomPreferenceRank === 0 && (
                  <div className="muted-sm">First-choice room for this teacher.</div>
                )}
              </>
            ) : (
              <div className="muted-sm" style={{ marginTop: 10 }}>
                Select a session in the grid to inspect it.
              </div>
            )}
          </div>

          <div className="card card--pad">
            <span className="eyebrow">Solver</span>
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                ['Status', stats.status],
                ['Solve time', `${stats.solveTimeSeconds.toFixed(2)} s`],
                ['Soft penalty', String(stats.objectiveValue ?? 0)],
                ['Preference misses', String(stats.preferenceViolations)],
                ['Room preference cost', String(stats.roomPreferencePenalty)],
                ['Group gaps', String(stats.gapPenalty)],
                ['Sessions placed', `${stats.numPlaced} / ${stats.numSessions}`],
              ].map(([k, v]) => (
                <div key={k} className="side__row">
                  <span className="side__k">{k}</span>
                  <span className="side__v">{v}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 12 }}>
              <span className={`badge ${result.validation?.ok ? 'badge--ok' : 'badge--bad'}`}>
                {result.validation?.ok ? 'All hard rules verified' : 'Verification failed'}
              </span>
            </div>
          </div>

          <div className="card card--pad">
            <span className="eyebrow">Utilisation</span>
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { label: 'Slots used', used: new Set(assignments.map((a) => a.slot)).size, total: stats.numSlots },
                ...ROOM_TYPES
                  .filter((t) => problem.rooms.some((r) => r.type === t))
                  .map((t) => ({
                    label: ROOM_TYPE_LABEL[t],
                    used: assignments.filter((a) => roomTypeOf(a.roomId) === t).length,
                    total: problem.rooms.filter((r) => r.type === t).length * stats.numSlots,
                  })),
              ].map((u) => (
                <div key={u.label}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                    <span className="side__k">{u.label}</span>
                    <span>
                      {u.used} of {u.total}
                    </span>
                  </div>
                  <div className="bar" style={{ marginTop: 5 }}>
                    <div
                      className="bar__fill"
                      style={{ width: `${u.total ? Math.min(100, (u.used / u.total) * 100) : 0}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {overflowSessions && (
        <div className="modal__backdrop" onClick={() => setOverflow(null)}>
          <div
            className="modal modal--fixed"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={overflowSessions.title}
          >
            <div className="modal__head">
              <div>
                <div className="display-sm">{overflowSessions.title}</div>
                <div className="muted-sm">
                  {overflowSessions.time && `${overflowSessions.time} · `}
                  {overflowSessions.items.length} session(s)
                </div>
              </div>
              <button className="linkbtn linkbtn--quiet" onClick={() => setOverflow(null)}>
                Close
              </button>
            </div>
            {/* The shell is a fixed height whatever the count, so the list is
                what scrolls -- a busy period and a quiet one open the same box. */}
            <div className="modal__scroll">
              {overflowSessions.items.map((a) => {
                const key = sessionKey(a);
                return (
                  <SessionCard
                    key={key}
                    assignment={a}
                    color={colorFor(a)}
                    selected={selected === key}
                    onClick={() => {
                      setSelected(key);
                      setOverflow(null);
                    }}
                  />
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
