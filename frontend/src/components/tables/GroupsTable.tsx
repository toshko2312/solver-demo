import type { Group, Subject } from '../../types';

interface Props {
  groups: Group[];
  subjects: Subject[];
  onEdit: (group: Group) => void;
  onDelete: (groupId: string) => void;
}

export function GroupsTable({ groups, subjects, onEdit, onDelete }: Props) {
  // Only the semesters this group actually attends count towards its load:
  // a subject can run for a different cohort in each term.
  const semesterLoad = (groupId: string) => {
    const perSemester = new Map<string, number>();
    for (const s of subjects) {
      for (const x of s.semesters) {
        if (!x.groupIds.includes(groupId)) continue;
        const k = `${x.academicYear} S${x.index}`;
        perSemester.set(k, (perSemester.get(k) ?? 0) + x.totalSessions);
      }
    }
    return [...perSemester.entries()].sort(([a], [b]) => a.localeCompare(b));
  };

  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Group</th>
            <th>Students</th>
            <th>Programme</th>
            <th>Semesters</th>
            <th>Sessions</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {groups.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-row">
                No groups yet.
              </td>
            </tr>
          )}
          {groups.map((g) => (
            <tr key={g.id}>
              <td className="name">{g.name}</td>
              <td className="num">{g.size}</td>
              <td>{g.programme ?? '—'}</td>
              <td>
                {g.semesters.length === 0 ? (
                  <span className="muted-sm">no dates yet</span>
                ) : (
                  g.semesters
                    .map((x) => `${x.academicYear} S${x.index}`)
                    .join(' · ')
                )}
              </td>
              <td>
                {semesterLoad(g.id).length === 0 ? (
                  <span className="muted-sm">—</span>
                ) : (
                  semesterLoad(g.id).map(([k, n]) => `${k}: ${n}`).join(' · ')
                )}
              </td>
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
