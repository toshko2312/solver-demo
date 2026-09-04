import { sessionsOf } from '../../slots';
import type { CourseInstance, Group, Specialty, Subgroup, SubjectOffering } from '../../types';

interface Props {
  groups: Group[];
  courses: CourseInstance[];
  specialties: Specialty[];
  subgroups: Subgroup[];
  offerings: SubjectOffering[];
  onEdit: (group: Group) => void;
  onDelete: (groupId: string) => void;
}

export function GroupsTable({
  groups,
  courses,
  specialties,
  subgroups,
  offerings,
  onEdit,
  onDelete,
}: Props) {
  const courseLabel = (id: string) => {
    const c = courses.find((x) => x.id === id);
    if (!c) return id;
    const code = specialties.find((s) => s.id === c.specialtyId)?.code ?? c.specialtyId;
    return `${c.year} курс ${code} · ${c.academicYear} S${c.semester}`;
  };

  /** Periods this група is busy for. Подгрупите of one група may run side by side,
   *  so their sessions are counted once per подгрупа but the група is only ever
   *  busy for as many periods as the fullest of them -- which is why this is a
   *  load figure and not a timetable. */
  const load = (groupId: string) => {
    const mine = subgroups.filter((s) => s.groupId === groupId).map((s) => s.id);
    let n = 0;
    for (const o of offerings) {
      if (o.streamGroupIds.includes(groupId)) n += sessionsOf(o, 'лекция');
      const units = o.exerciseUnitIds.filter((u) => u === groupId || mine.includes(u));
      n += sessionsOf(o, 'упражнение') * units.length;
    }
    return n;
  };

  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Група</th>
            <th>Обучаеми</th>
            <th>Курс</th>
            <th>Подгрупи</th>
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
          {groups.map((g) => {
            const mine = subgroups.filter((s) => s.groupId === g.id);
            return (
              <tr key={g.id}>
                <td className="name">{g.name}</td>
                <td className="num">{g.size}</td>
                <td>{courseLabel(g.courseInstanceId)}</td>
                <td>
                  {mine.length === 0 ? (
                    <span className="muted-sm">—</span>
                  ) : (
                    mine.map((s) => `${s.name} (${s.size})`).join(' · ')
                  )}
                </td>
                <td className="num">{load(g.id)}</td>
                <td className="right">
                  <button className="linkbtn" onClick={() => onEdit(g)}>
                    Edit
                  </button>
                  <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(g.id)}>
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
