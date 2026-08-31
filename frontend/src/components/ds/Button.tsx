import type { ButtonHTMLAttributes } from 'react';

/** The design system ships its Button as a canvas-runtime bundle; this is the
 *  same four variants re-implemented over the vendored tokens. Press state is
 *  scale(0.95) with no colour shift, per the design system's readme. */
type Variant = 'primary' | 'secondary-pill' | 'dark-utility' | 'pearl-capsule';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  large?: boolean;
}

export function Button({ variant = 'primary', large = false, className = '', ...rest }: Props) {
  const classes = ['btn', `btn--${variant}`, large ? 'btn--lg' : '', className]
    .filter(Boolean)
    .join(' ');
  return <button type="button" className={classes} {...rest} />;
}
