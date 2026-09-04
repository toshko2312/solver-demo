import { SlotPicker } from '../SlotPicker';
import { effectiveWeight } from '../../theme';
import type { Katedra, Role, Room, SlotConfig, Teacher } from '../../types';

interface Props {
  teachers: Teacher[];
  roles: Role[];
  rooms: Room[];
  katedri: Katedra[];
  slotConfig: SlotConfig;
  totalSlots: number;
  onTogglePreference: (teacherId: string, slotId: string) => void;
  onEdit: (teacher: Teacher) => void;
  onDelete: (teacherId: string) => void;
}

export function TeachersTable({
  teachers,
  roles,
  rooms,
  katedri,
  slotConfig,
  totalSlots,
  onTogglePreference,
  onEdit,
  onDelete,
}: Props) {
  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Teacher</th>
            <th>Катедра</th>
            <th>
              Rank <span className="field__soft">priority</span>
            </th>
            <th>
              Preferred periods <span className="field__soft">soft</span>
            </th>
            <th>
              Availability <span className="field__soft">HARD</span>
            </th>
            <th>
              Preferred rooms <span className="field__soft">soft, ranked</span>
            </th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {teachers.length === 0 && (
            <tr>
              <td colSpan={7} className="empty-row">
                No teachers yet.
              </td>
            </tr>
          )}
          {teachers.map((t) => (
            <tr key={t.id}>
              <td className="name">{t.name}</td>
              <td>{katedri.find((k) => k.id === t.katedraId)?.name ?? '—'}</td>
              <td>
                {roles.find((r) => r.id === t.role)?.short ?? (
                  <span className="muted-sm">unranked</span>
                )}{' '}
                <span className="muted-sm">
                  w{effectiveWeight(t, roles)}
                  {t.priorityWeight != null ? ' (override)' : ''}
                </span>
              </td>
              <td>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <SlotPicker
                    config={slotConfig}
                    selected={t.preferredSlots}
                    onToggle={(slotId) => onTogglePreference(t.id, slotId)}
                  />
                  <span className="muted-sm">
                    {t.preferredSlots.length} of {totalSlots} preferred
                  </span>
                </div>
              </td>
              <td>
                {t.hardAvailability.length === 0 ? (
                  <span className="muted-sm">always</span>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <SlotPicker
                      config={slotConfig}
                      selected={t.hardAvailability}
                      intent="hard"
                      onToggle={() => undefined}
                    />
                    <span className="muted-sm">
                      {t.hardAvailability.length} period(s)
                      {t.maxWeeklyPeriods != null ? `, max ${t.maxWeeklyPeriods}/week` : ''}
                    </span>
                  </div>
                )}
              </td>
              <td>
                {t.preferredRooms.length === 0 ? (
                  <span className="muted-sm">any</span>
                ) : (
                  <span className="chiprow">
                    {t.preferredRooms.map((id, i) => {
                      const room = rooms.find((r) => r.id === id);
                      return (
                        <span key={id} className="chip chip--static">
                          {i + 1}. {room ? room.name : id}
                        </span>
                      );
                    })}
                  </span>
                )}
              </td>
              <td className="right">
                <button className="linkbtn" onClick={() => onEdit(t)}>
                  Edit
                </button>
                <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(t.id)}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
