"""Regenerates shared/seed-full.json: Факултет "Полиция", Академия на МВР.

Kept in the repo because the dataset is generated, not hand-written -- 158
subjects across four years is not something to edit by hand. Knobs:

    YEARS=4 N_PPOOR=3 N_GP=2 python3 shared/generate_seed.py

Fewer years or fewer groups makes a materially easier instance if you want the
demo to prove optimality quickly rather than return a good FEASIBLE schedule.
The small example (shared/seed-small.json) is hand-written, not generated.
See the README for what in here is researched fact and what is modelled.
"""
import json, collections, os, sys

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIOD_TIMES = ["08:00-09:30", "09:45-11:15", "11:30-13:00",
                "13:45-15:15", "15:30-17:00", "17:15-18:45"]
PERIODS = len(PERIOD_TIMES)
SLOTS = [f"{d.lower()}-{p}" for d in DAYS for p in range(1, PERIODS + 1)]

# ---- катедри (real, from the faculty's own staff listing) -------------------
K_PUB   = 'катедра "Публичноправни науки"'
K_NAK   = 'катедра "Наказателноправни науки"'
K_OORGK = 'катедра "Опазване на обществения ред и граничен контрол"'
K_OID   = 'катедра "Оперативно-издирвателна дейност"'
K_SPT   = 'катедра "Специална полицейска тактика"'

# ---- instructors: generic Bulgarian surnames, realistic ranks --------------
TEACHERS = [
    ("проф. д-р Стоянов",    K_PUB),   ("доц. д-р Ковачева",   K_PUB),
    ("гл. ас. д-р Тодоров",  K_PUB),   ("ас. Маринов",         K_PUB),
    ("проф. д-р Влахов",     K_NAK),   ("доц. д-р Ангелова",   K_NAK),
    ("доц. д-р Първанов",    K_NAK),   ("гл. ас. д-р Илиев",   K_NAK),
    ("гл. ас. д-р Русева",   K_NAK),   ("ас. Данаилов",        K_NAK),
    ("проф. д-р Митев",      K_OORGK), ("доц. д-р Събева",     K_OORGK),
    ("гл. ас. д-р Кирилов",  K_OORGK), ("гл. ас. д-р Хаджиев", K_OORGK),
    ("ст. преп. Балабанов",  K_OORGK), ("ас. Германова",       K_OORGK),
    ("проф. д-р Драганов",   K_OID),   ("доц. д-р Керемидчиев",K_OID),
    ("доц. д-р Николова",    K_OID),   ("гл. ас. д-р Апостолов",K_OID),
    ("гл. ас. д-р Вълчев",   K_OID),   ("ас. Захариева",       K_OID),
    ("доц. д-р Шопов",       K_SPT),   ("гл. ас. д-р Гьошев",  K_SPT),
    ("ст. преп. Бонев",      K_SPT),   ("ст. преп. Тошева",    K_SPT),
    ("ст. преп. Джамбазов",  K_SPT),   ("ас. Райков",          K_SPT),
    ("ст. преп. Оруш",       K_SPT),   ("ст. преп. Личев",     K_SPT),
]

# ---- academic rank, read off the name --------------------------------------
# The ranks were always in the names; this is what turns them into a field the
# solver can order teachers by. Longest prefix first: "гл. ас. д-р" also ends in
# "ас.", and matching that first would demote every chief assistant.
# One table drives three things: matching a rank off an instructor's name, the
# `roles` array the seed ships, and the weights the priority ladder runs in.
# (prefix, id, full label, weight) -- weight is a tier key, so only the ordering
# and which ranks share a value matter.
RANKS = [
    ("проф.",     "professor",           "проф. — Professor",         6),
    ("доц.",      "associate_professor", "доц. — Assoc. Professor",   5),
    ("гл. ас.",   "chief_assistant",     "гл. ас. — Chief Assistant", 4),
    ("ст. преп.", "senior_lecturer",     "ст. преп. — Senior Lecturer", 3),
    ("преп.",     "lecturer",            "преп. — Lecturer",          2),
    ("ас.",       "assistant",           "ас. — Assistant",           1),
]

roles = [{"id": rid, "name": name, "short": prefix, "weight": w}
         for prefix, rid, name, w in RANKS]

def role_of(name):
    """Longest prefix first: "гл. ас. д-р" also ends in "ас.", and matching that
    first would demote every chief assistant."""
    for prefix, rid, _label, _w in sorted(RANKS, key=lambda r: -len(r[0])):
        if name.startswith(prefix):
            return rid
    raise ValueError(f"no rank prefix in {name!r}")


# ---- ranked room preferences ------------------------------------------------
# Index 0 is the room the instructor most wants. Everyone in a катедра ranks the
# same rooms in the same order on purpose: that is what makes them collide, and a
# collision is the only thing that can show rank deciding an outcome. The SPT
# staff are the sharpest case -- six of them, ranks from доц. down to ас., all
# wanting Полигон за специална тактика first, and only one полигон.
DEPT_ROOM_RANKING = {
    K_PUB:   ["r1", "r2", "r3"],
    K_NAK:   ["r1", "r3", "r2"],
    K_OORGK: ["r2", "r3", "r1"],
    K_OID:   ["r16", "r13", "r14", "r15"],
    K_SPT:   ["r21", "r22", "r19", "r20", "r18", "r17"],
}

# Preferred slots per instructor: deliberately narrow for some, so the soft
# constraints have something to trade. Pattern varies by index.
def prefs(i):
    """Preferred slots per instructor.

    Deliberately shaped so the tension is *local* rather than global: the
    Специална полицейска тактика staff prefer mornings while their sessions
    compete for two ranges and two полигона, which forces a handful of
    unavoidable misses. Everyone else is given a wide preference, because a
    dataset where every instructor is constrained is one CP-SAT cannot optimise
    while somebody watches -- and a timetable with zero soft penalty shows
    nothing at all.
    """
    if TEACHERS[i][1] == K_SPT:
        return [f"{d.lower()}-{p}" for d in DAYS for p in (1, 2)]
    return [f"{d.lower()}-{p}" for d in DAYS for p in (1, 2, 3, 4)]


teachers = [{"id": f"t{i+1}", "name": n, "department": d, "role": role_of(n),
             "preferredSlots": prefs(i), "preferredRooms": DEPT_ROOM_RANKING[d]}
            for i, (n, d) in enumerate(TEACHERS)]
by_dept = collections.defaultdict(list)
for t, (_n, d) in zip(teachers, TEACHERS):
    by_dept[d].append(t["id"])

# ---- rooms -----------------------------------------------------------------
rooms = []
def room(name, rtype, cap, building):
    rooms.append({"id": f"r{len(rooms)+1}", "name": name, "type": rtype,
                  "capacity": cap, "building": building})

for n, cap in [("Аудитория 1", 150), ("Аудитория 2", 120),
               ("Аудитория 3", 100), ("Аудитория 4", 80)]:
    room(n, "lecture", cap, "Учебен корпус, ет. 1")
for i in range(1, 9):
    room(f"Учебна зала {200+i}", "lecture", 30, "Учебен корпус, ет. 2")
for i in range(1, 4):
    room(f"Компютърна зала {i}", "lab", 25, "Учебен корпус, ет. 3")
room("Криминалистична лаборатория", "lab", 25, "Учебен корпус, ет. 3")
room("Физкултурен салон", "sports", 60, "Спортен комплекс")
room("Зала бойни спортове", "sports", 60, "Спортен комплекс")
room("Стрелбище – закрито", "firing_range", 30, "Стрелкови комплекс")
room("Стрелбище – открито", "firing_range", 30, "Стрелкови комплекс")
room("Полигон за специална тактика", "training_ground", 40, "Учебен полигон")
room("Тренировъчен град", "training_ground", 40, "Учебен полигон")

# ---- academic calendar -----------------------------------------------------
# Two semesters a year, September to before summer, with the winter break and a
# spring break carved out. Future years are here so the UI has something to show
# for "add dates for 2026/2027" without inventing them by hand.
import datetime as _dt

ACADEMIC_YEARS = {
    "2025/2026": [
        (1, "2025-09-15", "2026-01-30", [("2025-12-22", "2026-01-04", "Коледна ваканция")]),
        (2, "2026-02-09", "2026-06-12", [("2026-04-10", "2026-04-17", "Пролетна ваканция")]),
    ],
    "2026/2027": [
        (1, "2026-09-14", "2027-01-29", [("2026-12-21", "2027-01-03", "Коледна ваканция")]),
        (2, "2027-02-08", "2027-06-11", [("2027-04-02", "2027-04-09", "Пролетна ваканция")]),
    ],
}

def semesters_for_group():
    return [
        {"academicYear": year, "index": idx, "start": start, "end": end,
         "breaks": [{"start": b0, "end": b1, "label": lab} for b0, b1, lab in brk]}
        for year, entries in ACADEMIC_YEARS.items()
        for idx, start, end, brk in entries
    ]

def teaching_weeks(year, idx):
    """ISO weeks that carry at least one Mon-Fri teaching day, breaks excluded."""
    _i, start, end, brk = next(e for e in ACADEMIC_YEARS[year] if e[0] == idx)
    start, end = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
    holidays = [(_dt.date.fromisoformat(a), _dt.date.fromisoformat(b)) for a, b, _l in brk]
    weeks, day = set(), start
    while day <= end:
        if day.weekday() < 5 and not any(a <= day <= b for a, b in holidays):
            weeks.add(day.isocalendar()[:2])
        day += _dt.timedelta(days=1)
    return len(weeks)

# The seed schedules the first semester of 2025/2026; the rest exist so the
# semester picker and the "future year" case have real data behind them.
SEED_YEAR, SEED_INDEX = "2025/2026", 1
WEEKS = teaching_weeks(SEED_YEAR, SEED_INDEX)

# ---- groups: 4 курса x (ППООР 3 групи, ГП 2 групи) -------------------------
groups, cohorts = [], []
YEARS = int(os.environ.get("YEARS", "4"))
N_PPOOR = int(os.environ.get("N_PPOOR", "3"))
N_GP = int(os.environ.get("N_GP", "2"))
for year in range(1, YEARS + 1):
    for spec, label, n_groups in (("ППООР", "Противодействие на престъпността и опазване на обществения ред", N_PPOOR),
                                  ("ГП", "Гранична полиция", N_GP)):
        ids = []
        for g in range(1, n_groups + 1):
            gid = f"g{len(groups)+1}"
            groups.append({"id": gid, "name": f"{year} курс {spec} – гр. {g}",
                           "size": 25, "programme": f"{label}, {year} курс",
                           "semesters": semesters_for_group()})
            ids.append(gid)
        cohorts.append({"year": year, "spec": spec, "groupIds": ids})

# ---- subjects: лекции for the whole поток + семинари per group -------------
# (name, катедра, лекции/седмица, семинари/седмица, room types for the seminar)
CURRICULUM = {
    1: [("Обща теория на правото",        K_PUB,   1, 1, ["lecture"]),
        ("Конституционно право",          K_PUB,   1, 1, ["lecture"]),
        ("Наказателно право (обща част)",  K_NAK,   2, 1, ["lecture"]),
        ("Полицейска психология",          K_OORGK, 1, 1, ["lecture"]),
        ("Информационни технологии",       K_OID,   1, 1, ["lab"]),
        ("Физическа подготовка",           K_SPT,   0, 2, ["sports", "training_ground"])],
    2: [("Административно право и процес", K_PUB,   1, 1, ["lecture"]),
        ("Наказателно право (особена част)",K_NAK,  1, 1, ["lecture"]),
        ("Наказателен процес",             K_NAK,   1, 1, ["lecture"]),
        ("Криминалистика",                 K_NAK,   1, 1, ["lab"]),
        ("Оперативно-издирвателна дейност",K_OID,   1, 1, ["lecture"]),
        ("Огнева подготовка",              K_SPT,   0, 1, ["firing_range"]),
        ("Специална полицейска тактика",   K_SPT,   0, 1, ["training_ground", "sports"])],
    3: [("Криминология",                   K_NAK,   1, 1, ["lecture"]),
        ("Разследване на престъпления",    K_NAK,   1, 1, ["lab"]),
        ("Опазване на обществения ред",    K_OORGK, 1, 1, ["lecture"]),
        ("Гранично-полицейска дейност",    K_OORGK, 1, 1, ["lecture"]),
        ("Оперативно документиране",       K_OID,   1, 1, ["lab"]),
        ("Огнева подготовка",              K_SPT,   0, 1, ["firing_range"]),
        ("Специализирана полицейска тактика", K_SPT,0, 1, ["training_ground"])],
    4: [("Противодействие на тероризма",   K_OORGK, 1, 1, ["lecture"]),
        ("Противодействие на киберпрестъпността", K_OID, 1, 1, ["lab"]),
        ("Управление на полицейската дейност", K_PUB, 1, 1, ["lecture"]),
        ("Международно полицейско сътрудничество", K_PUB, 1, 0, ["lecture"]),
        ("Практическа подготовка",         K_SPT,   0, 2, ["training_ground", "sports"])],
}

subjects = []
def subject(name, rtypes, per_week, teacher_ids, group_ids):
    """Sessions are now a per-semester *total* on real dates, so the weekly rate
    the curriculum is written in becomes rate x teaching weeks."""
    subjects.append({"id": f"s{len(subjects)+1}", "name": name,
                     "allowedRoomTypes": rtypes,
                     "semesters": [{"academicYear": SEED_YEAR, "index": SEED_INDEX,
                                    "totalSessions": per_week * WEEKS,
                                    "spread": "whole",
                                    "groupIds": group_ids}],
                     "teacherIds": teacher_ids})

for c in cohorts:
    tag = f"{c['year']} к. {c['spec']}"
    for name, dept, lectures, seminars, sem_types in CURRICULUM[c["year"]]:
        pool = by_dept[dept]
        # a lecture may be taken by any two members of the department
        lecturers = pool[: 2] if len(pool) >= 2 else pool
        if lectures:
            subject(f"{name} – лекции ({tag})", ["lecture"], lectures, lecturers, c["groupIds"])
        for i, gid in enumerate(c["groupIds"]):
            if not seminars:
                continue
            tutors = [pool[(i + 2) % len(pool)]]
            gname = next(g["name"] for g in groups if g["id"] == gid).split("– ")[1]
            subject(f"{name} – упр. ({tag}, {gname})", sem_types, seminars,
                    sorted(set(tutors)), [gid])

data = collections.OrderedDict([
    ("_comment",
     "Seed dataset modelling Факултет \"Полиция\" at Академия на МВР (Sofia), all four years. "
     "Researched fact: the faculty's five катедри, the two cadet specialties it teaches (ППООР and "
     "Гранична полиция), and the academic ranks. Modelled, not cited: group sizes (standard "
     "Bulgarian учебна група of ~25 -- the Academy does not publish enrolment), the distribution of "
     "subjects across the four years, and the instructor names, which are generic Bulgarian "
     "surnames rather than real staff. Lectures are delivered to the whole поток (a multi-group "
     "subject needing a large аудитория); семинарни занятия run per group."),
    ("slotConfig", {"days": DAYS, "periods": PERIODS, "periodTimes": PERIOD_TIMES, "blockedSlots": []}),
    ("roles", roles), ("teachers", teachers), ("rooms", rooms), ("groups", groups), ("subjects", subjects),
])
out = os.environ.get(
    "OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed-full.json")
)
open(out, "w").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

# The rankings above hardcode room ids, which are positional. Catch a drift here
# rather than shipping a seed whose preferences point at the wrong rooms.
_room_ids = {r["id"] for r in rooms}
for _dept, _ranked in DEPT_ROOM_RANKING.items():
    missing = [r for r in _ranked if r not in _room_ids]
    assert not missing, f"{_dept} ranks unknown room(s) {missing}"

def _total(s):
    return sum(x["totalSessions"] for x in s["semesters"])

sessions = sum(_total(s) for s in subjects)
per_group = collections.Counter()
for s in subjects:
    for x in s["semesters"]:
        for g in x["groupIds"]:
            per_group[g] += x["totalSessions"]
print(f"teachers={len(teachers)} rooms={len(rooms)} groups={len(groups)} subjects={len(subjects)}")
print(f"semester={SEED_YEAR} S{SEED_INDEX}  teaching weeks={WEEKS}")
print(f"sessions/semester={sessions}  weekday-periods={len(SLOTS)}")
print(f"group load: min={min(per_group.values())} max={max(per_group.values())}")
