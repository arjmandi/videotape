// Viewport classes and the stage scaling rule (spec §6.1). Shared by the
// engine, which snaps a viewport to a class, and the player, which fits the
// canonical canvas into the window.

export const VIEWPORT_CLASSES = ["phone", "tablet", "desktop"] as const;
export type ViewportClass = (typeof VIEWPORT_CLASSES)[number];

export interface Size {
  w: number;
  h: number;
}

export const CANVAS: Record<ViewportClass, Size> = {
  phone: { w: 1080, h: 1920 },
  tablet: { w: 1536, h: 2048 },
  desktop: { w: 1920, h: 1080 },
};

/** Fraction of the canvas kept clear on each side. */
export const SAFE_MARGIN = 0.06;

export function viewportClass(widthCssPx: number): ViewportClass {
  if (widthCssPx < 600) return "phone";
  if (widthCssPx < 1024) return "tablet";
  return "desktop";
}

export interface StageFit {
  /** CSS px per canvas px. */
  scale: number;
  /** Stage box in CSS px, relative to the viewport. */
  x: number;
  y: number;
  w: number;
  h: number;
  /** True when the stage covers the viewport; false when edges need the blurred extension. */
  covers: boolean;
}

/**
 * `min(cover, safe-fit)`: cover the viewport unless that would crop into the
 * safe area, in which case shrink just enough to keep the safe area visible.
 */
export function stageFit(viewport: Size, canvas: Size, margin = SAFE_MARGIN): StageFit {
  const cover = Math.max(viewport.w / canvas.w, viewport.h / canvas.h);
  const inner = 1 - 2 * margin;
  const safeFit = Math.min(viewport.w / (canvas.w * inner), viewport.h / (canvas.h * inner));
  const scale = Math.min(cover, safeFit);
  const w = canvas.w * scale;
  const h = canvas.h * scale;
  return { scale, w, h, x: (viewport.w - w) / 2, y: (viewport.h - h) / 2, covers: scale === cover };
}
