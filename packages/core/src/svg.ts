// Wireframe drawings (spec §6.3). `wireframeSvg` is the conditioning image for
// generators: panels, fields, buttons, and text as grey bars. `sceneSvg` is
// what the flat renderer shows: the same structure with no text bars, over a
// soft palette gradient, because the content layer draws the real text.

import { mix } from "./color";
import type { Region } from "./layout";
import type { StylePack } from "./style";
import type { Size } from "./viewport";

const n = (v: number) => {
  const r = Math.round(v * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
};

interface Px { x: number; y: number; w: number; h: number }

function px(r: Region, c: Size): Px {
  const [x, y, w, h] = r.rect;
  return { x: x * c.w, y: y * c.h, w: w * c.w, h: h * c.h };
}

function rect(b: Px, fill: string, rx: number, extra = ""): string {
  return `<rect x="${n(b.x)}" y="${n(b.y)}" width="${n(b.w)}" height="${n(b.h)}" rx="${n(Math.min(rx, b.h / 2))}" fill="${fill}"${extra}/>`;
}

const BAR_WIDTHS = [1, 0.93, 0.86, 0.95, 0.78];

function textBars(r: Region, b: Px, color: string): string {
  const t = r.type;
  if (!t) return "";
  const lineH = b.h / Math.max(1, t.lines);
  const barH = Math.min(t.size * 0.55, lineH * 0.7);
  const out: string[] = [];
  for (let i = 0; i < t.lines; i++) {
    const ratio = t.lines > 1 && i === t.lines - 1 ? 0.6 : BAR_WIDTHS[i % BAR_WIDTHS.length]!;
    const w = b.w * ratio * (r.kind === "text" && t.role !== "body" ? 0.7 : 1);
    const x = t.align === "center" ? b.x + (b.w - w) / 2 : b.x;
    out.push(rect({ x, y: b.y + i * lineH + (lineH - barH) / 2, w, h: barH }, color, barH / 2));
  }
  return out.join("");
}

interface Shapes { bars: boolean }

function shapes(regions: Region[], canvas: Size, style: StylePack, opts: Shapes): string {
  const { bg, fg, accent, muted } = style.palette;
  const radius = Math.min(canvas.w, canvas.h) * 0.016;
  const out: string[] = [];
  for (const r of regions) {
    const b = px(r, canvas);
    switch (r.kind) {
      case "panel":
        out.push(rect(b, mix(bg, fg, 0.05), radius * 1.4, ` stroke="${mix(bg, fg, 0.12)}" stroke-width="${n(radius * 0.12)}"`));
        break;
      case "button":
        out.push(rect(b, r.emphasis === "primary" ? accent : mix(bg, fg, 0.16), radius));
        break;
      case "link":
        out.push(rect({ x: b.x, y: b.y + b.h * 0.78, w: b.w * 0.5, h: Math.max(2, b.h * 0.04) }, mix(bg, accent, 0.55), 1));
        break;
      case "input": case "textarea": case "select": case "date": case "slider": {
        const label = r.labelSize ? r.labelSize * 1.35 + radius * 0.4 : 0;
        if (label && opts.bars) out.push(rect({ x: b.x, y: b.y + label * 0.2, w: b.w * 0.3, h: label * 0.5 }, mix(bg, muted, 0.6), label * 0.25));
        out.push(rect({ ...b, y: b.y + label, h: b.h - label }, mix(bg, fg, 0.1), radius * 0.7, ` stroke="${mix(bg, fg, 0.24)}" stroke-width="${n(radius * 0.1)}"`));
        break;
      }
      case "toggle":
        out.push(rect({ x: b.x, y: b.y + b.h * 0.25, w: b.h * 0.9, h: b.h * 0.5 }, mix(bg, fg, 0.2), b.h));
        break;
      case "image": case "media":
        out.push(rect(b, mix(bg, fg, 0.08), radius * 0.6));
        break;
      case "list":
        if (opts.bars) out.push(textBars(r, b, mix(bg, muted, 0.55)));
        break;
      case "text":
        if (opts.bars) out.push(textBars(r, b, mix(bg, muted, 0.55)));
        break;
    }
  }
  return out.join("");
}

function open(canvas: Size): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.w}" height="${canvas.h}" viewBox="0 0 ${canvas.w} ${canvas.h}">`;
}

export function wireframeSvg(regions: Region[], canvas: Size, style: StylePack): string {
  return open(canvas) + rect({ x: 0, y: 0, w: canvas.w, h: canvas.h }, style.palette.bg, 0) +
    shapes(regions, canvas, style, { bars: true }) + "</svg>";
}

export function sceneSvg(regions: Region[], canvas: Size, style: StylePack): string {
  const { bg, accent, muted } = style.palette;
  const { w, h } = canvas;
  const defs =
    `<defs>` +
    `<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${bg}"/><stop offset="1" stop-color="${mix(bg, accent, 0.14)}"/></linearGradient>` +
    `<radialGradient id="a" cx="0.18" cy="0.12" r="0.75"><stop offset="0" stop-color="${accent}" stop-opacity="0.22"/><stop offset="1" stop-color="${accent}" stop-opacity="0"/></radialGradient>` +
    `<radialGradient id="b" cx="0.9" cy="0.95" r="0.7"><stop offset="0" stop-color="${muted}" stop-opacity="0.18"/><stop offset="1" stop-color="${muted}" stop-opacity="0"/></radialGradient>` +
    `<radialGradient id="v" cx="0.5" cy="0.5" r="0.75"><stop offset="0.6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.35"/></radialGradient>` +
    `</defs>`;
  const full = (fill: string) => `<rect width="${w}" height="${h}" fill="${fill}"/>`;
  return open(canvas) + defs + full("url(#g)") + full("url(#a)") + full("url(#b)") + full("url(#v)") +
    shapes(regions, canvas, style, { bars: false }) + "</svg>";
}
