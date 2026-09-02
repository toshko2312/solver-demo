import { useState } from 'react';

import { Button } from './ds/Button';
import { Select } from './ds/Select';
import { useBodyScrollLock } from './ds/useBodyScrollLock';
import { RankedRoomPicker } from './RankedRoomPicker';
import { SemesterDatesEditor } from './SemesterDatesEditor';
import { SubjectSemestersEditor } from './SubjectSemestersEditor';
import { SlotPicker } from './SlotPicker';
import { ROOM_TYPES, ROOM_TYPE_LABEL, UNRANKED_WEIGHT } from '../theme';
import type {
  Group,
  Problem,
  Role,
  Room,
  RoomType,
  Subject,
  SubjectSemester,
  Teacher,
} from '../types';

export type EntityKind = 'roles' | 'teachers' | 'rooms' | 'groups' | 'subjects';
export type Draft = Role | Teacher | Room | Group | Subject;

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
  teachers: 'teacher',
  rooms: 'room',
  groups: 'group',
  subjects: 'subject',
};

/** One modal for all four entity kinds -- the fields differ, the chrome does not. */
export function EntityFormModal({ kind, draft, isNew, problem, onSave, onClose }: Props) {
  const [value, setValue] = useState<any>({ ...draft });
  const [error, setError] = useState<string | null>(null);
  useBodyScrollLock(true);

  const patch = (fields: Record<string, unknown>) => setValue((v: any) => ({ ...v, ...fields }));

  // The weight this teacher would get from their rank alone -- what the override
  // field falls back to when left blank.
  const roleWeight =
    problem.roles.find((r) => r.id === value.role)?.weight ?? UNRANKED_WEIGHT;

  const toggleInArray = (field: string, item: string) => {
    const current: string[] = value[field] ?? [];
    patch({
      [field]: current.includes(item) ? current.filter((x) => x !== item) : [...current, item],
    });
  };

  const save = () => {
    if (!String(value.name ?? '').trim()) {
      setError('Name is required.');
      return;
    }
    if (kind === 'roles' && !String(value.short ?? '').trim()) {
      setError('Short label is required.');
      return;
    }
    if (kind === 'subjects') {
      if (!value.allowedRoomTypes || value.allowedRoomTypes.length === 0) {
        setError('Pick at least one room type.');
        return;
      }
      if (!value.teacherIds || value.teacherIds.length === 0) {
        setError('Pick at least one teacher.');
        return;
      }
      if (!value.semesters || value.semesters.length === 0) {
        setError('Add at least one semester.');
        return;
      }
      if (value.semesters.some((x: SubjectSemester) => x.groupIds.length === 0)) {
        setError('Every semester needs at least one group.');
        return;
      }
    }
    onSave(value as Draft);
  };

  return (
    <div className="modal__backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <div className="display-sm">
            {isNew ? 'Add' : 'Edit'} {TITLES[kind]}
          </div>
          <button className="linkbtn linkbtn--quiet" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="modal__body">
          <label className="field">
            <span className="field__label">Name</span>
            <input value={value.name ?? ''} onChange={(e) => patch({ name: e.target.value })} />
          </label>

          {kind === 'teachers' && (
            <>
              <label className="field">
                <span className="field__label">Department</span>
                <input
                  value={value.department ?? ''}
                  onChange={(e) => patch({ department: e.target.value })}
                />
              </label>
              {/* A div, not a label: a label forwards its own click to the
                  button inside it, which would toggle the menu twice. */}
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
                  weight share a tier and trade freely with each other; setting this is the only way
                  to move one person into another rank's tier without inventing a rank for them.
                </span>
              </label>
              <div className="field">
                <span className="field__label">
                  Preferred slots <span className="field__soft">soft preference</span>
                </span>
                <SlotPicker
                  config={problem.slotConfig}
                  selected={value.preferredSlots ?? []}
                  size="lg"
                  onToggle={(slotId) => toggleInArray('preferredSlots', slotId)}
                />
                <span className="field__hint">
                  The solver optimises towards these but will trade them away to satisfy a hard rule.
                </span>
              </div>
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
                  last named choice. Ranking is scored per room type — ranking labs says nothing
                  about which sports hall you get.
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
                      onClick={() => patch({ type: t })}
                    >
                      {ROOM_TYPE_LABEL[t]}
                    </button>
                  ))}
                </div>
                <span className="field__hint">
                  Hard rule. A subject is only placed in a room of its required type.
                </span>
              </div>
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
                <span className="field__label">Students</span>
                <input
                  type="number"
                  min={0}
                  value={value.size ?? 0}
                  onChange={(e) => patch({ size: Number(e.target.value) })}
                />
                <span className="field__hint">
                  Hard rule. Room capacity must cover every group in the session.
                </span>
              </label>
              <div className="field">
                <span className="field__label">Term dates</span>
                <SemesterDatesEditor
                  value={value.semesters ?? []}
                  config={problem.slotConfig}
                  onChange={(semesters) => patch({ semesters })}
                />
                <span className="field__hint">
                  Up to two semesters an academic year. Breaks are excluded from teaching
                  entirely: nothing is scheduled on them, and they do not count towards the weeks
                  a subject's sessions are spread across.
                </span>
              </div>
              <label className="field">
                <span className="field__label">Programme</span>
                <input
                  value={value.programme ?? ''}
                  onChange={(e) => patch({ programme: e.target.value })}
                />
              </label>
            </>
          )}

          {kind === 'subjects' && (
            <>
              <div className="field">
                <span className="field__label">Semesters, groups and sessions</span>
                <SubjectSemestersEditor
                  subject={value as Subject}
                  value={value.semesters ?? []}
                  groups={problem.groups}
                  config={problem.slotConfig}
                  onChange={(semesters) => patch({ semesters })}
                />
                <span className="field__hint">
                  Groups are picked per semester: a subject can be taught to a different cohort
                  each term, and a group with no term dates for that semester cannot attend it at
                  all. Taught to several groups it is one combined session, and every listed group
                  is busy for it. The session count is a total for the semester, not a weekly rate
                  — sessions land on real dates, so nothing has to divide evenly, and they are
                  spread as evenly as the week count allows.
                </span>
              </div>
              <div className="field">
                <span className="field__label">Allowed room types</span>
                <div className="chiprow">
                  {ROOM_TYPES.map((t: RoomType) => (
                    <button
                      key={t}
                      type="button"
                      className={`chip${
                        (value.allowedRoomTypes ?? []).includes(t) ? ' chip--active' : ''
                      }`}
                      onClick={() => toggleInArray('allowedRoomTypes', t)}
                    >
                      {ROOM_TYPE_LABEL[t]}
                    </button>
                  ))}
                </div>
                <span className="field__hint">
                  Hard rule. The session goes in a room of one of these types — pick several to give
                  the solver room to manoeuvre.
                </span>
              </div>
              <div className="field">
                <span className="field__label">Teachers</span>
                <div className="chiprow">
                  {problem.teachers.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className={`chip${
                        (value.teacherIds ?? []).includes(t.id) ? ' chip--active' : ''
                      }`}
                      onClick={() => toggleInArray('teacherIds', t.id)}
                    >
                      {t.name}
                    </button>
                  ))}
                </div>
                <span className="field__hint">
                  Candidates, not co-teachers: the solver gives each session to exactly one of them,
                  and may split a subject's sessions between them.
                </span>
              </div>
            </>
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
