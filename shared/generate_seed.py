"""Regenerates shared/seed-full.json: Факултет "Полиция", Академия на МВР.

Both semesters of 2025/2026, generated first-semester-first so the ids of the
first semester never move when the second one changes. One solve still covers
one semester -- the second is a separate problem over the same teachers and the
same rooms, with its own курсове and its own групи.

Kept in the repo because the dataset is generated, not hand-written -- a учебен
план across four курса is not something to edit by hand. Knobs:

    YEARS=4 N_PPOOR=3 N_GP=2 python3 shared/generate_seed.py

Fewer years or fewer groups makes a materially easier instance if you want the
demo to prove optimality quickly rather than return a good FEASIBLE schedule.
The small example (shared/seed-small.json) is hand-written, not generated.
See the README for what in here is researched fact and what is modelled.
"""
import collections
import datetime as _dt
import json
import os

# ---- the teaching day ------------------------------------------------------
# Six periods of 90 minutes, each two academic hours -- so a full day is the
# twelve academic hours a учебен план counts in. The обедна почивка is the
# 13:00-13:45 gap between period 3 and period 4: a break defined by absence,
# which needs no rule because no period covers it. Saturday is a teaching day:
# курсанти have Saturday classes.
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
PERIOD_TIMES = [
    "08:00-09:30", "09:45-11:15", "11:30-13:00",
    "13:45-15:15", "15:30-17:00", "17:15-18:45",
]
PERIODS = len(PERIOD_TIMES)
HOURS_PER_SESSION = 2


def slot_keys(periods, days=DAYS):
    """Weekday-keyed slot ids -- what preferredSlots and hardAvailability hold."""
    return [f"{d.lower()}-{p}" for d in days for p in periods]


# ---- катедри (real, from the faculty's own staff listing) -------------------
K_PUB   = 'катедра "Публичноправни науки"'
K_NAK   = 'катедра "Наказателноправни науки"'
K_OORGK = 'катедра "Опазване на обществения ред и граничен контрол"'
K_OID   = 'катедра "Оперативно-издирвателна дейност"'
K_SPT   = 'катедра "Специална полицейска тактика"'
K_EZIK  = 'катедра "Езиково обучение"'

KATEDRI = [K_PUB, K_NAK, K_OORGK, K_OID, K_SPT, K_EZIK]
katedra_id = {name: f"k{i+1}" for i, name in enumerate(KATEDRI)}

faculties = [{"id": "f1", "name": 'Факултет "Полиция"'}]
katedri = [{"id": katedra_id[n], "name": n, "facultyId": "f1"} for n in KATEDRI]

# ---- instructors: generic Bulgarian surnames, realistic ranks --------------
# The хонорувани преподаватели at the end are external: they carry a HARD
# availability window rather than a preference, which is the whole point of them
# being in the dataset.
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
    ("преп. Радева",         K_EZIK),  ("преп. Донев",         K_EZIK),
    ("хон. преп. Стаменова", K_EZIK),  ("хон. преп. Захариев",  K_EZIK),
]

# ---- academic rank, read off the name --------------------------------------
# The ranks were always in the names; this is what turns them into a field the
# solver can order teachers by. Longest prefix first: "гл. ас. д-р" also ends in
# "ас.", and matching that first would demote every chief assistant; "хон. преп."
# would likewise be read as "преп.".
# One table drives three things: matching a rank off an instructor's name, the
# `roles` array the seed ships, and the weights the priority ladder runs in.
# (prefix, id, full label, weight) -- weight is a tier key, so only the ordering
# and which ranks share a value matter.
RANKS = [
    ("проф.",      "professor",           "проф. — Professor",             7),
    ("доц.",       "associate_professor", "доц. — Assoc. Professor",       6),
    ("гл. ас.",    "chief_assistant",     "гл. ас. — Chief Assistant",     5),
    ("ас.",        "assistant",           "ас. — Assistant",               4),
    ("ст. преп.",  "senior_lecturer",     "ст. преп. — Senior Lecturer",   3),
    ("преп.",      "lecturer",            "преп. — Lecturer",              2),
    ("хон. преп.", "honorary_lecturer",   "хон. преп. — Honorary Lecturer", 1),
]

roles = [{"id": rid, "name": name, "short": prefix, "weight": w}
         for prefix, rid, name, w in RANKS]


def role_of(name):
    for prefix, rid, _label, _w in sorted(RANKS, key=lambda r: -len(r[0])):
        if name.startswith(prefix):
            return rid
    raise ValueError(f"no rank prefix in {name!r}")


# ---- ranked room preferences ------------------------------------------------
# Index 0 is the room the instructor most wants. Everyone in a катедра ranks the
# same rooms in the same order on purpose: that is what makes them collide, and a
# collision is the only thing that can show rank deciding an outcome. The SPT
# staff are the sharpest case -- eight of them, ranks from доц. down to ас., all
# wanting Полигон за специална тактика first, and only one полигон.
#
# Ranked by NAME, resolved to ids below: room ids are positional, and a ranking
# written against them drifts silently the moment a room is inserted.
DEPT_ROOM_RANKING = {
    K_PUB:   ["Аудитория 1", "Учебна зала 201", "Учебна зала 202"],
    K_NAK:   ["Аудитория 1", "Учебна зала 202", "Учебна зала 201"],
    K_OORGK: ["Учебна зала 201", "Учебна зала 202", "Аудитория 1"],
    K_OID:   ["Криминалистична лаборатория", "Компютърна зала 1",
              "Компютърна зала 2", "Компютърна зала 3"],
    K_SPT:   ["Полигон за специална тактика", "Тренировъчен град",
              "Стрелбище – закрито", "Стрелбище – открито",
              "Зала бойни спортове", "Физкултурен салон"],
    K_EZIK:  ["Учебна зала 203", "Учебна зала 204"],
}

# ---- rooms -----------------------------------------------------------------
rooms = []
room_id_of = {}


def room(name, rtype, cap, building, concurrent=1):
    rid = f"r{len(rooms)+1}"
    room_id_of[name] = rid
    rooms.append({"id": rid, "name": name, "type": rtype, "capacity": cap,
                  "building": building, "maxConcurrentGroups": concurrent})


for n, cap in [("Аудитория 1", 150), ("Аудитория 2", 120),
               ("Аудитория 3", 100), ("Аудитория 4", 80)]:
    room(n, "зала", cap, "Учебен корпус, ет. 1")
for i in range(1, 9):
    room(f"Учебна зала {200+i}", "малка зала", 30, "Учебен корпус, ет. 2")
for i in range(1, 4):
    room(f"Компютърна зала {i}", "компютърна зала", 25, "Учебен корпус, ет. 3")
# Модел: the new room vocabulary has no "лаборатория", so the криминалистична
# лаборатория is carried as a компютърна зала -- an equipped specialist room of
# the same size. Recorded as lossy in MIGRATION.md.
room("Криминалистична лаборатория", "компютърна зала", 25, "Учебен корпус, ет. 3")
room("Физкултурен салон", "спортен комплекс", 60, "Спортен комплекс")
room("Зала бойни спортове", "спортен комплекс", 60, "Спортен комплекс")
room("Тренажорна зала", "тренажорна зала", 30, "Спортен комплекс")
# Едно стрелбище приема една подгрупа: a firing line takes half a group at a
# time, which is what maxConcurrentGroups=1 plus a capacity of 15 encodes.
room("Стрелбище – закрито", "стрелбище", 15, "Стрелкови комплекс")
room("Стрелбище – открито", "стрелбище", 15, "Стрелкови комплекс")
room("Полигон за специална тактика", "полигон", 40, "Учебен полигон")
room("Тренировъчен град", "полигон", 40, "Учебен полигон")

# ---- instructors, now that rooms have ids ----------------------------------
# Preferred periods are deliberately narrow for some, so the soft constraints have
# something to trade: the Специална полицейска тактика staff prefer mornings
# while their sessions compete for two стрелбища and two полигона. Everyone else
# is given a wide preference, because a dataset where every instructor is
# constrained is one CP-SAT cannot optimise while somebody watches -- and a
# timetable with zero soft penalty shows nothing at all.
EARLY = slot_keys([1, 2])
WIDE = slot_keys([1, 2, 3])
# The external lecturers come in for two days a week and no more. This is HARD:
# no rank and no weight can schedule around it.
EXTERNAL_WINDOW = slot_keys([1, 2, 3], days=["Fri", "Sat"])

teachers = []
for i, (name, dept) in enumerate(TEACHERS):
    rank = role_of(name)
    external = rank == "honorary_lecturer"
    teachers.append({
        "id": f"t{i+1}",
        "name": name,
        "katedraId": katedra_id[dept],
        "role": rank,
        "preferredSlots": [] if external else (EARLY if dept == K_SPT else WIDE),
        "hardAvailability": EXTERNAL_WINDOW if external else [],
        "maxWeeklyPeriods": 6 if external else None,
        "preferredRooms": [room_id_of[n] for n in DEPT_ROOM_RANKING[dept]],
    })

by_dept = collections.defaultdict(list)
for t, (_n, d) in zip(teachers, TEACHERS):
    by_dept[d].append(t["id"])


# ---- academic calendar -----------------------------------------------------
# The seed schedules both semesters of 2025/2026. They are separate problems:
# one solve covers one semester, so the second one costs nothing at solve time
# and everything it exercises -- the семестър picker, one stored timetable per
# semester, a cohort continuing as a new CourseInstance -- is invisible with a
# single semester in the file.
#
# Non-teaching stretches are typed: ваканция, стаж, изпитна сесия and празник are
# all unusable for teaching, but the разписание prints them apart and section II
# counts each exam session separately. The изпитни сесии sit *after* their term by
# definition, which is why a semester declares closures outside its own dates.
SEED_YEAR = "2025/2026"

LIKVIDATSIONNA = {"start": "2026-09-01", "end": "2026-09-11", "kind": "изпитна сесия",
                  "session": "ликвидационна", "label": "Ликвидационна сесия"}

NON_TEACHING_S1 = [
    {"start": "2025-12-22", "end": "2026-01-04", "kind": "ваканция",
     "label": "Коледна ваканция"},
    {"start": "2025-12-24", "end": "2025-12-26", "kind": "празник",
     "label": "Рождество Христово"},
    {"start": "2026-02-02", "end": "2026-02-20", "kind": "изпитна сесия",
     "session": "редовна", "label": "Редовна изпитна сесия"},
    {"start": "2026-02-23", "end": "2026-03-06", "kind": "изпитна сесия",
     "session": "поправителна", "label": "Поправителна сесия"},
    LIKVIDATSIONNA,
]
# Вторият семестър starts after the поправителна сесия of the first, so the two
# terms never overlap. Великден 2026 is 12 April; the closure takes Велики петък
# through Светли понеделник, which removes days rather than a whole week.
NON_TEACHING_S2 = [
    {"start": "2026-04-10", "end": "2026-04-13", "kind": "ваканция",
     "label": "Великденска ваканция"},
    {"start": "2026-05-01", "end": "2026-05-01", "kind": "празник",
     "label": "Ден на труда"},
    {"start": "2026-05-06", "end": "2026-05-06", "kind": "празник",
     "label": "Гергьовден — Ден на храбростта"},
    # 24 May 2026 is a Sunday, so the неработен ден moves to the Monday.
    {"start": "2026-05-25", "end": "2026-05-25", "kind": "празник",
     "label": "Ден на светите братя Кирил и Методий"},
    {"start": "2026-06-29", "end": "2026-07-17", "kind": "изпитна сесия",
     "session": "редовна", "label": "Редовна изпитна сесия"},
    {"start": "2026-07-20", "end": "2026-07-31", "kind": "изпитна сесия",
     "session": "поправителна", "label": "Поправителна сесия"},
    LIKVIDATSIONNA,
]

# Четвъртокурсниците са на стаж twice: in November of the first semester and on
# преддипломен стаж in May of the second. A real reason a курс's calendar differs
# from its neighbours', which is why term dates live on CourseInstance.
STAZH_S1 = {"start": "2025-11-03", "end": "2025-11-15", "kind": "стаж",
            "label": "Учебен стаж в структурите на МВР"}
STAZH_S2 = {"start": "2026-05-04", "end": "2026-05-22", "kind": "стаж",
            "label": "Преддипломен стаж в структурите на МВР"}

# Изпитните дати of a semester sit inside its own редовна сесия.
EXAM_DATES_S1 = ["2026-02-03", "2026-02-05", "2026-02-09", "2026-02-11",
                 "2026-02-13", "2026-02-17", "2026-02-19"]
EXAM_DATES_S2 = ["2026-06-30", "2026-07-02", "2026-07-06", "2026-07-08",
                 "2026-07-10", "2026-07-14", "2026-07-16"]

# Задочна форма: a whole semester compressed into a three-week присъствен период,
# one per semester. This is what SpreadMode.block exists for.
ZADOCHNO_WINDOW_S1 = {"start": "2025-11-17", "end": "2025-12-06",
                      "label": "присъствен период"}
ZADOCHNO_WINDOW_S2 = {"start": "2026-04-20", "end": "2026-05-09",
                      "label": "присъствен период"}

SEMESTERS = {
    1: {"start": "2025-09-15", "end": "2026-01-31", "nonTeaching": NON_TEACHING_S1,
        "stazh": STAZH_S1, "exams": EXAM_DATES_S1, "window": ZADOCHNO_WINDOW_S1,
        "regDate": "08.09.2025", "approvalDate": "2025-09-08"},
    2: {"start": "2026-03-09", "end": "2026-06-27", "nonTeaching": NON_TEACHING_S2,
        "stazh": STAZH_S2, "exams": EXAM_DATES_S2, "window": ZADOCHNO_WINDOW_S2,
        "regDate": "16.02.2026", "approvalDate": "2026-02-16"},
}


def teaching_weeks(start, end, non_teaching):
    """ISO weeks that carry at least one teaching day, closures excluded."""
    start, end = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
    closed = [(_dt.date.fromisoformat(p["start"]), _dt.date.fromisoformat(p["end"]))
              for p in non_teaching]
    names = set(DAYS)
    weekday_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weeks, day = set(), start
    while day <= end:
        name = weekday_name[day.weekday()]
        if name in names and not any(a <= day <= b for a, b in closed):
            weeks.add(day.isocalendar()[:2])
        day += _dt.timedelta(days=1)
    return len(weeks)


WEEKS = {i: teaching_weeks(s["start"], s["end"], s["nonTeaching"])
         for i, s in SEMESTERS.items()}


def weeks_of(course) -> int:
    """Teaching weeks of one курс -- its own, not the faculty's.

    This matters more than it looks. A курс on стаж in November teaches sixteen
    weeks, not eighteen, and a хорариум sized for eighteen would ask for two
    sessions in some week. The even-spread constraint would still satisfy it, but
    the week-band pruning in the solver only collapses a session to a single week
    while the ceiling is one -- so a курс whose sessions do not divide by its own
    week count costs the model a multiple of its variables, and the whole instance
    stops being solvable. Sizing the хорариум to the курс keeps every series at
    one session a week, which is both what a учебен план actually says and what
    makes a faculty-wide semester tractable.
    """
    return teaching_weeks(course["start"], course["end"], course["nonTeaching"])

# ---- specialties, курсове, групи, подгрупи ---------------------------------
YEARS = int(os.environ.get("YEARS", "4"))
N_PPOOR = int(os.environ.get("N_PPOOR", "3"))
N_GP = int(os.environ.get("N_GP", "2"))

specialties = [
    {"id": "sp1", "facultyId": "f1", "code": "ППООР",
     "name": "Противодействие на престъпността и опазване на обществения ред",
     "degree": "бакалавър", "form": "редовна", "studentKind": "курсант",
     "durationYears": 4},
    {"id": "sp2", "facultyId": "f1", "code": "ГП", "name": "Гранична полиция",
     "degree": "бакалавър", "form": "редовна", "studentKind": "курсант",
     "durationYears": 4},
    # Задочна форма: a whole semester compressed into a three-week присъствен
    # period. This is what SpreadMode.block exists for -- an even weekly spread
    # over the term is simply the wrong shape here.
    {"id": "sp3", "facultyId": "f1", "code": "ППООР-З",
     "name": "Противодействие на престъпността — задочно обучение",
     "degree": "бакалавър", "form": "задочна", "studentKind": "студент",
     "durationYears": 4},
]

courses, groups, subgroups, cohorts = [], [], [], []


def add_course(spec_id, year, semester, otgovornik, extra_closures=()):
    term = SEMESTERS[semester]
    cid = f"c{len(courses)+1}"
    courses.append({
        "id": cid, "specialtyId": spec_id, "year": year,
        "academicYear": SEED_YEAR, "semester": semester,
        "start": term["start"], "end": term["end"],
        "nonTeaching": term["nonTeaching"] + list(extra_closures),
        "maxPeriodsPerDay": 6,
        "regNumber": f"рег. № {4800 + len(courses)}/{term['regDate']}",
        "approvedBy": 'ДЕКАН на факултет "Полиция"\nдоц. д-р Г. Маринов',
        "approvalDate": term["approvalDate"],
        "administrativenOtgovornik": otgovornik,
    })
    return cid


ADMINS = [t["name"] for t in teachers if t["role"] in ("chief_assistant", "senior_lecturer")]

# Семестрите се генерират последователно -- целият първи, после целият втори.
# The cohort of a курс continuing into семестър 2 is a *new* CourseInstance with
# its own група rows, because a Group belongs to exactly one CourseInstance.
for semester in sorted(SEMESTERS):
    for year in range(1, YEARS + 1):
        for spec_id, code, n_groups in (("sp1", "ППООР", N_PPOOR), ("sp2", "ГП", N_GP)):
            closures = (SEMESTERS[semester]["stazh"],) if year == 4 else ()
            cid = add_course(spec_id, year, semester,
                             ADMINS[len(courses) % len(ADMINS)], closures)
            ids = []
            for g in range(1, n_groups + 1):
                gid = f"g{len(groups)+1}"
                groups.append({"id": gid, "name": f"{year} курс {code} – гр. {g}",
                               "size": 25, "courseInstanceId": cid})
                # Стрелбището приема една подгрупа наведнъж, so every group is
                # split in half for стрелкова подготовка and ЛЗФП. The two halves
                # may be taught side by side whenever two instructors are free.
                subgroups.append({"id": f"{gid}a", "groupId": gid,
                                  "name": f"{year} к. {code} гр. {g} – подгрупа А", "size": 13})
                subgroups.append({"id": f"{gid}b", "groupId": gid,
                                  "name": f"{year} к. {code} гр. {g} – подгрупа Б", "size": 12})
                ids.append(gid)
            cohorts.append({"year": year, "semester": semester, "spec": code,
                            "courseId": cid, "groupIds": ids})

    # Задочно: one курс, two групи, no подгрупи -- the присъствен период is too
    # short to split anything.
    zad_course = add_course("sp3", 1, semester, ADMINS[0])
    zad_groups = []
    for g in range(1, 3):
        gid = f"g{len(groups)+1}"
        groups.append({"id": gid, "name": f"1 курс ППООР-З – гр. {g}", "size": 22,
                       "courseInstanceId": zad_course})
        zad_groups.append(gid)
    cohorts.append({"year": 1, "semester": semester, "spec": "ППООР-З",
                    "courseId": zad_course, "groupIds": zad_groups, "block": True})

# ---- учебен план -----------------------------------------------------------
# (code, name, катедра, лекции/седмица, упражнения/седмица, room types for the
#  упражнение, merge, audience, control form), keyed on (курс, семестър).
#
# `merge` is what makes a поток: общообразователните дисциплини merge the groups
# of both специалности into one lecture stream, специалните do not. That is the
# distinction SubjectOffering.streamGroupIds exists to express -- it is a join,
# not an attribute of the курс.
#
# Дисциплините, които продължават и през втория семестър -- Английски език,
# Стрелкова подготовка, ЛЗФП -- reuse their Subject row and get a second
# SubjectOffering. That split is the whole reason the catalogue and the offering
# are different tables.
CURRICULUM = {
    (1, 1): [("ОТП",  "Обща теория на правото",         K_PUB,   1, 0, [], True,  "group", "изпит"),
             ("КП",   "Конституционно право",           K_PUB,   1, 0, [], True,  "group", "изпит"),
             ("НПОЧ", "Наказателно право (обща част)",  K_NAK,   1, 0, [], True,  "group", "изпит"),
             ("ПП",   "Полицейска психология",          K_OORGK, 0, 1, ["малка зала"], False, "group", "КТО"),
             ("ИТ",   "Информационни технологии",       K_OID,   0, 1, ["компютърна зала"], False, "group", "КТО"),
             ("ЛЗФП", "Лична защита и физическа подготовка", K_SPT, 0, 1, ["спортен комплекс", "тренажорна зала"], False, "subgroup", "зачет"),
             ("АЕ",   "Английски език",                 K_EZIK,  0, 1, ["малка зала"], False, "group", "зачет")],
    (2, 1): [("АПП",  "Административно право и процес",  K_PUB,   1, 0, [], True,  "group", "изпит"),
             ("НПОсЧ","Наказателно право (особена част)",K_NAK,   1, 0, [], True,  "group", "изпит"),
             ("НПр",  "Наказателен процес",             K_NAK,   1, 0, [], False, "group", "изпит"),
             ("КРИМ", "Криминалистика",                 K_NAK,   0, 1, ["компютърна зала"], False, "group", "изпит"),
             ("ОИД",  "Оперативно-издирвателна дейност",K_OID,   0, 1, ["малка зала"], False, "group", "изпит"),
             ("СП",   "Стрелкова подготовка",           K_SPT,   0, 1, ["стрелбище"], False, "subgroup", "зачет"),
             ("АЕ",   "Английски език",                 K_EZIK,  0, 1, ["малка зала"], False, "group", "зачет")],
    (3, 1): [("КРМ",  "Криминология",                   K_NAK,   1, 0, [], True,  "group", "изпит"),
             ("ООР",  "Опазване на обществения ред",    K_OORGK, 1, 0, [], False, "group", "изпит"),
             ("ГПД",  "Гранично-полицейска дейност",    K_OORGK, 1, 0, [], False, "group", "изпит"),
             ("РП",   "Разследване на престъпления",    K_NAK,   0, 1, ["компютърна зала"], False, "group", "изпит"),
             ("ОД",   "Оперативно документиране",       K_OID,   0, 1, ["малка зала"], False, "group", "КТО"),
             ("СП",   "Стрелкова подготовка",           K_SPT,   0, 1, ["стрелбище"], False, "subgroup", "зачет"),
             ("СПТ2", "Специализирана полицейска тактика", K_SPT, 0, 1, ["полигон"], False, "group", "зачет")],
    (4, 1): [("ПТ",   "Противодействие на тероризма",   K_OORGK, 1, 0, [], True,  "group", "изпит"),
             ("УПД",  "Управление на полицейската дейност", K_PUB, 1, 0, [], False, "group", "изпит"),
             ("МПС",  "Международно полицейско сътрудничество", K_PUB, 1, 0, [], True, "group", "КТО"),
             ("ПКП",  "Противодействие на киберпрестъпността", K_OID, 0, 1, ["компютърна зала"], False, "group", "изпит"),
             ("ППК",  "Практическа подготовка",         K_SPT,   0, 1, ["полигон", "спортен комплекс"], False, "group", "зачет")],
    # Вторият семестър: нов учебен план, със същите продължаващи дисциплини.
    (1, 2): [("ОГП",  "Основи на гражданското право",   K_PUB,   1, 0, [], True,  "group", "изпит"),
             ("ПЕПЧ", "Полицейска етика и права на човека", K_PUB, 1, 0, [], True, "group", "КТО"),
             ("ППД",  "Превантивна полицейска дейност", K_OORGK, 0, 1, ["малка зала"], False, "group", "КТО"),
             ("СПТ1", "Специална полицейска тактика",   K_SPT,   0, 1, ["полигон"], False, "group", "зачет"),
             ("ЛЗФП", "Лична защита и физическа подготовка", K_SPT, 0, 1, ["спортен комплекс", "тренажорна зала"], False, "subgroup", "зачет"),
             ("АЕ",   "Английски език",                 K_EZIK,  0, 1, ["малка зала"], False, "group", "зачет")],
    (2, 2): [("ДПП",  "Досъдебно производство",         K_NAK,   1, 0, [], False, "group", "изпит"),
             ("АНД",  "Административно-наказателна дейност", K_PUB, 1, 0, [], True, "group", "изпит"),
             ("КРИМТ","Криминалистична тактика",        K_NAK,   0, 1, ["компютърна зала"], False, "group", "изпит"),
             ("ОИДТ", "Оперативно-издирвателна техника",K_OID,   0, 1, ["компютърна зала"], False, "group", "КТО"),
             ("СП",   "Стрелкова подготовка",           K_SPT,   0, 1, ["стрелбище"], False, "subgroup", "зачет"),
             ("АЕ",   "Английски език",                 K_EZIK,  0, 1, ["малка зала"], False, "group", "зачет")],
    (3, 2): [("МГР",  "Миграция и гранични режими",     K_OORGK, 1, 0, [], False, "group", "изпит"),
             ("ЗПЧ",  "Защита на правата на човека в полицейската дейност", K_PUB, 1, 0, [], True, "group", "КТО"),
             ("РПП",  "Разследване на престъпления — практикум", K_NAK, 0, 1, ["компютърна зала"], False, "group", "изпит"),
             ("ПТП",  "Пътна полиция и контрол на движението", K_OORGK, 0, 1, ["малка зала"], False, "group", "КТО"),
             ("СП",   "Стрелкова подготовка",           K_SPT,   0, 1, ["стрелбище"], False, "subgroup", "зачет"),
             ("СПТП", "Специализирана полицейска тактика — практикум", K_SPT, 0, 1, ["полигон"], False, "group", "зачет")],
    # Дипломният семестър: три седмици преддипломен стаж и по-лек хорариум.
    (4, 2): [("ЕПС",  "Европейски полицейски стандарти",K_PUB,   1, 0, [], True,  "group", "КТО"),
             ("ДИП",  "Подготовка за държавен изпит",   K_OORGK, 1, 0, [], False, "group", "изпит"),
             ("АНПР", "Анализ на престъпността",        K_NAK,   0, 1, ["компютърна зала"], False, "group", "изпит"),
             ("КПП",  "Комплексна практическа подготовка", K_SPT, 0, 1, ["полигон", "спортен комплекс"], False, "group", "зачет")],
}

# The задочен учебен план is the same subjects at a lower хорариум, saturated
# into the присъствен период instead of spread across the term.
ZADOCHNO = {
    1: [("ОТП",  "Обща теория на правото",        K_PUB,   10, 6, ["малка зала"], "изпит"),
        ("КП",   "Конституционно право",          K_PUB,   10, 6, ["малка зала"], "изпит"),
        ("НПОЧ", "Наказателно право (обща част)", K_NAK,   12, 6, ["малка зала"], "изпит"),
        ("ИТ",   "Информационни технологии",      K_OID,    0, 8, ["компютърна зала"], "КТО")],
    # Не английски: пулът по езиково обучение draws a хоноруван преподавател whose
    # hard Fri/Sat window and weekly cap fight a three-week saturation, which
    # would make the задочният курс infeasible for no demonstrative gain.
    2: [("АПП",  "Административно право и процес",  K_PUB,  10, 6, ["малка зала"], "изпит"),
        ("НПОсЧ","Наказателно право (особена част)",K_NAK,  10, 6, ["малка зала"], "изпит"),
        ("НПр",  "Наказателен процес",              K_NAK,  12, 6, ["малка зала"], "изпит"),
        ("ОИД",  "Оперативно-издирвателна дейност", K_OID,   0, 8, ["компютърна зала"], "КТО")],
}

subjects = []
subject_id_of = {}


def subject(code, name, dept):
    """Subjects are a catalogue now: one entry per subject, however many курсове
    it is taught to. What is *taught* is a SubjectOffering."""
    key = (code, name)
    if key not in subject_id_of:
        sid = f"s{len(subjects)+1}"
        subject_id_of[key] = sid
        subjects.append({"id": sid, "code": code, "name": name,
                         "katedraId": katedra_id[dept]})
    return subject_id_of[key]


offerings = []
groups_by_id = {g["id"]: g for g in groups}
subgroups_of = collections.defaultdict(list)
for sg in subgroups:
    subgroups_of[sg["groupId"]].append(sg["id"])

# Merged потоци are keyed on (семестър, курс, subject) so both специалности land
# in one stream and no stream ever spans two semesters; the offering is owned by
# the first курс that asks for it, and the other курс's разписание still shows the
# лекция because its groups attend it.
merged_stream = collections.defaultdict(list)
for c in cohorts:
    if c.get("block"):
        continue
    for entry in CURRICULUM.get((c["year"], c["semester"]), []):
        if entry[6]:
            merged_stream[(c["semester"], c["year"], entry[0])].extend(c["groupIds"])

# How many of a катедра's staff share its упражнения. Every extra candidate is a
# dimension of the variable cube, so this is deliberate rather than generous.
TUTOR_POOL = {
    K_SPT: by_dept[K_SPT][1:5],
    K_EZIK: by_dept[K_EZIK][1:4],
}

course_by_id = {c["id"]: c for c in courses}
emitted_lecture = set()

# Emitted semester by semester -- редовните курсове, then задочният -- so the
# offering ids of the first semester keep their numbers whatever is added after.
for sem in sorted(SEMESTERS):
  exam_dates = SEMESTERS[sem]["exams"]
  for c in [x for x in cohorts if x["semester"] == sem and not x.get("block")]:
    for exam_i, (code, name, dept, lectures, exercises, ex_types, merge,
                 audience, control) in enumerate(CURRICULUM[(c["year"], sem)]):
        sid = subject(code, name, dept)
        pool = by_dept[dept]
        lead = pool[0]
        stream = merged_stream[(sem, c["year"], code)] if merge else list(c["groupIds"])
        # A merged лекция is emitted once for the whole поток.
        lecture_key = (sem, c["year"], code) if merge else (c["courseId"], code)
        weeks = weeks_of(course_by_id[c["courseId"]])
        lecture_hours = 0
        if lectures and lecture_key not in emitted_lecture:
            emitted_lecture.add(lecture_key)
            lecture_hours = lectures * weeks * HOURS_PER_SESSION
        units = []
        if exercises:
            if audience == "subgroup":
                units = [s for gid in c["groupIds"] for s in subgroups_of[gid]]
            else:
                units = list(c["groupIds"])
        if not lecture_hours and not units:
            continue
        # Упражненията се водят от асистентите на катедрата, лекциите от нейния
        # хабилитиран състав. The pool is a dimension of the variable cube, so it
        # is kept narrow -- except where the катедра really does field a team.
        # Специална полицейска тактика teaches every подгрупа of every курс and
        # has eight instructors for exactly that reason; Езиково обучение runs
        # its groups by level and leans on two хонорувани преподаватели, whose
        # hard availability is the point of them being here.
        tutors = TUTOR_POOL.get(dept, pool[1:2]) or pool
        offerings.append({
            "id": f"o{len(offerings)+1}",
            "subjectId": sid,
            "courseInstanceId": c["courseId"],
            "lectureHours": lecture_hours,
            "exerciseHours": exercises * weeks * HOURS_PER_SESSION if units else 0,
            "hoursPerSession": HOURS_PER_SESSION,
            "controlForm": control,
            "lectureRoomTypes": ["зала"] if lecture_hours else [],
            "exerciseRoomTypes": list(ex_types) if units else [],
            "streamGroupIds": stream if lecture_hours else [],
            "leadTeacherId": lead if lecture_hours else None,
            "exerciseTeacherIds": tutors if units else [],
            "exerciseAudience": audience,
            "exerciseUnitIds": units,
            "spread": "whole",
            "examDate": exam_dates[exam_i % len(exam_dates)] if control == "изпит" else None,
        })

  # Задочно: block spread, saturating that semester's присъствен период.
  for zad in [x for x in cohorts if x["semester"] == sem and x.get("block")]:
    for exam_i, (code, name, dept, lect_h, ex_h, ex_types, control) in enumerate(ZADOCHNO[sem]):
        sid = subject(code, name, dept)
        pool = by_dept[dept]
        offerings.append({
            "id": f"o{len(offerings)+1}",
            "subjectId": sid,
            "courseInstanceId": zad["courseId"],
            "lectureHours": lect_h,
            "exerciseHours": ex_h,
            "hoursPerSession": HOURS_PER_SESSION,
            "controlForm": control,
            "lectureRoomTypes": ["зала"] if lect_h else [],
            "exerciseRoomTypes": list(ex_types) if ex_h else [],
            "streamGroupIds": list(zad["groupIds"]) if lect_h else [],
            "leadTeacherId": pool[0] if lect_h else None,
            "exerciseTeacherIds": (pool[1:3] or pool)[:2],
            "exerciseAudience": "group",
            "exerciseUnitIds": list(zad["groupIds"]) if ex_h else [],
            "spread": "block",
            "window": SEMESTERS[sem]["window"],
            "examDate": exam_dates[exam_i % len(exam_dates)] if control == "изпит" else None,
        })

data = collections.OrderedDict([
    ("_comment",
     "Seed dataset modelling Факултет \"Полиция\" at Академия на МВР (Sofia), all four курса plus "
     "one задочен, across BOTH semesters of 2025/2026. Researched fact: the faculty's катедри, the "
     "two cadet specialties it teaches (ППООР and Гранична полиция), and the academic ranks. "
     "Modelled, not cited: group sizes (standard Bulgarian учебна група of ~25 -- the Academy does "
     "not publish enrolment), the хорариум distribution across the four years, and the instructor "
     "names, which are generic Bulgarian surnames rather than real staff.\n\n"
     "Едно решение покрива един семестър. Вторият семестър е отделна задача: същите преподаватели "
     "и зали, нови CourseInstance и нови групи, защото една група принадлежи на точно един курс. "
     "Първият семестър се преподава 15.09.2025 - 31.01.2026, вторият 09.03.2026 - 27.06.2026 -- "
     "след поправителната сесия на първия, така че двата срока не се застъпват.\n\n"
     "Лекциите се четат на целия поток; общообразователните дисциплини merge both специалности "
     "into one stream, специалните do not. Упражненията run per група, and per подгрупа for "
     "стрелкова подготовка, ЛЗФП and чуждоезиково обучение -- едно стрелбище приема една подгрупа "
     "наведнъж. Четвъртокурсниците са на стаж през ноември и на преддипломен стаж през май, which "
     "is why term dates live on the CourseInstance and not on the група. The задочен курс "
     "compresses each of its semesters into a three-week присъствен период using spread=block, "
     "where an even weekly spread would be the wrong shape. Двамата хонорувани преподаватели по "
     "английски език carry a HARD availability window and a weekly cap, not a preference."),
    ("slotConfig", {"days": DAYS, "periods": PERIODS, "periodTimes": PERIOD_TIMES,
                    "blockedSlots": []}),
    ("roles", roles),
    ("faculties", faculties),
    ("katedri", katedri),
    ("specialties", specialties),
    ("courseInstances", courses),
    ("teachers", teachers),
    ("rooms", rooms),
    ("groups", groups),
    ("subgroups", subgroups),
    ("subjects", subjects),
    ("offerings", offerings),
])
out = os.environ.get(
    "OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed-full.json")
)
open(out, "w").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

# The rankings above are written against room NAMES, resolved to ids at build
# time. Catch a drift here rather than shipping a seed whose preferences point at
# rooms that no longer exist.
for _dept, _ranked in DEPT_ROOM_RANKING.items():
    missing = [n for n in _ranked if n not in room_id_of]
    assert not missing, f"{_dept} ranks unknown room(s) {missing}"

course_semester = {c["id"]: c["semester"] for c in courses}
sessions = collections.Counter()
per_group = collections.Counter()
for o in offerings:
    sem = course_semester[o["courseInstanceId"]]
    lec = -(-o["lectureHours"] // o["hoursPerSession"])
    ex = -(-o["exerciseHours"] // o["hoursPerSession"]) if o["exerciseUnitIds"] else 0
    sessions[sem] += lec + ex * len(o["exerciseUnitIds"])
    for gid in o["streamGroupIds"]:
        per_group[gid] += lec
    for unit in o["exerciseUnitIds"]:
        gid = unit if unit in groups_by_id else next(
            sg["groupId"] for sg in subgroups if sg["id"] == unit)
        per_group[gid] += ex

print(f"teachers={len(teachers)} rooms={len(rooms)} groups={len(groups)} "
      f"subgroups={len(subgroups)} subjects={len(subjects)} offerings={len(offerings)} "
      f"courses={len(courses)}")
for _sem in sorted(SEMESTERS):
    print(f"semester={SEED_YEAR} S{_sem}  teaching weeks={WEEKS[_sem]}  "
          f"sessions={sessions[_sem]}")
print(f"periods/day={PERIODS}  weekday-periods={len(DAYS)*PERIODS}")
print(f"group load: min={min(per_group.values())} max={max(per_group.values())}")
