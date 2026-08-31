import { allSlots } from '../slots';
import type { SlotConfig } from '../types';

interface Props {
  config: SlotConfig;
  selected: string[];
  onToggle: (slotId: string) => void;
  size?: 'sm' | 'lg';
}

/** The 5x5 preference grid: days across, periods down. Used inline in the
 *  teachers table and full-size in the teacher form. */
export function SlotPicker({ config, selected, onToggle, size = 'sm' }: Props) {
  const chosen = new Set(selected);
  const slots = allSlots(config);
  const byPeriod: string[][] = [];
  for (let p = 1; p <= config.periods; p++) {
    byPeriod.push(slots.filter((s) => s.period === p).map((s) => s.id));
  }

  return (
    <div
      className={`prefgrid${size === 'lg' ? ' prefgrid--lg' : ''}`}
      style={{ gridTemplateColumns: `repeat(${config.days.length}, ${size === 'lg' ? '1fr' : '13px'})` }}
    >
      {byPeriod.flatMap((row, pi) =>
        row.map((id, di) => {
          const on = chosen.has(id);
          return (
            <button
              key={id}
              type="button"
              title={`${config.days[di]} Period ${pi + 1}${on ? ' — preferred' : ''}`}
              aria-label={`${config.days[di]} period ${pi + 1}`}
              aria-pressed={on}
              className={`prefgrid__cell${on ? ' prefgrid__cell--on' : ''}`}
              onClick={() => onToggle(id)}
            />
          );
        }),
      )}
    </div>
  );
}
