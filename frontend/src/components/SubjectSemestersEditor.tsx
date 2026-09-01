import { Select } from './ds/Select';
import { groupSemester, knownSemesters, subjectDates } from '../slots';
import { semesterKey } from '../types';
import type { Group, SlotConfig, Subject, SubjectSemester } from '../types';

interface Props {
  subject: Subject;
  value: SubjectSemester[];
  groups: Group[];
  config: SlotConfig;
  onChange: (next: SubjectSemester[]) => void;
}

/** How much of a subject runs in each semester, who attends it, and where
 *  inside the term it sits.
 *
 *  Groups are picked per semester rather than per subject: a subject can be
 *  taught to a different cohort in each term, and a group that is not in term
 *  cannot attend at all -- so the choice is only meaningful once the semester is
 *  known.
 *
 *  The total is for the whole semester rather than a weekly rate: sessions land
 *  on real dates, so nothing has to divide evenly. What the editor does show is
 *  the resulting per-week load, because that is the number that tells you
 *  whether a total is sane before you spend a solve finding out.
 */
export function SubjectSemestersEditor({ subject, value, groups, config, onChange }: Props) {
  const available = knownSemesters(groups);
  const patch = (i: number, fields: Partial<SubjectSemester>) =>
    onChange(value.map((s, j) => (j === i ? { ...s, ...fields } : s)));

  const toggleGroup = (i: number, gid: string) => {
    const current = value[i].groupIds;
    patch(i, {
      groupIds: current.includes(gid)
        ? current.filter((x) => x !== gid)
        : [...current, gid],
    });
  };

  const unused = available.filter(
    (a) => !value.some((v) => v.academicYear === a.academicYear && v.index === a.index),
  );

  return (
    <div className="semlist">
      {available.length === 0 && (
        <div className="muted-sm">
          No group has term dates yet, so there is no semester to schedule into.
        </div>
      )}

      {value.map((spec, i) => {
        // Measured against the same window the solver will use, so the numbers
        // here and the timetable cannot disagree.
        const dates = subjectDates({ ...subject, semesters: value }, groups, config, spec);
        const weeks = new Set(dates.map((d) => d.slice(0, 4) + d.slice(5, 7) + d.slice(8, 10)));
        const weekCount = new Set(
          dates.map((d) => {
            const t = new Date(`${d}T12:00:00Z`);
            t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7));
            return t.toISOString().slice(0, 10);
          }),
        ).size;
        const perWeek = weekCount ? (spec.totalSessions / weekCount).toFixed(1) : '—';

        return (
          <div key={semesterKey(spec)} className="semrow">
            <div className="semrow__head">
              <Select
                size="sm"
                aria-label="Semester"
                value={semesterKey(spec)}
                options={available.map((a) => ({
                  value: semesterKey(a),
                  label: `${a.academicYear} · Semester ${a.index}`,
                }))}
                onChange={(key) => {
                  const next = available.find((a) => semesterKey(a) === key);
                  if (!next) return;
                  // Moving the row to another term can strand groups that are not
                  // in term then; drop them rather than keep an unschedulable pick.
                  patch(i, {
                    academicYear: next.academicYear,
                    index: next.index,
                    groupIds: spec.groupIds.filter((gid) => {
                      const g = groups.find((x) => x.id === gid);
                      return g !== undefined && groupSemester(g, next) !== undefined;
                    }),
                  });
                }}
              />

              <label className="muted-sm">
                Total sessions{' '}
                <input
                  type="number"
                  min={0}
                  max={400}
                  style={{ width: 72 }}
                  value={spec.totalSessions}
                  onChange={(e) => patch(i, { totalSessions: Number(e.target.value) })}
                />
              </label>

              <Select
                size="sm"
                aria-label="Spread"
                value={spec.spread}
                options={[
                  { value: 'whole', label: 'Spread across the whole semester' },
                  { value: 'range', label: 'Spread across a period inside it' },
                ]}
                onChange={(spread) =>
                  patch(i, {
                    spread,
                    window:
                      spread === 'range'
                        ? (spec.window ?? {
                            start: dates[0] ?? '',
                            end: dates[dates.length - 1] ?? '',
                          })
                        : undefined,
                  })
                }
              />

              {spec.spread === 'range' && spec.window && (
                <>
                  <input
                    type="date"
                    value={spec.window.start}
                    onChange={(e) =>
                      patch(i, { window: { ...spec.window!, start: e.target.value } })
                    }
                  />
                  <span className="muted-sm">to</span>
                  <input
                    type="date"
                    value={spec.window.end}
                    onChange={(e) =>
                      patch(i, { window: { ...spec.window!, end: e.target.value } })
                    }
                  />
                </>
              )}

              <button
                className="linkbtn linkbtn--quiet"
                onClick={() => onChange(value.filter((_, j) => j !== i))}
              >
                Remove
              </button>
            </div>

            <div className="chiprow">
              {groups.map((g) => {
                // A group with no term dates for this semester cannot attend it:
                // the session would have no day on which everyone is present.
                const inTerm = groupSemester(g, spec) !== undefined;
                return (
                  <button
                    key={g.id}
                    type="button"
                    disabled={!inTerm}
                    title={
                      inTerm
                        ? undefined
                        : `${g.name} has no term dates for ${spec.academicYear} semester ${spec.index}.`
                    }
                    className={`chip${spec.groupIds.includes(g.id) ? ' chip--active' : ''}${
                      inTerm ? '' : ' chip--disabled'
                    }`}
                    onClick={() => toggleGroup(i, g.id)}
                  >
                    {g.name} ({g.size})
                  </button>
                );
              })}
            </div>

            <div className="muted-sm">
              {spec.groupIds.length === 0 ? (
                <>Pick at least one group for this semester.</>
              ) : weeks.size === 0 ? (
                <>
                  No usable dates — its groups are not in term together for this semester.
                </>
              ) : (
                <>
                  {weekCount} teaching week(s) available · about {perWeek} session(s) a week
                </>
              )}
            </div>
          </div>
        );
      })}

      {unused.length > 0 && (
        <button
          className="linkbtn"
          onClick={() => {
            // Carry the previous row's cohort forward -- the usual case is the
            // same groups continuing -- but only the ones actually in term then.
            const carried = (value[value.length - 1]?.groupIds ?? []).filter((gid) => {
              const g = groups.find((x) => x.id === gid);
              return g !== undefined && groupSemester(g, unused[0]) !== undefined;
            });
            onChange([
              ...value,
              { ...unused[0], totalSessions: 1, spread: 'whole', groupIds: carried },
            ]);
          }}
        >
          + Semester
        </button>
      )}
    </div>
  );
}
