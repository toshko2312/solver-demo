import { useState } from 'react';

import { Button } from './ds/Button';
import { SearchInput } from './ds/SearchInput';
import { EntityFormModal, type Draft, type EntityKind } from './EntityFormModal';
import {
  CoursesTable,
  FacultiesTable,
  KatedriTable,
  SpecialtiesTable,
  SubgroupsTable,
} from './tables/HierarchyTables';
import { GroupsTable } from './tables/GroupsTable';
import { OfferingsTable } from './tables/OfferingsTable';
import { RolesTable } from './tables/RolesTable';
import { RoomsTable } from './tables/RoomsTable';
import { SlotConfigPane } from './tables/SlotConfigPane';
import { SubjectsTable } from './tables/SubjectsTable';
import { TeachersTable } from './tables/TeachersTable';
import { nextId } from '../seed';
import { allSlots, openSlots } from '../slots';
import type {
  CourseInstance,
  Faculty,
  Group,
  Katedra,
  Problem,
  Role,
  Room,
  SlotConfig,
  Specialty,
  Subgroup,
  Subject,
  SubjectOffering,
  Teacher,
} from '../types';

type Section = EntityKind | 'slots';

interface Props {
  problem: Problem;
  onChange: (problem: Problem) => void;
}

const COPY: Record<Section, [string, string, string]> = {
  roles: [
    'Roles',
    'Academic ranks, highest weight first. Rank decides whose preference wins a contested period or room: the solver settles one tier at a time, top down, and never trades a senior preference away to satisfy a junior one. Ranks sharing a weight share a tier.',
    'Add role',
  ],
  faculties: ['Факултети', 'The top of the hierarchy. A разписание carries its faculty in the header.', 'Add faculty'],
  katedri: ['Катедри', 'Departments own subjects and teachers, and the разписание names the катедра beside each discipline.', 'Add катедра'],
  specialties: [
    'Специалности',
    'Code, ОКС, form of study and how many years it runs. Задочната форма is what spread "block" exists for.',
    'Add specialty',
  ],
  courseInstances: [
    'Курсове',
    'One курс of one специалност in one semester — the scheduling unit, and the unit a printed разписание is emitted for. Term dates and non-teaching periods live here, not on the група.',
    'Add курс',
  ],
  teachers: [
    'Teachers',
    'Preferred periods are soft and the solver will trade them away. Availability is HARD: a хоноруван преподавател who cannot attend simply cannot, and no rank buys around it.',
    'Add teacher',
  ],
  rooms: ['Rooms', 'Room type is matched against each offering as a hard constraint, per activity kind.', 'Add room'],
  groups: [
    'Групи',
    'Group size is checked against room capacity before a session is placed. Every група belongs to one курс, which owns its calendar.',
    'Add група',
  ],
  subgroups: [
    'Подгрупи',
    'A група splits for стрелкова подготовка, ЛЗФП and чуждоезиково обучение. Two подгрупи of one група may be taught at the same time; anything taught to the whole група excludes both.',
    'Add подгрупа',
  ],
  subjects: [
    'Дисциплини',
    'The catalogue: a code, a name and an owning катедра. What is actually taught is an offering.',
    'Add subject',
  ],
  offerings: [
    'Учебен план',
    'One subject as taught to one курс: the хорариум "30/15", who leads the лекции, which групи or подгрупи sit the упражнения, and where in the term it runs.',
    'Add offering',
  ],
  slots: [
    'Time slots',
    'The teaching day. Which weekdays are taught, and when each period runs. The обедна почивка is not a setting: it is the gap the period times leave, and nothing can be scheduled across it because no period covers it.',
    'Add period',
  ],
};

const ORDER: Section[] = [
  'faculties',
  'katedri',
  'specialties',
  'courseInstances',
  'groups',
  'subgroups',
  'roles',
  'teachers',
  'rooms',
  'subjects',
  'offerings',
  'slots',
];

export function DataScreen({ problem, onChange }: Props) {
  const [section, setSection] = useState<Section>('offerings');
  const [filter, setFilter] = useState('');
  const [form, setForm] = useState<{ kind: EntityKind; draft: Draft; isNew: boolean } | null>(null);

  const counts: Record<Section, number> = {
    roles: problem.roles.length,
    faculties: problem.faculties.length,
    katedri: problem.katedri.length,
    specialties: problem.specialties.length,
    courseInstances: problem.courseInstances.length,
    teachers: problem.teachers.length,
    rooms: problem.rooms.length,
    groups: problem.groups.length,
    subgroups: problem.subgroups.length,
    subjects: problem.subjects.length,
    offerings: problem.offerings.length,
    slots: openSlots(problem.slotConfig).length,
  };
  const [title, blurb, addLabel] = COPY[section];
  const matches = (name: string) => name.toLowerCase().includes(filter.trim().toLowerCase());

  const firstCourse = problem.courseInstances[0];

  const blankDraft = (kind: EntityKind): Draft => {
    switch (kind) {
      case 'roles':
        return { id: nextId('role', problem.roles), name: '', short: '', weight: 1 };
      case 'faculties':
        return { id: nextId('f', problem.faculties), name: '' };
      case 'katedri':
        return {
          id: nextId('k', problem.katedri),
          name: '',
          facultyId: problem.faculties[0]?.id ?? null,
        };
      case 'specialties':
        return {
          id: nextId('sp', problem.specialties),
          facultyId: problem.faculties[0]?.id ?? '',
          code: '',
          name: '',
          degree: 'бакалавър',
          form: 'редовна',
          studentKind: 'курсант',
          durationYears: 4,
        };
      case 'courseInstances':
        // A new курс starts on the same calendar the others use, if there is one
        // -- retyping term dates per курс is the cost of per-курс dates, and
        // copying is the obvious mitigation.
        return {
          id: nextId('c', problem.courseInstances),
          specialtyId: problem.specialties[0]?.id ?? '',
          year: 1,
          academicYear: firstCourse?.academicYear ?? '2025/2026',
          semester: firstCourse?.semester ?? 1,
          start: firstCourse?.start ?? '2025-09-15',
          end: firstCourse?.end ?? '2026-01-31',
          nonTeaching: firstCourse
            ? JSON.parse(JSON.stringify(firstCourse.nonTeaching))
            : [],
          maxPeriodsPerDay: 6,
          regNumber: null,
          approvedBy: firstCourse?.approvedBy ?? null,
          approvalDate: firstCourse?.approvalDate ?? null,
          administrativenOtgovornik: null,
        };
      case 'teachers':
        return {
          id: nextId('t', problem.teachers),
          name: '',
          katedraId: problem.katedri[0]?.id ?? null,
          preferredSlots: [],
          hardAvailability: [],
          maxWeeklyPeriods: null,
          preferredRooms: [],
          role: null,
          priorityWeight: null,
        };
      case 'rooms':
        return {
          id: nextId('r', problem.rooms),
          name: '',
          capacity: 30,
          type: 'малка зала',
          building: '',
          maxConcurrentGroups: 1,
        };
      case 'groups':
        return {
          id: nextId('g', problem.groups),
          name: '',
          size: 25,
          courseInstanceId: firstCourse?.id ?? '',
        };
      case 'subgroups':
        return {
          id: nextId('sg', problem.subgroups),
          groupId: problem.groups[0]?.id ?? '',
          name: '',
          size: Math.ceil((problem.groups[0]?.size ?? 24) / 2),
        };
      case 'subjects':
        return {
          id: nextId('s', problem.subjects),
          code: '',
          name: '',
          katedraId: problem.katedri[0]?.id ?? null,
        };
      case 'offerings':
        return {
          id: nextId('o', problem.offerings),
          subjectId: problem.subjects[0]?.id ?? '',
          courseInstanceId: firstCourse?.id ?? '',
          lectureHours: 30,
          exerciseHours: 30,
          hoursPerSession: 2,
          controlForm: 'изпит',
          lectureRoomTypes: ['зала'],
          exerciseRoomTypes: ['малка зала'],
          streamGroupIds: [],
          leadTeacherId: problem.teachers[0]?.id ?? null,
          exerciseTeacherIds: [],
          exerciseAudience: 'group',
          exerciseUnitIds: [],
          spread: 'whole',
          examDate: null,
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

  /** Every delete on this screen has the same shape: name the knock-on effect,
   *  then cascade. Nothing is ever left pointing at something that is gone --
   *  a dangling id is MODEL_INVALID on the solver side. */
  const confirmCascade = (message: string) => message === '' || window.confirm(message);

  const deleteTeacher = (id: string) => {
    // A teacher is one candidate among possibly several: drop them from every
    // pool, and only delete offerings left with nobody who could teach them.
    const orphaned = problem.offerings.filter(
      (o) =>
        (o.leadTeacherId === id && o.lectureHours > 0 && !o.exerciseHours) ||
        (o.exerciseHours > 0 &&
          o.exerciseTeacherIds.length === 1 &&
          o.exerciseTeacherIds[0] === id &&
          !o.lectureHours),
    );
    if (
      orphaned.length > 0 &&
      !confirmCascade(
        `${orphaned.length} offering(s) have nobody else who could teach them and will be deleted too. Continue?`,
      )
    ) {
      return;
    }
    const doomed = new Set(orphaned.map((o) => o.id));
    onChange({
      ...problem,
      teachers: problem.teachers.filter((t) => t.id !== id),
      offerings: problem.offerings
        .filter((o) => !doomed.has(o.id))
        .map((o) => ({
          ...o,
          leadTeacherId: o.leadTeacherId === id ? null : o.leadTeacherId,
          exerciseTeacherIds: o.exerciseTeacherIds.filter((t) => t !== id),
        })),
    });
  };

  const deleteRole = (id: string) => {
    // Teachers keep their place in the timetable and simply fall to the bottom
    // tier, which the ladder already handles -- so this never leaves the problem
    // in a state the solver would reject.
    const holders = problem.teachers.filter((t) => t.role === id);
    if (
      holders.length > 0 &&
      !confirmCascade(
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

  const deleteFaculty = (id: string) => {
    const specialties = problem.specialties.filter((s) => s.facultyId === id);
    if (
      specialties.length > 0 &&
      !confirmCascade(
        `${specialties.length} specialty(ies) belong to this faculty and will be deleted too, with everything under them. Continue?`,
      )
    ) {
      return;
    }
    let next = { ...problem, faculties: problem.faculties.filter((f) => f.id !== id) };
    next.katedri = next.katedri.map((k) => (k.facultyId === id ? { ...k, facultyId: null } : k));
    for (const s of specialties) next = cascadeSpecialty(next, s.id);
    onChange(next);
  };

  /** Specialty → курсове → групи → подгрупи → offerings, in one pass. */
  const cascadeSpecialty = (p: Problem, id: string): Problem => {
    const courses = p.courseInstances.filter((c) => c.specialtyId === id).map((c) => c.id);
    const courseSet = new Set(courses);
    const groups = p.groups.filter((g) => courseSet.has(g.courseInstanceId)).map((g) => g.id);
    const groupSet = new Set(groups);
    const subgroups = p.subgroups.filter((s) => groupSet.has(s.groupId)).map((s) => s.id);
    const gone = new Set([...groups, ...subgroups]);
    return {
      ...p,
      specialties: p.specialties.filter((s) => s.id !== id),
      courseInstances: p.courseInstances.filter((c) => !courseSet.has(c.id)),
      groups: p.groups.filter((g) => !groupSet.has(g.id)),
      subgroups: p.subgroups.filter((s) => !gone.has(s.id)),
      offerings: p.offerings
        .filter((o) => !courseSet.has(o.courseInstanceId))
        .map((o) => ({
          ...o,
          streamGroupIds: o.streamGroupIds.filter((g) => !gone.has(g)),
          exerciseUnitIds: o.exerciseUnitIds.filter((u) => !gone.has(u)),
        })),
    };
  };

  const deleteSpecialty = (id: string) => {
    const courses = problem.courseInstances.filter((c) => c.specialtyId === id);
    if (
      courses.length > 0 &&
      !confirmCascade(
        `${courses.length} курс(ове), their групи and their offerings will be deleted too. Continue?`,
      )
    ) {
      return;
    }
    onChange(cascadeSpecialty(problem, id));
  };

  const deleteCourse = (id: string) => {
    const groups = problem.groups.filter((g) => g.courseInstanceId === id);
    const offerings = problem.offerings.filter((o) => o.courseInstanceId === id);
    if (
      (groups.length > 0 || offerings.length > 0) &&
      !confirmCascade(
        `${groups.length} група(и) and ${offerings.length} offering(s) belong to this курс and will be deleted too. Continue?`,
      )
    ) {
      return;
    }
    const groupSet = new Set(groups.map((g) => g.id));
    const subgroupSet = new Set(
      problem.subgroups.filter((s) => groupSet.has(s.groupId)).map((s) => s.id),
    );
    const gone = new Set([...groupSet, ...subgroupSet]);
    onChange({
      ...problem,
      courseInstances: problem.courseInstances.filter((c) => c.id !== id),
      groups: problem.groups.filter((g) => !groupSet.has(g.id)),
      subgroups: problem.subgroups.filter((s) => !subgroupSet.has(s.id)),
      offerings: problem.offerings
        .filter((o) => o.courseInstanceId !== id)
        .map((o) => ({
          ...o,
          streamGroupIds: o.streamGroupIds.filter((g) => !gone.has(g)),
          exerciseUnitIds: o.exerciseUnitIds.filter((u) => !gone.has(u)),
        })),
    });
  };

  const deleteGroup = (id: string) => {
    // A група is referenced from a поток and, through its подгрупи, from
    // упражнения. Strip it everywhere, then delete offerings left with nobody.
    const subgroupSet = new Set(
      problem.subgroups.filter((s) => s.groupId === id).map((s) => s.id),
    );
    const gone = new Set([id, ...subgroupSet]);
    const strip = (o: SubjectOffering): SubjectOffering => ({
      ...o,
      streamGroupIds: o.streamGroupIds.filter((g) => !gone.has(g)),
      exerciseUnitIds: o.exerciseUnitIds.filter((u) => !gone.has(u)),
    });
    const orphaned = problem.offerings
      .map(strip)
      .filter((o) => !o.streamGroupIds.length && !o.exerciseUnitIds.length);
    if (
      orphaned.length > 0 &&
      !confirmCascade(
        `${orphaned.length} offering(s) are taught only to this група and will be deleted too. Continue?`,
      )
    ) {
      return;
    }
    onChange({
      ...problem,
      groups: problem.groups.filter((g) => g.id !== id),
      subgroups: problem.subgroups.filter((s) => !subgroupSet.has(s.id)),
      offerings: problem.offerings
        .map(strip)
        .filter((o) => o.streamGroupIds.length || o.exerciseUnitIds.length),
    });
  };

  const deleteSubgroup = (id: string) => {
    const users = problem.offerings.filter((o) => o.exerciseUnitIds.includes(id));
    if (
      users.length > 0 &&
      !confirmCascade(
        `${users.length} offering(s) teach this подгрупа and will lose it. Continue?`,
      )
    ) {
      return;
    }
    onChange({
      ...problem,
      subgroups: problem.subgroups.filter((s) => s.id !== id),
      offerings: problem.offerings.map((o) => ({
        ...o,
        exerciseUnitIds: o.exerciseUnitIds.filter((u) => u !== id),
      })),
    });
  };

  const deleteSubject = (id: string) => {
    const offerings = problem.offerings.filter((o) => o.subjectId === id);
    if (
      offerings.length > 0 &&
      !confirmCascade(
        `${offerings.length} offering(s) teach this subject and will be deleted too. Continue?`,
      )
    ) {
      return;
    }
    onChange({
      ...problem,
      subjects: problem.subjects.filter((s) => s.id !== id),
      offerings: problem.offerings.filter((o) => o.subjectId !== id),
    });
  };

  const deleteKatedra = (id: string) => {
    onChange({
      ...problem,
      katedri: problem.katedri.filter((k) => k.id !== id),
      teachers: problem.teachers.map((t) => (t.katedraId === id ? { ...t, katedraId: null } : t)),
      subjects: problem.subjects.map((s) => (s.katedraId === id ? { ...s, katedraId: null } : s)),
    });
  };

  // Removing a day or a period is a delete like any other on this screen, so it
  // gets the same treatment. It has to live here rather than in the pane because
  // the orphans are teacher preferences and availability windows, and the pane is
  // only handed the slot config.
  const dropSlots = (doomed: (id: string) => boolean, where: string, slotConfig: SlotConfig) => {
    const hits = (t: Teacher) =>
      t.preferredSlots.filter(doomed).length + t.hardAvailability.filter(doomed).length;
    const affected = problem.teachers.filter((t) => hits(t) > 0);
    const n = affected.reduce((sum, t) => sum + hits(t), 0);
    if (
      n > 0 &&
      !window.confirm(
        `${affected.length} teacher(s) name ${n} period(s) ${where}. Those preferences and availability windows will be dropped. Continue?`,
      )
    ) {
      return;
    }
    // One edit, not two: App bumps its data version per change, and removing a
    // day should mark the stored timetables stale exactly once.
    onChange({
      ...problem,
      slotConfig: {
        ...slotConfig,
        blockedSlots: slotConfig.blockedSlots.filter((id) => !doomed(id)),
      },
      teachers: problem.teachers.map((t) =>
        hits(t) > 0
          ? {
              ...t,
              preferredSlots: t.preferredSlots.filter((id) => !doomed(id)),
              hardAvailability: t.hardAvailability.filter((id) => !doomed(id)),
            }
          : t,
      ),
    });
  };

  const removeDay = (day: string) => {
    const config = problem.slotConfig;
    if (config.days.length <= 1) return;
    const prefix = `${day.toLowerCase()}-`;
    dropSlots((id) => id.startsWith(prefix), `on ${day}`, {
      ...config,
      days: config.days.filter((d) => d !== day),
    });
  };

  const removePeriod = () => {
    const config = problem.slotConfig;
    if (config.periods <= 1) return;
    // Only the last period can go: the numbers are slot ids, and renumbering
    // would silently repoint every blocked cell and every teacher preference.
    const last = config.periods;
    const suffix = `-${last}`;
    dropSlots((id) => id.endsWith(suffix), `in Period ${last}`, {
      ...config,
      periods: last - 1,
      periodTimes: config.periodTimes.slice(0, last - 1),
    });
  };

  const togglePreference = (teacherId: string, slotIdent: string) => {
    onChange({
      ...problem,
      teachers: problem.teachers.map((t) =>
        t.id === teacherId
          ? {
              ...t,
              preferredSlots: t.preferredSlots.includes(slotIdent)
                ? t.preferredSlots.filter((s) => s !== slotIdent)
                : [...t.preferredSlots, slotIdent],
            }
          : t,
      ),
    });
  };

  const openForm = (kind: EntityKind, draft: Draft) => setForm({ kind, draft, isNew: false });

  return (
    <div className="data">
      <nav className="sidebar">
        <div className="eyebrow sidebar__label">Input data</div>
        {ORDER.map((key) => (
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

        {section === 'faculties' && (
          <FacultiesTable
            rows={problem.faculties.filter((f) => matches(f.name))}
            problem={problem}
            onEdit={(f: Faculty) => openForm('faculties', f)}
            onDelete={deleteFaculty}
          />
        )}

        {section === 'katedri' && (
          <KatedriTable
            rows={problem.katedri.filter((k) => matches(k.name))}
            problem={problem}
            onEdit={(k: Katedra) => openForm('katedri', k)}
            onDelete={deleteKatedra}
          />
        )}

        {section === 'specialties' && (
          <SpecialtiesTable
            rows={problem.specialties.filter((s) => matches(s.name) || matches(s.code))}
            problem={problem}
            onEdit={(s: Specialty) => openForm('specialties', s)}
            onDelete={deleteSpecialty}
          />
        )}

        {section === 'courseInstances' && (
          <CoursesTable
            rows={problem.courseInstances.filter((c) =>
              matches(
                `${c.year} курс ${
                  problem.specialties.find((s) => s.id === c.specialtyId)?.code ?? ''
                }`,
              ),
            )}
            problem={problem}
            config={problem.slotConfig}
            onEdit={(c: CourseInstance) => openForm('courseInstances', c)}
            onDelete={deleteCourse}
          />
        )}

        {section === 'roles' && (
          <RolesTable
            roles={problem.roles.filter((r) => matches(r.name) || matches(r.short))}
            teachers={problem.teachers}
            onEdit={(r: Role) => openForm('roles', r)}
            onDelete={deleteRole}
          />
        )}

        {section === 'teachers' && (
          <TeachersTable
            teachers={problem.teachers.filter((t) => matches(t.name))}
            roles={problem.roles}
            rooms={problem.rooms}
            katedri={problem.katedri}
            slotConfig={problem.slotConfig}
            totalSlots={allSlots(problem.slotConfig).length}
            onTogglePreference={togglePreference}
            onEdit={(t: Teacher) => openForm('teachers', t)}
            onDelete={deleteTeacher}
          />
        )}

        {section === 'rooms' && (
          <RoomsTable
            rooms={problem.rooms.filter((r) => matches(r.name))}
            onEdit={(r: Room) => openForm('rooms', r)}
            onDelete={(id) =>
              onChange({ ...problem, rooms: problem.rooms.filter((r) => r.id !== id) })
            }
          />
        )}

        {section === 'groups' && (
          <GroupsTable
            groups={problem.groups.filter((g) => matches(g.name))}
            courses={problem.courseInstances}
            specialties={problem.specialties}
            subgroups={problem.subgroups}
            offerings={problem.offerings}
            onEdit={(g: Group) => openForm('groups', g)}
            onDelete={deleteGroup}
          />
        )}

        {section === 'subgroups' && (
          <SubgroupsTable
            rows={problem.subgroups.filter((s) => matches(s.name))}
            groups={problem.groups}
            onEdit={(s: Subgroup) => openForm('subgroups', s)}
            onDelete={deleteSubgroup}
          />
        )}

        {section === 'subjects' && (
          <SubjectsTable
            subjects={problem.subjects.filter((s) => matches(s.name) || matches(s.code))}
            katedri={problem.katedri}
            offerings={problem.offerings}
            subjectIds={problem.subjects.map((s) => s.id)}
            onEdit={(s: Subject) => openForm('subjects', s)}
            onDelete={deleteSubject}
          />
        )}

        {section === 'offerings' && (
          <OfferingsTable
            offerings={problem.offerings.filter((o) => {
              const s = problem.subjects.find((x) => x.id === o.subjectId);
              return !s || matches(s.name) || matches(s.code);
            })}
            problem={problem}
            onEdit={(o: SubjectOffering) => openForm('offerings', o)}
            onDelete={(id) =>
              onChange({ ...problem, offerings: problem.offerings.filter((o) => o.id !== id) })
            }
          />
        )}

        {section === 'slots' && (
          <SlotConfigPane
            config={problem.slotConfig}
            onChange={(slotConfig) => onChange({ ...problem, slotConfig })}
            onRemoveDay={removeDay}
            onRemovePeriod={removePeriod}
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
