// The app's journey graph: (frame, event) → frame edges from static actions and
// declared handler outcomes (spec §2, §5.1). Built from the wire spec, so it
// needs no app code to run.

import type { DataPatch } from "./model";
import type { ActionSpec, AppSpec, TapeSpec } from "./schema";

export type NodeId = string;

export function nodeId(tape: string, frame: string): NodeId {
  return `${tape}/${frame}`;
}

export interface GraphEdge {
  from: NodeId;
  component: string;
  event: string;
  /** The frame handler the edge comes from, for declared outcomes. */
  handler?: string;
  kind: ActionSpec["type"];
  /** Static target. Absent for `back` (decided by history), `stay`, and unknown targets. */
  to?: NodeId;
  data?: DataPatch;
}

export interface Graph {
  entry: NodeId | undefined;
  nodes: NodeId[];
  edges: GraphEdge[];
}

export function resolveTarget(spec: AppSpec, fromTape: string, action: ActionSpec): NodeId | undefined {
  if (action.type === "goto") {
    const t = spec.tapes.find((x) => x.id === fromTape);
    return t?.frames.some((f) => f.id === action.frame) ? nodeId(fromTape, action.frame) : undefined;
  }
  if (action.type === "jump") {
    const t = spec.tapes.find((x) => x.id === action.tape);
    return t && t.frames.some((f) => f.id === t.entry) ? nodeId(t.id, t.entry) : undefined;
  }
  return undefined;
}

function entryNode(spec: AppSpec): NodeId | undefined {
  const t: TapeSpec | undefined = spec.tapes.find((x) => x.id === spec.entry);
  return t ? nodeId(t.id, t.entry) : undefined;
}

export function buildGraph(spec: AppSpec): Graph {
  const nodes: NodeId[] = [];
  const edges: GraphEdge[] = [];
  for (const t of spec.tapes) {
    for (const f of t.frames) {
      const from = nodeId(t.id, f.id);
      nodes.push(from);
      for (const c of f.components) {
        for (const [event, ref] of Object.entries(c.on ?? {})) {
          if (typeof ref === "string") {
            for (const outcome of f.on?.[ref]?.outcomes ?? []) edges.push(edge(spec, t.id, from, c.id, event, outcome, ref));
          } else {
            edges.push(edge(spec, t.id, from, c.id, event, ref));
          }
        }
      }
    }
  }
  return { entry: entryNode(spec), nodes, edges };
}

function edge(spec: AppSpec, tape: string, from: NodeId, component: string, event: string, action: ActionSpec, handler?: string): GraphEdge {
  const e: GraphEdge = { from, component, event, kind: action.type };
  if (handler) e.handler = handler;
  const to = resolveTarget(spec, tape, action);
  if (to) e.to = to;
  if (action.type === "jump" && action.data) e.data = action.data;
  return e;
}

/** Nodes reachable from the entry. `back` only returns to visited nodes, so it adds none. */
export function reachable(g: Graph): Set<NodeId> {
  const seen = new Set<NodeId>();
  if (!g.entry) return seen;
  const queue = [g.entry];
  while (queue.length) {
    const n = queue.shift()!;
    if (seen.has(n)) continue;
    seen.add(n);
    for (const e of g.edges) if (e.from === n && e.to && !seen.has(e.to)) queue.push(e.to);
  }
  return seen;
}

/** True when a node has any edge that can take the head elsewhere. */
export function hasExit(g: Graph, n: NodeId): boolean {
  return g.edges.some((e) => e.from === n && (e.kind === "back" || (e.to !== undefined && e.to !== n)));
}

/** Strongly connected components (Tarjan), over static edges. */
export function components(g: Graph): NodeId[][] {
  let index = 0;
  const idx = new Map<NodeId, number>();
  const low = new Map<NodeId, number>();
  const onStack = new Set<NodeId>();
  const stack: NodeId[] = [];
  const out: NodeId[][] = [];
  const succ = (n: NodeId) => g.edges.filter((e) => e.from === n && e.to).map((e) => e.to!);

  const visit = (v: NodeId) => {
    idx.set(v, index);
    low.set(v, index);
    index++;
    stack.push(v);
    onStack.add(v);
    for (const w of succ(v)) {
      if (!idx.has(w)) {
        visit(w);
        low.set(v, Math.min(low.get(v)!, low.get(w)!));
      } else if (onStack.has(w)) {
        low.set(v, Math.min(low.get(v)!, idx.get(w)!));
      }
    }
    if (low.get(v) === idx.get(v)) {
      const scc: NodeId[] = [];
      let w: NodeId;
      do {
        w = stack.pop()!;
        onStack.delete(w);
        scc.push(w);
      } while (w !== v);
      out.push(scc);
    }
  };
  for (const n of g.nodes) if (!idx.has(n)) visit(n);
  return out;
}

/** Cycles the head can enter but never leave: a terminal component with more than one frame. */
export function closedCycles(g: Graph): NodeId[][] {
  return components(g).filter((scc) => {
    if (scc.length < 2) return false;
    const inside = new Set(scc);
    return !g.edges.some((e) => inside.has(e.from) && (e.kind === "back" || (e.to !== undefined && !inside.has(e.to))));
  });
}

export function toMermaid(g: Graph): string {
  const safe = (n: string) => n.replace(/[^A-Za-z0-9_]/g, "_");
  const lines = ["flowchart LR"];
  for (const n of g.nodes) lines.push(`  ${safe(n)}["${n}"]`);
  if (g.edges.some((e) => e.kind === "back")) lines.push(`  back(("back"))`);
  for (const e of g.edges) {
    const label = `${e.component}·${e.event}${e.handler ? ` ⇒ ${e.handler}` : ""}`;
    if (e.kind === "back") lines.push(`  ${safe(e.from)} -.->|"${label}"| back`);
    else if (e.kind === "stay") lines.push(`  ${safe(e.from)} -->|"${label}"| ${safe(e.from)}`);
    else if (e.to) lines.push(`  ${safe(e.from)} -->|"${label}"| ${safe(e.to)}`);
  }
  if (g.entry) lines.push(`  style ${safe(g.entry)} stroke-width:3px`);
  return lines.join("\n") + "\n";
}
