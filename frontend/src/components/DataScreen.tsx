import { useState } from 'react';

import { Button } from './ds/Button';
import { SearchInput } from './ds/SearchInput';
import { EntityFormModal, type Draft, type EntityKind } from './EntityFormModal';
import { GroupsTable } from './tables/GroupsTable';
import { RolesTable } from './tables/RolesTable';
import { RoomsTable } from './tables/RoomsTable';
import { SlotConfigPane } from './tables/SlotConfigPane';
import { SubjectsTable } from './tables/SubjectsTable';
import { TeachersTable } from './tables/TeachersTable';
import { nextId } from '../seed';
import { allSlots, openSlots } from '../slots';
import type { Group, Problem, Role, Room, Subject, Teacher } from '../types';

type Section = EntityKind | 'slots';

interface Props {
  problem: Problem;
  onChange: (problem: Problem) => void;
}

const COPY: Record<Section, [string, string, string]> = {
  roles: [
    'Roles',
    'Academic ranks, highest weight first. Rank decides whose preference wins a contested slot or room: the solver settles one tier at a time, top down, and never trades a senior preference away to satisfy a junior one. Ranks sharing a weight share a tier.',
    'Add role',
  ],
  teachers: [
    'Teachers',
    'Hard availability comes from blocked time slots; the grid below records soft preferences.',
    'Add teacher',
  ],
  rooms: ['Rooms', 'Room type is matched against each subject as a hard constraint.', 'Add room'],
  groups: [
    'Groups',
    'Group size is checked against room capacity before a session is placed.',
    'Add group',
  ],
  subjects: [
    'Subjects',
    'Each subject lists the room types it accepts and the teachers who could take it. The solver picks one of each, per session.',
    'Add subject',
  ],
  slots: [
    'Time slots',
    'The weekly grid definition. Block a cell to remove it from solving.',
    'Add period',
  ],
};

export function DataScreen({ problem, onChange }: Props) {
  const [section, setSection] = useState<Section>('teachers');
  const [filter, setFilter] = useState('');
  const [form, setForm] = useState<{ kind: EntityKind; draft: Draft; isNew: boolean } | null>(null);

  const counts: Record<Section, number> = {
    roles: problem.roles.length,
    teachers: problem.teachers.length,
    rooms: problem.rooms.length,
    groups: problem.groups.length,
    subjects: problem.subjects.length,
    slots: openSlots(problem.slotConfig).length,
  };
  const [title, blurb, addLabel] = COPY[section];
  const matches = (name: string) => name.toLowerCase().includes(filter.trim().toLowerCase());

  const blankDraft = (kind: EntityKind): Draft => {
    switch (kind) {
      case 'roles':
        return { id: nextId('role', problem.roles), name: '', short: '', weight: 1 };
      case 'teachers':
        return {
          id: nextId('t', problem.teachers),
          name: '',
          department: '',
          preferredSlots: [],
          preferredRooms: [],
          role: null,
          priorityWeight: null,
        };
      case 'rooms':
        return { id: nextId('r', problem.rooms), name: '', capacity: 30, type: 'lecture', building: '' };
      case 'groups':
        return {
          id: nextId('g', problem.groups),
          name: '',
          size: 25,
          programme: '',
          // A new group starts on the same calendar the others use, if there is
          // one -- retyping term dates per group is the cost of per-group dates,
          // and copying is the obvious mitigation.
          semesters: problem.groups[0]
            ? JSON.parse(JSON.stringify(problem.groups[0].semesters))
            : [],
        };
      case 'subjects':
        return {
          id: nextId('s', problem.subjects),
          name: '',
          allowedRoomTypes: ['lecture'],
          semesters: [],
          teacherIds: problem.teachers[0] ? [problem.teachers[0].id] : [],
        };
    }
  };

  const saveEntity = (entity: Draft) => {
    if (!form) return;
    const key = form.kind;
    const list = problem[key] as Draft[];
    const next = form.isNew
      ? [...list, entity]
      : list.map((e) => (e.id === entity.id ? entity : e));
    onChange({ ...problem, [key]: next });
    setForm(null);
  };

  const deleteTeacher = (id: string) => {
    // A teacher is one candidate among possibly several: drop them from every
    // pool, and only delete subjects left with nobody who could teach them.
    const orphaned = problem.subjects.filter(
      (s) => s.teacherIds.length === 1 && s.teacherIds[0] === id,
    );
    if (
      orphaned.length > 0 &&
      !window.confirm(
        `${orphaned.length} subject(s) have no other candidate teacher and will be deleted too. Continue?`,
      )
    ) {
      return;
    }
    onChange({
      ...problem,
      teachers: problem.teachers.filter((t) => t.id !== id),
      subjects: problem.subjects
        .filter((s) => !(s.teacherIds.length === 1 && s.teacherIds[0] === id))
        .map((s) => ({ ...s, teacherIds: s.teacherIds.filter((t) => t !== id) })),
    });
  };

  const deleteRole = (id: string) => {
    // Same shape as deleting a teacher or a group: name the knock-on effect, then
    // cascade. Teachers keep their place in the timetable and simply fall to the
    // bottom tier, which the ladder already handles -- so this never leaves the
    // problem in a state the solver would reject.
    const holders = problem.teachers.filter((t) => t.role === id);
    if (
      holders.length > 0 &&
      !window.confirm(
        `${holders.length} teacher(s) hold this rank and will become unranked, joining the bottom priority tier. Continue?`,
      )
    ) {
      return;
    }
    onChange({
      ...problem,
      roles: problem.roles.filter((r) => r.id !== id),
      teachers: problem.teachers.map((t) => (t.role === id ? { ...t, role: null } : t)),
    });
  };

  const deleteGroup = (id: string) => {
    // Groups live on the semester entries, so the cascade walks two levels: drop
    // the group from every semester, drop a semester left with nobody in it, and
    // only then is a subject with no semester left an orphan.
    const strip = (s: Subject): Subject => ({
      ...s,
      semesters: s.semesters
        .map((x) => ({ ...x, groupIds: x.groupIds.filter((g) => g !== id) }))
        .filter((x) => x.groupIds.length > 0),
    });
    const orphaned = problem.subjects.filter((s) => strip(s).semesters.length === 0);
    if (
      orphaned.length > 0 &&
      !window.confirm(
        `${orphaned.length} subject(s) are taught only to this group and will be deleted too. Continue?`,
      )
    ) {
      return;
    }
    onChange({
      ...problem,
      groups: problem.groups.filter((g) => g.id !== id),
      subjects: problem.subjects.map(strip).filter((s) => s.semesters.length > 0),
    });
  };

  const togglePreference = (teacherId: string, slotId: string) => {
    onChange({
      ...problem,
      teachers: problem.teachers.map((t) =>
        t.id === teacherId
          ? {
              ...t,
              preferredSlots: t.preferredSlots.includes(slotId)
                ? t.preferredSlots.filter((s) => s !== slotId)
                : [...t.preferredSlots, slotId],
            }
          : t,
      ),
    });
  };

  return (
    <div className="data">
      <nav className="sidebar">
        <div className="eyebrow sidebar__label">Input data</div>
        {(['roles', 'teachers', 'rooms', 'groups', 'subjects', 'slots'] as Section[]).map((key) => (
          <button
            key={key}
            className={`sidebar__item${section === key ? ' sidebar__item--active' : ''}`}
            onClick={() => {
              setSection(key);
              setFilter('');
            }}
          >
            <span>{COPY[key][0]}</span>
            <span className="sidebar__count">{counts[key]}</span>
          </button>
        ))}
      </nav>

      <section className="card">
        <div className="pane__head">
          <div style={{ flex: '1 1 260px', minWidth: 0 }}>
            <div className="display-md">{title}</div>
            <div className="muted" style={{ marginTop: 3 }}>
              {blurb}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {section !== 'slots' && <SearchInput value={filter} onChange={setFilter} />}
            {section !== 'slots' && (
              <Button
                variant="dark-utility"
                onClick={() => setForm({ kind: section, draft: blankDraft(section), isNew: true })}
              >
                {addLabel}
              </Button>
            )}
          </div>
        </div>

        {section === 'roles' && (
          <RolesTable
            roles={problem.roles.filter((r) => matches(r.name) || matches(r.short))}
            teachers={problem.teachers}
            onEdit={(r: Role) => setForm({ kind: 'roles', draft: r, isNew: false })}
            onDelete={deleteRole}
          />
        )}

        {section === 'teachers' && (
          <TeachersTable
            teachers={problem.teachers.filter((t) => matches(t.name))}
            roles={problem.roles}
            rooms={problem.rooms}
            slotConfig={problem.slotConfig}
            totalSlots={allSlots(problem.slotConfig).length}
            onTogglePreference={togglePreference}
            onEdit={(t: Teacher) => setForm({ kind: 'teachers', draft: t, isNew: false })}
            onDelete={deleteTeacher}
          />
        )}

        {section === 'rooms' && (
          <RoomsTable
            rooms={problem.rooms.filter((r) => matches(r.name))}
            onEdit={(r: Room) => setForm({ kind: 'rooms', draft: r, isNew: false })}
            onDelete={(id) => onChange({ ...problem, rooms: problem.rooms.filter((r) => r.id !== id) })}
          />
        )}

        {section === 'groups' && (
          <GroupsTable
            groups={problem.groups.filter((g) => matches(g.name))}
            subjects={problem.subjects}
            onEdit={(g: Group) => setForm({ kind: 'groups', draft: g, isNew: false })}
            onDelete={deleteGroup}
          />
        )}

        {section === 'subjects' && (
          <SubjectsTable
            subjects={problem.subjects.filter((s) => matches(s.name))}
            teachers={problem.teachers}
            groups={problem.groups}
            subjectIds={problem.subjects.map((s) => s.id)}
            onEdit={(s: Subject) => setForm({ kind: 'subjects', draft: s, isNew: false })}
            onDelete={(id) =>
              onChange({ ...problem, subjects: problem.subjects.filter((s) => s.id !== id) })
            }
          />
        )}

        {section === 'slots' && (
          <SlotConfigPane
            config={problem.slotConfig}
            onChange={(slotConfig) => onChange({ ...problem, slotConfig })}
          />
        )}
      </section>

      {form && (
        <EntityFormModal
          kind={form.kind}
          draft={form.draft}
          isNew={form.isNew}
          problem={problem}
          onSave={saveEntity}
          onClose={() => setForm(null)}
        />
      )}
    </div>
  );
}
