// Finds lettering in a generated scene. Image models paint fake text and fake
// controls ("SIGN M UP.", "NORTE"); thin strokes barely change luma spread, and
// edge density cannot tell them from city lights or console detail, so this
// asks an OCR engine instead (tesseract, local model, no network).
//
// One shared worker is created on first use and shut down after a short idle
// spell, so a CLI run can still exit on its own.

/// <reference path="./vendor.d.ts" />
import eng from "@tesseract.js-data/eng";
import Tesseract from "tesseract.js";
import sharp from "sharp";
import type { Size } from "@videotape/core";

export interface Lettering {
  text: string;
  confidence: number;
  /** [x, y, w, h] as fractions of the canvas, like region rects. */
  rect: [number, number, number, number];
}

export interface LetteringOptions {
  /** Lowest OCR confidence, 0–100, for a word to count. */
  minConfidence?: number;
  /** Fewest letters in a row for a word to count; shorter hits are mostly noise. */
  minLetters?: number;
}

const IDLE_MS = 1500;
let worker: Promise<Tesseract.Worker> | undefined;
let idle: ReturnType<typeof setTimeout> | undefined;
let busy = 0;

async function withWorker<T>(fn: (w: Tesseract.Worker) => Promise<T>): Promise<T> {
  clearTimeout(idle);
  busy++;
  worker ??= Tesseract.createWorker("eng", Tesseract.OEM.LSTM_ONLY, {
    langPath: eng.langPath, gzip: eng.gzip, cacheMethod: "none", logger: () => {},
  }).then(async (w) => {
    await w.setParameters({ user_defined_dpi: "300" });
    return w;
  });
  try {
    return await fn(await worker);
  } finally {
    if (--busy === 0) {
      idle = setTimeout(() => {
        const w = worker;
        worker = undefined;
        void w?.then((x) => x.terminate());
      }, IDLE_MS);
    }
  }
}

/** Words an OCR engine reads in the image, filtered to ones that look like real lettering. */
export async function findLettering(bytes: Uint8Array, canvas: Size, opts: LetteringOptions = {}): Promise<Lettering[]> {
  const minConfidence = opts.minConfidence ?? 80;
  const letters = new RegExp(`[A-Za-z]{${opts.minLetters ?? 3},}`);
  const png = await sharp(bytes).resize(canvas.w, canvas.h, { fit: "fill" }).png().toBuffer();
  const page = await withWorker(async (w) => (await w.recognize(png, {}, { blocks: true })).data);
  const words = (page.blocks ?? []).flatMap((b) => b.paragraphs.flatMap((p) => p.lines.flatMap((l) => l.words)));
  return words
    .filter((w) => w.confidence >= minConfidence && letters.test(w.text))
    .map((w) => ({
      text: w.text,
      confidence: Math.round(w.confidence),
      rect: [w.bbox.x0 / canvas.w, w.bbox.y0 / canvas.h, (w.bbox.x1 - w.bbox.x0) / canvas.w, (w.bbox.y1 - w.bbox.y0) / canvas.h],
    }));
}

/** Share of `word` that lies inside `region`. */
export function overlap(word: Lettering["rect"], region: readonly number[]): number {
  const [ax, ay, aw, ah] = word;
  const [bx, by, bw, bh] = region as [number, number, number, number];
  const w = Math.max(0, Math.min(ax + aw, bx + bw) - Math.max(ax, bx));
  const h = Math.max(0, Math.min(ay + ah, by + bh) - Math.max(ay, by));
  return aw * ah > 0 ? (w * h) / (aw * ah) : 0;
}
