import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

/** Single-choice dropdown, to the spec on the design project's component-set
 *  screen (see frontend/DESIGN.md → Dropdown): a button trigger, a CSS-triangle
 *  caret and a hairline menu panel. Deliberately not a native <select> -- its
 *  option list is drawn by the OS and cannot carry the design.
 *
 *  Multi-choice belongs in a `chiprow`, not here.
 *
 *  The panel is portalled and positioned fixed rather than absolute as the mock
 *  has it: the entity modal scrolls (`.modal` is max-height 86vh, overflow auto)
 *  and would clip a panel belonging to any field low in a long form. Same
 *  offset, same geometry -- it just escapes the scroll container, and flips
 *  above the trigger when there is no room below.
 */

export interface SelectOption<T extends string | number> {
  value: T;
  label: string;
  disabled?: boolean;
}

interface Props<T extends string | number> {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  /** 'md' is the field size the mock specifies; 'sm' is the dense inline size. */
  size?: 'md' | 'sm';
  disabled?: boolean;
  /** Trigger text when `value` matches no option. */
  placeholder?: string;
  'aria-label'?: string;
  id?: string;
  className?: string;
}

/** Where the panel sits, in viewport coordinates. */
interface Rect {
  left: number;
  width: number;
  top: number;
  placement: 'below' | 'above';
}

const GAP = 6;

export function Select<T extends string | number>({
  value,
  options,
  onChange,
  size = 'md',
  disabled = false,
  placeholder = 'Select…',
  id,
  className = '',
  ...aria
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  const place = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    // Measure the panel if it is already up; before the first paint assume it
    // opens downwards, which the layout effect below then corrects.
    const height = menuRef.current?.offsetHeight ?? 0;
    const below = window.innerHeight - r.bottom - GAP;
    const flip = height > 0 && below < height && r.top - GAP > height;
    setRect({
      left: r.left,
      width: r.width,
      top: flip ? r.top - GAP - height : r.bottom + GAP,
      placement: flip ? 'above' : 'below',
    });
  }, []);

  // Re-measure once the panel has a height, so a flip happens before it is seen.
  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    // Capture, so a scroll inside the modal closes the panel too rather than
    // leaving it stranded next to a field that has moved.
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [open]);

  const openMenu = (from: number) => {
    if (disabled) return;
    setActive(from >= 0 ? from : 0);
    place();
    setOpen(true);
  };

  const commit = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  /** Next selectable option in `step` direction, skipping disabled ones. */
  const step = (from: number, direction: 1 | -1) => {
    for (let i = from + direction; i >= 0 && i < options.length; i += direction) {
      if (!options[i].disabled) return i;
    }
    return from;
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        openMenu(selectedIndex);
      }
      return;
    }
    switch (e.key) {
      case 'Escape':
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        break;
      case 'ArrowDown':
        e.preventDefault();
        setActive((i) => step(i, 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActive((i) => step(i, -1));
        break;
      case 'Home':
        e.preventDefault();
        setActive(step(-1, 1));
        break;
      case 'End':
        e.preventDefault();
        setActive(step(options.length, -1));
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        commit(active);
        break;
      case 'Tab':
        setOpen(false);
        break;
    }
  };

  const cls = (base: string) => `${base}${size === 'sm' ? ` ${base}--sm` : ''}`;

  return (
    <div className={`dd${className ? ` ${className}` : ''}`}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={aria['aria-label']}
        disabled={disabled}
        className={`${cls('dd__trigger')}${open ? ' dd__trigger--open' : ''}`}
        onClick={() => (open ? setOpen(false) : openMenu(selectedIndex))}
        onKeyDown={onKeyDown}
      >
        <span className="dd__value">{selected ? selected.label : placeholder}</span>
        <span
          className={`dd__caret${open ? ' dd__caret--up' : ''}${
            disabled ? ' dd__caret--muted' : ''
          }`}
        />
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={menuRef}
            id={menuId}
            role="listbox"
            aria-activedescendant={`${menuId}-${active}`}
            className={cls('dd__menu')}
            style={{ left: rect.left, top: rect.top, minWidth: rect.width }}
            // Keyboard lives on the trigger, which keeps focus throughout.
            onKeyDown={onKeyDown}
          >
            {options.map((o, i) => (
              <div
                key={String(o.value)}
                id={`${menuId}-${i}`}
                role="option"
                aria-selected={o.value === value}
                aria-disabled={o.disabled || undefined}
                className={`${cls('dd__option')}${
                  o.value === value ? ' dd__option--selected' : ''
                }${i === active ? ' dd__option--active' : ''}`}
                onPointerEnter={() => !o.disabled && setActive(i)}
                onClick={() => commit(i)}
              >
                <span>{o.label}</span>
                {o.value === value && <span className="dd__mark">Selected</span>}
              </div>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
