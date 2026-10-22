// Dotted paths into the reel's data store (spec §5.2).

import type { Data, DataPatch } from "./model";

const UNSAFE = new Set(["__proto__", "prototype", "constructor"]);

export function splitPath(path: string): string[] {
  const parts = path.split(".");
  if (parts.some((p) => p === "" || UNSAFE.has(p))) throw new Error(`invalid data path: ${JSON.stringify(path)}`);
  return parts;
}

export function getPath(data: unknown, path: string): unknown {
  let cur: unknown = data;
  for (const key of splitPath(path)) {
    if (typeof cur !== "object" || cur === null || !Object.hasOwn(cur, key)) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur;
}

/** Returns a new object with `value` at `path`; parents are created or replaced as needed. */
export function setPath(data: Data, path: string, value: unknown): Data {
  const [head, ...rest] = splitPath(path);
  const key = head as string;
  if (rest.length === 0) return { ...data, [key]: value };
  const child = data[key];
  const base = typeof child === "object" && child !== null && !Array.isArray(child) ? child : {};
  return { ...data, [key]: setPath(base, rest.join("."), value) };
}

export function applyPatch(data: Data, patch: DataPatch | undefined): Data {
  if (!patch) return data;
  let out = data;
  for (const [path, value] of Object.entries(patch)) out = setPath(out, path, value);
  return out;
}

/**
 * Calls `fn` with a recording proxy and returns every leaf path it read.
 * Used by `check` to see which data a flavour function looks at (spec §5.5).
 */
export function traceReads(fn: (data: any) => unknown): string[] {
  const reads = new Set<string>();
  const make = (path: string): unknown =>
    new Proxy(function () {}, {
      get(_t, key) {
        if (typeof key === "symbol") {
          if (key === Symbol.toPrimitive) return () => (reads.add(path), "");
          return undefined;
        }
        const next = path ? `${path}.${key}` : key;
        reads.add(next);
        if (path) reads.delete(path);
        return make(next);
      },
      apply() {
        return make(path);
      },
    });
  try {
    fn(make(""));
  } catch {
    // A flavour function may throw on the fake data; what it read so far still counts.
  }
  return [...reads].filter((p) => p !== "").sort();
}
