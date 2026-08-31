import { Button } from '../ds/Button';
import { periodTime, slotId } from '../../slots';
import type { SlotConfig } from '../../types';

interface Props {
  config: SlotConfig;
  onChange: (config: SlotConfig) => void;
}

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** The week definition, and the quickest way to make the problem impossible:
 *  block cells until a room type or a group runs out of room. */
export function SlotConfigPane({ config, onChange }: Props) {
  const blocked = new Set(config.blockedSlots);

  const toggle = (id: string) => {
    const next = new Set(blocked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange({ ...config, blockedSlots: [...next] });
  };

  const addPeriod = () => {
    const periods = config.periods + 1;
    onChange({
      ...config,
      periods,
      periodTimes: [...config.periodTimes, `Period ${periods}`],
    });
  };

  const removePeriod = () => {
    if (config.periods <= 1) return;
    const periods = config.periods - 1;
    const gone = config.days.map((d) => slotId(d, config.periods));
    onChange({
      ...config,
      periods,
      periodTimes: config.periodTimes.slice(0, periods),
      blockedSlots: config.blockedSlots.filter((s) => !gone.includes(s)),
    });
  };

  const addDay = () => {
    const next = DAY_NAMES.find((d) => !config.days.includes(d));
    if (next) onChange({ ...config, days: [...config.days, next] });
  };

  const removeDay = () => {
    if (config.days.length <= 1) return;
    const dropped = config.days[config.days.length - 1];
    onChange({
      ...config,
      days: config.days.slice(0, -1),
      blockedSlots: config.blockedSlots.filter((s) => !s.startsWith(`${dropped.toLowerCase()}-`)),
    });
  };

  const columns = `96px repeat(${config.days.length}, minmax(0,1fr))`;

  return (
    <div className="slotgrid">
      <div className="slotgrid__legend">
        <span>Click a cell to block it. Blocked slots are excluded from solving.</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="swatch" style={{ background: '#e9f1fb', boxShadow: '0 0 0 1px rgba(0,102,204,.35)' }} />
          Teaching
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="swatch" style={{ background: '#f5f5f7', boxShadow: '0 0 0 1px #c7c7cc' }} />
          Blocked
        </span>
      </div>

      <div className="slotgrid__row" style={{ gridTemplateColumns: columns }}>
        <div />
        {config.days.map((day) => (
          <div key={day} className="slotgrid__daylabel">
            {day}
          </div>
        ))}
      </div>

      {Array.from({ length: config.periods }, (_, i) => i + 1).map((period) => (
        <div key={period} className="slotgrid__row" style={{ gridTemplateColumns: columns }}>
          <div className="slotgrid__rowhead">
            <span className="grid__periodname">Period {period}</span>
            <span className="grid__periodtime">{periodTime(config, period)}</span>
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
      ))}

      <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
        <Button variant="pearl-capsule" onClick={addPeriod}>
          Add period
        </Button>
        <Button variant="pearl-capsule" onClick={removePeriod}>
          Remove period
        </Button>
        <Button variant="pearl-capsule" onClick={addDay}>
          Add day
        </Button>
        <Button variant="pearl-capsule" onClick={removeDay}>
          Remove day
        </Button>
      </div>
    </div>
  );
}
