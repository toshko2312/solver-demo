import { offeringSessions, sessionsOf } from '../../slots';
import { ROOM_TYPE_COLOR, ROOM_TYPE_LABEL, subjectColor } from '../../theme';
import type { Problem, SubjectOffering } from '../../types';

interface Props {
  offerings: SubjectOffering[];
  problem: Problem;
  onEdit: (offering: SubjectOffering) => void;
  onDelete: (id: string) => void;
}

/** What is actually taught: one row per subject-as-taught-to-one-курс, with its
 *  хорариум and the two audiences that hang off it. */
export function OfferingsTable({ offerings, problem, onEdit, onDelete }: Props) {
  const subjectIds = problem.subjects.map((s) => s.id);
  const subject = (id: string) => problem.subjects.find((s) => s.id === id);
  const teacher = (id?: string | null) => problem.teachers.find((t) => t.id === id)?.name;
  const courseLabel = (id: string) => {
    const c = problem.courseInstances.find((x) => x.id === id);
    if (!c) return id;
    const code = problem.specialties.find((s) => s.id === c.specialtyId)?.code ?? c.specialtyId;
    // The semester is part of the курс's identity: the same cohort runs under
    // the same name in both, as two курсове with two sets of offerings.
    return `${c.year} курс ${code} · ${c.academicYear} S${c.semester}`;
  };

  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Дисциплина</th>
            <th>Курс</th>
            <th>Хорариум л/у</th>
            <th>Поток</th>
            <th>Упражнения</th>
            <th>Зали</th>
            <th>Spread</th>
            <th>Sessions</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {offerings.length === 0 && (
            <tr>
              <td colSpan={9} className="empty-row">
                No offerings yet.
              </td>
            </tr>
          )}
          {offerings.map((o) => {
            const s = subject(o.subjectId);
            const color = subjectColor(subjectIds, o.subjectId);
            const types = [...new Set([...o.lectureRoomTypes, ...o.exerciseRoomTypes])];
            return (
              <tr key={o.id}>
                <td className="name">
                  <span className="dot" style={{ background: color.c }} />
                  {s ? `${s.code} — ${s.name}` : o.subjectId}
                </td>
                <td>{courseLabel(o.courseInstanceId)}</td>
                <td className="num">
                  {o.lectureHours}/{o.exerciseHours}
                </td>
                <td>
                  {o.lectureHours === 0 ? (
                    <span className="muted-sm">—</span>
                  ) : (
                    <>
                      {o.streamGroupIds.length} групи
                      <div className="muted-sm">{teacher(o.leadTeacherId) ?? 'no водещ'}</div>
                    </>
                  )}
                </td>
                <td>
                  {o.exerciseHours === 0 ? (
                    <span className="muted-sm">—</span>
                  ) : (
                    <>
                      {o.exerciseUnitIds.length}{' '}
                      {o.exerciseAudience === 'subgroup' ? 'подгрупи' : 'групи'}
                      <div className="muted-sm">
                        {o.exerciseTeacherIds.length} candidate(s)
                      </div>
                    </>
                  )}
                </td>
                <td>
                  {types.map((t) => {
                    const c = ROOM_TYPE_COLOR[t];
                    return (
                      <span
                        key={t}
                        className="badge"
                        style={{ background: c.tint, color: c.ink, marginRight: 4 }}
                      >
                        {ROOM_TYPE_LABEL[t]}
                      </span>
                    );
                  })}
                </td>
                <td>
                  {o.spread}
                  {o.window && (
                    <div className="muted-sm">
                      {o.window.start} → {o.window.end}
                    </div>
                  )}
                </td>
                <td className="num">
                  {offeringSessions(o)}
                  <div className="muted-sm">
                    {sessionsOf(o, 'лекция')}л + {sessionsOf(o, 'упражнение')}у ×{' '}
                    {o.exerciseUnitIds.length}
                  </div>
                </td>
                <td className="right">
                  <button className="linkbtn" onClick={() => onEdit(o)}>
                    Edit
                  </button>
                  <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(o.id)}>
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
