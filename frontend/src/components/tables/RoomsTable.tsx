import { ROOM_TYPE_COLOR, ROOM_TYPE_LABEL } from '../../theme';
import type { Room } from '../../types';

interface Props {
  rooms: Room[];
  onEdit: (room: Room) => void;
  onDelete: (roomId: string) => void;
}

export function RoomsTable({ rooms, onEdit, onDelete }: Props) {
  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Room</th>
            <th>Type</th>
            <th>Capacity</th>
            <th>Building</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rooms.length === 0 && (
            <tr>
              <td colSpan={5} className="empty-row">
                No rooms yet.
              </td>
            </tr>
          )}
          {rooms.map((r) => {
            const color = ROOM_TYPE_COLOR[r.type];
            return (
              <tr key={r.id}>
                <td className="name">{r.name}</td>
                <td>
                  <span className="badge" style={{ background: color.tint, color: color.ink }}>
                    {ROOM_TYPE_LABEL[r.type]}
                  </span>
                </td>
                <td className="num">{r.capacity}</td>
                <td>{r.building ?? '—'}</td>
                <td className="right">
                  <button className="linkbtn" onClick={() => onEdit(r)}>
                    Edit
                  </button>
                  <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(r.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
