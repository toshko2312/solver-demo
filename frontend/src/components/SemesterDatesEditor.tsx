import { Select } from './ds/Select';
import { teachingDates } from '../slots';
import type { GroupSemester, SlotConfig } from '../types';

interface Props {
  value: GroupSemester[];
  config: SlotConfig;
  onChange: (next: GroupSemester[]) => void;
}

/** A group's term dates, one row per semester.
 *
 *  Dates are per group by design, so this is where a cohort's calendar is set.
 *  The teaching-week count is shown live because it is what an even spread is
 *  measured against — and it is the number that moves when a break is added.
 */
export function SemesterDatesEditor({ value, config, onChange }: Props) {
  const patch = (i: number, fields: Partial<GroupSemester>) =>
    onChange(value.map((s, j) => (j === i ? { ...s, ...fields } : s)));

  const years = [...new Set(value.map((s) => s.academicYear))];
  const nextYear = () => {
    if (years.length === 0) return '2025/2026';
    const last = years.sort().at(-1)!;
    const start = Number(last.split('/')[0]) + 1;
    return `${start}/${start + 1}`;
  };

  const add = () => {
    // Offer the missing index of the newest year first, then a fresh year --
    // "up to two semesters per year" made concrete.
    const year = years.sort().at(-1) ?? nextYear();
    const taken = value.filter((s) => s.academicYear === year).map((s) => s.index);
    const [y, index] =
      taken.length < 2 ? [year, (taken.includes(1) ? 2 : 1) as 1 | 2] : [nextYear(), 1 as 1 | 2];
    const startYear = Number(y.split('/')[index === 1 ? 0 : 1]);
    onChange([
      ...value,
      {
        academicYear: y,
        index,
        start: index === 1 ? `${startYear}-09-15` : `${startYear}-02-09`,
        end: index === 1 ? `${startYear + 1}-01-30` : `${startYear}-06-12`,
        breaks: [],
      },
    ]);
  };

  return (
    <div className="semlist">
      {value.length === 0 && (
        <div className="muted-sm">
          No term dates yet — this group takes no part in any timetable until it has some.
        </div>
      )}

      {value.map((sem, i) => (
        <div key={`${sem.academicYear}-${sem.index}`} className="semrow">
          <div className="semrow__head">
            <input
              className="semrow__year"
              value={sem.academicYear}
              onChange={(e) => patch(i, { academicYear: e.target.value })}
            />
            <Select
              size="sm"
              aria-label="Semester"
              value={sem.index}
              options={[
                { value: 1, label: 'Semester 1' },
                { value: 2, label: 'Semester 2' },
              ]}
              onChange={(index) => patch(i, { index: index as 1 | 2 })}
            />
            <input type="date" value={sem.start} onChange={(e) => patch(i, { start: e.target.value })} />
            <span className="muted-sm">to</span>
            <input type="date" value={sem.end} onChange={(e) => patch(i, { end: e.target.value })} />
            <span className="muted-sm">
              {teachingDates(sem, config).length} teaching day(s)
            </span>
            <button
              className="linkbtn linkbtn--quiet"
              onClick={() => onChange(value.filter((_, j) => j !== i))}
            >
              Remove
            </button>
          </div>

          <div className="semrow__breaks">
            {sem.breaks.map((b, bi) => (
              <div key={bi} className="semrow__break">
                <input
                  placeholder="Break"
                  value={b.label ?? ''}
                  onChange={(e) =>
                    patch(i, {
                      breaks: sem.breaks.map((x, j) =>
                        j === bi ? { ...x, label: e.target.value } : x,
                      ),
                    })
                  }
                />
                <input
                  type="date"
                  value={b.start}
                  onChange={(e) =>
                    patch(i, {
                      breaks: sem.breaks.map((x, j) =>
                        j === bi ? { ...x, start: e.target.value } : x,
                      ),
                    })
                  }
                />
                <input
                  type="date"
                  value={b.end}
                  onChange={(e) =>
                    patch(i, {
                      breaks: sem.breaks.map((x, j) =>
                        j === bi ? { ...x, end: e.target.value } : x,
                      ),
                    })
                  }
                />
                <button
                  className="linkbtn linkbtn--quiet"
                  onClick={() =>
                    patch(i, { breaks: sem.breaks.filter((_, j) => j !== bi) })
                  }
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="linkbtn"
              onClick={() =>
                patch(i, {
                  breaks: [...sem.breaks, { start: sem.start, end: sem.start, label: '' }],
                })
              }
            >
              + Break
            </button>
          </div>
        </div>
      ))}

      <button className="linkbtn" onClick={add}>
        + Semester
      </button>
    </div>
  );
}
