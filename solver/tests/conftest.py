import json
import sys
from pathlib import Path

import pytest

# The service is imported as the `app` package, so `solver/` must be on the path
# whichever directory pytest was started from.
SOLVER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SOLVER_DIR.parent
sys.path.insert(0, str(SOLVER_DIR))

SMALL_SEED_PATH = REPO_ROOT / "shared" / "seed-small.json"
FULL_SEED_PATH = REPO_ROOT / "shared" / "seed-full.json"


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# The semester the seed files schedule, and what the fixtures generate for.
# Both files carry two semesters; everything here is about the first unless it
# says otherwise, because a solve covers one semester and the first is the one
# the tests' numbers are written against.
SEED_SEMESTER = {"academicYear": "2025/2026", "index": 1}
SEED_SEMESTER_2 = {"academicYear": "2025/2026", "index": 2}


def in_term(courses, semester):
    """The course instances of one semester."""
    return [
        c
        for c in courses
        if c["academicYear"] == semester["academicYear"] and c["semester"] == semester["index"]
    ]


def semester_span(courses, semester):
    """Earliest start and latest end across the courses in term that semester."""
    entries = in_term(courses, semester)
    if not entries:
        return None, None
    return min(c["start"] for c in entries), max(c["end"] for c in entries)


def slot_key(day, period):
    """What preferredSlots, hardAvailability and blockedSlots are keyed on."""
    return f"{day.lower()}-{period}"


def build_slots(days, periods, blocked=(), start=None, end=None):
    """Same slot generation the frontend does: the weekday x period template
    expanded across the semester's dates, id '<ISO date>-<period>'.

    `blocked` is weekday-keyed ('mon-1') and so blocks that period every week,
    which is what the blocking UI means.
    """
    import datetime as dt

    if start is None:
        # No dates given: one representative week, so slot-shape tests can stay
        # small without inventing a calendar.
        start, end = "2025-09-15", "2025-09-20"
    day = dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    wanted = set(days)
    blocked = set(blocked)
    slots = []
    while day <= last:
        name = DAY_NAMES[day.weekday()]
        if name in wanted:
            for period in range(1, periods + 1):
                if slot_key(name, period) in blocked:
                    continue
                slots.append(
                    {
                        "id": f"{day.isoformat()}-{period}",
                        "date": day.isoformat(),
                        "day": name,
                        "period": period,
                    }
                )
        day += dt.timedelta(days=1)
    return slots


# How many teaching weeks the quick fixtures compress a semester down to. The
# seed files carry a real 18-week term, which is the right thing for the app and
# far too slow for a test suite. Two weeks keeps every property the tests actually
# check -- dated periods, non-teaching stretches, even spread, pools, подгрупи, the
# priority ladder -- and still reaches a proven optimum, which several tests
# assert on.
FIXTURE_WEEKS = 2


def compress(data, semester, weeks=FIXTURE_WEEKS):
    """Narrow a seed's semester to `weeks` teaching weeks, scaling the хорариум.

    Returns (courseInstances, offerings). Hours are scaled by the change in week
    count so the load per week stays what the seed intended, and any spread window
    is clamped into the shorter span -- a window left pointing at November would
    have no usable dates at all once the term ends in September.
    """
    import copy, datetime as dt

    courses = copy.deepcopy(data["courseInstances"])
    offerings = copy.deepcopy(data["offerings"])
    days = set(data["slotConfig"]["days"])

    def weeks_between(start, end, non_teaching):
        out, day = set(), dt.date.fromisoformat(start)
        last = dt.date.fromisoformat(end)
        closed = [
            (dt.date.fromisoformat(p["start"]), dt.date.fromisoformat(p["end"]))
            for p in non_teaching
        ]
        while day <= last:
            if DAY_NAMES[day.weekday()] in days and not any(a <= day <= b for a, b in closed):
                out.add(day.isocalendar()[:2])
            day += dt.timedelta(days=1)
        return len(out)

    before = after = None
    span = None
    for course in in_term(courses, semester):
        if before is None:
            before = weeks_between(course["start"], course["end"], course["nonTeaching"])
        start = dt.date.fromisoformat(course["start"])
        # Land on the last teaching weekday of the last week we keep.
        course["end"] = (start + dt.timedelta(days=7 * weeks - 2)).isoformat()
        # Closures that fall past the shortened term go, but the изпитни сесии
        # stay: they sit *after* the term by definition, and section II of the
        # разписание is built out of them.
        course["nonTeaching"] = [
            p for p in course["nonTeaching"]
            if p["start"] <= course["end"] or p["kind"] == "изпитна сесия"
        ]
        after = weeks_between(course["start"], course["end"], course["nonTeaching"])
        span = (course["start"], course["end"])

    if before is None or not before:
        return courses, offerings

    kept = {c["id"] for c in in_term(courses, semester)}
    for offering in offerings:
        if offering["courseInstanceId"] not in kept:
            continue
        per_session = offering.get("hoursPerSession", 2)
        for field in ("lectureHours", "exerciseHours"):
            hours = offering.get(field, 0)
            if not hours:
                continue
            scaled = round(hours * after / before)
            offering[field] = max(per_session, scaled)
        window = offering.get("window")
        if offering.get("spread") in ("range", "block") and window:
            lo, hi = max(window["start"], span[0]), min(window["end"], span[1])
            if lo <= hi:
                window["start"], window["end"] = lo, hi
            else:
                # The window fell outside the shortened term entirely; a
                # nonsensical range is worse than no range.
                offering["spread"] = "whole"
                offering.pop("window", None)
    return courses, offerings


def _request(data, courses, offerings, seconds, semester=None):
    cfg = data["slotConfig"]
    semester = semester or SEED_SEMESTER
    start, end = semester_span(courses, semester)
    return {
        "semester": semester,
        "slots": build_slots(
            cfg["days"], cfg["periods"], set(cfg["blockedSlots"]), start, end
        ),
        "faculties": data["faculties"],
        "katedri": data["katedri"],
        "specialties": data["specialties"],
        "courseInstances": courses,
        "teachers": data["teachers"],
        "rooms": data["rooms"],
        "groups": data["groups"],
        "subgroups": data["subgroups"],
        "subjects": data["subjects"],
        "offerings": offerings,
        "maxTimeInSeconds": seconds,
    }


@pytest.fixture
def full_seed():
    """The UI's "Full example": all four years of Факултет "Полиция". Realistic,
    and slow enough that only the demo-budget test should use it."""
    data = json.loads(FULL_SEED_PATH.read_text())
    courses, offerings = compress(data, SEED_SEMESTER)
    return _request(data, courses, offerings, 30.0)


@pytest.fixture
def seed():
    """The UI's "Small example", and the default fixture for everything here.

    It carries every shape the tests select on -- a поток лекция spanning several
    groups and both специалности, per-group упражнения, подгрупи for стрелкова
    подготовка and чуждоезиково обучение, a хоноруван преподавател with a hard
    availability window, and every room type -- at a size that solves quickly,
    which is what keeps this suite usable.
    """
    data = json.loads(SMALL_SEED_PATH.read_text())
    courses, offerings = compress(data, SEED_SEMESTER)
    return _request(data, courses, offerings, 30.0)


@pytest.fixture
def seed_s2():
    """The same file, second semester. A different problem over the same
    преподаватели and the same зали: its own курсове, its own групи, its own
    учебен план. Compressed like `seed`, so the two cost the same."""
    data = json.loads(SMALL_SEED_PATH.read_text())
    courses, offerings = compress(data, SEED_SEMESTER_2)
    return _request(data, courses, offerings, 30.0, semester=SEED_SEMESTER_2)


# ---------------------------------------------------------------------------
# Hand-built problems. The seed fixtures are the realistic case; these are for
# tests that need to isolate one rule, where a whole faculty would be noise.
# ---------------------------------------------------------------------------

# The academy's own day: six periods of two academic hours. The обедна почивка is
# the gap between period 3 and period 4 -- a break defined by absence, which is
# why nothing here has to name it.
PERIODS = 6
ALL_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def teacher(tid, name=None, **over):
    out = {
        "id": tid,
        "name": name or tid.upper(),
        "preferredSlots": [],
        "hardAvailability": [],
        "preferredRooms": [],
    }
    out.update(over)
    return out


def room(rid, rtype="зала", capacity=100, **over):
    out = {"id": rid, "name": rid.upper(), "type": rtype, "capacity": capacity,
           "maxConcurrentGroups": 1}
    out.update(over)
    return out


def offering(oid, subject_id="s1", course="c1", **over):
    """A well-formed offering. Callers say what they are testing and nothing else."""
    out = {
        "id": oid,
        "subjectId": subject_id,
        "courseInstanceId": course,
        "lectureHours": 0,
        "exerciseHours": 0,
        "hoursPerSession": 2,
        "controlForm": "зачет",
        "lectureRoomTypes": [],
        "exerciseRoomTypes": [],
        "streamGroupIds": [],
        "leadTeacherId": None,
        "exerciseTeacherIds": [],
        "exerciseAudience": "group",
        "exerciseUnitIds": [],
        "spread": "whole",
    }
    out.update(over)
    return out


def problem(
    start="2025-09-15",
    end="2025-09-20",
    days=None,
    periods=PERIODS,
    blocked=(),
    non_teaching=(),
    max_periods_per_day=6,
    seconds=10.0,
    **over,
):
    """A minimal, well-formed problem: one faculty, one специалност, one курс.

    Everything the solver needs to accept a request is here; a test adds only the
    rows the rule it is checking is about.
    """
    days = list(days or ALL_DAYS)
    out = {
        "semester": {"academicYear": "2025/2026", "index": 1},
        "slots": build_slots(days, periods, set(blocked), start, end),
        "faculties": [{"id": "f1", "name": 'Факултет "Полиция"'}],
        "katedri": [{"id": "k1", "name": "катедра", "facultyId": "f1"}],
        "specialties": [{"id": "sp1", "facultyId": "f1", "code": "ППООР",
                         "name": "ППООР", "degree": "бакалавър", "form": "редовна",
                         "studentKind": "курсант", "durationYears": 4}],
        "courseInstances": [{
            "id": "c1", "specialtyId": "sp1", "year": 1,
            "academicYear": "2025/2026", "semester": 1,
            "start": start, "end": end,
            "nonTeaching": [dict(p) for p in non_teaching],
            "maxPeriodsPerDay": max_periods_per_day,
        }],
        "teachers": [teacher("t1")],
        "rooms": [room("r1")],
        "groups": [{"id": "g1", "name": "гр. 1", "size": 20, "courseInstanceId": "c1"}],
        "subgroups": [],
        "subjects": [{"id": "s1", "code": "S1", "name": "Дисциплина 1", "katedraId": "k1"}],
        "offerings": [],
        "maxTimeInSeconds": seconds,
    }
    out.update(over)
    return out
