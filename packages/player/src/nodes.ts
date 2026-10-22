// Content-layer nodes (spec §8): one native DOM element per content entry,
// placed by percentage over the stage. Interactivity comes only from here;
// nothing is ever hit-tested against the picture.

import type { Content, ListItem } from "@videotape/core";

export type Value = string | number | boolean;

export interface NodeHost {
  press(id: string, el: HTMLElement): void;
  select(id: string, item: string, el: HTMLElement): void;
  /** A `commit: "change"` component changed. */
  change(id: string, value: Value): void;
  /** A `commit: "blur"` component committed. */
  commit(id: string, value: Value): void;
  /** Enter in a single-line input. */
  submit(fromId: string): void;
  hrefFor(id: string): string;
}

export interface VNode {
  id: string;
  kind: Content["kind"];
  el: HTMLElement;
  /** The element that takes focus and carries the accessible name. */
  focusable?: HTMLElement;
  commit?: Content["commit"];
  emphasis?: Content["emphasis"];
  value?(): Value;
  update(p: Partial<Content>): void;
}

/** Canvas px → CSS, scaled with the stage. */
export const px = (size: number) => `calc(var(--s) * ${Math.round(size * 10) / 10}px)`;

function place(el: HTMLElement, rect: Content["rect"]): void {
  const pct = (n: number) => `${Math.round(n * 1e6) / 1e4}%`;
  el.style.left = pct(rect[0]);
  el.style.top = pct(rect[1]);
  el.style.width = pct(rect[2]);
  el.style.height = pct(rect[3]);
}

function make<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, text?: string): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function a11y(el: HTMLElement, c: Content): void {
  if (c.a11y?.label) el.setAttribute("aria-label", c.a11y.label);
  if (c.a11y?.role) el.setAttribute("role", c.a11y.role);
}

function debounce<A extends unknown[]>(fn: (...a: A) => void, ms: number): (...a: A) => void {
  let t: ReturnType<typeof setTimeout> | undefined;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

export interface BuildState {
  /** Only the first title on a frame becomes the page's h1. */
  headingUsed: boolean;
}

export function createNode(c: Content, host: NodeHost, state: BuildState): VNode {
  const node = build(c, host, state);
  node.el.classList.add("vt-node");
  node.el.dataset.vtId = c.id;
  place(node.el, c.rect);
  a11y(node.focusable ?? node.el, c);
  return node;
}

function build(c: Content, host: NodeHost, state: BuildState): VNode {
  const size = c.type?.size ?? 40;
  switch (c.kind) {
    case "text": return textNode(c, state);
    case "button": {
      const b = make("button", `vt-button${c.emphasis === "primary" ? " is-primary" : ""}`, c.label ?? "");
      b.type = "button";
      b.style.fontSize = px(size);
      b.addEventListener("click", () => host.press(c.id, b));
      return { id: c.id, kind: c.kind, el: b, ...(c.emphasis ? { emphasis: c.emphasis } : {}), update: (p) => { if (p.label != null) b.textContent = p.label; } };
    }
    case "link": {
      const a = make("a", `vt-link${c.type?.align === "end" ? " is-end" : ""}`, c.label ?? "");
      a.href = host.hrefFor(c.id);
      a.style.fontSize = px(size);
      a.addEventListener("click", (e) => {
        e.preventDefault();
        host.press(c.id, a);
      });
      return { id: c.id, kind: c.kind, el: a, update: (p) => { if (p.label != null) a.textContent = p.label; } };
    }
    case "input": case "textarea": case "select": case "slider": case "date":
      return fieldNode(c, host);
    case "toggle": {
      const label = make("label", "vt-toggle");
      const box = make("input", "");
      box.type = "checkbox";
      box.setAttribute("role", "switch");
      box.name = c.id;
      box.checked = c.value === true;
      label.style.fontSize = px(size);
      label.append(box, make("span", "", c.label ?? ""));
      const commitMode = c.commit ?? "submit";
      box.addEventListener("change", () => {
        if (commitMode === "change") host.change(c.id, box.checked);
        else if (commitMode === "blur") host.commit(c.id, box.checked);
      });
      return {
        id: c.id, kind: c.kind, el: label, focusable: box, commit: commitMode, value: () => box.checked,
        update: (p) => { if (typeof p.value === "boolean") box.checked = p.value; },
      };
    }
    case "list": return listNode(c, host);
    case "image": {
      const img = make("img", "vt-image");
      img.alt = c.alt ?? "";
      img.decoding = "async";
      const set = (src: string | undefined) => {
        img.hidden = !src;
        if (src) img.src = src;
      };
      set(c.src);
      return { id: c.id, kind: c.kind, el: img, update: (p) => { if (p.src !== undefined) set(p.src ?? undefined); if (p.alt != null) img.alt = p.alt; } };
    }
    case "media": {
      const m = make(c.media === "audio" ? "audio" : "video", "vt-image");
      m.controls = true;
      m.preload = "metadata";
      if (c.src) m.src = c.src;
      return { id: c.id, kind: c.kind, el: m, update: (p) => { if (p.src) m.src = p.src; } };
    }
  }
}

function textNode(c: Content, state: BuildState): VNode {
  const role = c.type?.role ?? "body";
  const lines = c.type?.lines ?? 1;
  const heading = role === "display" || role === "title";
  const tag = heading ? (state.headingUsed ? "h2" : "h1") : role === "body" ? "div" : "p";
  if (heading) state.headingUsed = true;
  const el = make(tag, `vt-text vt-role-${role}`);
  if (tag === "h1") el.tabIndex = -1;
  const single = lines === 1 && role !== "body";
  const scroll = role === "body";
  if (single) el.classList.add("is-single");
  else if (scroll) el.classList.add("is-scroll");
  else el.classList.add("is-clamped");
  if (c.type?.align === "center") el.classList.add("is-center");
  if (c.type?.align === "end") el.classList.add("is-end");
  const base = px(c.type?.size ?? 40);
  el.style.fontSize = base;
  el.style.setProperty("--lines", String(lines));
  el.style.setProperty("--lh", heading || role === "number" ? "1.15" : role === "body" ? "1.45" : "1.3");

  const target = single ? el.appendChild(make("span", "")) : el;
  const set = (v: unknown) => {
    target.textContent = typeof v === "string" ? v : v == null ? "" : String(v);
    if (single) {
      el.title = target.textContent;
      // A fact must not be cut off: shrink a single line to fit (to 60 %) before it ellipsises.
      // Box and type both scale with the stage, so the ratio holds across resizes.
      requestAnimationFrame(() => {
        el.style.fontSize = base;
        const need = target.scrollWidth;
        const have = el.clientWidth;
        if (need > have && have > 0) el.style.fontSize = `calc(${base} * ${Math.max(0.6, have / need).toFixed(3)})`;
      });
    }
    if (scroll) queueMicrotask(() => requestAnimationFrame(() => {
      // A scrollable region must be reachable by keyboard.
      if (el.scrollHeight > el.clientHeight + 1) el.tabIndex = 0;
      else el.removeAttribute("tabindex");
    }));
  };
  set(c.value);
  if (c.id === "error" || role === "caption") el.setAttribute("aria-live", "polite");
  return { id: c.id, kind: c.kind, el, update: (p) => { if (p.value !== undefined) set(p.value); } };
}

function fieldNode(c: Content, host: NodeHost): VNode {
  const size = c.type?.size ?? 40;
  const search = c.kind === "input" && c.inputType === "search";
  const label = make("label", `vt-field${search ? " is-search" : ""}`);
  const caption = make("span", "vt-label", c.label ?? "");
  caption.style.fontSize = px(c.labelSize ?? size * 0.8);
  let control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
  if (c.kind === "textarea") {
    control = make("textarea", "");
  } else if (c.kind === "select") {
    const sel = make("select", "");
    for (const o of c.options ?? []) sel.append(new Option(o.label, o.value));
    control = sel;
  } else {
    const input = make("input", "");
    input.type = c.kind === "slider" ? "range" : c.kind === "date" ? "date" : ({ secret: "password", email: "email", number: "number", search: "search", text: "text" } as const)[c.inputType ?? "text"];
    if (c.kind === "slider") {
      input.min = String(c.min ?? 0);
      input.max = String(c.max ?? 100);
      input.step = String(c.step ?? 1);
    }
    input.autocomplete = c.inputType === "secret" ? "current-password" : /user|login/i.test(c.id) ? "username" : c.inputType === "email" ? "email" : "off";
    if (c.inputType === "secret" || /user|login|email/i.test(c.id)) {
      input.spellcheck = false;
      input.autocapitalize = "none";
    }
    control = input;
  }
  control.name = c.id;
  control.id = `vt-${c.id}`;
  if (c.placeholder && !(control instanceof HTMLSelectElement)) control.placeholder = c.placeholder;
  if (c.value != null) control.value = String(c.value);
  // Never below 16 CSS px, or mobile browsers zoom on focus (spec §8).
  control.style.fontSize = `max(16px, ${px(size)})`;
  label.htmlFor = control.id;
  label.append(caption, control);

  const commitMode = c.commit ?? "submit";
  const read = (): Value => (c.kind === "slider" ? Number(control.value) : control.value);
  if (commitMode === "change") {
    const send = debounce(() => host.change(c.id, read()), 250);
    control.addEventListener("input", send);
  } else if (commitMode === "blur") {
    control.addEventListener("change", () => host.commit(c.id, read()));
  }
  if (control instanceof HTMLInputElement && control.type !== "range") {
    control.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) {
        e.preventDefault();
        host.submit(c.id);
      }
    });
  }
  return {
    id: c.id, kind: c.kind, el: label, focusable: control, commit: commitMode, value: read,
    update: (p) => {
      if (p.options && control instanceof HTMLSelectElement) {
        const keep = control.value;
        control.replaceChildren(...p.options.map((o) => new Option(o.label, o.value)));
        control.value = keep;
      }
      if (p.value != null && document.activeElement !== control) control.value = String(p.value);
    },
  };
}

function listNode(c: Content, host: NodeHost): VNode {
  const wrap = make("div", "vt-list");
  if (c.label) {
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", c.label);
  }
  wrap.style.fontSize = px(c.type?.size ?? 40);
  const ul = make("ul", "");
  wrap.append(ul);
  const render = (items: ListItem[]) => {
    ul.replaceChildren(...items.map((item) => {
      const li = make("li", "");
      const b = make("button", "vt-item");
      b.type = "button";
      b.append(make("span", "", item.label));
      if (item.meta) b.append(make("span", "vt-meta", item.meta));
      b.addEventListener("click", () => host.select(c.id, item.id, b));
      li.append(b);
      return li;
    }));
  };
  render(c.items ?? []);
  return { id: c.id, kind: c.kind, el: wrap, update: (p) => { if (p.items) render(p.items); } };
}
