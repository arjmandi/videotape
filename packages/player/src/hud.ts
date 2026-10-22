// The debug HUD (spec §8): region outlines with mask colours, the head, cache
// details, the last transition's timing, and outgoing edges with prefetch state.

import type { RenderMessage } from "@videotape/core";

export class Hud {
  readonly layer: HTMLDivElement;
  readonly panel: HTMLDivElement;
  enabled = false;
  visible = false;

  constructor(stage: HTMLElement, root: HTMLElement) {
    this.layer = document.createElement("div");
    this.layer.className = "vt-hud";
    this.layer.hidden = true;
    this.layer.setAttribute("aria-hidden", "true");
    stage.append(this.layer);
    this.panel = document.createElement("div");
    this.panel.className = "vt-hud-panel";
    this.panel.hidden = true;
    this.panel.setAttribute("aria-hidden", "true");
    root.append(this.panel);
  }

  toggle(force?: boolean): void {
    if (!this.enabled) return;
    this.visible = force ?? !this.visible;
    this.layer.hidden = !this.visible;
    this.panel.hidden = !this.visible;
  }

  show(r: RenderMessage, extra: { transitionMs?: number; prefetch: Map<string, string> }): void {
    if (!this.enabled) return;
    this.layer.replaceChildren(...r.regions.map((g) => {
      const d = document.createElement("div");
      d.className = `vt-hud-region is-${g.kind === "panel" ? "panel" : g.mask}`;
      d.style.left = `${g.rect[0] * 100}%`;
      d.style.top = `${g.rect[1] * 100}%`;
      d.style.width = `${g.rect[2] * 100}%`;
      d.style.height = `${g.rect[3] * 100}%`;
      d.textContent = g.id;
      return d;
    }));
    const dbg = r.debug ?? {};
    const lines = [
      `head      ${r.head.tape}/${r.head.frame}   seq ${r.seq}`,
      `key       ${r.key.slice(0, 23)}…`,
      `scene     ${String(dbg.renderer ?? "?")} · ${String(dbg.cache ?? "?")}${r.fallback ? " · FALLBACK" : ""}${dbg.ms !== undefined ? ` · ${String(dbg.ms)} ms` : ""}`,
      ...(dbg.rerolls !== undefined ? [`rerolls   ${String(dbg.rerolls)}${Array.isArray(dbg.patched) ? ` · patched ${dbg.patched.join(",")}` : ""}`] : []),
      ...(extra.transitionMs !== undefined ? [`click→frame ${Math.round(extra.transitionMs)} ms`] : []),
      ...(dbg.stats ? [`host      ${JSON.stringify(dbg.stats)}`] : []),
      "edges",
      ...r.edges.map((e) => {
        const to = e.to ? `${e.to.tape}/${e.to.frame}` : e.kind;
        const state = extra.prefetch.get(`${e.component}:${e.event}`) ?? "—";
        return `  ${e.component}·${e.event}${e.handler ? `⇒${e.handler}` : ""} → ${to}  [${state}]`;
      }),
    ];
    this.panel.textContent = lines.join("\n");
  }
}
