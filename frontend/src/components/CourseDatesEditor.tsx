import { Select } from './ds/Select';
import { teachingDates } from '../slots';
import type { CourseInstance, ExamSessionKind, NonTeachingKind, SlotConfig } from '../types';

interface Props {
  value: CourseInstance;
  config: SlotConfig;
  onChange: (course: CourseInstance) => void;
}

const KINDS: NonTeachingKind[] = ['ваканция', 'стаж', 'изпитна сесия', 'празник'];
const SESSIONS: ExamSessionKind[] = ['редовна', 'поправителна', 'ликвидационна'];

/** Term dates and the typed non-teaching periods inside them.
 *
 *  Dates live on the курс rather than on the група because year 1 routinely runs
 *  a different calendar from years 2-4 of the same специалност -- and because a
 *  курс on стаж in November is the ordinary reason why.
 *
 *  `input[type=date]` is the one native control this app uses, for the reason
 *  DESIGN.md records: a date picker is a month grid, and the design project
 *  documents no such panel.
 */
export function CourseDatesEditor({ value, config, onChange }: Props) {
  const teaching = teachingDates(value, config);
  const weeks = new Set(teaching.map((d) => d.slice(0, 4) + d.slice(5, 7))).size;

  const patchPeriod = (index: number, fields: Partial<CourseInstance['nonTeaching'][0]>) => {
    onChange({
      ...value,
      nonTeaching: value.nonTeaching.map((p, i) => (i === index ? { ...p, ...fields } : p)),
    });
  };

  return (
    <div className="semdates">
      <div className="semdates__row">
        <label className="semdates__date">
          <span className="field__label">Term starts</span>
          <input
            type="date"
            value={value.start}
            onChange={(e) => onChange({ ...value, start: e.target.value })}
          />
        </label>
        <label className="semdates__date">
          <span className="field__label">Term ends</span>
          <input
            type="date"
            value={value.end}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
          />
        </label>
        <div className="semdates__meta muted-sm">
          {teaching.length} teaching day(s) across {weeks} month(s)
        </div>
      </div>

      <div className="semdates__breaks">
        <div className="eyebrow">Non-teaching periods</div>
        {value.nonTeaching.length === 0 && (
          <div className="muted-sm">None — the term teaches straight through.</div>
        )}
        {value.nonTeaching.map((p, i) => (
          <div className="semdates__break" key={i}>
            <div style={{ minWidth: 170 }}>
              <Select
                aria-label="Kind"
                value={p.kind}
                options={KINDS.map((k) => ({ value: k, label: k }))}
                onChange={(kind) =>
                  patchPeriod(i, {
                    kind: kind as NonTeachingKind,
                    session: kind === 'изпитна сесия' ? (p.session ?? 'редовна') : null,
                  })
                }
              />
            </div>
            {p.kind === 'изпитна сесия' && (
              <div style={{ minWidth: 150 }}>
                <Select
                  aria-label="Exam session"
                  value={p.session ?? 'редовна'}
                  options={SESSIONS.map((s) => ({ value: s, label: s }))}
                  onChange={(session) => patchPeriod(i, { session: session as ExamSessionKind })}
                />
              </div>
            )}
            <input
              type="date"
              value={p.start}
              onChange={(e) => patchPeriod(i, { start: e.target.value })}
            />
            <input
              type="date"
              value={p.end}
              onChange={(e) => patchPeriod(i, { end: e.target.value })}
            />
            <input
              placeholder="Label"
              value={p.label ?? ''}
              onChange={(e) => patchPeriod(i, { label: e.target.value })}
            />
            <button
              type="button"
              className="microbtn"
              onClick={() =>
                onChange({ ...value, nonTeaching: value.nonTeaching.filter((_, j) => j !== i) })
              }
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="microbtn"
          onClick={() =>
            onChange({
              ...value,
              nonTeaching: [
                ...value.nonTeaching,
                { start: value.start, end: value.start, kind: 'ваканция', session: null, label: '' },
              ],
            })
          }
        >
          Add period
        </button>
      </div>
    </div>
  );
}
