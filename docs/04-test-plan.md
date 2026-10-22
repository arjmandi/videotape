# Videotape — Test Plan, v1

**Date:** 2026-10-22 · **Status:** active · **Covers:** M0, M1, the start of M2 ·
**Companion:** [02-spec-v1.md](02-spec-v1.md)

The client–server split is the riskiest part of the design: the player trusts nothing it is not
told, the engine trusts nothing the player sends, and both sides read the same schemas. This plan
tests each contract on its own first, then the loop end to end with the AI switched off, then the
generative path against fakes. Nothing in CI calls a paid model.

---

## 1. Layers and tools

| Layer | What it proves | Tool | Runs in CI |
|-------|----------------|------|------------|
| L1 Contract | Schemas accept every documented message and reject malformed ones; tapes round-trip to JSON | Vitest | yes |
| L2 Core logic | Validation rules, graph, layout invariants, wireframe snapshots | Vitest + file snapshots | yes |
| L3 Engine in-process | Session lifecycle, event validation, handlers, secrets, data store, patches, cache keys, pipeline, fallbacks | Vitest, fake transport, fake renderers | yes |
| L4 Wire | The same journeys over a real WebSocket and real HTTP asset routes | Vitest + `ws` client against a live engine on a random port | yes |
| L5 Browser | Player behaviour: layers, scaling, keyboard, focus, screen-reader names, reconnect; every edge of the demo graph | Playwright (Chromium) against `flat` | yes |
| L6 Live smoke | A real hosted model produces scenes that pass region validation | `videotape render --renderers still` by hand, needs `FAL_KEY` | no (manual, costs money) |

## 2. Contract tests (L1)

- Every message in spec Appendix B parses with the VTP schemas in `@videotape/core`.
- Each message type has at least one rejected variant: missing `t`, wrong `v`, negative `seq`,
  a `value` over 4 KB, an unknown field type.
- The demo app serialises to JSON that parses with the tape schema, and the JSON carries no
  function bodies.
- JSON Schema export produces a document for the tape spec and for each VTP message.

## 3. Core logic tests (L2)

**Validation (`videotape check`)**: one minimal fixture per rule, asserting the exact code.

| Errors | Warnings |
|--------|----------|
| `duplicate-id` (tape, frame, component) | `unreachable-frame` |
| `unknown-frame` (goto) | `handler-without-outcomes` |
| `unknown-tape` (jump, app entry) | `no-exit` |
| `unknown-slot`, `slot-taken`, `no-slot-available` | `closed-cycle` |
| `no-action` (button, link, list without one) | `scene-reads-input` |
| `unknown-handler` | `multiple-primary` |
| `secret-bind` | `unused-values` (inputs but no handler) |
| `bad-event` (event not allowed for the kind) | |
| `unknown-style`, `missing-rect` (blank archetype) | |

The demo app must produce zero errors and zero warnings.

**Graph**: edge extraction from static actions and declared outcomes; `back` edges marked dynamic;
reachability from the entry; terminal cycles; Mermaid output is stable.

**Layout**, checked for every archetype × viewport class and for every demo frame × class:

1. Every component is placed exactly once; no region falls outside the safe area.
2. No two `z: 2` regions overlap.
3. Phone touch targets: every interactive region is at least 44 CSS px tall and wide on a
   375 × 667 viewport, after the player's scaling rule.
4. Same input produces the same JSON and SVG (deterministic).
5. File snapshots of wireframe JSON and SVG for every demo frame × class (the M0 exit criterion).

**Flavour tracing**: reads through a recorded proxy are reported as paths; writes are ignored.

## 4. Engine tests (L3)

All of these run in-process with a fake transport that records outgoing messages.

| Area | Cases |
|------|-------|
| Session | `hello` gives `welcome` then `render` at the entry; viewport snaps to the right class at 599/600 and 1023/1024; `resume` with a valid token restores head and data; a bad token starts fresh |
| Event validation | Unknown component, an event the kind does not emit, an event the frame does not handle, a wrong value type, a value over 4 KB, a stale `render` seq, a replayed `seq`: each is dropped, logged, and the head does not move |
| Actions | `goto` moves within the tape; `jump` pushes history and merges data; `back` pops; `back` on an empty stack stays; `stay` sends a `patch` with only the changed components |
| Handlers | Receives committed `values`; an outcome it did not declare is allowed and logged; a thrown error gives a recoverable `error` and the head stays |
| Enter hook | Runs before the first render of a frame, on arrival by `goto`, `jump`, and `back`; its patch is visible in that render |
| Secrets | A `secret` value reaches the handler, is never in the data store, any log line, any `patch`, or any `render` |
| Render | Bound values are resolved; content is in slot order; edges list resolved targets, including the concrete `back` target |
| Cache key | The same frame, class, style, and flavour give the same key; reel data does not change the key; flavour, class, seed, and renderer version do |
| Prefetch | After a render, a `prefetch` lists the scene of every outgoing edge's target |
| Resize | A class change sends a new render; a change within the class sends nothing |

## 5. Wire tests (L4)

A real engine on a random port and a `ws` client walk landing → login (wrong password, then right)
→ dashboard → report → back → dashboard. Asset URLs from `render.layers` return 200 with
`Cache-Control: public, max-age=31536000, immutable` and the right content type, and the same URL
returns byte-identical bodies across two sessions.

## 6. Browser tests (L5)

Playwright against `videotape serve apps/site` with the `flat` renderer, at phone 375 × 667,
tablet 768 × 1024, and desktop 1440 × 900.

1. **Graph walk (S5).** Read the demo graph from `@videotape/core`, and for every edge find a path
   from the entry, follow it in the browser, trigger the edge, and assert the new head shown in the
   HUD. Handler edges use a small fixture table (for example, login with good credentials goes to
   the dashboard, with bad ones it stays and shows the error).
2. **Keyboard only (M1 exit).** From the landing page, Tab to "Sign in", type credentials, press
   Enter in the password field, reach the dashboard, open the report, press Escape to go back. No
   mouse events.
3. **Screen-reader names (S2).** Every interactive element is found by role and accessible name
   (`getByRole('textbox', { name: 'Username' })` and so on); an axe scan reports no serious or
   critical violations on each frame.
4. **Layers and alignment.** The scene image fills the stage; each content node's box matches its
   region within 1 CSS px at every size; the content layer is disabled while a transition is in
   flight and re-enabled after.
5. **Resilience.** Kill the socket: the picture stays, content is disabled, a badge shows, and the
   player reconnects with its resume token to the same head.
6. **Mobile basics.** Inputs compute to at least 16 px font size on the phone viewport.

## 7. Generative path against fakes (start of M2)

| Area | Cases |
|------|-------|
| Region validation | Synthetic images: a flat dark field passes; a high-variance noise field fails on variance; a mid-grey field fails on contrast with a light foreground colour; faint fake words in a field and on a button face fail on lettering although their spread passes; every flat scene of the demo passes |
| Conditioning | Generative renderers get the scene drawing, not the wireframe; editing a style's prompt changes the cache key |
| Re-roll | A fake renderer that fails validation twice, then passes, is called three times with seeds `s`, `s+1`, `s+2`; one that always fails ends with a flat fill composited into the failing regions only, and the HUD counters say so |
| Budgets | A fake renderer slower than 1.5 s on the first render gives a `flat` render with `fallback: true`, then a `patch` with `layers` when the asset lands |
| Cache | A second session over the same frames is served at least 90 % from the cache (counting renderer calls); re-rolls coexist in the manifest |
| fal renderer | With `fetch` mocked: the request carries `Authorization: Key …` from the environment, the model id from config, the wireframe as a data URI, the composed prompt, and the seed; non-2xx gives a typed error; abort cancels the request; no key means the renderer reports itself unavailable and the engine uses `flat` |
| Ahead-of-time | `videotape render --viewports phone,desktop` fills the cache, and a following `serve` session has no misses |

## 8. What is not covered yet

- Real-model quality (text crispness, region stability across reloads, the M2 ≥ 90 % hit rate on
  real renders) needs a key and is checked by hand with L6.
- Lettering is checked with OCR, which reads text a person would read. Lettering faint enough to
  slip past it (03-landscape §2.2) is also below what a person notices, but the check cannot rule
  out fake controls drawn without any text; review the contact sheet for new styles.
- Cuts (`renderer-cut-*`) and the 300 ms prefetched-click budget belong to M3.
- Real screen-reader runs (VoiceOver, NVDA) are manual; CI checks names, roles, and axe rules only.
