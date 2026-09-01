import { ROOM_TYPE_LABEL } from '../theme';
import type { Room } from '../types';

interface Props {
  rooms: Room[];
  /** Ordered: index 0 is the most wanted room. */
  selected: string[];
  onChange: (next: string[]) => void;
}

/** Ranked room preference.
 *
 *  SlotPicker cannot be reused here: it is an unordered toggle grid, and the
 *  whole point of this field is the order. Chosen rooms are a numbered list you
 *  reorder; unchosen ones are chips you append.
 *
 *  The ranking is scored *per room type* by the solver, so the chosen list is
 *  grouped by type -- otherwise "#3" reads as third overall when it is really
 *  third among lecture halls.
 */
export function RankedRoomPicker({ rooms, selected, onChange }: Props) {
  const byId = new Map(rooms.map((r) => [r.id, r]));
  const chosen = selected.filter((id) => byId.has(id));
  const available = rooms.filter((r) => !chosen.includes(r.id));

  const move = (from: number, to: number) => {
    if (to < 0 || to >= chosen.length) return;
    const next = [...chosen];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  // Rank shown per type, matching how the solver scores it.
  const rankWithinType = (index: number): number => {
    const type = byId.get(chosen[index])!.type;
    return chosen.slice(0, index).filter((id) => byId.get(id)!.type === type).length;
  };

  return (
    <div className="rankedrooms">
      {chosen.length === 0 && (
        <div className="muted-sm">No room preference — any suitable room will do.</div>
      )}

      <ol className="rankedrooms__list">
        {chosen.map((id, i) => {
          const room = byId.get(id)!;
          return (
            <li key={id} className="rankedrooms__item">
              <span className="rankedrooms__rank">#{rankWithinType(i) + 1}</span>
              <span className="rankedrooms__name">{room.name}</span>
              <span className="muted-sm">{ROOM_TYPE_LABEL[room.type]}</span>
              <span className="rankedrooms__actions">
                <button
                  type="button"
                  className="linkbtn"
                  aria-label={`Move ${room.name} up`}
                  disabled={i === 0}
                  onClick={() => move(i, i - 1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="linkbtn"
                  aria-label={`Move ${room.name} down`}
                  disabled={i === chosen.length - 1}
                  onClick={() => move(i, i + 1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="linkbtn linkbtn--quiet"
                  aria-label={`Remove ${room.name}`}
                  onClick={() => onChange(chosen.filter((x) => x !== id))}
                >
                  ×
                </button>
              </span>
            </li>
          );
        })}
      </ol>

      {available.length > 0 && (
        <div className="chiprow">
          {available.map((r) => (
            <button
              key={r.id}
              type="button"
              className="chip"
              onClick={() => onChange([...chosen, r.id])}
            >
              + {r.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
