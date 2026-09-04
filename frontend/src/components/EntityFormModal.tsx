import { useState } from 'react';

import { Button } from './ds/Button';
import { Select } from './ds/Select';
import { useBodyScrollLock } from './ds/useBodyScrollLock';
import { CourseDatesEditor } from './CourseDatesEditor';
import { OfferingEditor } from './OfferingEditor';
import { RankedRoomPicker } from './RankedRoomPicker';
import { SlotPicker } from './SlotPicker';
import { ROOM_TYPES, ROOM_TYPE_LABEL, SINGLE_GROUP_ROOM_TYPES, UNRANKED_WEIGHT } from '../theme';
import type {
  CourseInstance,
  Degree,
  Faculty,
  Group,
  Katedra,
  Problem,
  Role,
  Room,
  RoomType,
  Specialty,
  StudentKind,
  StudyForm,
  Subgroup,
  Subject,
  SubjectOffering,
  Teacher,
} from '../types';

export type EntityKind =
  | 'roles'
  | 'faculties'
  | 'katedri'
  | 'specialties'
  | 'courseInstances'
  | 'teachers'
  | 'rooms'
  | 'groups'
  | 'subgroups'
  | 'subjects'
  | 'offerings';

export type Draft =
  | Role
  | Faculty
  | Katedra
  | Specialty
  | CourseInstance
  | Teacher
  | Room
  | Group
  | Subgroup
  | Subject
  | SubjectOffering;

interface Props {
  kind: EntityKind;
  draft: Draft;
  isNew: boolean;
  problem: Problem;
  onSave: (entity: Draft) => void;
  onClose: () => void;
}

const TITLES: Record<EntityKind, string> = {
  roles: 'role',
  faculties: 'faculty',
  katedri: 'катедра',
  specialties: 'specialty',
  courseInstances: 'курс',
  teachers: 'teacher',
  rooms: 'room',
  groups: 'група',
  subgroups: 'подгрупа',
  subjects: 'subject',
  offerings: 'offering',
};

const DEGREES: Degree[] = ['бакалавър', 'магистър', 'доктор'];
const FORMS: StudyForm[] = ['редовна', 'задочна'];
const STUDENT_KINDS: StudentKind[] = ['курсант', 'студент'];

/** One modal for every entity kind -- the fields differ, the chrome does not. */
export function EntityFormModal({ kind, draft, isNew, problem, onSave, onClose }: Props) {
  const [value, setValue] = useState<any>({ ...draft });
  const [error, setError] = useState<string | null>(null);
  useBodyScrollLock(true);

  const patch = (fields: Record<string, unknown>) => setValue((v: any) => ({ ...v, ...fields }));

  // The weight this teacher would get from their rank alone -- what the override
  // field falls back to when left blank.
  const roleWeight = problem.roles.find((r) => r.id === value.role)?.weight ?? UNRANKED_WEIGHT;

  const toggleInArray = (field: string, item: string) => {
    const current: string[] = value[field] ?? [];
    patch({
      [field]: current.includes(item) ? current.filter((x) => x !== item) : [...current, item],
    });
  };

  const named = kind !== 'offerings';

  const save = () => {
    if (named && !String(value.name ?? '').trim()) {
      setError('Name is required.');
      return;
    }
    if (kind === 'roles' && !String(value.short ?? '').trim()) {
      setError('Short label is required.');
      return;
    }
    if (kind === 'specialties' && !String(value.code ?? '').trim()) {
      setError('Code is required.');
      return;
    }
    if (kind === 'subjects' && !String(value.code ?? '').trim()) {
      setError('Code is required — it is what the разписание prints.');
      return;
    }
    if ((kind === 'specialties' || kind === 'katedri') && !value.facultyId && problem.faculties.length) {
      setError('Pick a faculty.');
      return;
    }
    if (kind === 'courseInstances') {
      if (!value.specialtyId) {
        setError('Pick a specialty.');
        return;
      }
      if (!(value.start < value.end)) {
        setError('The term has to end after it starts.');
        return;
      }
    }
    if (kind === 'groups' && !value.courseInstanceId) {
      setError('Pick the курс this група belongs to.');
      return;
    }
    if (kind === 'subgroups' && !value.groupId) {
      setError('Pick the група this подгрупа splits.');
      return;
    }
    if (kind === 'offerings') {
      const o = value as SubjectOffering;
      if (!o.subjectId || !o.courseInstanceId) {
        setError('An offering needs a subject and a курс.');
        return;
      }
      if (!o.lectureHours && !o.exerciseHours) {
        setError('Give it лекционни or упражнителни часа — an offering with neither runs nothing.');
        return;
      }
      if (o.lectureHours && (!o.leadTeacherId || !o.streamGroupIds.length || !o.lectureRoomTypes.length)) {
        setError('Лекционни часа need a водещ преподавател, a поток and a room type.');
        return;
      }
      if (
        o.exerciseHours &&
        (!o.exerciseTeacherIds.length || !o.exerciseUnitIds.length || !o.exerciseRoomTypes.length)
      ) {
        setError('Упражнителни часа need teachers, групи or подгрупи, and a room type.');
        return;
      }
      if (o.spread !== 'whole' && !(o.window?.start && o.window?.end)) {
        setError(`Spread "${o.spread}" needs a window.`);
        return;
      }
    }
    onSave(value as Draft);
  };

  return (
    <div className="modal__backdrop" onClick={onClose}>
      <div className="modal modal--fixed" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <div className="display-sm">
            {isNew ? 'Add' : 'Edit'} {TITLES[kind]}
          </div>
          <button className="linkbtn linkbtn--quiet" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="modal__body modal__scroll">
          {named && (
            <label className="field">
              <span className="field__label">Name</span>
              <input value={value.name ?? ''} onChange={(e) => patch({ name: e.target.value })} />
            </label>
          )}

          {kind === 'katedri' && (
            <div className="field">
              <span className="field__label">Факултет</span>
              <Select
                aria-label="Faculty"
                value={value.facultyId ?? ''}
                options={[
                  { value: '', label: 'None' },
                  ...problem.faculties.map((f) => ({ value: f.id, label: f.name })),
                ]}
                onChange={(facultyId) => patch({ facultyId: facultyId === '' ? null : facultyId })}
              />
            </div>
          )}

          {kind === 'specialties' && (
            <>
              <label className="field">
                <span className="field__label">Код</span>
                <input value={value.code ?? ''} onChange={(e) => patch({ code: e.target.value })} />
              </label>
              <div className="field">
                <span className="field__label">Факултет</span>
                <Select
                  aria-label="Faculty"
                  value={value.facultyId ?? ''}
                  options={problem.faculties.map((f) => ({ value: f.id, label: f.name }))}
                  onChange={(facultyId) => patch({ facultyId })}
                />
              </div>
              <div className="field">
                <span className="field__label">ОКС</span>
                <div className="chiprow">
                  {DEGREES.map((d) => (
                    <button
                      key={d}
                      type="button"
                      className={`chip${value.degree === d ? ' chip--active' : ''}`}
                      onClick={() => patch({ degree: d })}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
              <div className="field">
                <span className="field__label">Форма на обучение</span>
                <div className="chiprow">
                  {FORMS.map((f) => (
                    <button
                      key={f}
                      type="button"
                      className={`chip${value.form === f ? ' chip--active' : ''}`}
                      onClick={() => patch({ form: f })}
                    >
                      {f}
                    </button>
                  ))}
                </div>
                <span className="field__hint">
                  Задочната форма compresses a whole semester into a присъствен период of two or
                  three weeks. Its offerings want spread "block", which saturates a window instead
                  of balancing weeks.
                </span>
              </div>
              <div className="field">
                <span className="field__label">Обучаеми</span>
                <div className="chiprow">
                  {STUDENT_KINDS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      className={`chip${value.studentKind === k ? ' chip--active' : ''}`}
                      onClick={() => patch({ studentKind: k })}
                    >
                      {k}и
                    </button>
                  ))}
                </div>
              </div>
              <label className="field">
                <span className="field__label">Години на обучение</span>
                <input
                  type="number"
                  min={1}
                  max={6}
                  value={value.durationYears ?? 4}
                  onChange={(e) => patch({ durationYears: Number(e.target.value) })}
                />
              </label>
            </>
          )}

          {kind === 'courseInstances' && (
            <>
              <div className="field">
                <span className="field__label">Специалност</span>
                <Select
                  aria-label="Specialty"
                  value={value.specialtyId ?? ''}
                  options={problem.specialties.map((s) => ({
                    value: s.id,
                    label: `${s.code} — ${s.name}`,
                  }))}
                  onChange={(specialtyId) => patch({ specialtyId })}
                />
              </div>
              <div className="offering__grid">
                <label className="field">
                  <span className="field__label">Курс</span>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={value.year ?? 1}
                    onChange={(e) => patch({ year: Number(e.target.value) })}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Учебна година</span>
                  <input
                    value={value.academicYear ?? ''}
                    placeholder="2025/2026"
                    onChange={(e) => patch({ academicYear: e.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Семестър</span>
                  <input
                    type="number"
                    min={1}
                    max={2}
                    value={value.semester ?? 1}
                    onChange={(e) => patch({ semester: Number(e.target.value) })}
                  />
                </label>
              </div>
              <div className="field">
                <span className="field__label">Учебно време</span>
                <CourseDatesEditor
                  value={value as CourseInstance}
                  config={problem.slotConfig}
                  onChange={(course) => setValue({ ...course })}
                />
                <span className="field__hint">
                  Dates live here, not on the група: a курс on стаж in November runs a different
                  calendar from its neighbours. Every non-teaching period is equally unusable for
                  teaching — the kinds are kept apart so the разписание can print them, and so
                  section II can count each изпитна сесия separately.
                </span>
              </div>
              <label className="field">
                <span className="field__label">Max periods a day</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={value.maxPeriodsPerDay ?? 6}
                  onChange={(e) => patch({ maxPeriodsPerDay: Number(e.target.value) })}
                />
                <span className="field__hint">
                  Hard rule, per група of this курс. Two подгрупи taught side by side cost the
                  група one period of its day, not two.
                </span>
              </label>
              <div className="eyebrow offering__head">Разписание header</div>
              <label className="field">
                <span className="field__label">Рег. №</span>
                <input
                  value={value.regNumber ?? ''}
                  onChange={(e) => patch({ regNumber: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="field__label">Утвърдил</span>
                <textarea
                  rows={2}
                  value={value.approvedBy ?? ''}
                  onChange={(e) => patch({ approvedBy: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="field__label">Дата на утвърждаване</span>
                <input
                  type="date"
                  value={value.approvalDate ?? ''}
                  onChange={(e) => patch({ approvalDate: e.target.value || null })}
                />
              </label>
              <label className="field">
                <span className="field__label">Административен отговорник</span>
                <input
                  value={value.administrativenOtgovornik ?? ''}
                  onChange={(e) => patch({ administrativenOtgovornik: e.target.value })}
                />
              </label>
            </>
          )}

          {kind === 'teachers' && (
            <>
              <div className="field">
                <span className="field__label">Катедра</span>
                <Select
                  aria-label="Катедра"
                  value={value.katedraId ?? ''}
                  options={[
                    { value: '', label: 'None' },
                    ...problem.katedri.map((k) => ({ value: k.id, label: k.name })),
                  ]}
                  onChange={(katedraId) => patch({ katedraId: katedraId === '' ? null : katedraId })}
                />
              </div>
              <div className="field">
                <span className="field__label">Academic rank</span>
                <Select
                  aria-label="Academic rank"
                  value={value.role ?? ''}
                  options={[
                    { value: '', label: 'Unranked — bottom tier' },
                    ...[...problem.roles]
                      .sort((a, b) => b.weight - a.weight)
                      .map((r) => ({ value: r.id, label: `${r.name} (weight ${r.weight})` })),
                  ]}
                  onChange={(role) => patch({ role: role === '' ? null : role })}
                />
                <span className="field__hint">
                  Decides whose preference wins when two teachers want the same room at the same
                  time. The solver settles the ranks one at a time, highest first — a senior
                  preference is never traded away to satisfy a junior one. Edit the ranks
                  themselves under Data setup → Roles.
                </span>
              </div>
              <label className="field">
                <span className="field__label">
                  Priority weight <span className="field__soft">override</span>
                </span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  placeholder={String(roleWeight)}
                  value={value.priorityWeight ?? ''}
                  onChange={(e) =>
                    patch({
                      priorityWeight: e.target.value === '' ? null : Number(e.target.value),
                    })
                  }
                />
                <span className="field__hint">
                  Leave blank to use the rank's own weight ({roleWeight}). Teachers sharing a
                  weight share a tier and trade freely with each other; setting this is the only
                  way to move one person into another rank's tier without inventing a rank for
                  them.
                </span>
              </label>
              <div className="field">
                <span className="field__label">
                  Preferred periods <span className="field__soft">soft preference</span>
                </span>
                <SlotPicker
                  config={problem.slotConfig}
                  selected={value.preferredSlots ?? []}
                  size="lg"
                  onToggle={(id) => toggleInArray('preferredSlots', id)}
                />
                <span className="field__hint">
                  The solver optimises towards these but will trade them away to satisfy a hard
                  rule. A period is a block of two academic hours — the smallest thing that can be
                  scheduled.
                </span>
              </div>
              <div className="field">
                <span className="field__label">
                  Availability <span className="field__soft">HARD</span>
                </span>
                <SlotPicker
                  config={problem.slotConfig}
                  selected={value.hardAvailability ?? []}
                  size="lg"
                  intent="hard"
                  onToggle={(id) => toggleInArray('hardAvailability', id)}
                />
                <span className="field__hint">
                  Leave empty for "always available". This is not a preference and no rank can buy
                  around it: a хоноруван преподавател who cannot be in the building simply cannot,
                  and a window too narrow for their load makes the problem INFEASIBLE rather than
                  expensive.
                </span>
              </div>
              <label className="field">
                <span className="field__label">
                  Max periods a week <span className="field__soft">HARD</span>
                </span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  placeholder="uncapped"
                  value={value.maxWeeklyPeriods ?? ''}
                  onChange={(e) =>
                    patch({
                      maxWeeklyPeriods: e.target.value === '' ? null : Number(e.target.value),
                    })
                  }
                />
              </label>
              <div className="field">
                <span className="field__label">
                  Preferred rooms <span className="field__soft">soft, ranked</span>
                </span>
                <RankedRoomPicker
                  rooms={problem.rooms}
                  selected={value.preferredRooms ?? []}
                  onChange={(next) => patch({ preferredRooms: next })}
                />
                <span className="field__hint">
                  Order matters: first choice is free, each place further down costs a little more,
                  and a room of a type you ranked but did not list costs one step worse than your
                  last named choice. Ranking is scored per room type — ranking полигони says
                  nothing about which стрелбище you get.
                </span>
              </div>
            </>
          )}

          {kind === 'roles' && (
            <>
              <label className="field">
                <span className="field__label">Short label</span>
                <input
                  value={value.short ?? ''}
                  onChange={(e) => patch({ short: e.target.value })}
                />
                <span className="field__hint">
                  Used where space is tight — the teachers table and the priority ladder.
                </span>
              </label>
              <label className="field">
                <span className="field__label">Weight</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={value.weight ?? 1}
                  onChange={(e) => patch({ weight: Number(e.target.value) })}
                />
                <span className="field__hint">
                  Higher wins. This is a tier key, not a multiplier: only the ordering matters and
                  which ranks share a value. Two ranks on the same weight share a tier and trade
                  freely with each other; a rank on its own weight is settled before every rank
                  below it.
                </span>
              </label>
            </>
          )}

          {kind === 'rooms' && (
            <>
              <label className="field">
                <span className="field__label">Capacity</span>
                <input
                  type="number"
                  min={0}
                  value={value.capacity ?? 0}
                  onChange={(e) => patch({ capacity: Number(e.target.value) })}
                />
              </label>
              <div className="field">
                <span className="field__label">Room type</span>
                <div className="chiprow">
                  {ROOM_TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      className={`chip${value.type === t ? ' chip--active' : ''}`}
                      onClick={() =>
                        patch({
                          type: t,
                          maxConcurrentGroups: SINGLE_GROUP_ROOM_TYPES.includes(t)
                            ? 1
                            : (value.maxConcurrentGroups ?? 1),
                        })
                      }
                    >
                      {ROOM_TYPE_LABEL[t]}
                    </button>
                  ))}
                </div>
                <span className="field__hint">
                  Hard rule. A session is only placed in a room of a type its offering accepts.
                </span>
              </div>
              <label className="field">
                <span className="field__label">Groups at once</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={value.maxConcurrentGroups ?? 1}
                  onChange={(e) =>
                    patch({ maxConcurrentGroups: Math.max(1, Number(e.target.value)) })
                  }
                />
                <span className="field__hint">
                  {SINGLE_GROUP_ROOM_TYPES.includes(value.type as RoomType)
                    ? 'Едно стрелбище приема една подгрупа наведнъж — leave this at 1 unless the room really does run two sessions side by side.'
                    : 'One for almost everything. Above 1 the room can host that many sessions in the same period.'}
                </span>
              </label>
              <label className="field">
                <span className="field__label">Building</span>
                <input
                  value={value.building ?? ''}
                  onChange={(e) => patch({ building: e.target.value })}
                />
              </label>
            </>
          )}

          {kind === 'groups' && (
            <>
              <label className="field">
                <span className="field__label">Обучаеми</span>
                <input
                  type="number"
                  min={0}
                  value={value.size ?? 0}
                  onChange={(e) => patch({ size: Number(e.target.value) })}
                />
                <span className="field__hint">
                  Hard rule. Room capacity must cover every група in the session.
                </span>
              </label>
              <div className="field">
                <span className="field__label">Курс</span>
                <Select
                  aria-label="Course"
                  value={value.courseInstanceId ?? ''}
                  options={problem.courseInstances.map((c) => {
                    const code =
                      problem.specialties.find((s) => s.id === c.specialtyId)?.code ?? c.specialtyId;
                    return {
                      value: c.id,
                      label: `${c.year} курс ${code} · ${c.academicYear} S${c.semester}`,
                    };
                  })}
                  onChange={(courseInstanceId) => patch({ courseInstanceId })}
                />
                <span className="field__hint">
                  The курс owns the term dates, the non-teaching periods and the daily cap.
                </span>
              </div>
            </>
          )}

          {kind === 'subgroups' && (
            <>
              <label className="field">
                <span className="field__label">Обучаеми</span>
                <input
                  type="number"
                  min={0}
                  value={value.size ?? 0}
                  onChange={(e) => patch({ size: Number(e.target.value) })}
                />
                <span className="field__hint">
                  Езиковите подгрупи split by level, so the halves are uneven on purpose. This size
                  is what the room has to hold, not the група's.
                </span>
              </label>
              <div className="field">
                <span className="field__label">Група</span>
                <Select
                  aria-label="Group"
                  value={value.groupId ?? ''}
                  options={problem.groups.map((g) => ({ value: g.id, label: g.name }))}
                  onChange={(groupId) => patch({ groupId })}
                />
                <span className="field__hint">
                  Two подгрупи of one група may be taught at the same time; anything taught to the
                  whole група excludes every one of them.
                </span>
              </div>
            </>
          )}

          {kind === 'subjects' && (
            <>
              <label className="field">
                <span className="field__label">Код</span>
                <input
                  value={value.code ?? ''}
                  placeholder="ОИД"
                  onChange={(e) => patch({ code: e.target.value })}
                />
                <span className="field__hint">
                  What section I of the разписание prints beside the name.
                </span>
              </label>
              <div className="field">
                <span className="field__label">Катедра</span>
                <Select
                  aria-label="Катедра"
                  value={value.katedraId ?? ''}
                  options={[
                    { value: '', label: 'None' },
                    ...problem.katedri.map((k) => ({ value: k.id, label: k.name })),
                  ]}
                  onChange={(katedraId) => patch({ katedraId: katedraId === '' ? null : katedraId })}
                />
                <span className="field__hint">
                  A subject is a catalogue entry. What is <em>taught</em> — the хорариум, the
                  поток, the teachers and the rooms — is an offering.
                </span>
              </div>
            </>
          )}

          {kind === 'offerings' && (
            <OfferingEditor
              value={value as SubjectOffering}
              problem={problem}
              onChange={(offering) => setValue({ ...offering })}
            />
          )}

          {error && <div className="error">{error}</div>}
        </div>

        <div className="modal__foot">
          <Button variant="primary" onClick={save}>
            Save {TITLES[kind]}
          </Button>
          <Button variant="secondary-pill" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
