import { useMemo, useState } from 'react';

import { Button } from './ds/Button';
import { ROOM_TYPES, ROOM_TYPE_COLOR, ROOM_TYPE_LABEL, subjectColor } from '../theme';
import { periodTime, slotId, slotLabel } from '../slots';
import type { Assignment, Lens, Problem, RunState, SolveResponse } from '../types';

interface Props {
  problem: Problem;
  run: RunState;
  result: SolveResponse | null;
  onGenerate: () => void;
  onGoData: () => void;
  onGoGenerate: () => void;
}

/** The three lenses filter one shared `assignments` array -- there is no
 *  per-lens data path, so the views cannot disagree with each other. */
function matchesLens(a: Assignment, lens: Lens, pick: string): boolean {
  if (pick === 'all') return true;
  if (lens === 'group') return a.groupIds.includes(pick);
  if (lens === 'teacher') return a.teacherId === pick;
  return a.roomId === pick;
}

export function ResultScreen({ problem, run, result, onGenerate, onGoData, onGoGenerate }: Props) {
  const [lens, setLens] = useState<Lens>('group');
  // A faculty-sized timetable is unreadable with every group shown at once, so
  // large results open focused on a single group instead of "All".
  const [pick, setPick] = useState(() =>
    (result?.assignments.length ?? 0) > 60 ? (problem.groups[0]?.id ?? 'all') : 'all',
  );
  const [colorBy, setColorBy] = useState<'subject' | 'roomType'>('subject');
  const [dense, setDense] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

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
    const header = 'day,period,subject,teacher,groups,room,soft_preference_violated';
    const rows = [...assignments]
      .sort((a, b) => a.slot.localeCompare(b.slot))
      .map((a) => {
        const slot = problem.slotConfig.days.flatMap((day) =>
          Array.from({ length: problem.slotConfig.periods }, (_, i) => ({ day, period: i + 1 })),
        ).find((s) => slotId(s.day, s.period) === a.slot);
        return [
          slot?.day ?? a.slot,
          slot?.period ?? '',
          a.subjectName,
          a.teacherName,
          a.groupNames.join(' + '),
          a.roomName,
          a.softViolated ? 'yes' : 'no',
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

  const columns = `96px repeat(${problem.slotConfig.days.length}, minmax(0,1fr))`;
  const selectedAssignment = assignments.find((a) => `${a.subjectId}-${a.slot}` === selected) ?? null;
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

          <div className="grid__row grid__row--head" style={{ gridTemplateColumns: columns }}>
            <div className="grid__daycell" />
            {problem.slotConfig.days.map((d) => (
              <div key={d} className="grid__daycell">
                {d}
              </div>
            ))}
          </div>

          {Array.from({ length: problem.slotConfig.periods }, (_, i) => i + 1).map((period) => (
            <div key={period} className="grid__row" style={{ gridTemplateColumns: columns }}>
              <div className="grid__rowhead">
                <div className="grid__periodname">Period {period}</div>
                <div className="grid__periodtime">{periodTime(problem.slotConfig, period)}</div>
              </div>
              {problem.slotConfig.days.map((day) => {
                const id = slotId(day, period);
                const cell = visible.filter((a) => a.slot === id);
                return (
                  <div
                    key={id}
                    className={`grid__cell${blocked.has(id) ? ' grid__cell--blocked' : ''}`}
                    style={{ minHeight: dense ? 62 : 92 }}
                  >
                    {cell.map((a) => {
                      const key = `${a.subjectId}-${a.slot}`;
                      const color = colorFor(a);
                      const isSelected = selected === key;
                      return (
                        <button
                          key={key}
                          className={`sesscard${a.softViolated ? ' sesscard--soft' : ''}${
                            isSelected ? ' sesscard--selected' : ''
                          }`}
                          style={{ background: color.tint, borderLeftColor: color.c }}
                          onClick={() => setSelected(isSelected ? null : key)}
                        >
                          <div className="sesscard__top">
                            <span className="sesscard__subject">{a.subjectName}</span>
                            {a.softViolated && (
                              <span className="sesscard__flag" title={a.softReason ?? ''} />
                            )}
                          </div>
                          <div className="sesscard__teacher">{a.teacherName}</div>
                          <div className="sesscard__group">{a.groupNames.join(' · ')}</div>
                          <div className="sesscard__room">{a.roomName}</div>
                        </button>
                      );
                    })}
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
    </div>
  );
}
