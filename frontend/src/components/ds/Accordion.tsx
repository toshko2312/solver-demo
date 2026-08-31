import type { ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** Native <details>/<summary>: open/close state, keyboard support and the
 *  initial-open default come free, and no JS runs to maintain them. */
export function Accordion({ title, subtitle, defaultOpen = false, children }: Props) {
  return (
    <details className="accordion" open={defaultOpen}>
      <summary className="accordion__summary">
        <span className="accordion__chevron" aria-hidden="true" />
        <span>
          <span className="accordion__title">{title}</span>
          {subtitle && <span className="accordion__subtitle">{subtitle}</span>}
        </span>
      </summary>
      <div className="accordion__body">{children}</div>
    </details>
  );
}
