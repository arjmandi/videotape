// Measures E5's and E10's latencies (05 §15): a local change, and a decision, played through the
// app protocol against the sample apps' Python processes on this machine.
//
//   npx -y pnpm@9.15.0 --filter @videotape/engine latency      (N=300 by default)
//
// - local change: a fill of the draft until the session hears the document change (no app involved);
// - decision: a press until the handler's first change is shown (tentative) and until its outcome
//   has played (confirmed), for journeys' "Wave" (a handler with no service call) and relay's "Send"
//   (whose fake service waits 1 ms), and for relay the same moments in a second session showing the
//   conversation (fan-out). Each send adds a message, and a decide carries the whole conversation
//   both ways, so relay's figures are reported by the conversation's size.

import { Headless } from "../src/driver";
import { play } from "../test/harness";

const N = Number(process.env.N ?? 300);
const WARMUP = 30;

type Sample = Record<string, number>;

function stats(values: number[]): string {
  const s = [...values].sort((a, b) => a - b);
  const q = (p: number) => s[Math.min(s.length - 1, Math.floor(p * s.length))]!;
  const f = (v: number) => (v < 1 ? v.toFixed(3) : v.toFixed(2));
  return `p50 ${f(q(0.5))} ms · p95 ${f(q(0.95))} ms · p99 ${f(q(0.99))} ms · max ${f(s[s.length - 1]!)} ms`;
}

function report(title: string, samples: Sample[]): void {
  console.log(`\n${title} (n=${samples.length})`);
  for (const key of Object.keys(samples[0]!)) console.log(`  ${key.padEnd(34)} ${stats(samples.map((x) => x[key]!))}`);
}

async function journeys(): Promise<void> {
  const p = await play("journeys");
  try {
    const user = { record: "Person", id: "p1", value: { id: "p1", name: "Ada" } };
    const s = await Headless.open(p.engine, { tape: "home", user });
    const samples: Sample[] = [];
    for (let i = 0; i < N + WARMUP; i++) {
      const seen = s.changes.length;
      const t0 = performance.now();
      await s.press("Wave");
      const t1 = performance.now();
      const tentative = s.changes.slice(seen).find((c) => c.state === "tentative")!;
      if (i >= WARMUP) samples.push({ "press → change shown (tentative)": tentative.at - t0, "press → outcome played (confirmed)": t1 - t0 });
    }
    report("journeys: a decision (Wave)", samples);
  } finally {
    await p.stop();
  }
}

async function relay(): Promise<void> {
  const p = await play("relay");
  try {
    const ada = { record: "User", id: "u1", value: { id: "u1", name: "Ada" } };
    const grace = { record: "User", id: "u2", value: { id: "u2", name: "Grace" } };
    const a = await Headless.open(p.engine, { address: "/c/c1", user: ada });
    const b = await Headless.open(p.engine, { address: "/c/c1", user: grace });
    const local: Sample[] = [];
    const decisions: Sample[] = [];
    for (let i = 0; i < N + WARMUP; i++) {
      const seenA = a.changes.length;
      const t0 = performance.now();
      await a.fill({ text: `message ${i}` });
      const filled = a.changes.slice(seenA).find((c) => c.record === "Draft")!;
      if (i >= WARMUP) local.push({ "fill → change heard": filled.at - t0 });

      const fromA = a.changes.length;
      const fromB = b.changes.length;
      const t1 = performance.now();
      await a.press("Send");
      const t2 = performance.now();
      const at = (list: typeof a.changes, from: number, state: string) => list.slice(from).find((c) => c.record === "Conversation" && c.state === state)!.at - t1;
      if (i >= WARMUP) {
        decisions.push({
          "press → shown here (tentative)": at(a.changes, fromA, "tentative"),
          "press → shown in the other session": at(b.changes, fromB, "tentative"),
          "press → confirmed in the other session": at(b.changes, fromB, "confirmed"),
          "press → outcome played": t2 - t1,
        });
      }
    }
    report("relay: a local change (Draft.text)", local);
    // Every send adds a message, and a decide carries the whole conversation: report by its size.
    const third = Math.floor(decisions.length / 3);
    report(`relay: a decision (Send; its fake service waits 1 ms), conversation of ${WARMUP + 2}–${WARMUP + third + 1} messages`, decisions.slice(0, third));
    report(`relay: the same, conversation of ${WARMUP + 2 * third + 2}–${WARMUP + N + 1} messages`, decisions.slice(2 * third));
  } finally {
    await p.stop();
  }
}

console.log(`node ${process.version}, ${process.platform} ${process.arch}; N=${N} after ${WARMUP} warm-up`);
await journeys();
await relay();
