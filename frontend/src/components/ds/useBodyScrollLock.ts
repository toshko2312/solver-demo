import { useEffect } from 'react';

/** Stop the page scrolling behind an open dialog.
 *
 *  The backdrop is `position: fixed`, so it covers the page but does not stop a
 *  wheel over it reaching the document -- the content slides around behind the
 *  dialog while the dialog itself stays put.
 *
 *  Reference-counted, because two dialogs can be up at once (an entity form over
 *  a screen, say) and the first to close must not unlock for the other. The
 *  original inline values are captured on the first lock and put back on the
 *  last unlock, so a page that sets its own body styles keeps them.
 */

let locks = 0;
let previousOverflow = '';
let previousPaddingRight = '';

function lock(): void {
  locks += 1;
  if (locks > 1) return;
  const { body } = document;
  previousOverflow = body.style.overflow;
  previousPaddingRight = body.style.paddingRight;
  // Removing the scrollbar widens the viewport, which would shift the whole page
  // sideways as the dialog opens. Pad by exactly what the scrollbar occupied.
  const scrollbar = window.innerWidth - document.documentElement.clientWidth;
  body.style.overflow = 'hidden';
  if (scrollbar > 0) {
    const current = parseFloat(getComputedStyle(body).paddingRight) || 0;
    body.style.paddingRight = `${current + scrollbar}px`;
  }
}

function unlock(): void {
  locks = Math.max(locks - 1, 0);
  if (locks > 0) return;
  document.body.style.overflow = previousOverflow;
  document.body.style.paddingRight = previousPaddingRight;
}

export function useBodyScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) return;
    lock();
    return unlock;
  }, [locked]);
}
