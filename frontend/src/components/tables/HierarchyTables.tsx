/** The academic hierarchy above and below Group: Faculty, Katedra, Specialty,
 *  CourseInstance and Subgroup.
 *
 *  Five small tables in one file on purpose -- each is a handful of columns over
 *  a flat list, and five files of thirty lines would say less than this one. */

import { teachingDates } from '../../slots';
import type {
  CourseInstance,
  Faculty,
  Group,
  Katedra,
  Problem,
  SlotConfig,
  Specialty,
  Subgroup,
} from '../../types';

interface Row<T> {
  rows: T[];
  onEdit: (row: T) => void;
  onDelete: (id: string) => void;
}

function Actions<T extends { id: string }>({ row, onEdit, onDelete }: { row: T } & Omit<Row<T>, 'rows'>) {
  return (
    <td className="right">
      <button className="linkbtn" onClick={() => onEdit(row)}>
        Edit
      </button>
      <button className="linkbtn linkbtn--quiet" onClick={() => onDelete(row.id)}>
        Delete
      </button>
    </td>
  );
}

function Empty({ colSpan, what }: { colSpan: number; what: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="empty-row">
        No {what} yet.
      </td>
    </tr>
  );
}

export function FacultiesTable({ rows, onEdit, onDelete, problem }: Row<Faculty> & { problem: Problem }) {
  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Факултет</th>
            <th>Катедри</th>
            <th>Специалности</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <Empty colSpan={4} what="faculties" />}
          {rows.map((f) => (
            <tr key={f.id}>
              <td className="name">{f.name}</td>
              <td className="num">{problem.katedri.filter((k) => k.facultyId === f.id).length}</td>
              <td className="num">
                {problem.specialties.filter((s) => s.facultyId === f.id).length}
              </td>
              <Actions row={f} onEdit={onEdit} onDelete={onDelete} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function KatedriTable({ rows, onEdit, onDelete, problem }: Row<Katedra> & { problem: Problem }) {
  const facultyName = (id?: string | null) =>
    problem.faculties.find((f) => f.id === id)?.name ?? '—';
  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Катедра</th>
            <th>Факултет</th>
            <th>Преподаватели</th>
            <th>Дисциплини</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <Empty colSpan={5} what="катедри" />}
          {rows.map((k) => (
            <tr key={k.id}>
              <td className="name">{k.name}</td>
              <td>{facultyName(k.facultyId)}</td>
              <td className="num">{problem.teachers.filter((t) => t.katedraId === k.id).length}</td>
              <td className="num">{problem.subjects.filter((s) => s.katedraId === k.id).length}</td>
              <Actions row={k} onEdit={onEdit} onDelete={onDelete} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SpecialtiesTable({
  rows,
  onEdit,
  onDelete,
  problem,
}: Row<Specialty> & { problem: Problem }) {
  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Код</th>
            <th>Специалност</th>
            <th>ОКС</th>
            <th>Форма</th>
            <th>Обучаеми</th>
            <th>Години</th>
            <th>Курсове</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <Empty colSpan={8} what="specialties" />}
          {rows.map((s) => (
            <tr key={s.id}>
              <td className="name">{s.code}</td>
              <td>{s.name}</td>
              <td>{s.degree}</td>
              <td>{s.form}</td>
              <td>{s.studentKind}и</td>
              <td className="num">{s.durationYears}</td>
              <td className="num">
                {problem.courseInstances.filter((c) => c.specialtyId === s.id).length}
              </td>
              <Actions row={s} onEdit={onEdit} onDelete={onDelete} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CoursesTable({
  rows,
  onEdit,
  onDelete,
  problem,
  config,
}: Row<CourseInstance> & { problem: Problem; config: SlotConfig }) {
  const code = (id: string) => problem.specialties.find((s) => s.id === id)?.code ?? id;
  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Курс</th>
            <th>Семестър</th>
            <th>Term</th>
            <th>Teaching days</th>
            <th>Non-teaching</th>
            <th>Групи</th>
            <th>Periods/day</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <Empty colSpan={8} what="курсове" />}
          {rows.map((c) => (
            <tr key={c.id}>
              <td className="name">
                {c.year} курс {code(c.specialtyId)}
              </td>
              <td>
                {c.academicYear} S{c.semester}
              </td>
              <td>
                {c.start} → {c.end}
              </td>
              <td className="num">{teachingDates(c, config).length}</td>
              <td>
                {c.nonTeaching.length === 0 ? (
                  <span className="muted-sm">—</span>
                ) : (
                  [...new Set(c.nonTeaching.map((p) => p.kind))].join(' · ')
                )}
              </td>
              <td className="num">
                {problem.groups.filter((g) => g.courseInstanceId === c.id).length}
              </td>
              <td className="num">{c.maxPeriodsPerDay}</td>
              <Actions row={c} onEdit={onEdit} onDelete={onDelete} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SubgroupsTable({
  rows,
  onEdit,
  onDelete,
  groups,
}: Row<Subgroup> & { groups: Group[] }) {
  const groupName = (id: string) => groups.find((g) => g.id === id)?.name ?? id;
  const groupSize = (id: string) => groups.find((g) => g.id === id)?.size;
  return (
    <div className="tablewrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Подгрупа</th>
            <th>Група</th>
            <th>Обучаеми</th>
            <th>Of group</th>
            <th className="right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <Empty colSpan={5} what="подгрупи" />}
          {rows.map((s) => {
            const whole = groupSize(s.groupId);
            return (
              <tr key={s.id}>
                <td className="name">{s.name}</td>
                <td>{groupName(s.groupId)}</td>
                <td className="num">{s.size}</td>
                <td className="num">{whole ? `${Math.round((s.size / whole) * 100)}%` : '—'}</td>
                <Actions row={s} onEdit={onEdit} onDelete={onDelete} />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
