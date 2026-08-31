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


teachers = [{"id": f"t{i+1}", "name": n, "department": d, "preferredSlots": prefs(i)}
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
                           "size": 25, "programme": f"{label}, {year} курс"})
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
    subjects.append({"id": f"s{len(subjects)+1}", "name": name,
                     "allowedRoomTypes": rtypes, "sessionsPerWeek": per_week,
                     "teacherIds": teacher_ids, "groupIds": group_ids})

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
    ("teachers", teachers), ("rooms", rooms), ("groups", groups), ("subjects", subjects),
])
out = os.environ.get(
    "OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed-full.json")
)
open(out, "w").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

sessions = sum(s["sessionsPerWeek"] for s in subjects)
per_group = collections.Counter()
for s in subjects:
    for g in s["groupIds"]:
        per_group[g] += s["sessionsPerWeek"]
print(f"teachers={len(teachers)} rooms={len(rooms)} groups={len(groups)} subjects={len(subjects)}")
print(f"sessions/week={sessions}  slots={len(SLOTS)}")
print(f"group load: min={min(per_group.values())} max={max(per_group.values())}")
