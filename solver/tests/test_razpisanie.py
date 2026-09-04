"""The printed разписание.

One document per CourseInstance, assembled from a problem and the answer that
came back. Nothing here decides anything, so what these tests check is that the
document *agrees* with the timetable: the same sessions, in the same cells, under
the numbers section I gave them.
"""

import json

import pytest

from app.models import ActivityKind, SolveRequest
from app.razpisanie import build_razpisanie, render_html
from app.timetable_solver import solve_timetable
from conftest import SMALL_SEED_PATH, offering, problem, room, teacher


def solve(payload):
    req = SolveRequest(**payload)
    return req, solve_timetable(req)


@pytest.fixture
def solved(seed):
    """The small seed, solved, plus its clock times -- what the endpoint gets."""
    data = json.loads(SMALL_SEED_PATH.read_text())
    times = {i + 1: t for i, t in enumerate(data["slotConfig"]["periodTimes"])}
    req, result = solve(seed)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    return req, result, times


def test_one_document_per_course_instance(solved):
    req, result, times = solved
    for course in req.courseInstances:
        doc = build_razpisanie(req, result, course.id, times)
        assert doc.courseInstanceId == course.id


def test_an_unknown_course_is_a_clean_error(solved):
    req, result, times = solved
    with pytest.raises(KeyError):
        build_razpisanie(req, result, "no-such-course", times)


def test_the_header_carries_what_the_academy_prints(solved):
    req, result, times = solved
    doc = build_razpisanie(req, result, "c1", times)
    h = doc.header
    assert h.facultyName
    assert h.regNumber and h.approvedBy and h.approvalDate
    assert h.specialtyCode == "ППООР"
    assert (h.degree.value, h.form.value, h.studentKind.value) == (
        "бакалавър", "редовна", "курсант"
    )
    assert (h.year, h.semester) == (1, 1)
    assert h.start < h.end
    assert h.administrativenOtgovornik


def test_section_one_numbers_every_subject_the_course_is_taught(solved):
    req, result, times = solved
    doc = build_razpisanie(req, result, "c1", times)
    assert [s.number for s in doc.subjects] == list(range(1, len(doc.subjects) + 1))
    our = {g.id for g in req.groups if g.courseInstanceId == "c1"}
    taught = {
        a.subjectCode for a in result.assignments if our.intersection(a.groupIds)
    }
    assert taught <= {s.code for s in doc.subjects}


def test_section_one_reports_the_horarium_and_who_taught_it(solved):
    req, result, times = solved
    doc = build_razpisanie(req, result, "c1", times)
    lectured = [s for s in doc.subjects if s.lectureHours]
    assert lectured, "1 курс has поток лекции"
    for s in lectured:
        assert s.leadTeacher, f"{s.code} has лекционни часа but no водещ"
    exercised = [s for s in doc.subjects if s.exerciseHours]
    assert exercised
    for s in exercised:
        assert s.exerciseTeachers and s.rooms


def test_a_merged_potok_appears_on_both_courses_documents(solved):
    """Ownership of the offering is bookkeeping; attendance is what puts a
    лекция on a курс's разписание. A общообразователна лекция merges both
    специалности, and both documents have to show it."""
    req, result, times = solved
    lectures = [a for a in result.assignments
                if a.activity is ActivityKind.lektsiya and len(a.groupIds) > 1]
    assert lectures
    code = lectures[0].subjectCode
    for course_id in ("c1", "c2"):
        doc = build_razpisanie(req, result, course_id, times)
        line = next(s for s in doc.subjects if s.code == code)
        assert line.lectureHours > 0
        assert line.leadTeacher


def test_section_two_lists_the_teaching_period_and_every_exam_session(solved):
    req, result, times = solved
    doc = build_razpisanie(req, result, "c1", times)
    labels = [b.label for b in doc.timeBlocks]
    assert labels[0] == "занятия"
    assert "редовна сесия" in labels
    assert "поправителна сесия" in labels
    assert "ликвидационна сесия" in labels
    for block in doc.timeBlocks:
        assert block.start <= block.end
        assert block.weeks >= 1


def test_section_three_carries_an_exam_line_per_subject(solved):
    req, result, times = solved
    doc = build_razpisanie(req, result, "c1", times)
    assert [e.number for e in doc.exams] == [s.number for s in doc.subjects]
    dated = [e for e in doc.exams if e.examDate]
    assert dated, "the seed sets exam dates"
    for e in dated:
        assert e.controlForm is not None


def test_grid_cells_carry_the_subject_number_and_the_activity_marker(solved):
    req, result, times = solved
    doc = build_razpisanie(req, result, "c1", times)
    numbers = {s.code: s.number for s in doc.subjects}
    our = {g.id for g in req.groups if g.courseInstanceId == "c1"}
    cells = {
        (c.date, c.period): c.entries for m in doc.months for c in m.cells
    }
    for a in result.assignments:
        if not our.intersection(a.groupIds):
            continue
        entries = cells[(a.date, a.period)]
        marker = {"лекция": "л", "упражнение": "у", "практика": "п"}[a.activity.value]
        assert any(
            e.startswith(f"{numbers[a.subjectCode]} {marker}") for e in entries
        ), (a.subjectCode, entries)


def test_a_cell_names_the_subgroup_when_two_run_side_by_side(solved):
    req, result, times = solved
    doc = build_razpisanie(req, result, "c1", times)
    by_cell = {}
    for m in doc.months:
        for c in m.cells:
            by_cell[(c.date, c.period)] = c.entries
    shared = [
        entries for entries in by_cell.values() if len(entries) > 1
    ]
    parallel = [
        a for a in result.assignments if a.subgroupId
    ]
    if parallel:
        assert any("(" in e for entries in by_cell.values() for e in entries)
    assert all(len(set(e)) == len(e) for e in shared)


def test_the_grid_never_shows_a_non_teaching_day(solved):
    req, result, times = solved
    course = next(c for c in req.courseInstances if c.id == "c1")
    doc = build_razpisanie(req, result, "c1", times)
    for month in doc.months:
        for day in month.dates:
            assert course.teaches_on(day)


def test_html_renders_every_section_and_is_print_ready(solved):
    req, result, times = solved
    html = render_html(build_razpisanie(req, result, "c1", times))
    assert "@page" in html and "landscape" in html
    assert "РАЗПИСАНИЕ НА УЧЕБНИТЕ ЗАНЯТИЯ" in html
    assert "I. Учебни дисциплини" in html
    assert "II. Разпределение на учебното време" in html
    assert "III. Изпитни дати" in html
    assert "УТВЪРЖДАВАМ" in html
    assert "л — лекция" in html


def test_html_escapes_what_it_is_given():
    """A subject name is user data and lands in the document verbatim."""
    payload = problem(
        start="2025-09-15",
        end="2025-09-20",
        subjects=[{"id": "s1", "code": "<b>", "name": "Право & <script>",
                   "katedraId": "k1"}],
        offerings=[offering("o1", exerciseHours=2, exerciseRoomTypes=["зала"],
                            exerciseTeacherIds=["t1"], exerciseUnitIds=["g1"])],
    )
    req, result = solve(payload)
    html = render_html(build_razpisanie(req, result, "c1", {}))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_a_course_with_no_sessions_still_produces_a_document():
    payload = problem(start="2025-09-15", end="2025-09-20", offerings=[])
    req, result = solve(payload)
    doc = build_razpisanie(req, result, "c1", {})
    assert doc.subjects == []
    assert doc.timeBlocks[0].label == "занятия"
    assert render_html(doc)
