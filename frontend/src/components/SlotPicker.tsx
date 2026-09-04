import { allSlots, periodTime } from '../slots';
import type { SlotConfig } from '../types';

interface Props {
  config: SlotConfig;
  selected: string[];
  onToggle: (slotId: string) => void;
  size?: 'sm' | 'lg';
  /** 'pref' is the soft preference grid; 'hard' is availability, which the
   *  solver may never trade away. The two are drawn apart on purpose. */
  intent?: 'pref' | 'hard';
}

/** The weekly grid: days across, periods down. Used inline in the teachers table
 *  and full-size in the teacher form. */
export function SlotPicker({ config, selected, onToggle, size = 'sm', intent = 'pref' }: Props) {
  const chosen = new Set(selected);
  const slots = allSlots(config);
  const byPeriod: typeof slots[] = [];
  for (let p = 1; p <= config.periods; p++) {
    byPeriod.push(slots.filter((s) => s.period === p));
  }

  return (
    <div
      className={`prefgrid${size === 'lg' ? ' prefgrid--lg' : ''}${
        intent === 'hard' ? ' prefgrid--hard' : ''
      }`}
      style={{
        gridTemplateColumns: `repeat(${config.days.length}, ${size === 'lg' ? '1fr' : '13px'})`,
      }}
    >
      {byPeriod.flatMap((row, pi) =>
        row.map((cell) => {
          const on = chosen.has(cell.id);
          const when = periodTime(config, pi + 1);
          const label = `${cell.day} period ${pi + 1}${when ? ` (${when})` : ''}`;
          return (
            <button
              key={cell.id}
              type="button"
              title={`${label}${on ? (intent === 'hard' ? ' — available' : ' — preferred') : ''}`}
              aria-label={label}
              aria-pressed={on}
              className={`prefgrid__cell${on ? ' prefgrid__cell--on' : ''}`}
              onClick={() => onToggle(cell.id)}
            />
          );
        }),
      )}
    </div>
  );
}
