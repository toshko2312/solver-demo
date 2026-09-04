# Migration — generic university model → Академия на МВР

The wire format changed shape. This is a **clean break**: a request in the old
format is rejected, and both seed files were migrated in the same change. Nothing
reads the old shape any more — there is no adapter and no fallback.

`frontend/src/types.ts` and `solver/app/models.py` still mirror each other and
still *are* the whole wire format.

---

## Why

The old model was a generic university one: a flat `Group` that owned its own
term dates, a `Subject` carrying a raw session count, five English room types,
and a Mon–Fri × 6 single-period grid. Real разписания at Академия на МВР are
issued **per курс + семестър + специалност**, built from a учебен план хорариум
(`30/15` = лекции/упражнения), run on a **six-day week**, and split групи into
подгрупи for стрелкова подготовка, ЛЗФП and чуждоезиково обучение.

The CP-SAT core did not change. The priority ladder, the three soft costs and
their relative weights, and the structural (variable-omission) enforcement of
room type and capacity all survive untouched.

---

## New entities

| Entity | What it is |
|---|---|
| `Faculty` | Факултет — Полиция, ПБЗН. |
| `Katedra` | A department. Owns subjects and teachers; printed on the разписание. |
| `Specialty` | Специалност with `code`, `degree` (ОКС), `form` (редовна/задочна), `studentKind` (курсант/студент), `durationYears`. |
| `CourseInstance` | One курс of one специалност in one semester. **The scheduling unit**, and the unit a printed разписание is emitted for. Owns the term dates, the non-teaching periods, `maxPeriodsPerDay`, and the разписание header fields. |
| `Subgroup` | Подгрупа: a група split for стрелкова подготовка, ЛЗФП or чуждоезиково обучение, with its own size and its own busy calendar. |
| `SubjectOffering` | One subject as taught to one курс: the хорариум and everything hanging off it. **This is what is actually taught.** |
| `NonTeachingPeriod` | Replaces `breaks`. Typed: `ваканция \| стаж \| изпитна сесия \| празник`, with an `ExamSessionKind` (`редовна \| поправителна \| ликвидационна`) when it is an exam session. |
| `Razpisanie` + friends | The printed document model — see `solver/app/razpisanie.py`. |

---

## Renamed, moved, dropped

### `Group`

| Field | Change |
|---|---|
| `semesters[]` | **Dropped.** Term dates moved up to `CourseInstance`. |
| `programme` | **Dropped.** Derivable from the group's `Specialty`. |
| — | **Gained** `courseInstanceId`. |

A cohort continuing into the next semester is a **new** `CourseInstance` with its
own `Group` rows. Both seed files carry the two semesters of 2025/2026 rather
than the old four semesters of dates per група: the same 1 курс appears twice,
once per семестър, with a different set of група rows each time. That is the rule
above made visible — and it is why the семестър picker offers two entries and
each is solved and stored on its own.

### `Subject`

Became a catalogue entry: `id`, `code`, `name`, `katedraId`.

| Field | Moved to |
|---|---|
| `allowedRoomTypes` | `SubjectOffering.lectureRoomTypes` / `.exerciseRoomTypes` — **per activity kind**, because лекции and упражнения of one subject routinely want different rooms. |
| `semesters[]` | `SubjectOffering` (one per курс the subject is taught to). |
| `teacherIds` | `SubjectOffering.leadTeacherId` (лекции — one named водещ преподавател) and `.exerciseTeacherIds` (упражнения — the pool, unchanged). |
| — | **Gained** `code`, `katedraId`. |

### `SubjectSemester` → `SubjectOffering`

| Old | New |
|---|---|
| `totalSessions` | `lectureHours` / `exerciseHours` + `hoursPerSession` (default 2). Sessions = `ceil(hours / hoursPerSession)`. |
| `groupIds` | `streamGroupIds` (the **поток** for лекции — a join, not an attribute of the курс) and `exerciseUnitIds` + `exerciseAudience` (групи or подгрупи for упражнения). |
| `academicYear`, `index` | `courseInstanceId`. |
| `spread: whole \| range` | `spread: whole \| range \| **block**`. |
| — | **Gained** `controlForm` (изпит/КТО/зачет) and `examDate`, both for the разписание. |

**The хорариум is per unit.** 15 упражнителни часа means fifteen hours for *each*
група or подгрупа in `exerciseUnitIds` — it is what one student is owed, not what
the катедра delivers once. Лекции are counted once for the whole поток.

### `Teacher`

| Field | Change |
|---|---|
| `department` | → `katedraId` (a real reference, not free text). |
| `preferredSlots` | Same field, **new key shape** — see below. Still soft. |
| — | **Gained** `hardAvailability[]`: same key shape, but **hard**. A literal is never created outside it, so no rank and no weight can buy around it. An impossible availability is `INFEASIBLE`, not expensive. |
| — | **Gained** `maxWeeklyPeriods` — hard cap per ISO week, `null` for uncapped. |

### `Room`

| Field | Change |
|---|---|
| `type` | Enum **replaced wholesale** — see the mapping below. |
| — | **Gained** `maxConcurrentGroups` (default 1). |

### `Role`

Shape unchanged. `DEFAULT_ROLES` is now **seven** ranks and the weights moved:

```
проф. 7 · доц. 6 · гл. ас. 5 · ас. 4 · ст. преп. 3 · преп. 2 · хон. преп. 1
```

Note `ас.` now outranks `ст. преп.`, which is the order the academy uses; under
the old six-rank table it was the other way round.

### `SolveRequest`

| Field | Change |
|---|---|
| `slots` | Unchanged — dated single periods. Still what the разписание draws with. |
| — | **Gained** `faculties`, `katedri`, `specialties`, `courseInstances`, `subgroups`, `offerings`. |
| `semester` | Unchanged. One solve still covers **every** курс of that semester — rooms and teachers are shared, and solving курсове one at a time would double-book both. |
| `maxTimeInSeconds` | **Default changed from `30` to `null`** — no deadline at all. A faculty-sized semester needs about ninety seconds just to find its first legal timetable, so the old default returned `UNKNOWN` with nothing placed. A slow timetable beats no timetable; set a limit explicitly when a fixed answer time matters. |

### `Assignment`

| Field | Change |
|---|---|
| `slot` | Unchanged. **Gained** `period: int` alongside it, so a card can label its row without parsing the id. |
| — | **Gained** `offeringId`, `subjectCode`, `activity`, `day`, `subgroupId`, `subgroupName`. |

### `SlotConfig` (frontend only — never on the wire)

| Field | Change |
|---|---|
| `days` | Now Mon–**Sat** by default: курсанти have Saturday classes. |
| `periods` | 6 → 12, with clock times 08:00–19:30. |

---

## Key formats

| Key | Old | New |
|---|---|---|
| Weekday preference / availability / blocking | `mon-1` | unchanged |
| Dated period slot id | `2025-09-15-1` | unchanged |

---

## Room types

| Old | New |
|---|---|
| `lecture` | `зала` (capacity ≥ 60) or `малка зала` (seminar rooms) |
| `lab` | `компютърна зала` |
| `sports` | `спортен комплекс` |
| `firing_range` | `стрелбище` |
| `training_ground` | `полигон` |
| — | `тренажорна зала` (new; ЛЗФП) |

---

## Lossy conversions — read these

1. **`lab` → `компютърна зала`.** The new vocabulary has no *лаборатория*, so
   "Криминалистична лаборатория" is carried as a компютърна зала: an equipped
   specialist room of the same size. Anything that relied on distinguishing a
   crime-lab from a computer room no longer can.

2. **`ceil(hours / hoursPerSession)`.** An odd хорариум rounds **up**: 15
   упражнителни часа become 8 periods = 16 delivered hours. Rounding down would
   silently under-deliver the учебен план, and a leftover hour is a smaller lie
   than a missing one.

3. **The day grew a sixth teaching weekday.** Saturday is now a teaching day, so
   the grid is 6 × 6 = 36 slots a week rather than 5 × 6 = 30. The period times
   themselves are unchanged, обедна почивка included: it is still the 13:00→13:45
   gap between period 3 and period 4, a break defined by absence rather than by
   a rule.

4. **`Group.programme` and `Group.semesters` are gone.** Free-text programme
   names in an old dataset have no home; term dates have to be re-entered once
   per `CourseInstance` rather than once per група (which is fewer places, not
   more).

5. **The seeds model two semesters, not four.** Because a `Group` belongs to
   exactly one `CourseInstance`, each semester of the old `Group.semesters[]`
   would now be its own set of група rows. The seeds keep the two semesters of
   2025/2026 and drop 2026/2027: семестър 1 teaches 15.09.2025 – 31.01.2026 and
   семестър 2 teaches 09.03.2026 – 27.06.2026, after the поправителна сесия of
   the first. Dates for a third semester have to be entered as new курсове.

---

## Behaviour that changed

- **A група-level session excludes every подгрупа of that група, and two
  подгрупи of one група may run at the same time.** This is why подгрупи exist:
  гр. 1а at стрелбището while гр. 1б is in АЕ. A naive union over "everything the
  група could be doing" would forbid exactly that.
- **`spread: block`** drops the weekly floor and ceiling *and* the week-band
  pruning that depends on them. It saturates its window instead.
- **A period is still the atomic unit.** It carries two academic hours because
  the period times say so, not because anything enforces it — so a faculty that
  defines a 45-minute period will get single-hour sessions. That is the same kind
  of convention as "no period spans lunch", and deliberately so.
- **The хорариум must divide by the курс's own teaching weeks.** A курс on стаж
  teaches sixteen weeks, not eighteen; a хорариум sized for eighteen asks for two
  sessions in some week, which widens every week-band and multiplies the model.
  `shared/generate_seed.py` sizes hours per курс for exactly this reason.
- **`gapWeight` still cannot buy a compact day at the price of a preference.**
  Unchanged from before this migration, and worth restating: gaps are the last
  rung of the ladder, so every teacher rank is frozen by the time they are
  scored.

---

## New endpoint

`POST /razpisanie` takes `{request, response, courseInstanceId, periodTimes}` and
returns the printed document — `?format=json` for the model, anything else for
print-ready HTML (A4 landscape). It is a renderer over a `SolveResponse` that
already exists; it never re-solves.
