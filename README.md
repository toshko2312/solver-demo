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
| `solver`   | http://localhost:8000   | FastAPI + CP-SAT (`/health`, `/solve`, `/solve/stream`, `/razpisanie`, `/docs`) |

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
cd solver && .venv/bin/python -m pytest      # ~100 tests, ~10 min
```

---

## Demo flow

1. **Load an example** (top right) — two datasets, both modelling **Факултет "Полиция" of
   Академия на МВР**, on the academy's own day: **six 90-minute periods on a six-day week**,
   08:00–18:45, each period two academic hours — so a day is the twelve academic hours a учебен
   план counts in. Editable in *Data setup → Time slots*, expanded across real semester dates.

   | | Contents | Behaviour |
   |---|---|---|
   | **Small example** | 7 instructors, 9 rooms, 6 групи, 8 подгрупи, 14 offerings — **268 sessions** in семестър 1, **240** in семестър 2 | `OPTIMAL` in ~22 s and ~39 s: the проф. and the доц. take the two contested morning periods and the гл. ас. pays for every session — start here |
   | **Full example** | 34 instructors, 23 rooms, 44 групи, 80 подгрупи, 91 offerings — **1832 sessions** in семестър 1, **1552** in семестър 2 | a genuinely hard instance: ~90 s to a first timetable, then it keeps improving |

   The small one is the better first click: it fits on screen and shows the ladder deciding an
   outcome. The full one is what a faculty timetable actually looks like — four курса plus a
   задочен, and it needs a minute or two to find its first legal timetable.

   **Both datasets carry both semesters of 2025/2026** — семестър 1 teaches 15.09.2025–31.01.2026,
   семестър 2 teaches 09.03.2026–27.06.2026 — and **a solve covers one of them**. Pick the semester
   on the Generate screen; each keeps its own timetable, its own run and its own ladder, and
   generating one leaves the other alone. The same 1 курс appears in both, as different курсове with
   different групи: a група belongs to exactly one `CourseInstance`, so a cohort continuing into the
   next semester is new rows. In the small example семестър 2 settles at a penalty of 512 against
   семестър 1's 540, and the доц. pays 30 of it — the same three ranks, a different bargain.

   **Обедната почивка is not a setting.** It is the 13:00→13:45 gap the period times leave between
   period 3 and period 4 — a break defined by absence. Nothing can be scheduled across it because
   no period covers it, and there is no rule anywhere in the model that says so.
2. **Generate** — POSTs the whole problem to `/solve/stream`, which runs the identical solve and
   reports its own milestones as server-sent events: the model being built, then each rung of the
   priority ladder starting, improving and settling, and finally the same `SolveResponse` that
   `/solve` returns in one piece. That is what drives the progress bar — the ladder's phase count is
   fixed before the search starts, so the bar only ever moves forwards. A server without the
   streaming endpoint falls back to plain `/solve`. Several semesters can be generated at once; each
   run gets its own row on the Generate screen. The small example comes back `OPTIMAL` in about
   twenty-five seconds. The full one is a genuinely hard instance: it takes **a minute or two**
   just to find its first legal timetable, and then keeps improving it rung by rung. **The default
   time limit is Unlimited**, so it runs until it has settled every rank it can — which is why the
   progress bar and the live clock exist. Set a limit in Settings if you would rather have an answer
   at a fixed moment: what comes back is **FEASIBLE** rather than `OPTIMAL`, every session placed
   and every hard rule verified but not *proven* best. That distinction is the point, and it is what
   real timetabling looks like.
3. **Timetable** — days as columns, periods as rows. A card shows the subject code and
   its activity marker (л / у / п), and the teacher on it is the one the solver *chose* out of that
   offering's pool (open *Data setup → Учебен план → Edit* to see the хорариум, the поток and the
   candidate teachers). A подгрупа session names its подгрупа rather than the whole група. Switch
   the lens between **by group / by teacher / by room**; all three filter the same `assignments`
   array, so they cannot disagree. Colour by subject or room type, toggle density, export CSV.
4. **Разписание** — the printed document, one per курс: approval header, numbered дисциплини with
   хорариум, разпределение на учебното време, изпитни дати, then the month grid whose cells carry
   the subject's number and its activity marker. Rendered by the solver (`POST /razpisanie`) and
   shown in a frame with a Print button; the JSON stays the machine-readable form.
5. **Break it** — several easy ways:
   - *Data setup → Teachers →* narrow **хон. преп. Радева**'s availability from five periods to one.
     Unlike a preference, this is HARD: the problem does not get more expensive, it becomes
     `INFEASIBLE` and the hint names her.
   - *Data setup → Time slots →* switch **Sat** off in the teaching-days row. The column and every
     Saturday date go with it, and any preference or availability window on that weekday is dropped
     after a prompt naming the count. Switch it back on and it returns to its own column.
   - *Data setup → Time slots →* block cells. Block enough and the problem becomes impossible;
     block a few and watch the soft penalty rise instead.
   - *Data setup → Курсове →* drop **Max periods a day** to 2. The groups' days compact, and past a
     point there is nowhere left to put the load.
6. **Move a session by hand** — drag a card to another cell of the week on screen, or select it and
   use *Move to another week* in the Session panel to pick a week, day and period. Moves are never
   refused: one that double-books a teacher, room, група or подгрупа — or lands on a blocked period,
   a date a курс is not in term, a day already at its period cap, a period outside a хоноруван
   преподавател's availability, or a week already at its even-spread ceiling — is accepted and then flagged,
   with a red ring on the cards and the reasons under the Session panel's verification badge. The
   solver's own figures above it keep describing the *run*, not the edited grid, and a moved card
   keeps the preference flags it was given. Generate is the reset: hand edits do not survive it.
7. **Tinker** — the *Settings* button on the Generate tab opens the solver settings dialog.
   - **Stop at first solution.** Returns a legal-but-bad timetable instead of the optimum. On the
     small example: **FEASIBLE at penalty 1933** in ~15 s, against **OPTIMAL at 540** in ~25 s.
   - **Priority.** The small example is built around this. проф. Стоянов, доц. Ковачева and
     гл. ас. Илиев all teach 1 курс and all three want the same two morning periods, `mon-1` and
     `wed-1`; the поток cannot be in two places at once, so exactly two of them can be satisfied.
     The ladder gives them to the проф. and the доц., and the гл. ас. pays for all 54 of his
     sessions. Open *Data setup → Teachers*, give гл. ас. Илиев a *Priority weight* above 7 and
     re-generate: the ladder reorders and the проф. is the one who pays. The ladder panel on the
     Generate tab shows each rank in turn and what it had to give up.
   - **Availability.** Narrow хон. преп. Радева's availability from five periods to one. Unlike a
     preference this is hard, so the problem does not get more expensive — it becomes `INFEASIBLE`
     and the hint names her.
   - **Gap weight** is deliberately *not* a demonstration any more — see the table below for why.
8. Every successful solve is **re-checked independently** of the model (`validate_assignments`) and the
   result shown as *All hard rules verified*. That badge is what makes "the solver produced a valid
   timetable" a claim you can check rather than trust — and once a session is moved by hand, the
   frontend re-runs the same rules and the badge starts reporting the grid instead of the run.

---

## Solver settings

The **Solver settings** dialog — opened from the *Settings* button on the Generate tab — exposes the
knobs, in two accordions. Every label carries a `?` with a
plain-language explanation on hover or keyboard focus — no CP-SAT vocabulary required to use it.

**A · Objective** (open by default) — these change *which* timetable comes back:

| Setting | Effect on the seed dataset |
|---|---|
| Time limit | **Default Unlimited.** The solver runs until it finishes or proves optimality, so it always comes back with the best timetable it found. A budget short enough to feel like a demo is the trap: the full seed needs ~90 s just to find its *first* legal timetable, and a 30 s cap returns `UNKNOWN` with nothing placed. Set one when you need an answer at a fixed moment — the request stays open for the whole run either way. |
| Teacher preference weight (default 10) | Cost of a session outside a teacher's preferred periods. It trades against the room weight *within* a rank; it cannot trade across ranks. |
| Room preference weight (default 5) | Cost per place down a teacher's ranked room list, scored per room type. Below the period weight, so when both cannot be met the period is the one kept. |
| Gap weight (default 1) | **No longer a trade-off knob**, and the change is worth understanding: group gaps are the last rung of the priority ladder, so by the time they are scored every teacher rank is frozen at its best. On the small example the gap rung still has enough freedom left to reach **zero gaps**, and raising the weight from 1 to 10 gives the same answer — the objective is identical at **540** either way. It cannot buy a compact day at the price of a preference, because by then there is nothing left to trade against. Set it to `0` to stop reporting gaps. |
| Stop at first solution | Collapses the ladder to one un-optimised solve. On the small example: **FEASIBLE at penalty 1933** (186 preference misses, 20 room cost, 53 gaps) in **~15 s**, against **OPTIMAL at 540** in **~25 s**. The clearest demonstration of what optimising buys. |

**B · Search** (collapsed by default) — same answer, different amount of work:

| Setting | Effect on the seed dataset |
|---|---|
| Parallel workers (default 8) | On the small example, 8 workers prove the optimum (540) in ~27 s and 1 worker takes ~42 s to reach the same answer. Set it to 1 for reproducible runs — with a fixed seed the same problem returns the same timetable, which a test asserts. |
| Random seed | Only meaningful with a single worker; changes which of several equally optimal timetables you get. |
| Presolve (default on) | Now that a semester is thousands of sessions, presolve pays for itself: the small example reaches the same optimum in ~27 s with it and ~47 s without. |
| Symmetry detection | Left unset by default, and forced to `0` inside the ladder: CP-SAT's symmetry presolve fixes literals in each orbit, which turns the previous rung's solution hint from "complete and feasible" into "infeasible, we will try to repair it" — and on a hard instance the hint matters far more. |
| Arithmetic reasoning | CP-SAT's linearization level. |
| Our own symmetry shortcut | Our hand-written constraint forcing a series' sessions into period order. It does double duty: together with even spread it pins session *k* to a narrow band of weeks, which is applied when the variables are built. Turning it off reaches the same optimum on the small seed and costs a much larger model — the tab lets you measure it. |

Settings are sent with every solve and echoed back as `settingsUsed`, so the Generate tab always
describes a result by the settings it was actually produced with — not by whatever is on screen now.
Server side they are a typed Pydantic model (`SearchParams` in `solver/app/models.py`), which *is*
the whitelist: there is no passthrough of arbitrary solver proto fields.

## The model

**Decision variables.** A `SubjectOffering` carries a **хорариум** — hours, not sessions. `30/15`
means 30 лекционни and 15 упражнителни часа, and `sessions.build_series` turns that into *series* of
interchangeable sessions: one series for the offering's лекции (attended by the whole **поток**) and
one **per unit** for its упражнения, because the хорариум is what one student is owed rather than
what the катедра delivers once. Each session lands on a real dated period.

One boolean per `(session, period, room, teacher)` quadruple:

```
x[s, t, r, k] == 1   <=>   session s runs in period t, in room r, taught by k
```

The set is **pruned at construction** — a room only gets variables for a session if its type is one
the *activity* accepts and its capacity covers the audience, and a teacher only gets one for a period
inside their hard availability. Three hard constraints are therefore structural rather than posted.

Carrying the teacher in the variable index is what makes the pool work: the session's "happens
exactly once" constraint already ranges over teacher-tagged literals, so **"exactly one teacher out
of the pool" needs no constraint of its own**. A лекция has a single **водещ преподавател**, which is
simply a pool of one, so the same machinery covers both.

**The teaching day.** A period is a block of two academic hours, and it is the atomic unit — there is
no finer thing to place. Six of them make the twelve academic hours a учебен план counts in. The
**обедна почивка needs no representation at all**: it is the 13:00→13:45 gap the period times leave
between period 3 and period 4, and nothing can be scheduled across it because no period covers it. A
faculty whose lunch falls elsewhere moves its period times; there is no rule to edit.

**Hard constraints**

| Requirement | Encoding |
|---|---|
| Each series scheduled exactly its хорариум | `AddExactlyOne` per session instance |
| Exactly one teacher per session, drawn from the pool | implied by the same `AddExactlyOne` — no separate constraint |
| No teacher teaches two sessions in one period | `AddAtMostOne` per (teacher, period) |
| No група attends two sessions in one period, and a група-level session excludes every подгрупа of it | `AddAtMostOne` per (група, period, подгрупа) |
| No подгрупа attends two sessions in one period | `AddAtMostOne` per (подгрупа, period) |
| A room hosts at most `maxConcurrentGroups` sessions in one period | `AddAtMostOne`, or a counting constraint above 1 |
| Room type is one the activity accepts | structural (pruned variables) |
| Room capacity ≥ the audience — подгрупа size for a подгрупа session, the whole поток for a лекция | structural (pruned variables) |
| A teacher is only scheduled inside their `hardAvailability` | structural (pruned variables) |
| Even weekly spread | floor/ceil per ISO week, per series |
| No група exceeds its курс's `maxPeriodsPerDay` | counting constraint over the group's busy literals |
| No teacher exceeds `maxWeeklyPeriods` | counting constraint per (teacher, ISO week) |

**Групи, подгрупи and потоци.** Two rules pull against each other, and the second is the whole point
of splitting a група: a **група-level session excludes every подгрупа of that група**, but **two
подгрупи of one група may be taught at the same time** — гр. 1а at стрелбището while гр. 1б is in АЕ.
A single `AtMostOne` over "everything the група could be doing" would satisfy the first and break the
second, so the constraint is posted once per (група, period, подгрупа) instead. A подгрупа session
still busies its parent група for the daily cap and for the gap objective, where two подгрупи side by
side cost the група one period of its day rather than two.

A **поток** is `SubjectOffering.streamGroupIds` — a join, not an attribute of the курс, because
общообразователните дисциплини merge групи across специалности and специалните do not.

**The calendar.** A timetable is generated for one **semester**, and one solve covers *every* курс in
it: rooms and teachers are shared, and solving курсове one at a time would double-book both. The
dates live on the `CourseInstance`, not on the група — a курс on **стаж** in November runs a
different calendar from its neighbours, which is exactly why they moved up. Non-teaching stretches are
typed (ваканция, стаж, изпитна сесия, празник); all four are equally unusable for teaching, and they
are kept apart so the разписание can print them and section II can count each изпитна сесия
separately.

Sessions may only use dates on which **every** група of the session is in term: the intersection,
because a поток session busies all of them at once.

**Spread.** `whole` and `range` distribute a series across the teaching weeks of its window, every
week carrying between `floor(N/W)` and `ceil(N/W)` sessions. **`block`** does not, and that is what
задочната форма needs: a whole semester compressed into a two- or three-week присъствен период has no
even spread to find, so the window is saturated instead — no weekly floor, no ceiling, and no
week-band pruning either, since that pruning is only sound while the ceiling is one.

That pruning is worth understanding, because it is what makes a semester affordable: together with
even spread and symmetry breaking it pins session *k* of a series to a narrow band of weeks, applied
when the variables are built rather than only as a constraint. It also means a хорариум should divide
by its **курс's own** teaching weeks — a курс on стаж teaches sixteen weeks, and a хорариум sized for
eighteen asks for two sessions in some week, which widens every band and multiplies the model.
`shared/generate_seed.py` sizes hours per курс for exactly that reason.

**Soft constraints, and the priority ladder**

Unchanged by the restructure, and still the interesting part. Teachers carry an academic rank
(`role`), and rank decides who wins a contested period or room. This is **not** a weighted trade-off:
the solver optimises one rank at a time, highest first, and freezes each rank's result before the
next one bargains. A професор's preference is never sold to satisfy any number of асистенти — a
guarantee no choice of weights can express.

- **Rank → tier.** Ranks are **data, not code**: a request carries a `roles` array of
  `{id, name, short, weight}`, edited under *Data setup → Roles*. The weights are *tier keys, not
  multipliers*: only their ordering and which ranks share a value matter. `priorityWeight` on a
  teacher overrides their rank's weight. A teacher with no rank shares the bottom tier, so a problem
  with no roles at all behaves exactly as it did before the ladder existed. A request that omits
  `roles` falls back to the seven ranks in `DEFAULT_ROLES`.
- **Period preference:** a session outside its teacher's `preferredSlots` costs
  `preferenceWeight = 10`. The keys are weekday-keyed (`mon-1`), so a preference means that period
  *every* week. Because
  *which* teacher is itself a decision, the penalty is a property of the literal, not of the session.
- **Room preference:** `preferredRooms` is **ranked** — first choice free, each place further down
  costs `roomPreferenceWeight = 5` again, and a room not on the list costs one step worse than the
  last named choice. Ranking is scored **per room type**, so ranking two полигона says nothing about
  which стрелбище you get.
- **Group day-gaps:** a free period with teaching on both sides of it, in the same група's day, costs
  `gapWeight = 1`. This is the **last rung**, after every teacher rank — so `gapWeight` can no longer
  buy a compact day at the price of a teacher preference.

**Hard availability is the line between a preference and a constraint.** `preferredSlots` is bought
and sold by the objective; `hardAvailability` is not available at any price, because a хоноруван
преподавател genuinely cannot be in the building. When it cannot be met the answer is `INFEASIBLE`
with a name attached, not an expensive timetable.

**Search.** The ladder runs as a sequence of solves against one model: a warm-up with no objective at
all, then one phase per rank, then gaps. Each phase sets its own objective and freezes the result
with `Add(expr <= achieved)` before the next begins — a bound taken from a solution that demonstrably
exists, so the model can never be made infeasible by its own ladder.

The warm-up is deliberately **not** rationed: a run has to *have* a timetable before optimising one
means anything. Each rung then gets an even share of what is left, floored at the warm-up's own
measured cost. When the remaining budget cannot afford another real rung the ladder stops there,
which starves the *junior* ranks: the right way round. Rungs that never ran are reported as
`NOT REACHED` rather than passed off as satisfied.

On the full seed, finding a first timetable takes a minute or two; the small example finishes the
whole ladder in about twenty-five seconds.

`maxTimeInSeconds` **defaults to `null` — no deadline at all** — and has no ceiling either. The
Settings dialog offers 10 s / 30 s / 2 min / 20 min presets and a free-form box for when a fixed
answer time matters more than a good answer. The default is unlimited because the alternative is
worse: a budget that expires before the warm-up finds anything returns `UNKNOWN` with nothing
placed, and a slow timetable beats no timetable. The cost is real and deliberate — the HTTP request
stays open for the whole run, holding a worker, and nothing short of restarting the service will
stop it.

**Infeasibility.** CP-SAT says *infeasible*; it does not say *why*. `solver/app/diagnostics.py` runs
cheap counting checks and reports the over-subscribed resource: an offering no room can hold, a група
with more sessions than its курс has periods for, total sessions vs total room-periods, and — for
rooms and teachers — Hall's condition over the type-sets and candidate pools that actually appear in
the data. Teacher supply counts **availability windows and weekly caps**, so a хоноруван
преподавател with six periods a week is not credited with the whole calendar. These are necessary
conditions only — when none fires, the response says so instead of inventing a reason.

**The разписание.** `POST /razpisanie` takes a problem and the answer that came back and returns the
document the faculty actually issues, one per `CourseInstance`: approval header, numbered
дисциплини with хорариум and зали, разпределение на учебното време, изпитни дати, then a month grid
whose cells carry the subject's number and its activity marker. It never re-solves — it is a view of
a `SolveResponse` that already exists. Membership is decided by **attendance**, not ownership, so a
merged общообразователна лекция appears on the разписание of every курс in its поток.

---

## What this tests

That CP-SAT can express the hard/soft constraint structure of a real Bulgarian academy timetable —
поток лекции, per-подгрупа упражнения, a six-day week, hard availability for external staff,
задочна форма — solve it at faculty scale, and fail *informatively* rather than hanging.

What it does **not** cover:

- **No co-teaching** — an offering's `exerciseTeacherIds` is a pool of candidates, exactly one of
  whom takes each session. There is no way to say "both of these instructors attend together".
- **No cross-semester optimisation** — semesters are generated one at a time and stored separately;
  the solver never balances one term against another. A група belongs to one `CourseInstance`, so a
  cohort continuing into the next semester is new rows rather than a second entry on the same one.
  Both seeds ship the two semesters of 2025/2026, so this is something to look at rather than take
  on trust: the same 1 курс, twice, sharing every преподавател and every зала and nothing else.
- **No room adjacency, travel time, or building constraints** — a курс can be sent from the стрелбище
  to a зала in consecutive periods with no allowance for the walk.
- **No teacher day-compaction** — gaps are penalised for групи only. A преподавател with a
  first-period and a last-period session and nothing between them pays nothing for it.
- **No session longer than one period** — a session occupies exactly one period, and
  `hoursPerSession` only sets the divisor that turns a хорариум into a count. A four-hour полигон
  block spanning two consecutive periods cannot be expressed.
- **"Never a single academic hour" is a data convention, not a model rule** — a period is two
  academic hours because the period times say so. Define a 45-minute period and the solver will
  happily schedule single hours into it.
- **No persistence** — state lives in the browser and is POSTed in full on every solve. A reload
  loses the problem.

---

## Layout

```
solver/app/timetable_solver.py   the CP-SAT model + independent output validator
solver/app/sessions.py           хорариум -> session series
solver/app/diagnostics.py        reference checks and infeasibility hints
solver/app/razpisanie.py         the printed document, and its HTML
solver/app/models.py             the whole wire format
solver/app/main.py               FastAPI (/health, /solve, /solve/stream, /razpisanie)
solver/tests/test_solver.py      feasibility, validity, infeasibility, the ladder
solver/tests/test_periods.py     the teaching day, обедна почивка, Saturday, the daily cap
solver/tests/test_hierarchy.py   групи, подгрупи and потоци
solver/tests/test_teachers.py    hard availability, weekly caps, водещ преподавател
solver/tests/test_spread.py      whole / range / block
solver/tests/test_razpisanie.py  the document agrees with the timetable
solver/tests/test_semesters.py   two semesters in one file, one per solve
shared/seed-small.json           the small example — also the default test fixture
shared/seed-full.json            the full faculty example
shared/generate_seed.py          regenerates the full one (YEARS / N_PPOOR / N_GP knobs)
MIGRATION.md                     every field renamed, moved or dropped in the restructure
frontend/src/                    React UI (Data setup / Generate / Timetable / Разписание)
frontend/src/styles/ds/          design tokens vendored from the Claude Design project
```

### A note on the seed data

Both datasets model **Факултет "Полиция"** at the **Академия на МВР** (Sofia) across both semesters
of 2025/2026 — the small one a single курс, the full one all four курса plus a задочен. Be clear about which parts are researched
and which are modelled:

**From the Academy's own published material:**
- It has two faculties — Факултет "Полиция" and Факултет "Пожарна безопасност и защита на
  населението". Only the first is modelled here.
- Факултет "Полиция" comprises five катедри: Публичноправни науки; Наказателноправни науки; Опазване
  на обществения ред и граничен контрол; Оперативно-издирвателна дейност; Специална полицейска
  тактика. These are the instructors' departments.
- Cadets are admitted to three bachelor specialties — "Противодействие на престъпността и опазване на
  обществения ред", "Гранична полиция" and "Пожарна и аварийна безопасност". The first two belong to
  Факултет "Полиция" and appear here; the third belongs to ПБЗН and does not.
- The academic ranks used (проф. д-р, доц. д-р, гл. ас. д-р, ас., ст. преп., преп., хон. преп.).

**Modelled, not cited:**
- **Group sizes.** The Academy does not publish enrolment figures, and none were reachable. Groups
  are the standard Bulgarian учебна група of ~25, with lectures delivered to the whole поток — about
  500 cadets across the faculty. Plausible, but a model rather than a number to quote.
- **The учебен план.** Subject names come from the real subject areas of the катедри; which year
  each falls in, and the хорариум attached to it, are reasonable approximations — учебните планове
  are not public. The same goes for which дисциплини are общообразователни (and so merge both
  специалности into one поток) and which are специални.
- **The подгрупи.** Splitting a група in half for стрелкова подготовка and ЛЗФП, and by level for
  чуждоезиково обучение, is how such training is organised; the exact split sizes are chosen, not
  cited.
- **The стаж and the задочен курс.** A November стаж for четвъртокурсниците and a three-week
  присъствен период for the задочна форма are plausible shapes, included because they are what
  per-курс calendars and `spread: block` exist for.
- **Instructor names** are generic Bulgarian surnames, not Academy staff. Naming real employees in a
  demo dataset would be a privacy problem for no benefit.
- **Room inventory.** Аудитории, учебни зали, компютърни зали, криминалистична лаборатория,
  физкултурен салон, тренажорна зала, стрелбища and полигони are the kinds of facilities such an
  academy has; the counts and capacities are chosen so the problem is solvable, not taken from a
  floor plan. The room vocabulary has no *лаборатория*, so the криминалистична лаборатория is
  carried as a компютърна зала — see MIGRATION.md.
- **The clock times.** Six 90-minute periods between 08:00 and 18:45 — twelve academic hours,
  taught two at a time — with the обедна почивка as the 13:00–13:45 gap, is the shape of the
  academy's day; the exact minute boundaries are chosen to fit it.

Sources: [Академия на МВР](https://www.mvr.bg/academy) ·
[Факултет "Полиция" — академичен състав](https://www.mvr.bg/academy/академията/факултет-полиция/академичен-състав) ·
[Прием курсанти и студенти](https://www.mvr.bg/academy/прием/учебна-дейност/прием-курсанти-и-студенти)
