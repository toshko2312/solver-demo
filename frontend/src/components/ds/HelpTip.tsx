import { useCallback, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  /** Plain-language explanation. No solver jargon: this is the one place in the
   *  app where CP-SAT terminology would otherwise leak out to the user. */
  text: string;
  label?: string;
}

const GAP = 8;
const EDGE = 8;

/** A "?" marker that reveals an explanation on hover and on keyboard focus.
 *
 *  The bubble is rendered through a portal into <body> and positioned with
 *  `position: fixed`. That is the only way to be certain it is never clipped:
 *  it lives inside a dialog that has to scroll, and any scrolling ancestor
 *  clips absolutely-positioned descendants at its own edge.
 */
export function HelpTip({ text, label = 'What does this do?' }: Props) {
  const id = useId();
  const dotRef = useRef<HTMLButtonElement>(null);
  const bubbleRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; below: boolean } | null>(null);

  const place = useCallback(() => {
    const dot = dotRef.current;
    const bubble = bubbleRef.current;
    if (!dot || !bubble) return;
    const d = dot.getBoundingClientRect();
    const { offsetWidth: w, offsetHeight: h } = bubble;

    // Above by default; underneath when there is not enough room up there.
    const below = d.top - h - GAP < EDGE;
    const top = below ? d.bottom + GAP : d.top - h - GAP;
    // Centred on the marker, then pulled back inside the viewport if need be.
    const left = Math.min(
      Math.max(EDGE, d.left + d.width / 2 - w / 2),
      window.innerWidth - w - EDGE,
    );
    setPos({ top, left, below });
  }, []);

  // Measure after the bubble exists, before the browser paints it.
  useLayoutEffect(() => {
    if (!open) return;
    place();
    // Scrolling the dialog moves the marker, so the bubble has to follow it.
    const onMove = () => place();
    window.addEventListener('scroll', onMove, true);
    window.addEventListener('resize', onMove);
    return () => {
      window.removeEventListener('scroll', onMove, true);
      window.removeEventListener('resize', onMove);
    };
  }, [open, place]);

  const show = () => setOpen(true);
  const hide = () => {
    setOpen(false);
    setPos(null);
  };

  return (
    <span className="helptip">
      <button
        ref={dotRef}
        type="button"
        className="helptip__dot"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        ?
      </button>
      {open &&
        createPortal(
          <div
            ref={bubbleRef}
            role="tooltip"
            id={id}
            className={`helptip__bubble${pos?.below ? ' helptip__bubble--below' : ''}`}
            style={
              pos
                ? { top: pos.top, left: pos.left, visibility: 'visible', opacity: 1 }
                : { top: 0, left: 0, visibility: 'hidden' }
            }
          >
            {text}
          </div>,
          document.body,
        )}
    </span>
  );
}
