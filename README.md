# University Timetable Generator — OR-Tools CP-SAT proof of concept

A reduced-scope university timetabler: a **FastAPI + OR-Tools CP-SAT** solver service behind a
**React + Vite + TypeScript** UI. The point of the project is the solver — the UI exists to feed it
a problem and make its answers (including its refusals) legible.

The interesting file is [`solver/app/timetable_solver.py`](solver/app/timetable_solver.py): the whole
CP-SAT model, commented.

---

## Run it

### Docker (one command)

```bash
docker compose up --build
```

| Service    | URL                     | What it is                                  |
|------------|-------------------------|---------------------------------------------|
| `frontend` | http://localhost:5173   | React + Vite dev server (open this)         |
| `solver`   | http://localhost:8000   | FastAPI + CP-SAT (`/health`, `/solve`, `/docs`) |

The frontend proxies `/api/*` to the solver, so the browser only ever talks to port 5173.

### Local, two commands

```bash
# terminal 1 — solver on :8000
cd solver
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend on :5173
cd frontend
npm install && npm run dev
```

### Tests

```bash
cd solver && .venv/bin/python -m pytest      # 14 tests, ~3s
```

---

## Demo flow

1. **Load an example** (top right) — two datasets, both modelling **Факултет "Полиция" of
   Академия на МВР** on a Mon–Fri × 6-period grid:

   | | Contents | Behaviour |
   |---|---|---|
   | **Small example** | 6 instructors, 8 rooms, 3 groups, 12 subjects, 21 sessions | `OPTIMAL` in ~0.6 s, with 2 unavoidable preference misses — start here |
   | **Full example** | 30 instructors, 22 rooms, 20 groups, 158 subjects, **170 sessions** | a genuinely hard instance; see below |

   The small one is the better first click: it solves instantly, fits on screen, and still shows a
   real trade-off. The full one is what a faculty timetable actually looks like.
2. **Generate** — POSTs the whole problem to `/solve`. The small example comes back `OPTIMAL`
   almost immediately. The full one is a genuinely hard instance: within the default 30 s budget
   CP-SAT returns a valid, good schedule — every session placed, all hard rules verified — but often
   with status **FEASIBLE**, because it cannot *prove* optimality in the time. That distinction is
   the point, and it is what real timetabling looks like; give it longer in Settings to improve the
   objective.
3. **Timetable** — days as columns, periods as rows. The teacher shown on a card is the one the
   solver *chose* out of that subject's pool (open *Data setup → Subjects → Edit* to see the
   multi-selects for allowed room types and candidate teachers). Switch the lens between **by group / by teacher /
   by room** and pick an entity; all three lenses filter the same `assignments` array, so they cannot
   disagree. Colour by subject or room type, toggle density, export CSV.
4. **Break it** — two easy ways:
   - *Data setup → Time slots →* **Remove period** until only one period a day remains. Recruit
     Class A needs 7 sessions and only 5 slots exist → `INFEASIBLE`, with that named as the reason.
   - *Data setup → Time slots →* block cells (e.g. the whole Period 1 row). Blocked slots are excluded
     from solving; block enough and the problem becomes impossible. Block just a few and watch the
     soft penalty rise instead — Sgt. Bergstrom prefers period-1 slots, so blocking that row costs
     3 preference violations and the cards get a dashed edge and an amber marker.
5. **Tinker** — the *Settings* button on the Generate tab opens the solver settings dialog. Two
   demonstrations worth a minute each, both on the **small example**:
   - **Gap weight.** The default timetable has visible holes — a group sitting 1st, 2nd and then 6th
     period — because its morning and late instructors both got the slots they asked for, and a hole
     is cheaper than a broken preference. Raise *Gap weight* to 10, press Generate, and the days
     compact to zero gaps while three preferences get traded away instead. One knob, both halves of
     the objective visible.
   - **Stop at first solution.** Returns a legal-but-bad timetable instead of the optimum — on the
     full example, a penalty in the hundreds against 0.
6. Every successful solve is **re-checked independently** of the model (`validate_assignments`) and the
   result shown as *All hard rules verified*. That badge is what makes "the solver produced a valid
   timetable" a claim you can check rather than trust.

---

## Solver settings

The **Solver settings** dialog — opened from the *Settings* button on the Generate tab — exposes the
knobs, in two accordions. Every label carries a `?` with a
plain-language explanation on hover or keyboard focus — no CP-SAT vocabulary required to use it.

**A · Objective** (open by default) — these change *which* timetable comes back:

| Setting | Effect on the seed dataset |
|---|---|
| Time limit | **Default 30 s**, ceiling 20 min. The full seed is hard enough to use every second it is given, so this one binds — more time buys a better objective, not a faster answer. |
| Teacher preference weight (default 10) | With the Period 1 row blocked: `pref=1, gap=10` gives 4 preference misses but **0 gaps**, against 3 misses / 2 gaps at the defaults — the trade-off flips. |
| Gap weight (default 1) | The clearest knob in the app. On the **small example** the default leaves **12 gap units across 3 split days** and breaks no preferences; raise it to **10** and the days compact to **zero gaps**, paid for with **3** teacher preferences. Set it to `0` and the solver stops caring about compact days entirely. |
| Stop at first solution | **FEASIBLE at a penalty of roughly 115-140** (a dozen or so preference misses) instead of OPTIMAL at 0. The exact number moves run to run, since which worker finds the first solution is a matter of timing. The clearest demonstration of what optimising buys — the first legal timetable is bad, and polishing it takes ~30 ms. |

**B · Search** (collapsed by default) — same answer, different amount of work:

| Setting | Effect on the seed dataset |
|---|---|
| Parallel workers (default 8) | 8 workers: ~520 branches, 0 conflicts. 1 worker: ~18,600 branches, 46 conflicts. Set to 1 for reproducible runs. |
| Random seed | Only meaningful with a single worker; changes which of several equally optimal timetables you get. |
| Presolve (default on) | Off is *faster* here (197 ms vs 299 ms) — this model is too small for presolve to pay for itself. |
| Symmetry detection | `0` barely moves the needle (255 ms, 400 branches). |
| Arithmetic reasoning | CP-SAT's linearization level. |
| Our own symmetry shortcut | Our hand-written constraint forcing a subject's sessions into time order. Turning it off still reaches the same optimum — CP-SAT's presolve finds dozens of symmetry generators on its own, so this is a genuine open question the tab lets you measure. |

Settings are sent with every solve and echoed back as `settingsUsed`, so the Generate tab always
describes a result by the settings it was actually produced with — not by whatever is on screen now.
Server side they are a typed Pydantic model (`SearchParams` in `solver/app/models.py`), which *is*
the whitelist: there is no passthrough of arbitrary solver proto fields.

## The model

**Decision variables.** Each subject with `sessionsPerWeek = n` expands into `n` session instances.
A subject names a *set* of acceptable room types and a *pool* of candidate teachers, so when, where
and who are all decisions. There is one boolean per `(session, slot, room, teacher)` quadruple:

```
x[s, t, r, k] == 1   <=>   session s runs in slot t, in room r, taught by k
```

The set is **pruned at construction** — a room only gets variables for a session if its type is one
the subject accepts *and* its capacity covers every group in the session. Two hard constraints are
therefore structural rather than posted as constraints.

Carrying the teacher in the variable index is what makes the pool work: the session's
"happens exactly once" constraint already ranges over teacher-tagged literals, so **"exactly one
teacher out of the pool" needs no constraint of its own** — it falls out of that one. The solver is
free to give two sessions of the same subject to different candidates.

**Hard constraints**

| Requirement | Encoding |
|---|---|
| Each subject scheduled exactly `sessionsPerWeek` times | `AddExactlyOne` per session instance |
| Exactly one teacher per session, drawn from the subject's pool | implied by the same `AddExactlyOne` — no separate constraint |
| No teacher teaches two sessions in one slot | `AddAtMostOne` per (teacher, slot), keyed on the literal's own candidate |
| No group attends two sessions in one slot (all groups of a multi-group subject are busy) | `AddAtMostOne` per (group, slot) |
| No room hosts two sessions in one slot | `AddAtMostOne` per (room, slot) |
| Room type is one the subject accepts | structural (pruned variables) |
| Room capacity ≥ total size of the session's groups | structural (pruned variables) |

Sessions of the same subject are interchangeable, so a `slot_index` integer is channelled from the
booleans and forced strictly increasing across a subject's sessions — symmetry breaking that keeps the
search from re-exploring permutations of the same schedule.

**Soft constraints (minimised)**

- Teacher preference: a session outside its teacher's `preferredSlots` costs `PREFERENCE_WEIGHT = 10`.
  Teachers with no stated preference cost nothing. Because *which* teacher is itself a decision, the
  penalty is a property of the literal, not of the session — picking a candidate who likes that slot
  is cheaper, and watching CP-SAT make that trade is half the point of the demo.
- Group day-gaps: a free period with teaching on both sides of it, in the same group's day, costs
  `GAP_WEIGHT = 1` — an order of magnitude below preferences, so a compact day never outbids one.

**Search.** `max_time_in_seconds` is always set. It defaults to the 20-minute ceiling
(`MAX_SOLVE_SECONDS` in `solver/app/models.py`), so a solve runs as long as it needs to and answers
the moment it finishes; the Generate tab offers 10 s / 1 min / 20 min presets and a free-form box, and
the API rejects anything above the ceiling. The cap exists because CP-SAT can take unbounded time to
*prove* infeasibility — without it a hard instance would pin a worker thread and an open HTTP request
indefinitely. A running solve shows a live elapsed clock. 8
workers. `OPTIMAL` and `FEASIBLE` are reported distinctly: "proven minimum penalty" and "best found
inside the time limit" are different claims. A timeout with nothing found is `UNKNOWN`, never
`INFEASIBLE`.

**Infeasibility.** CP-SAT says *infeasible*; it does not say *why*. `solver/app/diagnostics.py` runs
cheap counting checks and reports the over-subscribed resource: a subject no room can hold, a group
with more sessions than slots, total sessions vs total room-slots, and — for rooms and teachers —
Hall's condition over the type-sets and candidate pools that actually appear in the data. That last
part matters once pools exist: sessions whose pool fits inside some set of teachers can only be taught
by that set, so the check blames the pool collectively instead of blaming one teacher for work a
colleague could take. These are necessary conditions only — when none fires, the response says so
instead of inventing a reason.

---

## What this tests

That CP-SAT can express the hard/soft constraint structure of a real university timetable, solve it
fast at small scale, and fail *informatively* rather than hanging. What it does **not** cover, versus
the full requirement:

- **No потоци / streams** — no lecture-stream hierarchy above groups.
- **No split-group-per-subject** — a subject cannot fan a group into lab subgroups; a session is one
  room for the whole group set.
- **No co-teaching** — a subject's teacher list is a pool of candidates, exactly one of whom takes
  each session. There is no way to say "both of these instructors attend together".
- **No multi-semester or multi-week** — one representative week, one semester.
- **No teacher hard availability** — a teacher's unavailability can only be expressed globally, by
  blocking a slot for everyone; per-teacher preferences are soft.
- **No session length or double-period blocking** — every session is exactly one period.
- **No room adjacency, travel time, or building constraints.**
- **No persistence** — state lives in the browser and is POSTed in full on every solve.

---

## Layout

```
solver/app/timetable_solver.py   the CP-SAT model + independent output validator
solver/app/diagnostics.py        infeasibility hints
solver/app/models.py             the whole wire format
solver/app/main.py               FastAPI (/health, /solve)
solver/tests/test_solver.py      feasibility, validity, infeasibility, soft-constraint tests
shared/seed-small.json           the small example — also the default test fixture
shared/seed-full.json            the full four-year faculty example
shared/generate_seed.py          regenerates the full one (YEARS / N_PPOOR / N_GP knobs)
frontend/src/                    React UI (DataScreen / GenerateScreen / ResultScreen)
frontend/src/styles/ds/          design tokens vendored from the Claude Design project
```

### A note on the seed data

Both datasets model **Факултет "Полиция"** at the **Академия на МВР** (Sofia) — the small one a
single курс, the full one all four years. Be clear about which parts are researched and which are
modelled:

**From the Academy's own published material:**
- It has two faculties — Факултет "Полиция" and Факултет "Пожарна безопасност и защита на
  населението". Only the first is modelled here.
- Факултет "Полиция" comprises five катедри: Публичноправни науки; Наказателноправни науки; Опазване
  на обществения ред и граничен контрол; Оперативно-издирвателна дейност; Специална полицейска
  тактика. These are the instructors' departments.
- Cadets are admitted to three bachelor specialties — "Противодействие на престъпността и опазване на
  обществения ред", "Гранична полиция" and "Пожарна и аварийна безопасност". The first two belong to
  Факултет "Полиция" and appear here; the third belongs to ПБЗН and does not.
- The academic ranks used (проф. д-р, доц. д-р, гл. ас. д-р, ст. преп., ас.).

**Modelled, not cited:**
- **Group sizes.** The Academy does not publish enrolment figures, and none were reachable. Groups
  are the standard Bulgarian учебна група of ~25, with lectures delivered to the whole поток — about
  500 cadets across the faculty. Plausible, but a model rather than a number to quote.
- **The curriculum split across years.** Subject names come from the real subject areas of the five
  катедри; which year each falls in is a reasonable approximation, as учебните планове are not public.
- **Instructor names** are generic Bulgarian surnames, not Academy staff. Naming real employees in a
  demo dataset would be a privacy problem for no benefit.
- **Room inventory.** Аудитории, учебни зали, компютърни зали, криминалистична лаборатория, физкултурен
  салон, стрелбища and полигони are the kinds of facilities such an academy has; the counts and
  capacities are chosen so the problem is solvable, not taken from a floor plan.

Sources: [Академия на МВР](https://www.mvr.bg/academy) ·
[Факултет "Полиция" — академичен състав](https://www.mvr.bg/academy/академията/факултет-полиция/академичен-състав) ·
[Прием курсанти и студенти](https://www.mvr.bg/academy/прием/учебна-дейност/прием-курсанти-и-студенти)
