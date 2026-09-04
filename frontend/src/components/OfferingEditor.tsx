import { Select } from './ds/Select';
import { offeringDates, sessionsOf } from '../slots';
import { ROOM_TYPES, ROOM_TYPE_LABEL } from '../theme';
import type {
  Audience,
  ControlForm,
  Problem,
  RoomType,
  SpreadMode,
  SubjectOffering,
} from '../types';

interface Props {
  value: SubjectOffering;
  problem: Problem;
  onChange: (offering: SubjectOffering) => void;
}

const CONTROL_FORMS: ControlForm[] = ['изпит', 'КТО', 'зачет'];
const SPREADS: { value: SpreadMode; label: string }[] = [
  { value: 'whole', label: 'whole — evenly across the term' },
  { value: 'range', label: 'range — evenly inside a window' },
  { value: 'block', label: 'block — saturate a присъствен период' },
];

function ChipRow({
  items,
  selected,
  onToggle,
  empty,
}: {
  items: { id: string; label: string }[];
  selected: string[];
  onToggle: (id: string) => void;
  empty: string;
}) {
  if (items.length === 0) return <div className="muted-sm">{empty}</div>;
  return (
    <div className="chiprow">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`chip${selected.includes(item.id) ? ' chip--active' : ''}`}
          onClick={() => onToggle(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

/** The хорариум and everything hanging off it.
 *
 *  A учебен план gives hours, not sessions -- "30/15" is 30 лекционни and 15
 *  упражнителни часа -- and the two halves are almost different subjects: the
 *  лекция goes to the whole поток with one водещ преподавател, the упражнения run
 *  per група or подгрупа with a pool. So the form is in two halves too.
 */
export function OfferingEditor({ value, problem, onChange }: Props) {
  const patch = (fields: Partial<SubjectOffering>) => onChange({ ...value, ...fields });
  const toggle = (field: 'lectureRoomTypes' | 'exerciseRoomTypes', t: RoomType) =>
    patch({
      [field]: value[field].includes(t)
        ? value[field].filter((x) => x !== t)
        : [...value[field], t],
    } as Partial<SubjectOffering>);
  const toggleId = (field: 'streamGroupIds' | 'exerciseTeacherIds' | 'exerciseUnitIds', id: string) =>
    patch({
      [field]: value[field].includes(id)
        ? value[field].filter((x) => x !== id)
        : [...value[field], id],
    } as Partial<SubjectOffering>);

  const course = problem.courseInstances.find((c) => c.id === value.courseInstanceId);
  const ourGroups = problem.groups.filter((g) => g.courseInstanceId === value.courseInstanceId);
  const ourSubgroups = problem.subgroups.filter((s) =>
    ourGroups.some((g) => g.id === s.groupId),
  );
  const units =
    value.exerciseAudience === 'subgroup'
      ? ourSubgroups.map((s) => ({ id: s.id, label: `${s.name} (${s.size})` }))
      : ourGroups.map((g) => ({ id: g.id, label: `${g.name} (${g.size})` }));

  const lectures = sessionsOf(value, 'лекция');
  const exercises = sessionsOf(value, 'упражнение');
  const ref = course
    ? { academicYear: course.academicYear, index: course.semester }
    : null;
  const dates = ref
    ? offeringDates(
        value,
        problem.groups,
        problem.subgroups,
        problem.courseInstances,
        problem.slotConfig,
        ref,
      )
    : [];

  return (
    <div className="offering">
      <div className="field">
        <span className="field__label">Subject</span>
        <Select
          aria-label="Subject"
          value={value.subjectId}
          options={problem.subjects.map((s) => ({ value: s.id, label: `${s.code} — ${s.name}` }))}
          onChange={(subjectId) => patch({ subjectId })}
        />
      </div>

      <div className="field">
        <span className="field__label">Курс</span>
        <Select
          aria-label="Course"
          value={value.courseInstanceId}
          options={problem.courseInstances.map((c) => {
            const spec = problem.specialties.find((s) => s.id === c.specialtyId);
            return {
              value: c.id,
              label: `${c.year} курс ${spec?.code ?? c.specialtyId} · ${c.academicYear} S${c.semester}`,
            };
          })}
          onChange={(courseInstanceId) =>
            patch({ courseInstanceId, streamGroupIds: [], exerciseUnitIds: [] })
          }
        />
      </div>

      <div className="offering__grid">
        <label className="field">
          <span className="field__label">
            Лекционни часа <span className="field__soft">хорариум</span>
          </span>
          <input
            type="number"
            min={0}
            max={600}
            value={value.lectureHours}
            onChange={(e) => patch({ lectureHours: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span className="field__label">
            Упражнителни часа <span className="field__soft">хорариум</span>
          </span>
          <input
            type="number"
            min={0}
            max={600}
            value={value.exerciseHours}
            onChange={(e) => patch({ exerciseHours: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span className="field__label">Hours per session</span>
          <input
            type="number"
            min={1}
            max={12}
            value={value.hoursPerSession}
            onChange={(e) => patch({ hoursPerSession: Math.max(1, Number(e.target.value)) })}
          />
        </label>
      </div>
      <span className="field__hint">
        {value.lectureHours}/{value.exerciseHours} = {lectures} лекции for the поток and{' '}
        {exercises} упражнения <em>per unit</em> — the хорариум is what one student is owed, not
        what the катедра delivers once. Odd hours round up: a leftover hour is a smaller lie than
        a missing one.
      </span>

      <div className="field">
        <span className="field__label">Форма на контрол</span>
        <div className="chiprow">
          {CONTROL_FORMS.map((f) => (
            <button
              key={f}
              type="button"
              className={`chip${value.controlForm === f ? ' chip--active' : ''}`}
              onClick={() => patch({ controlForm: f })}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {value.lectureHours > 0 && (
        <>
          <div className="eyebrow offering__head">Лекции</div>
          <div className="field">
            <span className="field__label">Поток</span>
            <ChipRow
              items={problem.groups.map((g) => ({ id: g.id, label: g.name }))}
              selected={value.streamGroupIds}
              onToggle={(id) => toggleId('streamGroupIds', id)}
              empty="No groups defined yet."
            />
            <span className="field__hint">
              The групи merged for this offering's лекции. Общообразователните дисциплини merge
              across специалности; специалните do not. Every listed група is busy for the whole
              session, and the room has to hold all of them.
            </span>
          </div>
          <div className="field">
            <span className="field__label">Водещ преподавател</span>
            <Select
              aria-label="Lead teacher"
              value={value.leadTeacherId ?? ''}
              options={[
                { value: '', label: 'None — лекциите will not be scheduled' },
                ...problem.teachers.map((t) => ({ value: t.id, label: t.name })),
              ]}
              onChange={(id) => patch({ leadTeacherId: id === '' ? null : id })}
            />
            <span className="field__hint">
              One named lecturer, not a pool: a лекция is delivered by the person the катедра put
              on it.
            </span>
          </div>
          <div className="field">
            <span className="field__label">Allowed room types — лекция</span>
            <div className="chiprow">
              {ROOM_TYPES.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`chip${value.lectureRoomTypes.includes(t) ? ' chip--active' : ''}`}
                  onClick={() => toggle('lectureRoomTypes', t)}
                >
                  {ROOM_TYPE_LABEL[t]}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {value.exerciseHours > 0 && (
        <>
          <div className="eyebrow offering__head">Упражнения</div>
          <div className="field">
            <span className="field__label">Attended by</span>
            <div className="chiprow">
              {(['group', 'subgroup'] as Audience[]).map((a) => (
                <button
                  key={a}
                  type="button"
                  className={`chip${value.exerciseAudience === a ? ' chip--active' : ''}`}
                  onClick={() => patch({ exerciseAudience: a, exerciseUnitIds: [] })}
                >
                  {a === 'group' ? 'цели групи' : 'подгрупи'}
                </button>
              ))}
            </div>
            <span className="field__hint">
              Стрелковата подготовка, ЛЗФП and чуждоезиковото обучение split a група. Two подгрупи
              of one група may be taught at the same time; a група-level session excludes both.
            </span>
          </div>
          <div className="field">
            <span className="field__label">
              {value.exerciseAudience === 'subgroup' ? 'Подгрупи' : 'Групи'}
            </span>
            <ChipRow
              items={units}
              selected={value.exerciseUnitIds}
              onToggle={(id) => toggleId('exerciseUnitIds', id)}
              empty={
                value.exerciseAudience === 'subgroup'
                  ? 'This курс has no подгрупи yet.'
                  : 'This курс has no групи yet.'
              }
            />
          </div>
          <div className="field">
            <span className="field__label">Teachers</span>
            <ChipRow
              items={problem.teachers.map((t) => ({ id: t.id, label: t.name }))}
              selected={value.exerciseTeacherIds}
              onToggle={(id) => toggleId('exerciseTeacherIds', id)}
              empty="No teachers defined yet."
            />
            <span className="field__hint">
              Candidates, not co-teachers: the solver gives each session to exactly one of them,
              and may split a group's упражнения between them.
            </span>
          </div>
          <div className="field">
            <span className="field__label">Allowed room types — упражнение</span>
            <div className="chiprow">
              {ROOM_TYPES.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`chip${value.exerciseRoomTypes.includes(t) ? ' chip--active' : ''}`}
                  onClick={() => toggle('exerciseRoomTypes', t)}
                >
                  {ROOM_TYPE_LABEL[t]}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="eyebrow offering__head">Spread</div>
      <div className="field">
        <Select
          aria-label="Spread"
          value={value.spread}
          options={SPREADS.map((s) => ({ value: s.value, label: s.label }))}
          onChange={(spread) =>
            patch({
              spread: spread as SpreadMode,
              window:
                spread === 'whole'
                  ? undefined
                  : (value.window ?? { start: course?.start ?? '', end: course?.end ?? '' }),
            })
          }
        />
        <span className="field__hint">
          {value.spread === 'block'
            ? 'Задочна форма: the sessions saturate the window instead of balancing its weeks. No weekly floor, no ceiling — which is the whole point, because a semester compressed into three weeks has no even spread to find.'
            : 'Sessions are distributed across the teaching weeks of the window, each week carrying between floor(N/W) and ceil(N/W) of them.'}
        </span>
      </div>
      {value.spread !== 'whole' && (
        <div className="semdates__row">
          <label className="semdates__date">
            <span className="field__label">Window starts</span>
            <input
              type="date"
              value={value.window?.start ?? ''}
              onChange={(e) =>
                patch({ window: { start: e.target.value, end: value.window?.end ?? '' } })
              }
            />
          </label>
          <label className="semdates__date">
            <span className="field__label">Window ends</span>
            <input
              type="date"
              value={value.window?.end ?? ''}
              onChange={(e) =>
                patch({ window: { start: value.window?.start ?? '', end: e.target.value } })
              }
            />
          </label>
        </div>
      )}

      <label className="field">
        <span className="field__label">
          Изпитна дата <span className="field__soft">section III</span>
        </span>
        <input
          type="date"
          value={value.examDate ?? ''}
          onChange={(e) => patch({ examDate: e.target.value || null })}
        />
      </label>

      <div className="muted-sm">
        {dates.length} teachable date(s) available to this offering.
        {dates.length === 0 && ' Its групи are never all in term inside the window.'}
      </div>
    </div>
  );
}
