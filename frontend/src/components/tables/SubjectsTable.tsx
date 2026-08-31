import { ROOM_TYPE_COLOR, ROOM_TYPE_LABEL, subjectColor } from '../../theme';
import type { Group, Subject, Teacher } from '../../types';

interface Props {
  subjects: Subject[];
  teachers: Teacher[];
  groups: Group[];
  subjectIds: string[];
  onEdit: (subject: Subject) => void;
  onDelete: (subjectId: string) => void;
}

export function SubjectsTable({
  subjects,
  teachers,
  groups,
  subjectIds,
  onEdit,
  onDelete,
}: Props) {
  const teacherName = (id: string) => teachers.find((t) => t.id === id)?.name ?? '(unknown)';
  const groupName = (id: string) => groups.find((g) => g.id === id)?.name ?? '(unknown)';

  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Subject</th>
            <th>Room types</th>
            <th>Sessions / wk</th>
            <th>Teachers</th>
            <th>Groups</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {subjects.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-row">
                No subjects yet.
              </td>
            </tr>
          )}
          {subjects.map((s) => {
            return (
              <tr key={s.id}>
                <td className="name">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 3,
                        flex: 'none',
                        background: subjectColor(subjectIds, s.id).c,
                      }}
                    />
                    <span>{s.name}</span>
                  </div>
                </td>
                <td>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {s.allowedRoomTypes.map((t) => (
                      <span
                        key={t}
                        className="badge"
                        style={{ background: ROOM_TYPE_COLOR[t].tint, color: ROOM_TYPE_COLOR[t].ink }}
                      >
                        {ROOM_TYPE_LABEL[t]}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="num">{s.sessionsPerWeek}</td>
                <td>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {s.teacherIds.map((id) => (
                      <span key={id} className="badge badge--plain">
                        {teacherName(id)}
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {s.groupIds.map((gid) => (
                      <span key={gid} className="badge badge--plain">
                        {groupName(gid)}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="right">
                  <button className="linkbtn" onClick={() => onEdit(s)}>
                    Edit
                  </button>
                  <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(s.id)}>
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
