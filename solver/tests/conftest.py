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
SEED_SEMESTER = {"academicYear": "2025/2026", "index": 1}


def semester_span(groups, semester):
    """Earliest start and latest end across the groups in term that semester."""
    entries = [
        gs
        for g in groups
        for gs in g.get("semesters", [])
        if gs["academicYear"] == semester["academicYear"] and gs["index"] == semester["index"]
    ]
    if not entries:
        return None, None
    return min(e["start"] for e in entries), max(e["end"] for e in entries)


def build_slots(days, periods, blocked=(), start=None, end=None):
    """Same slot generation the frontend does: the weekday x period template
    expanded across the semester's dates, id '<ISO date>-<period>'.

    `blocked` stays weekday-keyed ('mon-1') and so blocks that period every week,
    which is what the blocking UI means.
    """
    import datetime as dt

    if start is None:
        # No dates given: one representative week, so slot-shape tests can stay
        # small without inventing a calendar.
        start, end = "2025-09-15", "2025-09-19"
    day = dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    wanted = set(days)
    slots = []
    while day <= last:
        name = DAY_NAMES[day.weekday()]
        if name in wanted:
            for period in range(1, periods + 1):
                if f"{name.lower()}-{period}" in blocked:
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
# far too slow for a test suite: 384 sessions over 600 slots takes about a minute
# to solve. Two weeks keeps every property the tests actually check -- dated
# slots, breaks, even spread, pools, the priority ladder -- and still reaches a
# proven optimum, which several tests assert on. Measured: 2 weeks OPTIMAL in
# ~14s, 3 weeks ~23s, 4 weeks does not prove optimality inside 30s.
FIXTURE_WEEKS = 2


def compress(data, semester, weeks=FIXTURE_WEEKS):
    """Narrow a seed's semester to `weeks` teaching weeks, scaling session totals.

    Returns (groups, subjects). Totals are scaled by the change in week count so
    the load per week stays what the seed intended, and any spread window is
    clamped into the shorter span -- a window left pointing at November would have
    no usable dates at all once the term ends in October.
    """
    import copy, datetime as dt

    groups = copy.deepcopy(data["groups"])
    subjects = copy.deepcopy(data["subjects"])

    def weeks_between(start, end, breaks):
        out, day = set(), dt.date.fromisoformat(start)
        last = dt.date.fromisoformat(end)
        holidays = [
            (dt.date.fromisoformat(b["start"]), dt.date.fromisoformat(b["end"]))
            for b in breaks
        ]
        while day <= last:
            if day.weekday() < 5 and not any(a <= day <= b for a, b in holidays):
                out.add(day.isocalendar()[:2])
            day += dt.timedelta(days=1)
        return len(out)

    before = after = None
    for g in groups:
        for gs in g["semesters"]:
            if gs["academicYear"] != semester["academicYear"] or gs["index"] != semester["index"]:
                continue
            if before is None:
                before = weeks_between(gs["start"], gs["end"], gs["breaks"])
            start = dt.date.fromisoformat(gs["start"])
            gs["end"] = (start + dt.timedelta(days=7 * weeks - 3)).isoformat()
            gs["breaks"] = [b for b in gs["breaks"] if b["start"] <= gs["end"]]
            after = weeks_between(gs["start"], gs["end"], gs["breaks"])
            span = (gs["start"], gs["end"])

    if before is None:
        return groups, subjects

    for s in subjects:
        for spec in s["semesters"]:
            if spec["academicYear"] != semester["academicYear"] or spec["index"] != semester["index"]:
                continue
            spec["totalSessions"] = max(1, round(spec["totalSessions"] * after / before))
            window = spec.get("window")
            if spec.get("spread") == "range" and window:
                lo, hi = max(window["start"], span[0]), min(window["end"], span[1])
                if lo <= hi:
                    window["start"], window["end"] = lo, hi
                else:
                    # The window fell outside the shortened term entirely; a
                    # nonsensical range is worse than no range.
                    spec["spread"] = "whole"
                    spec.pop("window", None)
    return groups, subjects


def _request(data, groups, subjects, seconds, semester=None):
    cfg = data["slotConfig"]
    semester = semester or SEED_SEMESTER
    start, end = semester_span(groups, semester)
    return {
        "semester": semester,
        "slots": build_slots(
            cfg["days"], cfg["periods"], set(cfg["blockedSlots"]), start, end
        ),
        "teachers": data["teachers"],
        "rooms": data["rooms"],
        "groups": groups,
        "subjects": subjects,
        "maxTimeInSeconds": seconds,
    }


@pytest.fixture
def full_seed():
    """The UI's "Full example": all four years of Факултет "Полиция". Realistic,
    and slow enough that only the demo-budget test should use it."""
    data = json.loads(FULL_SEED_PATH.read_text())
    groups, subjects = compress(data, SEED_SEMESTER)
    return _request(data, groups, subjects, 30.0)


@pytest.fixture
def seed():
    """The UI's "Small example", and the default fixture for everything here.

    It carries every shape the tests select on -- a поток lecture spanning
    several groups, per-group упражнения, all five room types (including
    firing_range, which the capacity test needs) and multi-candidate teacher
    pools -- at a size that solves in a fraction of a second, which is what keeps
    this suite quick.
    """
    data = json.loads(SMALL_SEED_PATH.read_text())
    groups, subjects = compress(data, SEED_SEMESTER)
    return _request(data, groups, subjects, 30.0)
