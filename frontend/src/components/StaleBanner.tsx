import { Button } from './ds/Button';

/** Shown above a timetable that was generated before the input data changed.
 *
 *  Edits used to discard every stored result. They no longer do -- a timetable
 *  can take minutes to prove optimal, and losing it to a renamed teacher is the
 *  worse failure. What is left is telling the truth about the one on screen: it
 *  is a real timetable, generated from data that has since moved.
 */
export function StaleBanner({ onRegenerate }: { onRegenerate: () => void }) {
  return (
    <div className="stalebar">
      <span>
        Input data changed since this timetable was generated. It still shows what the solver
        returned, from the data as it was.
      </span>
      <Button variant="primary" onClick={onRegenerate}>
        Regenerate
      </Button>
    </div>
  );
}
