import type { Group, Subject } from '../../types';

interface Props {
  groups: Group[];
  subjects: Subject[];
  onEdit: (group: Group) => void;
  onDelete: (groupId: string) => void;
}

export function GroupsTable({ groups, subjects, onEdit, onDelete }: Props) {
  const weeklySessions = (groupId: string) =>
    subjects
      .filter((s) => s.groupIds.includes(groupId))
      .reduce((total, s) => total + s.sessionsPerWeek, 0);

  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Group</th>
            <th>Students</th>
            <th>Programme</th>
            <th>Weekly sessions</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {groups.length === 0 && (
            <tr>
              <td colSpan={5} className="empty-row">
                No groups yet.
              </td>
            </tr>
          )}
          {groups.map((g) => (
            <tr key={g.id}>
              <td className="name">{g.name}</td>
              <td className="num">{g.size}</td>
              <td>{g.programme ?? '—'}</td>
              <td className="num">{weeklySessions(g.id)}</td>
              <td className="right">
                <button className="linkbtn" onClick={() => onEdit(g)}>
                  Edit
                </button>
                <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(g.id)}>
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
