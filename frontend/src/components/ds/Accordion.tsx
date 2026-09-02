import { useState, type ReactNode } from 'react';

interface Props {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Rendered at the right of the summary row -- a status, a progress bar, a clock. */
  aside?: ReactNode;
  defaultOpen?: boolean;
  /** Fires when the row is opened or closed, for callers that track which is open. */
  onToggle?: (open: boolean) => void;
  children: ReactNode;
}

/** Native <details>/<summary>: open/close state, keyboard support and the
 *  initial-open default come free, and no JS runs to maintain them. */
export function Accordion({
  title,
  subtitle,
  aside,
  defaultOpen = false,
  onToggle,
  children,
}: Props) {
  // Held here rather than left to the DOM: passing `open` straight from a prop
  // makes React re-assert it on every render, so a row would snap shut again the
  // moment anything above it re-rendered -- which, for a row watching a solve,
  // is several times a second.
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      className="accordion"
      open={open}
      onToggle={(e) => {
        const next = (e.currentTarget as HTMLDetailsElement).open;
        setOpen(next);
        onToggle?.(next);
      }}
    >
      <summary className="accordion__summary">
        <span className="accordion__chevron" aria-hidden="true" />
        <span>
          <span className="accordion__title">{title}</span>
          {subtitle && <span className="accordion__subtitle">{subtitle}</span>}
        </span>
        {aside && <span className="accordion__aside">{aside}</span>}
      </summary>
      <div className="accordion__body">{children}</div>
    </details>
  );
}
