"""Two semesters in one file, one semester per solve.

A `Group` belongs to exactly one `CourseInstance` and a `CourseInstance` is one
semester, so the same cohort continuing into семестър 2 is new rows, not a second
entry on the same ones. That is what makes solving one semester at a time correct
-- and it is also the thing that makes cross-semester optimisation impossible,
which is stated as a limitation rather than hidden.

These tests are about the *seed data* carrying both semesters and the solver
honouring the boundary. The numbers of семестър 1 are pinned elsewhere.
"""

import datetime as dt
import json

import pytest

from app.models import SolveRequest
from app.razpisanie import build_razpisanie
from app.sessions import build_series, courses_in_term
from app.timetable_solver import solve_timetable, validate_assignments
from conftest import FULL_SEED_PATH, SEED_SEMESTER, SEED_SEMESTER_2, SMALL_SEED_PATH


def solve(payload):
    return solve_timetable(SolveRequest(**payload))


def in_semester(data, index):
    return [c for c in data["courseInstances"]
            if c["academicYear"] == "2025/2026" and c["semester"] == index]


# ---------------------------------------------------------------------------
# 1. What the seed files declare
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [SMALL_SEED_PATH, FULL_SEED_PATH])
def test_both_seeds_ship_two_semesters(path):
    data = json.loads(path.read_text())
    assert in_semester(data, 1) and in_semester(data, 2)


@pytest.mark.parametrize("path", [SMALL_SEED_PATH, FULL_SEED_PATH])
def test_no_group_belongs_to_two_semesters(path):
    """The structural claim the whole design rests on: a група is one курс's, and
    a курс is one semester's. The same cohort in семестър 2 is new група rows."""
    data = json.loads(path.read_text())
    semester_of = {c["id"]: c["semester"] for c in data["courseInstances"]}
    for group in data["groups"]:
        assert group["courseInstanceId"] in semester_of
    by_id = {g["id"]: semester_of[g["courseInstanceId"]] for g in data["groups"]}
    for offering in data["offerings"]:
        owner = semester_of[offering["courseInstanceId"]]
        for gid in offering["streamGroupIds"]:
            assert by_id[gid] == owner, f"{offering['id']} streams across semesters"


@pytest.mark.parametrize("path", [SMALL_SEED_PATH, FULL_SEED_PATH])
def test_the_two_terms_do_not_overlap(path):
    data = json.loads(path.read_text())
    first = max(c["end"] for c in in_semester(data, 1))
    second = min(c["start"] for c in in_semester(data, 2))
    assert first < second


@pytest.mark.parametrize("path", [SMALL_SEED_PATH, FULL_SEED_PATH])
def test_semesters_share_teachers_and_rooms_but_never_a_group(path):
    """Which is exactly why one solve has to cover every курс of its semester:
    the преподаватели and the зали are the shared resource."""
    data = json.loads(path.read_text())
    ids = {i: {c["id"] for c in in_semester(data, i)} for i in (1, 2)}
    groups = {
        i: {g["id"] for g in data["groups"] if g["courseInstanceId"] in ids[i]}
        for i in (1, 2)
    }
    assert groups[1] and groups[2]
    assert not groups[1] & groups[2]

    def staff(index):
        out = set()
        for o in data["offerings"]:
            if o["courseInstanceId"] not in ids[index]:
                continue
            if o["leadTeacherId"]:
                out.add(o["leadTeacherId"])
            out.update(o["exerciseTeacherIds"])
        return out

    assert staff(1) & staff(2), "the same катедри teach in both semesters"


def test_a_continuing_subject_is_one_catalogue_entry_with_two_offerings():
    """Английски език runs in both semesters. That is two SubjectOfferings of one
    Subject -- which is the whole reason the catalogue and the offering are
    different tables."""
    data = json.loads(SMALL_SEED_PATH.read_text())
    semester_of = {c["id"]: c["semester"] for c in data["courseInstances"]}
    by_subject = {}
    for o in data["offerings"]:
        by_subject.setdefault(o["subjectId"], set()).add(semester_of[o["courseInstanceId"]])
    continuing = [sid for sid, sems in by_subject.items() if len(sems) > 1]
    assert continuing, "at least one дисциплина continues into семестър 2"
    codes = {s["id"]: s["code"] for s in data["subjects"]}
    assert "АЕ" in {codes[sid] for sid in continuing}


# ---------------------------------------------------------------------------
# 2. What the solver does with them
# ---------------------------------------------------------------------------


def test_the_second_semester_solves_on_its_own(seed_s2):
    result = solve(seed_s2)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
    assert result.stats.numPlaced == result.stats.numSessions
    assert result.validation is not None and result.validation.ok, (
        result.validation.errors if result.validation else None
    )


def test_a_solve_places_nothing_from_the_other_semester(seed, seed_s2):
    """Both requests carry the whole file -- every курс, every offering, both
    semesters. What separates them is `semester` on the request, and nothing
    else."""
    for payload, ref, other in (
        (seed, SEED_SEMESTER, SEED_SEMESTER_2),
        (seed_s2, SEED_SEMESTER_2, SEED_SEMESTER),
    ):
        req = SolveRequest(**payload)
        assert len(req.courseInstances) > len(courses_in_term(req, req.semester))
        mine = set(courses_in_term(req, req.semester))
        theirs = {c.id for c in req.courseInstances if c.id not in mine}
        assert theirs, "the other semester is in the payload"
        group_course = {g.id: g.courseInstanceId for g in req.groups}
        offering_course = {o.id: o.courseInstanceId for o in req.offerings}

        result = solve_timetable(req)
        assert result.status in ("OPTIMAL", "FEASIBLE"), result.message
        assert result.assignments
        for a in result.assignments:
            assert offering_course[a.offeringId] in mine
            for gid in a.groupIds:
                assert group_course[gid] in mine, f"{gid} belongs to {other}"


def test_each_semester_asks_for_its_own_horarium(seed, seed_s2):
    """`build_series` is the only place hours become sessions, and it is filtered
    by the request's semester -- so the two requests describe disjoint work."""
    one, two = SolveRequest(**seed), SolveRequest(**seed_s2)
    first = {s.key for s in build_series(one, one.semester)}
    second = {s.key for s in build_series(two, two.semester)}
    assert first and second
    assert not first & second


def test_hand_validation_rejects_a_session_moved_into_the_other_semester(seed):
    """The independent re-check knows the boundary too: a session dragged onto a
    date the other semester owns is named, not quietly accepted."""
    req = SolveRequest(**seed)
    result = solve_timetable(req)
    assert result.assignments
    moved = [a.model_copy() for a in result.assignments]
    # A date inside семестър 2's term and outside this one.
    moved[0].date = dt.date(2026, 4, 15)
    moved[0].slot = f"2026-04-15-{moved[0].period}"
    check = validate_assignments(moved, req)
    assert not check.ok


# ---------------------------------------------------------------------------
# 3. The printed document
# ---------------------------------------------------------------------------


def test_the_razpisanie_of_a_second_semester_course_says_so(seed_s2):
    data = json.loads(SMALL_SEED_PATH.read_text())
    times = {i + 1: t for i, t in enumerate(data["slotConfig"]["periodTimes"])}
    req = SolveRequest(**seed_s2)
    result = solve_timetable(req)
    assert result.status in ("OPTIMAL", "FEASIBLE")

    course = next(iter(courses_in_term(req, req.semester).values()))
    doc = build_razpisanie(req, result, course.id, times)
    assert doc.header.semester == 2
    assert doc.header.start.isoformat() == "2026-03-09"
    # Section II is built out of that семестър's own изпитни сесии, not the
    # first's: the редовна сесия of семестър 2 is in July.
    regular = next(b for b in doc.timeBlocks if b.label == "редовна сесия")
    assert regular.start.isoformat().startswith("2026-06")
    assert doc.subjects and doc.months
