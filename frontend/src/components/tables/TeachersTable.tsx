import { SlotPicker } from '../SlotPicker';
import type { SlotConfig, Teacher } from '../../types';

interface Props {
  teachers: Teacher[];
  slotConfig: SlotConfig;
  totalSlots: number;
  onTogglePreference: (teacherId: string, slotId: string) => void;
  onEdit: (teacher: Teacher) => void;
  onDelete: (teacherId: string) => void;
}

export function TeachersTable({
  teachers,
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
            <th>Department</th>
            <th>
              Preferred slots <span className="field__soft">soft</span>
            </th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {teachers.length === 0 && (
            <tr>
              <td colSpan={4} className="empty-row">
                No teachers yet.
              </td>
            </tr>
          )}
          {teachers.map((t) => (
            <tr key={t.id}>
              <td className="name">{t.name}</td>
              <td>{t.department ?? '—'}</td>
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
