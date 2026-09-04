import { useState } from 'react';

import { Button } from './ds/Button';
import { Select } from './ds/Select';
import { useBodyScrollLock } from './ds/useBodyScrollLock';
import { periodTime, weekdayName } from '../slots';
import type { Assignment, Problem, SemesterRef } from '../types';

interface Props {
  assignment: Assignment;
  problem: Problem;
  semester: SemesterRef;
  weeks: { week: string; dates: string[] }[];
  /** What moving to a candidate period would break, so the dialog can say so
   *  before the move rather than only after it. */
  conflictsAt: (date: string, period: number) => string[];
  onMove: (period: number, date: string) => void;
  onClose: () => void;
}

const dayLabel = (date: string) => `${weekdayName(date)} ${date.slice(8, 10)}/${date.slice(5, 7)}`;

/** Move a session anywhere in the semester.
 *
 *  Dragging covers the week on screen, which is all a week grid can express;
 *  this is the way to any other week -- and the only way at all from a keyboard,
 *  since a native drag has no keyboard equivalent.
 *
 *  Nothing here is disabled. A move that double-books somebody is allowed and
 *  then flagged, in the grid and here: the warning is the same one the card will
 *  carry, shown a moment earlier.
 */
export function MoveSessionDialog({
  assignment,
  problem,
  weeks,
  conflictsAt,
  onMove,
  onClose,
}: Props) {
  useBodyScrollLock(true);
  const current = weeks.findIndex((w) => w.dates.includes(assignment.date));
  const [weekIndex, setWeekIndex] = useState(Math.max(current, 0));
  const [date, setDate] = useState(assignment.date);
  const [period, setPeriod] = useState(assignment.period);

  const week = weeks[weekIndex];
  const dates = week?.dates ?? [];
  const target = dates.includes(date) ? date : (dates[0] ?? assignment.date);
  const warnings = conflictsAt(target, period);
  const unchanged = target === assignment.date && period === assignment.period;

  return (
    <div className="modal__backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Move ${assignment.subjectName}`}
      >
        <div className="modal__head">
          <div>
            <div className="display-sm">Move {assignment.subjectName}</div>
            <div className="muted-sm">
              {assignment.activity} · {assignment.teacherName} ·{' '}
              {assignment.subgroupName ?? assignment.groupNames.join(' · ')} ·{' '}
              {assignment.roomName}
            </div>
          </div>
          <button className="linkbtn linkbtn--quiet" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="modal__body">
          {/* Divs, not labels: a label forwards its click to the button inside,
              which would open and close the menu in one go. */}
          <div className="field">
            <span className="field__label">Week</span>
            <Select
              aria-label="Week"
              value={week?.week ?? ''}
              options={weeks.map((w, i) => ({
                value: w.week,
                label: `Week ${i + 1} of ${weeks.length} · ${w.dates[0]} – ${
                  w.dates[w.dates.length - 1]
                }`,
              }))}
              onChange={(key) => {
                const next = weeks.findIndex((w) => w.week === key);
                setWeekIndex(next);
                // The day has to follow: last week's Tuesday is not a date in
                // this one. The period is kept -- it means the same thing in
                // every week.
                setDate(weeks[next]?.dates[0] ?? date);
              }}
            />
          </div>

          <div className="field">
            <span className="field__label">Day</span>
            <Select
              aria-label="Day"
              value={target}
              options={dates.map((d) => ({ value: d, label: dayLabel(d) }))}
              onChange={setDate}
            />
          </div>

          <div className="field">
            <span className="field__label">Period</span>
            <Select
              aria-label="Period"
              value={period}
              options={Array.from({ length: problem.slotConfig.periods }, (_, i) => {
                const p = i + 1;
                const time = periodTime(problem.slotConfig, p);
                return { value: p, label: time ? `Period ${p} · ${time}` : `Period ${p}` };
              })}
              onChange={setPeriod}
            />
          </div>

          {warnings.length > 0 && (
            <div className="failbox">
              {warnings.map((w, i) => (
                <div key={i} className="hint__detail">
                  {w}
                </div>
              ))}
              <div className="hint__detail">
                The move is still allowed; the session will be flagged in the grid.
              </div>
            </div>
          )}
        </div>

        <div className="modal__foot">
          <Button
            variant="primary"
            disabled={unchanged}
            onClick={() => onMove(period, target)}
          >
            Move session
          </Button>
          <Button variant="secondary-pill" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
