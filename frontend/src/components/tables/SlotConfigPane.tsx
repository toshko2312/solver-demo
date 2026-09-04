import { useState } from 'react';

import { Button } from '../ds/Button';
import { Select } from '../ds/Select';
import {
  clockTime,
  formatPeriodTime,
  minutesOf,
  parsePeriodTime,
  periodTimeErrors,
  slotId,
} from '../../slots';
import type { SlotConfig } from '../../types';

interface Props {
  config: SlotConfig;
  onChange: (config: SlotConfig) => void;
  /** Removing a day or a period orphans teacher preferences too, which this pane
   *  cannot see -- the cascade lives on the Data setup screen with the others. */
  onRemoveDay: (day: string) => void;
  onRemovePeriod: () => void;
}

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** A period with no stored time, so the editor has something to render. */
const BLANK = '';

const pad = (n: number) => String(n).padStart(2, '0');

// Built once: four dropdowns per period, six periods, and none of it depends on
// the problem. Times are picked to the quarter hour -- every period in both seed
// files already lands on one.
const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: pad(h), label: pad(h) }));
const MINUTES = ['00', '15', '30', '45'];

/** The minute list, widened to hold a value that is not on the quarter hour.
 *  A problem stored before the picker existed can carry any minute, and a Select
 *  whose value matches no option falls back to its placeholder -- which would
 *  hide a real time rather than let it be seen and changed. */
function minuteOptions(current: string) {
  const all = MINUTES.includes(current) || !/^\d{2}$/.test(current)
    ? MINUTES
    : [...MINUTES, current].sort();
  return all.map((m) => ({ value: m, label: m }));
}

/** periodTimes and periods are two fields that must agree; an older stored
 *  problem can have a short array, and `periodTime()` covers it with ''. */
function padded(config: SlotConfig): string[] {
  return Array.from({ length: config.periods }, (_, i) => config.periodTimes[i] ?? BLANK);
}

/** The week definition: which weekdays are taught, when each period runs, and
 *  which cells are switched off. Blocking cells is still the quickest way to make
 *  the problem impossible -- block until a room type or a group runs out of room. */
export function SlotConfigPane({ config, onChange, onRemoveDay, onRemovePeriod }: Props) {
  const blocked = new Set(config.blockedSlots);

  // Times are edited through a draft, so a period whose new time would overlap
  // its neighbour keeps what was typed and shows why, instead of being silently
  // dropped or half-written into the problem. `source` is the last set of times
  // this pane agreed with, which is what tells our own writes coming back as
  // props apart from a real outside change -- a seed load, or a day removed
  // through the cascade -- that the draft must adopt. It is state and not a ref
  // on purpose: a ref mutated during render is a side effect, and React is free
  // to render twice and swallow the update that goes with it.
  const [draft, setDraft] = useState<string[]>(() => padded(config));
  const [source, setSource] = useState(() => padded(config).join('|'));
  const incoming = padded(config).join('|');
  if (incoming !== source) {
    setSource(incoming);
    setDraft(padded(config));
  }

  const errors = periodTimeErrors(draft);

  const commit = (times: string[], rest: Partial<SlotConfig> = {}) => {
    setSource(times.join('|'));
    onChange({ ...config, periodTimes: times, ...rest });
  };

  const setBound = (period: number, field: 'start' | 'end', value: string) => {
    // A row with no readable time at all -- an older stored problem can hold free
    // text, since 'Add period' once wrote 'Period 7' -- is repaired by the first
    // pick rather than left half-written: the other end follows at the 90 minutes
    // `addPeriod` also assumes. Writing '09:00-' instead would parse as nothing,
    // so both dropdowns would go on showing the empty placeholder.
    const span =
      parsePeriodTime(draft[period - 1]) ??
      (field === 'start'
        ? { start: value, end: clockTime(minutesOf(value) + 90) }
        : { start: clockTime(minutesOf(value) - 90), end: value });
    const next = [...draft];
    next[period - 1] = formatPeriodTime(
      field === 'start' ? { ...span, start: value } : { ...span, end: value },
    );
    setDraft(next);
    // Write through only when the edit makes nothing worse. Comparing against the
    // errors already there, rather than demanding a clean grid, keeps a legacy
    // row with no readable time from freezing every other period.
    const before = periodTimeErrors(draft);
    if (![...periodTimeErrors(next).keys()].some((p) => !before.has(p))) commit(next);
  };

  /** One end of a period, as an hour dropdown and a minute dropdown.
   *
   *  Native time inputs drew this until now, and drew it in whatever format the
   *  viewer's locale asked for -- 12-hour with an AM/PM field and a clock glyph
   *  from an icon set this app does not own. The labels are ours here, so the
   *  clock is always 24-hour (see DESIGN.md on why there are no native selects
   *  either). Half a time is never written: picking an hour into an empty bound
   *  settles the minute at :00 rather than leaving 08: behind, which parses as
   *  nothing at all. */
  const bound = (
    period: number,
    field: 'start' | 'end',
    value: string | undefined,
    verb: string,
  ) => {
    const [hh = '', mm = ''] = (value ?? '').split(':');
    return (
      <span className="slotgrid__time">
        <Select
          size="sm"
          value={hh}
          placeholder="--"
          aria-label={`Period ${period} ${verb} — hour`}
          options={HOURS}
          onChange={(h) => setBound(period, field, `${h}:${mm || '00'}`)}
        />
        <Select
          size="sm"
          value={mm}
          placeholder="--"
          aria-label={`Period ${period} ${verb} — minute`}
          options={minuteOptions(mm)}
          onChange={(m) => setBound(period, field, `${hh || '00'}:${m}`)}
        />
      </span>
    );
  };

  const toggle = (id: string) => {
    const next = new Set(blocked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange({ ...config, blockedSlots: [...next] });
  };

  const addPeriod = () => {
    // A real span, not the placeholder 'Period N' this used to write: the new
    // period picks up where the last one left off, 15 minutes later and just as
    // long, so it is valid the moment it appears.
    const last = parsePeriodTime(draft[draft.length - 1] ?? BLANK);
    const start = last ? minutesOf(last.end) + 15 : 8 * 60;
    const length = last ? minutesOf(last.end) - minutesOf(last.start) : 90;
    const span = { start: clockTime(start), end: clockTime(start + length) };
    const times = [...draft, formatPeriodTime(span)];
    setDraft(times);
    commit(times, { periods: config.periods + 1 });
  };

  const toggleDay = (day: string) => {
    if (config.days.includes(day)) {
      onRemoveDay(day);
      return;
    }
    // Rebuilt from DAY_NAMES rather than appended, so a day switched back on
    // returns to its own column instead of the end of the week.
    onChange({ ...config, days: DAY_NAMES.filter((d) => d === day || config.days.includes(d)) });
  };

  const columns = `280px repeat(${config.days.length}, minmax(0,1fr))`;

  return (
    <div className="slotgrid">
      <div className="slotgrid__legend">
        <span>
          Click a cell to block that period. Blocked periods are excluded from solving. The обедна
          почивка is not a setting: it is the gap the period times leave, and nothing can be
          scheduled across it because no period covers it.
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="swatch" style={{ background: '#e9f1fb', boxShadow: '0 0 0 1px rgba(0,102,204,.35)' }} />
          Teaching
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="swatch" style={{ background: '#f5f5f7', boxShadow: '0 0 0 1px #c7c7cc' }} />
          Blocked
        </span>
      </div>

      <div className="daytoggles">
        <span className="daytoggles__label">Teaching days</span>
        {DAY_NAMES.map((day) => {
          const on = config.days.includes(day);
          const last = on && config.days.length <= 1;
          return (
            <button
              key={day}
              type="button"
              className={`daytoggle${on ? ' daytoggle--on' : ''}`}
              aria-pressed={on}
              disabled={last}
              title={last ? 'A week needs at least one teaching day.' : undefined}
              onClick={() => toggleDay(day)}
            >
              {day}
            </button>
          );
        })}
      </div>

      <div className="slotgrid__row" style={{ gridTemplateColumns: columns }}>
        <div />
        {config.days.map((day) => (
          <div key={day} className="slotgrid__daylabel">
            {day}
          </div>
        ))}
      </div>

      {Array.from({ length: config.periods }, (_, i) => i + 1).map((period) => {
        const span = parsePeriodTime(draft[period - 1]);
        const bad = errors.get(period);
        // The gap before this period, if the timetable leaves one. That gap is
        // the обедна почивка -- there is nothing else to say about it.
        const previous = parsePeriodTime(draft[period - 2] ?? BLANK);
        const gap =
          previous && span ? minutesOf(span.start) - minutesOf(previous.end) : 0;
        return (
          <div key={period}>
            {gap >= 30 && (
              <div className="slotgrid__break">
                {previous!.end}–{span!.start} · {gap} min between periods
              </div>
            )}
            <div className="slotgrid__row" style={{ gridTemplateColumns: columns }}>
              <div className={`slotgrid__rowhead${bad ? ' slotgrid__rowhead--bad' : ''}`}>
                <span className="grid__periodname">Period {period}</span>
                <span className="slotgrid__times">
                  {bound(period, 'start', span?.start, 'starts')}
                  <span aria-hidden="true">–</span>
                  {bound(period, 'end', span?.end, 'ends')}
                </span>
                {bad && <span className="slotgrid__err">{bad}</span>}
              </div>
              {config.days.map((day) => {
                const id = slotId(day, period);
                const off = blocked.has(id);
                return (
                  <button
                    key={id}
                    type="button"
                    className={`slotcell${off ? ' slotcell--blocked' : ''}`}
                    onClick={() => toggle(id)}
                  >
                    {off ? 'Blocked' : 'Teaching'}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}

      <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
        <Button variant="pearl-capsule" onClick={addPeriod}>
          Add period
        </Button>
        <Button variant="pearl-capsule" onClick={onRemovePeriod}>
          Remove period
        </Button>
      </div>
    </div>
  );
}
