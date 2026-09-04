import { subjectColor } from '../../theme';
import type { Katedra, Subject, SubjectOffering } from '../../types';

interface Props {
  subjects: Subject[];
  katedri: Katedra[];
  offerings: SubjectOffering[];
  subjectIds: string[];
  onEdit: (subject: Subject) => void;
  onDelete: (subjectId: string) => void;
}

/** The catalogue. What is *taught* is a SubjectOffering, so this table is short
 *  on purpose: a code, a name, an owning катедра, and where it is taught. */
export function SubjectsTable({
  subjects,
  katedri,
  offerings,
  subjectIds,
  onEdit,
  onDelete,
}: Props) {
  const katedraName = (id?: string | null) => katedri.find((k) => k.id === id)?.name ?? '—';

  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Код</th>
            <th>Дисциплина</th>
            <th>Катедра</th>
            <th>Offerings</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {subjects.length === 0 && (
            <tr>
              <td colSpan={5} className="empty-row">
                No subjects yet.
              </td>
            </tr>
          )}
          {subjects.map((s) => {
            const color = subjectColor(subjectIds, s.id);
            const mine = offerings.filter((o) => o.subjectId === s.id);
            return (
              <tr key={s.id}>
                <td className="name">
                  <span className="dot" style={{ background: color.c }} />
                  {s.code}
                </td>
                <td>{s.name}</td>
                <td>{katedraName(s.katedraId)}</td>
                <td className="num">{mine.length}</td>
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
