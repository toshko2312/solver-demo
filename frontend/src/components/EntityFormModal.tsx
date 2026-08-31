import { useState } from 'react';

import { Button } from './ds/Button';
import { SlotPicker } from './SlotPicker';
import { ROOM_TYPES, ROOM_TYPE_LABEL } from '../theme';
import type { Group, Problem, Room, RoomType, Subject, Teacher } from '../types';

export type EntityKind = 'teachers' | 'rooms' | 'groups' | 'subjects';
export type Draft = Teacher | Room | Group | Subject;

interface Props {
  kind: EntityKind;
  draft: Draft;
  isNew: boolean;
  problem: Problem;
  onSave: (entity: Draft) => void;
  onClose: () => void;
}

const TITLES: Record<EntityKind, string> = {
  teachers: 'teacher',
  rooms: 'room',
  groups: 'group',
  subjects: 'subject',
};

/** One modal for all four entity kinds -- the fields differ, the chrome does not. */
export function EntityFormModal({ kind, draft, isNew, problem, onSave, onClose }: Props) {
  const [value, setValue] = useState<any>({ ...draft });
  const [error, setError] = useState<string | null>(null);

  const patch = (fields: Record<string, unknown>) => setValue((v: any) => ({ ...v, ...fields }));

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
    if (kind === 'subjects') {
      if (!value.allowedRoomTypes || value.allowedRoomTypes.length === 0) {
        setError('Pick at least one room type.');
        return;
      }
      if (!value.teacherIds || value.teacherIds.length === 0) {
        setError('Pick at least one teacher.');
        return;
      }
      if (!value.groupIds || value.groupIds.length === 0) {
        setError('Pick at least one group.');
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
              <label className="field">
                <span className="field__label">Sessions per week</span>
                <input
                  type="number"
                  min={0}
                  value={value.sessionsPerWeek ?? 1}
                  onChange={(e) => patch({ sessionsPerWeek: Number(e.target.value) })}
                />
              </label>
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
              <div className="field">
                <span className="field__label">Groups</span>
                <div className="chiprow">
                  {problem.groups.map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      className={`chip${(value.groupIds ?? []).includes(g.id) ? ' chip--active' : ''}`}
                      onClick={() => toggleInArray('groupIds', g.id)}
                    >
                      {g.name} ({g.size})
                    </button>
                  ))}
                </div>
                <span className="field__hint">
                  A subject taught to several groups is scheduled as one combined session, and every
                  listed group is busy for it.
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
