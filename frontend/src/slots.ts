/** Slot ids are derived, never stored: '<lowercased day>-<period>', e.g. mon-1.
 *  The solver's tests build them the same way (solver/tests/conftest.py). */

import type { Slot, SlotConfig } from './types';

export function slotId(day: string, period: number): string {
  return `${day.toLowerCase()}-${period}`;
}

/** Every slot in the day x period grid, blocked ones included. */
export function allSlots(config: SlotConfig): Slot[] {
  const out: Slot[] = [];
  for (const day of config.days) {
    for (let period = 1; period <= config.periods; period++) {
      out.push({ id: slotId(day, period), day, period });
    }
  }
  return out;
}

/** What actually gets sent to the solver: a blocked slot simply does not exist. */
export function openSlots(config: SlotConfig): Slot[] {
  const blocked = new Set(config.blockedSlots);
  return allSlots(config).filter((s) => !blocked.has(s.id));
}

export function periodTime(config: SlotConfig, period: number): string {
  return config.periodTimes[period - 1] ?? '';
}

export function slotLabel(config: SlotConfig, id: string): string {
  const slot = allSlots(config).find((s) => s.id === id);
  return slot ? `${slot.day} · Period ${slot.period}` : id;
}
