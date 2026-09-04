"""The printed разписание.

`SolveResponse` is the machine-readable answer; this is the document a faculty
actually issues. One per CourseInstance -- курс + семестър + специалност -- laid
out the way the academy publishes it: an approval header, a numbered subject list
with хорариум, разпределение на учебното време, exam dates, and then the month
grid whose cells carry the subject's number and an activity marker.

Nothing here decides anything. It reads a request and the answer that came back
and arranges them; if the timetable is wrong, the document is wrong in exactly
the same way.
"""

import datetime as dt
from collections import OrderedDict, defaultdict
from html import escape
from typing import Dict, List, Optional

from .models import (
    ACTIVITY_MARKER,
    ActivityKind,
    Razpisanie,
    RazpisanieCell,
    RazpisanieExam,
    RazpisanieHeader,
    RazpisanieMonth,
    RazpisanieSubject,
    RazpisanieTimeBlock,
    SolveRequest,
    SolveResponse,
)

MONTHS_BG = [
    "януари", "февруари", "март", "април", "май", "юни",
    "юли", "август", "септември", "октомври", "ноември", "декември",
]
DAYS_BG = {
    "Mon": "понеделник", "Tue": "вторник", "Wed": "сряда", "Thu": "четвъртък",
    "Fri": "петък", "Sat": "събота", "Sun": "неделя",
}


def _weeks(start: dt.date, end: dt.date) -> int:
    """ISO weeks a closed date range touches."""
    if end < start:
        return 0
    weeks, day = set(), start
    while day <= end:
        weeks.add(day.isocalendar()[:2])
        day += dt.timedelta(days=1)
    return len(weeks)


def build_razpisanie(
    req: SolveRequest,
    response: SolveResponse,
    course_instance_id: str,
    period_times: Optional[Dict[int, str]] = None,
) -> Razpisanie:
    """Assemble the document for one курс out of the problem and its answer.

    Membership is decided by *attendance*, not by ownership: a общообразователна
    лекция is one offering owned by whichever курс asked for it first, and every
    курс in its поток has to see it on their own разписание. So every assignment
    whose groups intersect this course's groups belongs on this document.
    """
    course = next((c for c in req.courseInstances if c.id == course_instance_id), None)
    if course is None:
        raise KeyError(f"No course instance '{course_instance_id}' in this problem.")
    specialty = next((s for s in req.specialties if s.id == course.specialtyId), None)
    if specialty is None:
        raise KeyError(f"Course '{course_instance_id}' names a specialty that is not here.")
    faculty = next((f for f in req.faculties if f.id == specialty.facultyId), None)

    our_groups = {g.id for g in req.groups if g.courseInstanceId == course.id}
    # Подгрупите на нашите групи attend on our behalf too.
    our_units = set(our_groups) | {
        sg.id for sg in req.subgroups if sg.groupId in our_groups
    }
    mine = [a for a in response.assignments if our_groups.intersection(a.groupIds)]

    subjects_by_id = {s.id: s for s in req.subjects}
    katedri_by_id = {k.id: k.name for k in req.katedri}
    offerings_by_id = {o.id: o for o in req.offerings}

    header = RazpisanieHeader(
        facultyName=faculty.name if faculty else "",
        regNumber=course.regNumber,
        approvedBy=course.approvedBy,
        approvalDate=course.approvalDate,
        specialtyCode=specialty.code,
        specialtyName=specialty.name,
        degree=specialty.degree,
        form=specialty.form,
        studentKind=specialty.studentKind,
        year=course.year,
        semester=course.semester,
        start=course.start,
        end=course.end,
        administrativenOtgovornik=course.administrativenOtgovornik,
    )

    # ---- section I: the numbered subject list -------------------------------
    # Numbered in first-appearance order over the offerings, which is учебен план
    # order. The number is the document's own identifier for the subject: it is
    # what every grid cell prints, so nothing else may renumber.
    hours: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    lead: Dict[str, Optional[str]] = {}
    control: Dict[str, object] = {}
    exam_date: Dict[str, Optional[dt.date]] = {}
    order: "OrderedDict[str, None]" = OrderedDict()

    teacher_names = {t.id: t.name for t in req.teachers}

    # Membership is attendance, not ownership. A общообразователна лекция is one
    # offering owned by whichever курс asked for it first, and a упражнение can
    # name units from more than one курс; both belong on the разписание of every
    # курс that sits in them. Owning the row would leave a курс's own document
    # showing 0/0 for a subject it is actually taught.
    for offering in req.offerings:
        in_stream = bool(our_groups.intersection(offering.streamGroupIds))
        in_exercises = bool(our_units.intersection(offering.exerciseUnitIds))
        if not (in_stream or in_exercises):
            continue
        sid = offering.subjectId
        order.setdefault(sid, None)
        if offering.lectureHours and in_stream:
            hours[sid][0] += offering.lectureHours
            if offering.leadTeacherId:
                lead[sid] = teacher_names.get(offering.leadTeacherId)
        if offering.exerciseHours and in_exercises:
            hours[sid][1] += offering.exerciseHours
        control.setdefault(sid, offering.controlForm)
        if offering.examDate:
            exam_date[sid] = offering.examDate

    # Who actually taught, and where -- read off the answer rather than off the
    # pools, because "who might have" is not what a разписание states.
    tutors: Dict[str, List[str]] = defaultdict(list)
    rooms_used: Dict[str, List[str]] = defaultdict(list)
    for a in mine:
        order.setdefault(a.subjectId, None)
        if a.activity is not ActivityKind.lektsiya:
            if a.teacherName not in tutors[a.subjectId]:
                tutors[a.subjectId].append(a.teacherName)
        if a.roomName not in rooms_used[a.subjectId]:
            rooms_used[a.subjectId].append(a.roomName)
        offering = offerings_by_id.get(a.offeringId)
        if offering is not None:
            control.setdefault(a.subjectId, offering.controlForm)

    numbers: Dict[str, int] = {}
    section_i: List[RazpisanieSubject] = []
    for sid in order:
        subject = subjects_by_id.get(sid)
        if subject is None:
            continue
        numbers[sid] = len(section_i) + 1
        section_i.append(
            RazpisanieSubject(
                number=numbers[sid],
                code=subject.code,
                name=subject.name,
                lectureHours=hours[sid][0],
                exerciseHours=hours[sid][1],
                katedra=katedri_by_id.get(subject.katedraId) if subject.katedraId else None,
                leadTeacher=lead.get(sid),
                exerciseTeachers=sorted(tutors.get(sid, [])),
                rooms=sorted(rooms_used.get(sid, [])),
                controlForm=control.get(sid),
            )
        )

    # ---- section II: разпределение на учебното време -------------------------
    time_blocks = [
        RazpisanieTimeBlock(
            label="занятия",
            start=course.start,
            end=course.end,
            weeks=_weeks(course.start, course.end),
        )
    ]
    for period in course.nonTeaching:
        if period.session is None:
            continue
        time_blocks.append(
            RazpisanieTimeBlock(
                label=f"{period.session.value} сесия",
                start=period.start,
                end=period.end,
                weeks=_weeks(period.start, period.end),
            )
        )

    # ---- section III: exam dates --------------------------------------------
    exams = [
        RazpisanieExam(
            number=line.number,
            code=line.code,
            name=line.name,
            controlForm=line.controlForm,
            examDate=exam_date.get(sid),
        )
        for sid, line in zip(order, section_i)
    ]

    # ---- the month grid ------------------------------------------------------
    # Cells carry the subject number and the activity marker, which is what the
    # published document prints -- the names are in section I and repeating them
    # in a cell 30mm wide is not possible.
    cells: Dict[tuple, List[str]] = defaultdict(list)
    for a in mine:
        number = numbers.get(a.subjectId)
        if number is None:
            continue
        marker = ACTIVITY_MARKER.get(a.activity, "")
        entry = f"{number} {marker}"
        if a.subgroupName:
            # Подгрупи run side by side, so the cell has to say which is which.
            entry = f"{entry} ({a.subgroupName.split('–')[-1].strip()})"
        if entry not in cells[(a.date, a.period)]:
            cells[(a.date, a.period)].append(entry)

    dates = sorted({a.date for a in mine})
    if not dates:
        dates = []
    by_month: "OrderedDict[tuple, List[dt.date]]" = OrderedDict()
    day = course.start
    while day <= course.end:
        if course.teaches_on(day) and day.strftime("%a") in DAYS_BG:
            by_month.setdefault((day.year, day.month), []).append(day)
        day += dt.timedelta(days=1)

    months = [
        RazpisanieMonth(
            label=f"{MONTHS_BG[month - 1]} {year}",
            year=year,
            month=month,
            dates=days,
            cells=[
                RazpisanieCell(date=d, period=period, entries=entries)
                for (d, period), entries in sorted(cells.items())
                if d in set(days)
            ],
        )
        for (year, month), days in by_month.items()
    ]

    return Razpisanie(
        courseInstanceId=course.id,
        header=header,
        subjects=section_i,
        timeBlocks=time_blocks,
        exams=exams,
        periods=sorted({s.period for s in req.slots}),
        periodTimes=period_times or {},
        months=months,
    )


# ---------------------------------------------------------------------------
# HTML. Print-first: A4 landscape, hairline rules, no colour. The viewer prints
# it to PDF -- adding a PDF library to a service that has none would buy nothing
# a browser does not already do better.
# ---------------------------------------------------------------------------

_CSS = """
@page { size: A4 landscape; margin: 12mm 10mm; }
* { box-sizing: border-box; }
body { font: 11px/1.35 "Times New Roman", Georgia, serif; color: #111; margin: 0; }
h1, h2 { font-weight: 700; margin: 0; }
h1 { font-size: 15px; text-align: center; letter-spacing: .02em; }
h2 { font-size: 12px; margin: 14px 0 5px; text-transform: uppercase; letter-spacing: .04em; }
.approval { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }
.approval div { white-space: pre-line; }
.approval .right { text-align: right; }
.meta { margin: 10px 0 4px; text-align: center; }
.meta .line { margin: 2px 0; }
.meta strong { font-weight: 700; }
table { border-collapse: collapse; width: 100%; margin-bottom: 6px; }
th, td { border: 1px solid #111; padding: 2px 4px; vertical-align: top; }
th { font-weight: 700; background: #f2f2f2; }
td.num, th.num { text-align: center; width: 26px; }
td.c { text-align: center; }
.grid td, .grid th { font-size: 10px; padding: 1px 2px; }
.grid td.cell { text-align: center; height: 16px; min-width: 26px; }
.grid th.day { text-align: left; white-space: nowrap; }
.grid tr.newweek td, .grid tr.newweek th { border-top: 2px solid #111; }
.month { page-break-inside: avoid; margin-bottom: 10px; }
.foot { margin-top: 10px; display: flex; justify-content: space-between; }
.empty { color: #777; font-style: italic; }
"""


def _fmt(day: Optional[dt.date]) -> str:
    return day.strftime("%d.%m.%Y") if day else "—"


def _period_label(period: int, period_times: Dict[int, str]) -> str:
    span = period_times.get(period) or period_times.get(str(period))
    if span:
        return f"{period}<br><span style='font-size:9px'>{escape(span)}</span>"
    return str(period)


def render_html(doc: Razpisanie) -> str:
    h = doc.header
    parts: List[str] = []
    parts.append(f"<style>{_CSS}</style>")

    parts.append('<div class="approval">')
    parts.append(f"<div>{escape(h.facultyName)}<br>{escape(h.regNumber or '')}</div>")
    approved = escape(h.approvedBy or "").replace("\n", "<br>")
    parts.append(
        f'<div class="right">УТВЪРЖДАВАМ:<br>{approved}<br>{_fmt(h.approvalDate)}</div>'
    )
    parts.append("</div>")

    parts.append("<h1>РАЗПИСАНИЕ НА УЧЕБНИТЕ ЗАНЯТИЯ</h1>")
    parts.append('<div class="meta">')
    parts.append(
        f'<div class="line"><strong>специалност</strong> {escape(h.specialtyName)} '
        f"({escape(h.specialtyCode)})</div>"
    )
    parts.append(
        f'<div class="line">ОКС <strong>{escape(h.degree.value)}</strong> · '
        f"{escape(h.form.value)} форма · {escape(h.studentKind.value)}и · "
        f"<strong>{h.year} курс</strong> · <strong>{h.semester} семестър</strong></div>"
    )
    parts.append(f'<div class="line">{_fmt(h.start)} – {_fmt(h.end)}</div>')
    parts.append("</div>")

    # ---- I ----
    parts.append("<h2>I. Учебни дисциплини</h2>")
    parts.append(
        "<table><tr><th class='num'>№</th><th>код</th><th>дисциплина</th>"
        "<th>катедра</th><th class='num'>л</th><th class='num'>у</th>"
        "<th>водещ преподавател</th><th>упражнения</th><th>зали</th>"
        "<th>контрол</th></tr>"
    )
    for s in doc.subjects:
        parts.append(
            f"<tr><td class='num'>{s.number}</td><td>{escape(s.code)}</td>"
            f"<td>{escape(s.name)}</td><td>{escape(s.katedra or '')}</td>"
            f"<td class='num'>{s.lectureHours or ''}</td>"
            f"<td class='num'>{s.exerciseHours or ''}</td>"
            f"<td>{escape(s.leadTeacher or '')}</td>"
            f"<td>{escape(', '.join(s.exerciseTeachers))}</td>"
            f"<td>{escape(', '.join(s.rooms))}</td>"
            f"<td class='c'>{escape(s.controlForm.value if s.controlForm else '')}</td></tr>"
        )
    parts.append("</table>")

    # ---- II ----
    parts.append("<h2>II. Разпределение на учебното време</h2>")
    parts.append("<table><tr><th>период</th><th>от</th><th>до</th><th class='num'>седмици</th></tr>")
    for b in doc.timeBlocks:
        parts.append(
            f"<tr><td>{escape(b.label)}</td><td class='c'>{_fmt(b.start)}</td>"
            f"<td class='c'>{_fmt(b.end)}</td><td class='num'>{b.weeks}</td></tr>"
        )
    parts.append("</table>")

    # ---- III ----
    parts.append("<h2>III. Изпитни дати</h2>")
    parts.append(
        "<table><tr><th class='num'>№</th><th>дисциплина</th><th>форма на контрол</th>"
        "<th>дата</th></tr>"
    )
    for e in doc.exams:
        parts.append(
            f"<tr><td class='num'>{e.number}</td><td>{escape(e.name)}</td>"
            f"<td class='c'>{escape(e.controlForm.value if e.controlForm else '')}</td>"
            f"<td class='c'>{_fmt(e.examDate)}</td></tr>"
        )
    parts.append("</table>")

    # ---- the grid ----
    parts.append("<h2>Разписание по дни и часове</h2>")
    by_cell = {}
    for month in doc.months:
        for cell in month.cells:
            by_cell[(cell.date, cell.period)] = cell.entries

    for month in doc.months:
        parts.append(f'<div class="month"><table class="grid">')
        parts.append("<tr><th class='day'>{}</th>".format(escape(month.label)))
        for period in doc.periods:
            parts.append(f"<th class='c'>{_period_label(period, doc.periodTimes)}</th>")
        parts.append("</tr>")
        previous_week = None
        for day in month.dates:
            week = day.isocalendar()[:2]
            klass = " class='newweek'" if previous_week and week != previous_week else ""
            previous_week = week
            label = f"{day.day:02d}.{day.month:02d} {DAYS_BG.get(day.strftime('%a'), '')}"
            parts.append(f"<tr{klass}><th class='day'>{escape(label)}</th>")
            for period in doc.periods:
                entries = by_cell.get((day, period), [])
                parts.append(f"<td class='cell'>{escape(' / '.join(entries))}</td>")
            parts.append("</tr>")
        parts.append("</table></div>")

    parts.append('<div class="foot">')
    parts.append(
        f"<div>Административен отговорник на курса: "
        f"{escape(h.administrativenOtgovornik or '—')}</div>"
    )
    parts.append("<div>л — лекция · у — упражнение · п — практика</div>")
    parts.append("</div>")
    return "\n".join(parts)
