// Content-addressed asset store plus a manifest from cache keys to assets
// (spec §7.2). Assets hold no user data by construction, so they can be public.

import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";

export const MIME_EXT: Record<string, string> = {
  "image/png": "png", "image/webp": "webp", "image/jpeg": "jpg", "video/webm": "webm", "video/mp4": "mp4",
};
const EXT_MIME = Object.fromEntries(Object.entries(MIME_EXT).map(([m, e]) => [e, m]));

/** `<sha256>.<ext>`: the only asset file names the store accepts. */
export const ASSET_FILE = /^[0-9a-f]{64}\.(png|webp|jpg|webm|mp4)$/;

export interface AssetRef {
  /** `<sha256>.<ext>` */
  file: string;
  mime: string;
  url: string;
}

export interface ManifestEntry {
  file: string;
  renderer: string;
  seed: number;
  createdAt: string;
  pinned?: boolean;
  meta?: Record<string, unknown>;
}

export interface Cache {
  putAsset(bytes: Uint8Array, mime: string): Promise<AssetRef>;
  getAsset(file: string): Promise<{ bytes: Uint8Array; mime: string } | undefined>;
  /** The pinned entry for a key, else the most recent one. */
  lookup(key: string): Promise<ManifestEntry | undefined>;
  entries(key: string): Promise<ManifestEntry[]>;
  record(key: string, entry: ManifestEntry): Promise<void>;
}

export function assetUrl(file: string): string {
  return `/a/${file}`;
}

function refFor(bytes: Uint8Array, mime: string): AssetRef {
  const ext = MIME_EXT[mime];
  if (!ext) throw new Error(`unsupported asset type ${mime}`);
  const file = `${createHash("sha256").update(bytes).digest("hex")}.${ext}`;
  return { file, mime, url: assetUrl(file) };
}

function pick(entries: ManifestEntry[]): ManifestEntry | undefined {
  return entries.find((e) => e.pinned) ?? entries[entries.length - 1];
}

export class MemoryCache implements Cache {
  private assets = new Map<string, { bytes: Uint8Array; mime: string }>();
  private manifest = new Map<string, ManifestEntry[]>();

  async putAsset(bytes: Uint8Array, mime: string): Promise<AssetRef> {
    const ref = refFor(bytes, mime);
    this.assets.set(ref.file, { bytes, mime });
    return ref;
  }

  async getAsset(file: string) {
    return this.assets.get(file);
  }

  async lookup(key: string) {
    return pick(this.manifest.get(key) ?? []);
  }

  async entries(key: string) {
    return [...(this.manifest.get(key) ?? [])];
  }

  async record(key: string, entry: ManifestEntry) {
    this.manifest.set(key, [...(this.manifest.get(key) ?? []), entry]);
  }
}

/** Filesystem store: `<dir>/assets/<sha256>.<ext>` and `<dir>/keys/<key>.json`. */
export class FsCache implements Cache {
  private manifest = new Map<string, ManifestEntry[]>();

  constructor(readonly dir: string) {}

  private keyFile(key: string): string {
    return join(this.dir, "keys", `${key.replace(/^sha256:/, "")}.json`);
  }

  async putAsset(bytes: Uint8Array, mime: string): Promise<AssetRef> {
    const ref = refFor(bytes, mime);
    const path = join(this.dir, "assets", ref.file);
    await mkdir(join(this.dir, "assets"), { recursive: true });
    const tmp = `${path}.${process.pid}.${Date.now()}.tmp`;
    await writeFile(tmp, bytes);
    await rename(tmp, path);
    return ref;
  }

  async getAsset(file: string) {
    if (!ASSET_FILE.test(file)) return undefined;
    try {
      const bytes = new Uint8Array(await readFile(join(this.dir, "assets", file)));
      return { bytes, mime: EXT_MIME[file.split(".")[1]!]! };
    } catch {
      return undefined;
    }
  }

  async entries(key: string): Promise<ManifestEntry[]> {
    const cached = this.manifest.get(key);
    if (cached) return [...cached];
    try {
      const list = JSON.parse(await readFile(this.keyFile(key), "utf8")) as ManifestEntry[];
      this.manifest.set(key, list);
      return [...list];
    } catch {
      return [];
    }
  }

  async lookup(key: string) {
    return pick(await this.entries(key));
  }

  async record(key: string, entry: ManifestEntry) {
    const list = [...(await this.entries(key)), entry];
    this.manifest.set(key, list);
    await mkdir(join(this.dir, "keys"), { recursive: true });
    const file = this.keyFile(key);
    const tmp = `${file}.${process.pid}.tmp`;
    await writeFile(tmp, JSON.stringify(list, null, 2));
    await rename(tmp, file);
  }
}
