import { useEffect, useMemo, useRef, useState } from 'react';

import { Button } from './ds/Button';
import { Select } from './ds/Select';
import { useBodyScrollLock } from './ds/useBodyScrollLock';
import { MoveSessionDialog } from './MoveSessionDialog';
import { StaleBanner } from './StaleBanner';
import { findConflicts, spreadNotices } from '../conflicts';
import { ACTIVITY_MARKER, ROOM_TYPES, ROOM_TYPE_COLOR, ROOM_TYPE_LABEL, subjectColor } from '../theme';
import type { Swatch } from '../theme';
import {
  coursesIn,
  offeringSessions,
  offeringsIn,
  periodTime,
  semesterWeeks,
  slotId,
  slotLabel,
  weekdayName,
} from '../slots';
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
  /** Run state per semester, so the picker can say which ones are still solving. */
  runs: Record<string, RunState>;
  /** Semester keys whose stored timetable predates the current input data. */
  staleKeys: string[];
  onPickSemester: (next: SemesterRef) => void;
  run: RunState;
  result: SolveResponse | null;
  /** The semester on screen is one of `staleKeys`. */
  stale: boolean;
  onGenerate: () => void;
  /** Move one session, by its index in `result.assignments`, to another period. */
  onMoveSession: (index: number, period: number, date: string) => void;
  onGoData: () => void;
  onGoGenerate: () => void;
}

/** How many session cards a grid cell shows before the rest collapse into a
 *  single "+N more" card. The same in both densities: how much the grid hides
 *  should not depend on a display toggle. */
const SHOWN_PER_CELL = 2;

/** Identity of one placed session is its index in `result.assignments`.
 *
 *  It used to be `subjectId-slot`, which a hand move breaks twice over: the key
 *  changes under the selection every time a card is dragged, and two sessions of
 *  one subject can now be put in the same slot, which collides the key outright.
 *  A move rewrites the array entry in place, so the index is the one thing about
 *  a session that a move never touches.
 */
type SessionId = number;

/** One placed session. Rendered in the grid cell and, for the sessions a full
 *  cell cannot show, in the overflow dialog -- the same card in both, so a
 *  session does not change appearance depending on where it is read. */
function SessionCard({
  assignment: a,
  color,
  selected,
  clash,
  dragging,
  onClick,
  onDragStart,
  onDragEnd,
}: {
  assignment: Assignment;
  color: Swatch;
  selected: boolean;
  /** Hard rules this session breaks, after being moved by hand. */
  clash?: string[];
  dragging?: boolean;
  onClick: () => void;
  /** Absent in the overflow dialog, which is a reader rather than a grid cell. */
  onDragStart?: (e: React.DragEvent) => void;
  onDragEnd?: () => void;
}) {
  return (
    <button
      className={`sesscard${a.softViolated ? ' sesscard--soft' : ''}${
        clash ? ' sesscard--clash' : ''
      }${selected ? ' sesscard--selected' : ''}${dragging ? ' sesscard--dragging' : ''}`}
      style={{ background: color.tint, borderLeftColor: color.c }}
      draggable={onDragStart !== undefined}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
    >
      <div className="sesscard__top">
        <span className="sesscard__subject">
          {a.subjectCode} <span className="sesscard__marker">{ACTIVITY_MARKER[a.activity]}</span>
        </span>
        {clash && <span className="sesscard__clashflag" title={clash.join(' ')} />}
        {a.softViolated && <span className="sesscard__flag" title={a.softReason ?? ''} />}
      </div>
      <div className="sesscard__teacher">{a.teacherName}</div>
      <div className="sesscard__group">{a.subgroupName ?? a.groupNames.join(' · ')}</div>
      <div className="sesscard__room">{a.roomName}</div>
    </button>
  );
}

/** The групи in term this semester. A група belongs to exactly one курс and a
 *  курс to one semester, so the same cohort appears once per семестър under the
 *  same name -- and the group lens has to offer only the ones whose sessions
 *  this grid could possibly show. Teachers and rooms are shared across
 *  semesters and are not filtered. */
function groupsOf(problem: Problem, ref: SemesterRef | null) {
  if (!ref) return problem.groups;
  const ids = new Set(coursesIn(problem.courseInstances, ref).map((c) => c.id));
  return problem.groups.filter((g) => ids.has(g.courseInstanceId));
}

/** The three lenses filter one shared `assignments` array -- there is no
 *  per-lens data path, so the views cannot disagree with each other. */
function matchesLens(a: Assignment, lens: Lens, pick: string): boolean {
  if (pick === 'all') return true;
  if (lens === 'group') return a.groupIds.includes(pick);
  if (lens === 'teacher') return a.teacherId === pick;
  return a.roomId === pick;
}

export function ResultScreen({
  problem,
  semester,
  semesters,
  results,
  runs,
  staleKeys,
  onPickSemester,
  run,
  result,
  stale,
  onGenerate,
  onMoveSession,
  onGoData,
  onGoGenerate,
}: Props) {
  const [lens, setLens] = useState<Lens>('group');
  // A faculty-sized timetable is unreadable with every group shown at once, so
  // large results open focused on a single group instead of "All".
  const [pick, setPick] = useState(() =>
    (result?.assignments.length ?? 0) > 60
      ? (groupsOf(problem, semester)[0]?.id ?? 'all')
      : 'all',
  );
  const [colorBy, setColorBy] = useState<'subject' | 'roomType'>('subject');
  const [dense, setDense] = useState(false);
  const [selected, setSelected] = useState<SessionId | null>(null);
  // Index being dragged, and the cell it is currently over. Both are transient
  // and live only for the length of one drag. The index is also held in a ref:
  // the drop handler must not depend on a re-render having happened between
  // dragstart and drop, and the state is only there to fade the card.
  const [dragging, setDragging] = useState<SessionId | null>(null);
  const draggingRef = useRef<SessionId | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [moving, setMoving] = useState<SessionId | null>(null);
  // Slot id whose overflow dialog is open. A cell shows at most SHOWN_PER_CELL
  // cards; everything past that is only reachable through here.
  const [overflow, setOverflow] = useState<string | null>(null);
  useBodyScrollLock(overflow !== null);
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
    () =>
      semester ? semesterWeeks(problem.slotConfig, problem.courseInstances, semester) : [],
    [problem.slotConfig, problem.courseInstances, semester],
  );
  const week = weeks[Math.min(weekIndex, Math.max(weeks.length - 1, 0))];
  const weekDates = week?.dates ?? [];

  const assignments = result?.assignments ?? [];
  const subjectIds = problem.subjects.map((s) => s.id);
  const blocked = new Set(problem.slotConfig.blockedSlots);
  const roomTypeOf = (roomId: string) =>
    problem.rooms.find((r) => r.id === roomId)?.type ?? 'зала';

  const visible = useMemo(
    () => assignments.filter((a) => matchesLens(a, lens, pick)),
    [assignments, lens, pick],
  );

  // A session's identity is its position in the full array, so the grid needs a
  // way back from the filtered view to that position.
  const indexOf = useMemo(
    () => new Map<Assignment, SessionId>(assignments.map((a, i) => [a, i])),
    [assignments],
  );

  // Hand moves are accepted whatever they break, so the breach is found here.
  // Recomputed on every edit -- the whole point is that it tracks the grid, not
  // the solve the grid came from.
  const conflicts = useMemo(
    () => (semester ? findConflicts(assignments, problem, semester) : new Map<number, string[]>()),
    [assignments, problem, semester],
  );
  const spread = useMemo(
    () => (semester ? spreadNotices(assignments, problem, semester) : []),
    [assignments, problem, semester],
  );

  const colorFor = (a: Assignment) =>
    colorBy === 'roomType' ? ROOM_TYPE_COLOR[roomTypeOf(a.roomId)] : subjectColor(subjectIds, a.subjectId);

  const pickOptions =
    lens === 'group'
      ? groupsOf(problem, semester).map((g) => ({ id: g.id, label: g.name }))
      : lens === 'teacher'
        ? problem.teachers.map((t) => ({ id: t.id, label: t.name }))
        : problem.rooms.map((r) => ({ id: r.id, label: r.name }));

  const legend =
    colorBy === 'roomType'
      ? ROOM_TYPES.filter((t) => problem.rooms.some((r) => r.type === t)).map((t) => ({
          label: ROOM_TYPE_LABEL[t],
          c: ROOM_TYPE_COLOR[t].c,
        }))
      : problem.subjects
          .filter((s) => visible.some((a) => a.subjectId === s.id))
          .map((s) => ({ label: `${s.code} — ${s.name}`, c: subjectColor(subjectIds, s.id).c }));

  const exportCsv = () => {
    const header =
      'date,day,period,code,subject,activity,teacher,groups,subgroup,room,' +
      'soft_preference_violated,room_choice_rank';
    const rows = [...assignments]
      .sort((a, b) => a.slot.localeCompare(b.slot))
      .map((a) => {
        return [
          a.date,
          weekdayName(a.date),
          a.period,
          a.subjectCode,
          a.subjectName,
          a.activity,
          a.teacherName,
          a.groupNames.join(' + '),
          a.subgroupName ?? '',
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

  // Sessions this semester actually has. Zero means there is nothing to solve --
  // the run would come back OPTIMAL over an empty grid, which reads as a bug.
  const semesterSessions = semester
    ? offeringsIn(problem.offerings, problem.courseInstances, semester).reduce(
        (n, o) => n + offeringSessions(o),
        0,
      )
    : 0;

  // The semester picker, shared by the empty state and the full toolbar: landing
  // on an ungenerated semester must not be a one-way door.
  const semesterPicker = semesters.length > 0 && (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} className="muted-sm">
      <span>Semester</span>
      <Select
        size="sm"
        aria-label="Semester"
        value={semester ? semesterKey(semester) : ''}
        options={semesters.map((x) => {
          const key = semesterKey(x);
          const note =
            runs[key] === 'solving'
              ? ' (solving…)'
              : !results[key]
                ? ' (not generated)'
                : staleKeys.includes(key)
                  ? ' (stale)'
                  : '';
          return { value: key, label: `${x.academicYear} · Semester ${x.index}${note}` };
        })}
        onChange={(key) => {
          const next = semesters.find((x) => semesterKey(x) === key);
          if (next) {
            onPickSemester(next);
            // The focused група belongs to the semester we are leaving, and its
            // name repeats in the one we are entering -- so re-point it rather
            // than leave the grid empty under a familiar label.
            if (lens === 'group' && pick !== 'all') {
              const mine = groupsOf(problem, next);
              if (!mine.some((g) => g.id === pick)) setPick(mine[0]?.id ?? 'all');
            }
            setWeekIndex(0);
            setSelected(null);
            setOverflow(null);
            setMoving(null);
          }
        }}
      />
    </div>
  );

  if (run !== 'solved' || !result) {
    const empty = semesterSessions === 0 && semester;
    return (
      <div className="screen">
        {semesterPicker && (
          <div className="result__controls" style={{ justifyContent: 'flex-end' }}>
            {semesterPicker}
          </div>
        )}
        <div className="card emptystate">
          <div className="ghostgrid">
            {Array.from({ length: 15 }, (_, i) => (
              <div key={i} />
            ))}
          </div>
          <div className="display-md">
            {run === 'solving'
              ? 'Solving…'
              : run === 'failed'
                ? 'No valid schedule'
                : empty
                  ? 'Nothing to schedule'
                  : 'No timetable yet'}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            {run === 'failed'
              ? 'The solver proved the hard constraints cannot all be satisfied. See the Generate tab for the reasons.'
              : run === 'error'
                ? 'The solver service could not be reached.'
                : empty
                  ? `No subject runs in ${semester.academicYear} · Semester ${semester.index}. Give a subject sessions in this semester under Data setup → Subjects.`
                  : `${problem.teachers.length} teachers, ${problem.rooms.length} rooms, ${problem.groups.length} groups, ${problem.subjects.length} subjects. Run the scheduler to produce a weekly grid.`}
          </div>
          <div style={{ marginTop: 18, display: 'flex', gap: 8, justifyContent: 'center' }}>
            {!empty && (
              <Button variant="primary" onClick={run === 'failed' ? onGoGenerate : onGenerate}>
                {run === 'failed' ? 'See why' : 'Generate timetable'}
              </Button>
            )}
            <Button variant={empty ? 'primary' : 'secondary-pill'} onClick={onGoData}>
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
  const selectedAssignment = selected === null ? null : (assignments[selected] ?? null);
  const stats = result.stats!;

  return (
    <div className="screen">
      {stale && <StaleBanner onRegenerate={onGenerate} />}
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
          {semesterPicker}
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
                // blockedSlots stays weekday-keyed, so a blocked period is
                // blocked on that weekday every week of the term.
                const isBlocked = blocked.has(slotId(weekdayName(date), period));
                return (
                  <div
                    key={id}
                    className={`grid__cell${isBlocked ? ' grid__cell--blocked' : ''}${
                      dropTarget === id ? ' grid__cell--drop' : ''
                    }`}
                    style={{ minHeight: dense ? 62 : 92 }}
                    // preventDefault is what makes a cell a drop target at all.
                    // Every cell is one: a move that breaks a rule is allowed and
                    // then flagged, so there is nothing to refuse here.
                    onDragOver={(e) => {
                      if (draggingRef.current === null) return;
                      e.preventDefault();
                      setDropTarget(id);
                    }}
                    onDragLeave={() => setDropTarget((t) => (t === id ? null : t))}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDropTarget(null);
                      // dataTransfer first: it is the drag's own payload, and it
                      // is readable in `drop` even when the drag began elsewhere.
                      const carried = Number(e.dataTransfer.getData('text/plain'));
                      const index = Number.isInteger(carried) ? carried : draggingRef.current;
                      // End the drag here rather than leaving it to `dragend`: the
                      // move unmounts the card that was being dragged, so its own
                      // dragend never arrives and the card would stay faded.
                      draggingRef.current = null;
                      setDragging(null);
                      if (index === null) return;
                      const from = assignments[index];
                      if (from && from.slot !== id) onMoveSession(index, period, date);
                    }}
                  >
                    {cell.slice(0, SHOWN_PER_CELL).map((a) => {
                      const key = indexOf.get(a)!;
                      return (
                        <SessionCard
                          key={key}
                          assignment={a}
                          color={colorFor(a)}
                          selected={selected === key}
                          clash={conflicts.get(key)}
                          dragging={dragging === key}
                          onClick={() => setSelected(selected === key ? null : key)}
                          onDragStart={(e) => {
                            // dataTransfer carries the payload; a drag that sets
                            // none is a no-op in Firefox anyway.
                            e.dataTransfer.setData('text/plain', String(key));
                            e.dataTransfer.effectAllowed = 'move';
                            draggingRef.current = key;
                            setDragging(key);
                          }}
                          onDragEnd={() => {
                            draggingRef.current = null;
                            setDragging(null);
                            setDropTarget(null);
                          }}
                        />
                      );
                    })}
                    {hidden.length > 0 && (
                      // Carries the selected ring when the chosen session is one
                      // of the hidden ones, so a selection never looks lost.
                      <button
                        className={`sesscard sesscard--more${
                          hidden.some((a) => indexOf.get(a) === selected)
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
                    ['Activity', selectedAssignment.activity],
                    ['Teacher', selectedAssignment.teacherName],
                    [
                      selectedAssignment.subgroupId ? 'Подгрупа' : 'Групи',
                      selectedAssignment.subgroupName ?? selectedAssignment.groupNames.join(', '),
                    ],
                    ['Room', selectedAssignment.roomName],
                    [
                      'Period',
                      slotLabel(
                        problem.slotConfig,
                        slotId(selectedAssignment.day, selectedAssignment.period),
                      ),
                    ],
                  ].map(([k, v]) => (
                    <div key={k} className="side__row">
                      <span className="side__k">{k}</span>
                      <span className="side__v">{v}</span>
                    </div>
                  ))}
                </div>
                {selected !== null &&
                  conflicts.get(selected)?.map((c, i) => (
                    <div key={i} className="penalty penalty--bad">
                      {c}
                    </div>
                  ))}
                {selectedAssignment.softViolated && (
                  <div className="penalty">{selectedAssignment.softReason}</div>
                )}
                {selectedAssignment.roomPreferenceRank === 0 && (
                  <div className="muted-sm">First-choice room for this teacher.</div>
                )}
                {/* Dragging reaches the week on screen; this reaches the rest of
                    the semester, and is the only route from a keyboard. */}
                <div style={{ marginTop: 14 }}>
                  <Button variant="secondary-pill" onClick={() => setMoving(selected)}>
                    Move to another week
                  </Button>
                </div>
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
            {/* The solver's own verdict, until the grid is edited by hand -- at
                which point the figures above still describe the run, and only
                this re-check describes what is on screen. */}
            <div style={{ marginTop: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span
                className={`badge ${
                  conflicts.size > 0 || !result.validation?.ok ? 'badge--bad' : 'badge--ok'
                }`}
              >
                {conflicts.size > 0
                  ? `${conflicts.size} session(s) in conflict`
                  : result.validation?.ok
                    ? 'All hard rules verified'
                    : 'Verification failed'}
              </span>
              {spread.length > 0 && (
                <span className="badge badge--warn">
                  {spread.length} week(s) over the even spread
                </span>
              )}
            </div>
            {(conflicts.size > 0 || spread.length > 0) && (
              <div className="failbox" style={{ marginTop: 10 }}>
                {[...new Set([...conflicts.values()].flat())].map((c, i) => (
                  <div key={`c${i}`} className="hint__detail">
                    {c}
                  </div>
                ))}
                {spread.map((c, i) => (
                  <div key={`s${i}`} className="hint__detail">
                    {c}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card card--pad">
            <span className="eyebrow">Utilisation</span>
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                {
                  label: 'Periods used',
                  used: new Set(assignments.map((a) => a.slot)).size,
                  total: stats.numSlots,
                },
                ...ROOM_TYPES
                  .filter((t) => problem.rooms.some((r) => r.type === t))
                  .map((t) => ({
                    label: ROOM_TYPE_LABEL[t],
                    used: assignments.filter((a) => roomTypeOf(a.roomId) === t).length,
                    total:
                      problem.rooms
                        .filter((r) => r.type === t)
                        .reduce((n, r) => n + r.maxConcurrentGroups, 0) * stats.numSlots,
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

      {moving !== null && assignments[moving] && semester && (
        <MoveSessionDialog
          assignment={assignments[moving]}
          problem={problem}
          semester={semester}
          weeks={weeks}
          conflictsAt={(date, period) => {
            // The same check the grid runs, against the timetable this move would
            // produce -- so the dialog and the card can never disagree.
            const slot = `${date}-${period}`;
            const next = assignments.map((a, i) => (i === moving ? { ...a, slot, date } : a));
            return findConflicts(next, problem, semester).get(moving) ?? [];
          }}
          onMove={(slot, date) => {
            onMoveSession(moving, slot, date);
            // Follow the session to its new week, so the move can be seen rather
            // than taken on trust.
            const target = weeks.findIndex((w) => w.dates.includes(date));
            if (target >= 0) setWeekIndex(target);
            setMoving(null);
          }}
          onClose={() => setMoving(null)}
        />
      )}

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
                const key = indexOf.get(a)!;
                return (
                  <SessionCard
                    key={key}
                    assignment={a}
                    color={colorFor(a)}
                    selected={selected === key}
                    clash={conflicts.get(key)}
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
