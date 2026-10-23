# Videotape — Design v2

**Date:** 2026-10-23 · **Status:** draft for decision; no code yet · **Supersedes:** the concept of
[02-spec-v1.md](02-spec-v1.md) · **Evidence:** [03-landscape.md](03-landscape.md) §2 (live runs)
· **Prototype:** tag `prototype-0` (the v1 spec, built and measured)

---

## 0. Why a v2

Prototype-0 built the v1 spec faithfully: tapes of frames, a thin player, a server engine, a layout
engine with three viewport classes and seven templates, and a generated picture behind native DOM
controls. It works, and it is not new. A thin client is server-driven UI; a generated background
behind ordinary controls is a skin. Worse, the v1 design ruled out the parts that would have been
new:

| v1 commitment | Effect |
|---------------|--------|
| "The generator never renders a fact" and "no pixel-derived interactivity" (principles 2, 6) | The picture may not contain controls; the harness rejected generated controls as defects. |
| "A frame is one screen" (N7) and a statically checked graph | A frame cannot be broken down or merged at runtime. |
| Three viewport classes with fixed canvases (§6.1) | A watch gets a phone canvas with 20 px buttons; a phone turned sideways gets a portrait tablet canvas using 42 % of the screen. |
| Real-time generation as a non-goal (N1); generation as ahead-of-time compilation | The UI is a still with a crossfade, never a live picture. |
| Templates and slots chosen by the developer | Layout code under another name. |

v2 keeps what prototype-0 proved (§15) and redesigns the concept.

## 1. The thesis

> **The interface is a live, generated picture of a world. The developer declares what the
> interface must do; the designer declares the world it lives in; the device declares where it is
> shown. The engine composes, embodies, renders, and verifies the picture continuously, and the
> harness guarantees that what you see is what you can operate.**

- **Generative UI by video, not by code.** Generative-UI projects today write front-end code on the
  fly. Videotape writes no front-end code at all, at any time: there is a declaration of intent,
  and there is a picture. Between them is an engine.
- **Controls live in the world.** A tree trunk can be the button; a flag can be the field you write
  on; a sheet of paper can be the form. The engine decides which object embodies which control, and
  the harness checks that the object is really there, really where the control is, and nothing
  else in the picture pretends to be a control.
- **The canvas is a camera on a set.** A screen size is not a template to pick; it is a camera on a
  world bigger than any screen. Changing the screen moves the camera at once, recomposes the objects
  soon after, and re-renders the world shortly after that.
- **Built for next year's models.** Real-time, controllable video is close but not here. The product
  is the harness that makes such models behave as interfaces; today it runs on slower models and
  deterministic fallbacks, and it gets better every time a better model is plugged in.

What stays from v1, because it was right: the journey is the program (tapes, frames, handlers,
edges, a graph you can check); facts the user must trust come from code, never from the generator;
accessibility comes from the declaration, not from pixels; everything works with the AI switched
off.

## 2. Goals, non-goals, success criteria

### 2.1 Goals
- **G1 Intent-only authoring.** No layout, style, routing, or screen code. Developers declare
  components, their roles and relations, data, and handlers.
- **G2 Any canvas.** From a watch face to a wall display, portrait or landscape, with no device
  detection: only measurements. Reaction to a canvas change: the camera within 100 ms, a new
  composition within 300 ms, a re-rendered picture within about 1 s on the live tier.
- **G3 Composition that adapts.** Frames break down into steps when the canvas is small and merge
  with neighbours when it is large; groups re-arrange by priority and relation.
- **G4 Embodied controls.** Components appear as objects of the world, under an affordance contract.
- **G5 Exact facts.** Every string, number, and value comes from code and is legible on the object
  that carries it.
- **G6 Accessible by construction.** Roles, names, focus order, and keyboard paths come from intent.
- **G7 Live video is the main path.** Stills and the deterministic proxy are tiers below it, and
  the interface stays operable on every tier.
- **G8 A measurable harness.** Grounding, legibility, stability, latency, and cost are scored per
  frame and tracked over time.

### 2.2 Non-goals for v2
- Training a video model. We condition and, at most, fine-tune existing ones.
- Native apps for every platform. The player is a web page; native shells are thin wrappers
  (see Q11 for watches).
- Multi-user sessions, persistence beyond the session, SEO.
- Letting the generator render facts. Burn-in is an open question (Q1), not a goal.

### 2.3 Success criteria (the v2 demo shows all of these)
- **S1** The same tapes play on a watch-sized canvas (about 200 × 240), a phone in portrait and
  landscape, a desktop, and a wall display, with no per-device code.
- **S2** Rotating a phone moves the camera within 100 ms and settles a new composition within
  300 ms; the live tier shows the recomposed world within about 1 s.
- **S3** A 20-field form on a watch-sized canvas becomes a derived tape of steps; on a wall display
  a list frame and its detail frame merge into one shot. Handlers are unchanged.
- **S4** The same tapes under two worlds (a surf shack; a quiet modern office) produce different
  embodiments for the same components, and both pass grounding.
- **S5** The harness catches a moved control, a missing control, and a phantom control, and recovers
  without the user losing input.
- **S6** Keyboard-only and screen-reader runs pass on every tier.
- **S7** Cost per active minute and the fallback rate per tier are reported.

## 3. Vocabulary

| Term | Meaning |
|------|---------|
| **Intent** | What the developer declares: tapes, frames, components, roles, relations, data, handlers. |
| **World** | What the designer declares: the place, mood, materials, and embodiment hints. |
| **Context** | What the device reports: canvas size, density, orientation, input methods, motion and colour preferences, network. |
| **Tape / frame** | As in v1: a journey and one purposeful step of it. A frame is no longer one screen. |
| **Shot** | What is on screen at once: one frame, part of one (a step), or several merged. |
| **Composition** | The engine's plan for a context: shots, groups, placements, and any derived tape. |
| **Derived tape** | Steps and edges the engine creates when it breaks a frame down. |
| **Embodiment** | The world object a component appears as, with its affordance contract. |
| **Set** | The arrangement of a tape's objects in world space, larger than any canvas. |
| **Camera** | The view of the set that a canvas shows. |
| **Proxy** | A deterministic rendering of the set: each object as a labelled, flat-shaded shape. It conditions generators and is the AI-off tier. |
| **Object map** | Per rendered frame: object id ↔ component ↔ hit area ↔ fact surface. The interaction map. |
| **Grounding** | Checking that a rendered frame agrees with the object map. |
| **Tier** | A rendering level: live video, stills and cuts, or proxy. |

## 4. Architecture

```
      INTENT (developer)        WORLD (designer)              CONTEXT (device, continuous)
            │                         │                                 │
            ▼                         ▼                                 ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────┐
 │ ENGINE                                                                               │
 │  Composer ──► Embodier ──► Director (set, camera) ──► Renderer tiers ──► Grounder    │
 │  shots,        objects &      world-space layout,       live │ stills │ proxy   checks│
 │  steps,        contracts      reframing                       ▼                 │     │
 │  merges                                                  picture + object map ◄─┘     │
 │                                                                                      │
 │  Journey runtime (reels, handlers, values, derived tapes) — as in v1, extended       │
 └──────────────────────────────────────────────────────────────────────────────────────┘
            │ picture stream (WebRTC for live; images for stills)   ▲ events on objects
            │ object map + facts + accessibility tree (data channel)│ context changes
            ▼                                                       │
 ┌──────────────────────────────────────────────────────────────────────────────────────┐
 │ PLAYER: video surface · interaction map (hit areas from the object map) ·            │
 │         native text on fact surfaces · native inputs transformed onto surfaces ·     │
 │         an accessibility tree from intent · camera reframing between compositions    │
 └──────────────────────────────────────────────────────────────────────────────────────┘
```

Three loops run at different speeds:

| Loop | Trigger | Work | Budget |
|------|---------|------|--------|
| **Camera** | Canvas change | Reframe the current picture and transform the object map (player, local) | ≤ 100 ms |
| **Composition** | Canvas change, data change, navigation | Recompose, re-embody if needed, update the set and the proxy | ≤ 300 ms |
| **Render** | Continuous on the live tier; per shot on stills | Generate the picture from the proxy and the world; ground it | Live: about 1 s to settle; stills: seconds, proxy shown meanwhile |

## 5. Intent

Intent keeps v1's tapes, frames, components, actions (`goto`, `jump`, `back`, `stay`), binds,
handlers, and enter hooks. It drops every presentation field: no `layout`, `slot`, `rect`, or
template. In their place, components say what they are for.

```ts
const register = tape("register", {
  frames: [
    frame("details", {
      purpose: "Collect what we need to open an account",
      components: [
        text("title", "Create your account", { role: "heading" }),
        group("name", { label: "Your name", keepTogether: true }, [
          input("first", { label: "First name", required: true }),
          input("last", { label: "Last name", required: true }),
        ]),
        input("email", { label: "Email", type: "email", required: true }),
        // … seventeen more fields, some grouped
        toggle("news", { label: "Send me news", importance: "optional" }),
        button("create", "Create account", { role: "primary", on: { press: "create" } }),
      ],
      breakdown: { allowed: true },
      on: { create: handler(async ({ values, services }) => /* … */, { outcomes: [jump("welcome"), stay()] }) },
    }),
  ],
});
```

What components can declare:

| Field | Meaning |
|-------|---------|
| `role` | heading, primary, secondary, navigation, status, supporting, … |
| `importance` | `required` (always shown), `normal`, `optional` (may be deferred to a later step or folded) |
| `group` | Components that belong together; `keepTogether` forbids splitting them across steps |
| `order` | Reading order, when declaration order is not it |
| `relations` | `labels`, `summarises`, `dependsOn`, `follows`: what the composer must keep near or in order |

What frames can declare: `purpose` (one line, used by embodiment and the coherence critic),
`breakdown` (allowed or not, and hooks), and `merge` (which neighbouring frames may share a shot).

Handlers do not change when a frame is broken down: values collected across steps are buffered by
the engine and delivered to the original handler as one `values` object, exactly as if the frame
had been one screen.

## 6. World

A world is the designer's declaration of where the interface lives.

```ts
export default world("surf-shack", {
  prompt: "A sunlit surf shack at golden hour: boards on racks, a chalkboard, coiled rope, sand on
           wooden floors. Warm, unhurried, a little salt in the air.",
  palette: { base: "#2b1d14", ink: "#f6ecd9", accent: "#ff8a3d" },
  references: ["worlds/surf/ref-1.jpg"],
  embody: {
    "button.primary": "a carved driftwood sign",
    "input.text": "a paper tag tied on with string",
    list: "boards on a rack, one per item",
  },
});
```

- **Embodiment hints** are optional. Without them the embodier chooses (§8).
- **Coherence.** A critic compares the world with the intent (domain, density, tone) before any
  pixel is generated and warns about strained pairings: a forty-field expense approval in a surf
  shack, say. It warns; it does not block. Quality depends on the pairing, and the designer should
  know early.
- **Worlds are swappable.** The same tapes can run in different worlds, per app, per tape, or per
  context (Q6).

## 7. Context

The player measures and streams context; the engine never detects devices.

```ts
interface Context {
  canvas: { w: number; h: number; dpr: number };        // CSS px; continuous, not bucketed
  pointer: "coarse" | "fine" | "none";
  inputs: Array<"touch" | "mouse" | "keyboard" | "crown" | "voice">;
  prefers: { reducedMotion: boolean; colorScheme: "dark" | "light"; contrast: "more" | "no-preference" };
  locale: string;
  network: { rttMs: number; kbps: number };
  tiers: Array<"live" | "stills" | "proxy">;            // what this client can play
}
```

CSS pixels are close enough to visual angle to set legibility and touch minimums without knowing
the device. Orientation is just the aspect ratio. A change of context is an event like any other,
debounced at the camera loop's rate and coalesced for the composition loop.

## 8. Composition engine (replaces the layout engine)

The composer is a pure function of `(intent for the current frame and its neighbours, context,
world-derived sizes)` that returns a composition. It runs on every relevant change and must finish
in under 50 ms.

### 8.1 Capacity
Each component has a minimum footprint for the context: its kind's legibility and target minimums
(for example, 44 CSS px touch targets on coarse pointers), its label, its embodiment's minimum size,
and its facts' length. The canvas has a usable area after safe margins and pinned items (title,
primary action, navigation). Capacity is the comparison of the two.

### 8.2 One shot, breakdown, or merge
- **Fits:** one shot. Place components by role, relation, and reading order; score placements for
  proximity of related items, reachability of the primary action (thumb zone on coarse pointers),
  and room for the world's subject.
- **Does not fit: breakdown.** Partition components into steps: keep groups whole, keep order, put
  required items before optional ones, pin the title to every step and the primary action to the
  last, and add generated "next" and "back" edges. If a single group cannot fit, split it unless it
  is `keepTogether`; then fall back to a plainer embodiment; scrolling inside a shot is the last
  resort. The result is a **derived tape**.
- **Room to spare: merge.** If the frame declares (or the composer may infer, Q5) mergeable
  neighbours, place them in one shot: a list and its detail, a dashboard and the report it opens.
  An edge between merged frames becomes a change of focus within the shot, not a cut.

### 8.3 Developer control
Hooks receive the engine's plan and may change it: `breakdown(plan, context) => plan`,
`merge(plan, context) => plan`. Plans are data, so hooks are testable. A frame can opt out of
breakdown or merge entirely.

### 8.4 Stability
Small canvas changes must not reshuffle the interface. The composer keeps object identity stable
across compositions, applies hysteresis (a new composition only when capacity crosses a threshold
or placements would violate minimums), and hands the director moves, not replacements, so objects
glide to new places.

### 8.5 Static guarantees, kept
`videotape check` still knows every journey before anything runs. It runs the composer for a set of
reference contexts (watch, phone portrait and landscape, tablet, desktop, wall) and verifies that
every authored edge survives in every derived tape, every required component is reachable, every
primary action is reachable, and every minimum is met. The graph is no longer one static graph; it
is a static graph plus derived graphs that are checked for a known set of contexts.

## 9. Embodiment

The embodier gives every placed component an object of the world.

```ts
interface Embodiment {
  component: string;                 // which component
  description: string;               // "a carved driftwood sign, sun-bleached, rope-hung"
  affordance: {
    press?: true;                    // must read as something you press
    write?: { lines: number };       // must offer a surface you write on
    read?: { maxChars: number };     // must offer a surface that carries text
    choose?: { options: number };    // must show distinct choices
  };
  factSurface?: "front" | "top" | "inside";
  minSize: { w: number; h: number }; // CSS px at the reference context
  states: Partial<Record<"hover" | "pressed" | "focused" | "disabled" | "error", string>>;
  fallback: "plain";                 // what to use when the world cannot host it
}
```

- **How it is chosen.** A language model proposes embodiments for each component kind and role in
  a world, once per (world, kind, role), and the result is cached and reviewable. Designers can pin
  or override any choice; developers can override per component.
- **Consistency.** Within a tape, the same kind and role keep the same embodiment, so users learn
  the world's vocabulary once.
- **States** are part of the contract. On the live tier they are conditioning changes in the proxy
  (a pressed sign tilts); on stills they are pre-rendered variants or overlays.
- **Plain fallback.** Every embodiment has a plain form (a panel, a field) that the world can always
  host. Prototype-0's native controls over a calm picture become this fallback.

## 10. Set and camera

The director turns a composition into a **set**: objects placed in world space, plus the world
around them, in layers with depth. A set is larger than any canvas, so a canvas is a camera on it.

| Event | What happens | Budget |
|-------|--------------|--------|
| Canvas grows or rotates | The camera reframes the current picture; the object map is transformed with it. Pictures are rendered oversize (or outpainted) so reframing never shows an edge. | ≤ 100 ms, in the player |
| Capacity threshold crossed | The composer recomposes; objects move in the set; the proxy animates them | ≤ 300 ms |
| New placements settle | The live tier re-renders from the new proxy; stills tier fetches or generates a new plate | about 1 s live; seconds on stills |
| Navigation | The camera travels through the set to the next shot; a generated cut on stills, continuous video on live | per tier |

This is where the "head moving along the tape" metaphor becomes literal: moving through the
journey is moving the camera through a world.

## 11. Rendering tiers

| Tier | What it is | Conditioning | When |
|------|------------|--------------|------|
| **Live** | Real-time video-to-video: the proxy stream in, the world out, at 20–30 fps | The proxy (structure and object identity), the world prompt, references | The main path whenever the client and budget allow |
| **Stills** | Generated plates per shot and generated cuts between shots | The proxy frame, the world prompt; inpainting to place objects | When live is unavailable or too costly; also to warm the cache |
| **Proxy** | The deterministic rendering of the set | — | AI off, CI, every fallback, and the first frame while anything else loads |

- **The proxy is the contract.** Every object is drawn with a stable identity (an id colour in a
  separate channel), depth, and its affordance shape. Generators restyle it; the grounder compares
  their output with it.
- **Tier choice** is per session and per object: an object that keeps failing grounding falls back
  to its plain embodiment while the rest of the picture stays generated.
- **Economics.** Live streams cost per minute (vendor claims of a few dollars an hour, list prices
  far higher); stills cost per image and cache well. The engine reports cost per active minute and
  chooses tiers against a budget (Q10).

## 12. Facts on generated surfaces

- Every string, number, and value is rendered by the player from code, onto the fact surface of the
  object that carries it: a quad in screen space, updated with the object map, so the text follows
  the object's perspective.
- Typing stays native. The input element is placed and transformed onto the writable surface, so
  the caret, selection, IME, autofill, and password managers behave normally.
- Legibility comes first: when the surface cannot carry the text at the required contrast, the
  player adds a scrim on the surface, and the grounder records it.
- The accessibility tree comes from intent and is always present. Screen readers never depend on
  pixels.

## 13. Grounding harness

Prototype-0's harness kept the generator out of the interface. v2's harness keeps it **in** the
interface, correctly. Its policy:

> The picture must contain every control the object map declares, where the map declares it, in a
> form that affords its use; it must contain nothing else that looks like a control or like text;
> and every fact surface must carry its text legibly.

| Check | How | Runs |
|-------|-----|------|
| **Presence and placement** | Correspondence between the proxy's object regions and the output (structure similarity per object region); open-vocabulary detection for the stills tier | Every still; sampled frames on live |
| **Affordance** | A vision-language judge: does this region read as something you can press, write on, choose? | Offline and on new embodiments |
| **Phantom controls and text** | OCR (prototype-0's lettering check) and a detector for control-like objects outside the map | Every still; sampled on live |
| **Fact surfaces** | Calm and contrast under projected text (prototype-0's whole-region and tile spread) | Every frame that shows facts |
| **Stability** | Object drift and identity across frames on the live tier | Continuous |
| **Latency** | Camera, composition, and render budgets per loop | Continuous |

On failure: re-roll a still, re-condition or reset the live stream, fall back one object to its
plain embodiment, or drop a tier, in that order. Hit areas always come from the composition; the
grounder may only shift them within a tolerance (Q2).

The same checks, run over reference worlds and contexts, form the offline evaluation suite. It is
the ratchet: plug in a better model, rerun the suite, and the scores say how much of the interface
can be generated.

## 14. Protocol, sketched

v2 keeps VTP's session model: hello, resume, events validated against what is on screen, sequence
guards, secrets kept out of everything. It changes what flows:

| Direction | Message | Carries |
|-----------|---------|---------|
| C→S | `hello`, `context` | Context, then context deltas |
| S→C | `composition` | Shots, the current shot, derived steps and edges, the accessibility tree, facts |
| S→C | `objects` | The object map, keyed to a picture timestamp (live) or a plate (stills) |
| S→C | `stream` / `plate` | Live tier negotiation (WebRTC) or a still to show |
| S→C | `patch` | Changed facts and states |
| C→S | `event` | Object id, event type, value, the composition version and picture timestamp it was made against |

## 15. What carries over from prototype-0

| Prototype-0 part | In v2 |
|------------------|-------|
| Tape model, actions, binds, handlers, enter hooks, `check`, graph | Kept; presentation fields removed; check extended to derived graphs |
| Layout engine (templates, slots, three classes) | Replaced by the composer; its free-space search and touch-target rules are reused |
| VTP sessions, event validation, sequence and render guards, resume, secrets handling | Kept; payloads change (§14) |
| Engine reels, handler runtime, budgets and fallbacks, renderer host | Kept and generalised to tiers |
| Cache keys that cover every input; validator versions and re-checks of cached assets | Kept |
| Region validation (spread, tile spread, contrast), OCR lettering, attempt logs, contact sheets | Kept as parts of the grounder |
| Flat renderer | Becomes the proxy renderer |
| fal still renderer | Becomes the stills tier, conditioned on the proxy |
| Player | Rewritten: video surface, interaction map, transformed native inputs |

Lessons from the live runs ([03-landscape.md](03-landscape.md) §2) that shape v2:

1. Image-to-image follows structure only at moderate strength (≈ 0.8). At 0.95 it ignores the
   drawing, including where its subject should go. Placement needs constraints (inpainting, object
   conditioning), not prompt words.
2. Shown a drawing that looks like a UI, a model paints a UI, with fake text. v2 wants that, but
   only through the object map: what the model paints must be declared.
3. OCR cleanly separates fake lettering from scenery; edge density does not.
4. Spread over a whole region misses a small object behind a few words; tiles catch it, at the price
   of also catching busy but legible backgrounds.
5. A still takes 10–50 s with re-rolls. Nothing generative fits a 1 s budget today without the live
   tier; the camera and proxy loops must carry the interface until it does.
6. Backends fail in ordinary ways (503s, locked accounts). The engine must fail once and fall back,
   not retry into every request.

## 16. Risks

| Risk | Mitigation |
|------|------------|
| Real-time models restyle well but do not keep object-level fidelity | The proxy carries identity; grounding measures fidelity; per-object plain fallback; experiment E4 decides how much is possible today |
| Users do not recognise an embodied control | Affordance contract and judge; focus and hover cues; a consistent vocabulary per world; a plain-mode switch (Q7) |
| Facts become hard to read on textured surfaces | Fact surfaces checked every frame; scrims; plain fallback |
| Breakdown surprises developers | Plans are data; hooks; `check` shows derived tapes for every reference context |
| Cost per active minute | Tiers, budgets, caching sets per world and context bucket |
| Latency across the network | The camera loop is local; composition is fast and could run in the player (Q8) |
| A world prompt or data steers the generator into deception | The generator never receives reel data; phantom-control checks; interactivity only from the composition |
| Grounding is wrong on stylised images | Correspondence with the proxy first, detectors second; human review of new worlds |

## 17. Plan: experiments first

No product code until the experiments answer whether each part can work.

| # | Experiment | Answers | Output |
|---|------------|---------|--------|
| E1 | Composer on paper and in a pure TypeScript sketch: the 20-field form and the demo journey across reference contexts | Is capacity-driven breakdown and merge legible and stable? | Plans and wireframes per context |
| E2 | Embodiment: a language model maps the demo's components into three worlds | Are embodiments consistent and recognisable? | Embodiment tables, reviewed by you |
| E3 | Stills with placement: proxy-conditioned generation plus inpainting into object masks | Do objects land where the map says, with usable fact surfaces? | Grounding scores per object |
| E4 | Live: a real-time video-to-video model (Decart's family, on Decart or fal) over a proxy stream with moving objects | Latency, object stability, fact legibility on the live tier | Measured numbers in 03-landscape |
| E5 | Camera: oversize plates and reframing between watch, phone portrait, phone landscape, and desktop | Can reframing hold the interface while recomposition and rendering catch up? | A clickable sketch |

Then the build, in order: composer, proxy tier, and player v2 with the AI off; embodiment and the
stills tier with grounding; the live tier; breakdown and merge hooks and the demo.

## 18. Open questions

Each has the default this document assumes. Confirm or change.

| # | Question | Default |
|---|----------|---------|
| Q1 | May the generator render facts (text, numbers) itself, verified by OCR, or are facts always drawn by the player on fact surfaces? | Always drawn by the player. Burn-in only as a later experiment. |
| Q2 | Do hit areas come only from the composition, or may grounding move them to where the object was actually painted? | From the composition; grounding may shift within a small tolerance, otherwise it fails the frame. |
| Q3 | Which tier does the first demo lead with: live video, or stills with embodied objects? | Stills with embodiment first (E3), live in parallel as an experiment (E4); live becomes the main path when E4 passes. |
| Q4 | Does the engine break frames down by default, with developers opting out, or only where developers opt in? | By default, with opt-out and hooks. |
| Q5 | May the composer infer which frames merge from the graph, or only merge frames that declare it? | Only declared merges in v2; inference later. |
| Q6 | One world per app, per tape, or per context (night, locale, user preference)? | Per app, overridable per tape. Context-driven worlds later. |
| Q7 | Should users always have a plain mode (embodiments off, plain controls)? | Yes, as an accessibility and trust feature. |
| Q8 | Where does composition run: on the server only, or also in the player for instant reaction? | Server is the source of truth; the player runs the same pure composer to predict, and the server confirms. |
| Q9 | Are sets cached per world and context bucket (shared, cheap) or per user (personal, costly)? | Per world and context bucket; facts make them personal. |
| Q10 | What budget per active minute should the demo hold to, and who pays for the live tier? | Set after E4 measures it. |
| Q11 | Watches have no general web browser. Is a watch-sized canvas in a browser enough for the demo, or do we need a minimal native watch player? | A watch-sized canvas in the browser for v2; a native shell later. |
| Q12 | Which language model proposes embodiments and runs the coherence critic, and only at build time or also at runtime? | A Claude model at build time, cached and reviewable; nothing generative in the click path except rendering. |
| Q13 | The v1 non-goals N1 (no real-time), N7 (a frame is one screen), and principle 6 (no pixel-derived interactivity, as worded) are revoked by this design. Confirm. | Revoked; interactivity still comes only from the composition, never from pixels alone. |
