// Kept journeys (05 §6.2, Q69): a signed-in user's journey outlives the session, so any device the
// user signs in on resumes the most recent one. Only the position and history are kept (which tape
// visits, at which frames, with which tape arguments, the root, open calls, and each hub
// destination's saved history), never documents: loaders fetch them again on resume, and the
// engine still never persists facts (05 §12). The store is an interface; `MemoryJourneys` keeps
// journeys in memory, and the README says what a durable store needs.

import type { JsonObject } from "./intent";

/** One step of a kept journey: a frame of a tape visit. Steps of one visit share its `visit` number. */
export interface KeptStep {
  visit: number;
  tape: string;
  /** The frame's id, or null in a tape of one frame. */
  frame: string | null;
  /** The tape's arguments: part of the position, like the parts of an address. */
  args: JsonObject;
}

export interface KeptJourney {
  /** The user, as `record#id`. */
  user: string;
  device: string;
  /** When it was last saved, in ms since the epoch. */
  savedAt: number;
  head: KeptStep;
  history: KeptStep[];
  root: string | null;
  calls: Array<{ tape: string; then?: string; caller: KeptStep; history: KeptStep[]; root: string | null }>;
  stacks: Array<{ tape: string; head: KeptStep; history: KeptStep[] }>;
}

export interface JourneyStore {
  /** Keeps a user's journey on a device, replacing the one kept there before. */
  save(journey: KeptJourney): void;
  /** The user's most recently saved journey on any device, saved at `since` or later. */
  latest(user: string, since: number): KeptJourney | undefined;
  /** Forgets the user's journey on a device (a sign-out there). */
  forget(user: string, device: string): void;
  /** Forgets every journey saved before `before`. */
  sweep(before: number): void;
}

export class MemoryJourneys implements JourneyStore {
  private readonly kept = new Map<string, Map<string, KeptJourney>>();

  save(journey: KeptJourney): void {
    let devices = this.kept.get(journey.user);
    if (!devices) this.kept.set(journey.user, (devices = new Map()));
    devices.set(journey.device, structuredClone(journey));
  }

  latest(user: string, since: number): KeptJourney | undefined {
    let best: KeptJourney | undefined;
    for (const j of this.kept.get(user)?.values() ?? []) {
      if (j.savedAt >= since && (!best || j.savedAt >= best.savedAt)) best = j;
    }
    return best ? structuredClone(best) : undefined;
  }

  forget(user: string, device: string): void {
    this.kept.get(user)?.delete(device);
  }

  sweep(before: number): void {
    for (const [user, devices] of this.kept) {
      for (const [device, j] of devices) if (j.savedAt < before) devices.delete(device);
      if (devices.size === 0) this.kept.delete(user);
    }
  }

  /** Every kept journey, for tests. */
  all(): KeptJourney[] {
    return [...this.kept.values()].flatMap((d) => [...d.values()]).map((j) => structuredClone(j));
  }

  clear(): void {
    this.kept.clear();
  }
}
