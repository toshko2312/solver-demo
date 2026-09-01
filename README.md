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
cd solver && .venv/bin/python -m pytest      # 51 tests, ~10 min
```

---

## Demo flow

1. **Load an example** (top right) — two datasets, both modelling **Факултет "Полиция" of
   Академия на МВР**, on a Mon–Fri × 6-period template expanded across real semester dates:

   | | Contents | Behaviour |
   |---|---|---|
   | **Small example** | 6 instructors, 8 rooms, 3 groups, 12 subjects, 21 sessions | `OPTIMAL` in ~4 s: all four rank tiers settled, every teacher gets their slots and their first-choice rooms — start here |
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
5. **Tinker** — the *Settings* button on the Generate tab opens the solver settings dialog.
   - **Stop at first solution.** Returns a legal-but-bad timetable instead of the optimum. On the
     small example: penalty 182 in 0.8 s, against 12 in ~4 s.
   - **Priority.** Open *Data setup → Teachers*, give a junior instructor a *Priority weight* above
     a senior one's, and re-generate: the ladder reorders and the contested room changes hands. The
     ladder panel on the Generate tab shows each rank in turn and what it had to give up.
   - **Gap weight** is deliberately *not* a demonstration any more — see the table below for why.
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
| Teacher preference weight (default 10) | Cost of a session outside a teacher's preferred slots. It trades against the room weight *within* a rank; it cannot trade across ranks. |
| Room preference weight (default 5) | Cost per place down a teacher's ranked room list, scored per room type. Below the slot weight, so when both cannot be met the slot is the one kept. |
| Gap weight (default 1) | **No longer a trade-off knob**, and the change is worth understanding: group gaps are the last rung of the priority ladder, so by the time they are considered every teacher rank is frozen at its best. On the small example the default gives **12 gap units**, and raising it to **10** gives the same 12 — it only scales the number, because nothing is left to trade against. Set it to `0` to stop reporting them. |
| Stop at first solution | Collapses the ladder to one un-optimised solve. On the small example: **FEASIBLE at penalty 182** (17 preference misses, 5 room cost, 7 gaps) in **0.8 s**, against **OPTIMAL at 12** in ~4 s. The clearest demonstration of what optimising buys. |

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

**Decision variables.** Each subject expands into one session instance per session it runs that
semester, and each lands on a real date.
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
| Each subject scheduled exactly its semester total | `AddExactlyOne` per session instance |
| Exactly one teacher per session, drawn from the subject's pool | implied by the same `AddExactlyOne` — no separate constraint |
| No teacher teaches two sessions in one slot | `AddAtMostOne` per (teacher, slot), keyed on the literal's own candidate |
| No group attends two sessions in one slot (all groups of a multi-group subject are busy) | `AddAtMostOne` per (group, slot) |
| No room hosts two sessions in one slot | `AddAtMostOne` per (room, slot) |
| Room type is one the subject accepts | structural (pruned variables) |
| Room capacity ≥ total size of the session's groups | structural (pruned variables) |

Sessions of the same subject are interchangeable, so a `slot_index` integer is channelled from the
booleans and forced strictly increasing across a subject's sessions — symmetry breaking that keeps the
search from re-exploring permutations of the same schedule. It earns much more here than it did over
a single week, and it does double duty: together with the even-spread constraint it pins session *k* to
a narrow band of weeks, which is applied when the variables are built rather than only as a constraint.
That pruning is what makes a semester affordable — on the full seed it is the difference between
~718,000 booleans and roughly ten million.

**Even spread.** Each subject's sessions are distributed across the teaching weeks of its window, every
week carrying between `floor(N/W)` and `ceil(N/W)` of them. This is what "spread evenly" means once
sessions are dated, and being hard it can make a problem infeasible — `diagnostics.py` names the
subject when it does.

**The calendar.** A timetable is generated for one **semester**, identified by academic year and
index (`2025/2026`, semester 1). The *dates* are per group: each group carries its own start and end
for a semester, plus any breaks, so two cohorts can run the same term on different calendars. The
weekday × period template defines which periods exist and `blockedSlots` still blocks a period on that
weekday *every* week; the frontend expands that template across the semester's real dates, and slots
falling on a break simply do not exist.

A subject declares a **total for the semester** rather than a weekly rate — sessions land on real
dates, so nothing has to divide evenly — and whether they spread across the whole term or across a
period chosen inside it. It also declares **which groups attend, per semester**: the cohort lives on
the semester entry, not on the subject, so the same subject can run for one set of groups in the
autumn and another in the spring. Sessions may only use dates on which **every** one of that
semester's groups is in term: the intersection, because a multi-group session busies all of them at
once.

**Soft constraints, and the priority ladder**

Teachers carry an academic rank (`role`), and rank decides who wins a contested slot or room. This is
**not** a weighted trade-off: the solver optimises one rank at a time, highest first, and freezes each
rank's result before the next one bargains. A професор's preference is never sold to satisfy any
number of асистенти — a guarantee no choice of weights can express.

- **Rank → tier.** Ranks are **data, not code**: a request carries a `roles` array of
  `{id, name, short, weight}`, edited under *Data setup → Roles*, so a faculty can name the ranks it
  actually has and decide what outranks what. The weights are *tier keys, not multipliers*: only
  their ordering and which ranks share a value matter, and ranks sharing a weight share a tier and
  trade freely with each other. `priorityWeight` on a teacher overrides their rank's weight, and is
  the only way to move one person without inventing a rank for them. A teacher with no rank — or one
  naming a rank that has since been deleted — shares the bottom tier, so a problem with no roles at
  all behaves exactly as it did before the ladder existed.

  A request that omits `roles` falls back to the six Bulgarian ranks in `DEFAULT_ROLES`
  (`solver/app/models.py`), whose ids are the values the old fixed enum used — so every existing
  caller keeps its ranking without changing anything.
- **Slot preference:** a session outside its teacher's `preferredSlots` costs `preferenceWeight = 10`.
  Because *which* teacher is itself a decision, the penalty is a property of the literal, not of the
  session — picking a candidate who likes that slot is cheaper.
- **Room preference:** `preferredRooms` is **ranked** — first choice free, each place further down
  costs `roomPreferenceWeight = 5` again, and a room not on the list costs one step worse than the
  last named choice. Ranking is scored **per room type**: which types a session may use is a hard
  constraint, so ranking two полигона says nothing about which стрелбище you get, and a teacher is
  never billed for a type they expressed no opinion about. An empty list can never be violated.
- **Group day-gaps:** a free period with teaching on both sides of it, in the same group's day, costs
  `gapWeight = 1`. This is the **last rung**, after every teacher rank. A consequence worth stating:
  `gapWeight` can no longer buy a compact day at the price of a teacher preference, because by the
  time gaps are considered every teacher tier is already frozen. It orders solutions within the gap
  stage only.

**Search.** The ladder runs as a sequence of solves against one model: a warm-up with no objective at
all (which returns the instant it finds any legal timetable), then one phase per rank, then gaps. Each
phase sets its own objective, and freezes the result with `Add(expr <= achieved)` before the next
begins — a bound taken from a solution that demonstrably exists, so the model can never be made
infeasible by its own ladder.

The warm-up is deliberately **not** rationed: a run has to *have* a timetable before optimising one
means anything, and once it has one every later rung can only improve on it. That is what guarantees a
solve always returns the best timetable it found, however little time it was given.

Each rung then gets an even share of what is left, floored at the warm-up's own measured cost — the
best available estimate of what this model's presolve costs, since a rung given less than that spends
its whole slice in presolve and returns `UNKNOWN` having never searched. When the remaining budget
cannot afford another real rung the ladder stops there, which starves the *junior* ranks: the right
way round. Rungs that never ran are reported as `NOT REACHED` rather than being passed off as
satisfied, and a rung that hit its limit at `FEASIBLE` says so — the ranks below it were frozen
against a number it might have improved on, and that is exactly the situation the ladder exists to
prevent, so it is surfaced rather than buried.

On the four-year seed, presolve alone is ~6s and finding a first timetable ~6s, so a 30s budget
settles the top rank or two and leaves the rest `NOT REACHED`; more time settles more of them. The
small example finishes the whole ladder in ~3s.

`max_time_in_seconds` is always set. It defaults to the 20-minute ceiling
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
- **No cross-semester optimisation** — semesters are generated one at a time and stored separately;
  the solver never balances one term against another.
- **No teacher hard availability** — a teacher's unavailability can only be expressed globally, by
  blocking a slot for everyone. Per-teacher preferences are soft, and stay soft however senior the
  teacher: rank decides who wins a contested slot or room, never whether the session happens.
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
