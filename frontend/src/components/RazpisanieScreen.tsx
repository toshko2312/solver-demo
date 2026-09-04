import { useEffect, useState } from 'react';

import { Button } from './ds/Button';
import { Select } from './ds/Select';
import { razpisanieHtml } from '../api';
import { coursesIn } from '../slots';
import type { Problem, SemesterRef, SolveResponse } from '../types';

interface Props {
  problem: Problem;
  semester: SemesterRef | null;
  result: SolveResponse | null;
  onGoGenerate: () => void;
}

/** The printed разписание, one курс at a time.
 *
 *  The document is built and rendered by the solver (`POST /razpisanie`) rather
 *  than here, for the reason the JSON exists at all: the разписание is a view of
 *  an answer, and a second implementation of the layout would be a second thing
 *  to keep in step with the academy's format. What this screen owns is the
 *  picker, the frame and the Print button.
 *
 *  It is shown in a sandboxed iframe because the payload is a whole HTML
 *  document with its own print stylesheet -- @page and all -- which cannot be
 *  spliced into this one without either losing the page setup or leaking its
 *  rules into the app.
 */
export function RazpisanieScreen({ problem, semester, result, onGoGenerate }: Props) {
  const courses = semester ? coursesIn(problem.courseInstances, semester) : [];
  const [courseId, setCourseId] = useState(courses[0]?.id ?? '');
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const active = courses.some((c) => c.id === courseId) ? courseId : (courses[0]?.id ?? '');

  useEffect(() => {
    if (!semester || !result || !active) {
      setHtml(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    razpisanieHtml(problem, semester, result, active)
      .then((text) => {
        if (!cancelled) setHtml(text);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `problem` is deliberately not a dependency: the document describes the run
    // it was generated from, and re-fetching it on every keystroke in Data setup
    // would show a разписание for data the timetable was never solved against.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [semester?.academicYear, semester?.index, result, active]);

  const label = (id: string) => {
    const c = problem.courseInstances.find((x) => x.id === id);
    if (!c) return id;
    const spec = problem.specialties.find((s) => s.id === c.specialtyId);
    return `${c.year} курс ${spec?.code ?? c.specialtyId} — ${spec?.name ?? ''}`;
  };

  const print = () => {
    const frame = document.querySelector<HTMLIFrameElement>('.razp__frame');
    frame?.contentWindow?.focus();
    frame?.contentWindow?.print();
  };

  if (!result) {
    return (
      <div className="screen">
        <section className="card card--pad">
          <div className="display-md">No timetable yet</div>
          <div className="muted" style={{ marginTop: 6, maxWidth: 560 }}>
            A разписание is a view of a solved semester. Generate one first, and this screen will
            print it курс by курс.
          </div>
          <div style={{ marginTop: 16 }}>
            <Button variant="primary" onClick={onGoGenerate}>
              Go to Generate
            </Button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="screen razp">
      <section className="card card--pad">
        <div className="razp__bar">
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div className="display-md">Разписание</div>
            <div className="muted" style={{ marginTop: 4 }}>
              One document per курс, in the layout the academy publishes: approval header, numbered
              дисциплини with хорариум, разпределение на учебното време, изпитни дати, and the
              month grid.
            </div>
          </div>
          <Select
            aria-label="Курс"
            value={active}
            options={courses.map((c) => ({ value: c.id, label: label(c.id) }))}
            onChange={setCourseId}
          />
          <Button variant="dark-utility" onClick={print} disabled={!html}>
            Print
          </Button>
        </div>

        {error && <div className="failbox">{error}</div>}
        {loading && !html && <div className="muted" style={{ marginTop: 12 }}>Building…</div>}
        {html && (
          <iframe
            className="razp__frame"
            title={`Разписание — ${label(active)}`}
            sandbox="allow-same-origin allow-modals"
            srcDoc={html}
            style={{ marginTop: 14 }}
          />
        )}
      </section>
    </div>
  );
}
