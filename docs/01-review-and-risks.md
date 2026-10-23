# Videotape — Review and Risk Register

**Date:** 2026-10-22 · **Status:** the risks still apply; the recommendation in §5 and §7 (a picture
behind ordinary controls) is superseded by [05-design-v2.md](05-design-v2.md) · **Companion:** [02-spec-v1.md](02-spec-v1.md), [03-landscape.md](03-landscape.md)

This is an honest review of the Videotape idea as pitched: user interfaces defined as chains of
interaction (tapes of frames), rendered as video by a generative model, and displayed by a thin
player that knows which regions of the picture are interactive.

---

## 1. Verdict in short

1. **The core idea is sound and well timed.** Making the *journey* the unit of authorship, pushing
   presentation to a generator, and shipping one thin player for every screen are each defensible on
   their own. Together they form a coherent thesis that nobody has built end to end.
2. **The pitch carries one load-bearing assumption that is false today:** that a video model can
   *be* the UI. Current models cannot render exact text, exact numbers, pixel-stable layouts across
   frames, native text entry, or a hit-map. Nothing in the next model generation changes the
   "exact facts" part, because a generator that is allowed to invent pixels is a generator that is
   allowed to invent a wrong number on a dashboard.
3. **The fix is architectural, and it strengthens the idea rather than diluting it.** Split every
   frame into what the model owns (*form*: look, chrome, mood, motion, transitions) and what code
   owns (*facts*: text, values, inputs, hit regions). A layout engine owns *space* and produces the
   wireframe that both conditions the generator and positions the facts. The result still looks
   like a generated video UI, but it is correct by construction, testable with the AI switched off,
   and the share of the screen that is generated can grow as models improve (the "ratchet").
4. **With that split, v1 is buildable now** with hosted or open-weight models: a generated still per
   frame, a generated transition per edge, native widgets overlaid in the player. Real-time
   whole-screen generation becomes a renderer plugin added later, not a v1 dependency.

---

## 2. What is genuinely strong

### 2.1 Journey-first authoring
Today the user journey is a *side* artifact: a Figma flow, a user story, an end-to-end test. The
program itself is a pile of components and routes, and the journey is reconstructed by reading them.
Videotape inverts this: the tape **is** the program, and components hang off frames. That gives you,
for free and by construction:

- an enumerable graph of every reachable state and edge, so reachability, dead ends, and missing
  handlers are *static checks*, not QA findings;
- exhaustive, cheap end-to-end tests (walk the graph);
- analytics, documentation, onboarding flows, and prefetching that all read from the same graph;
- a vocabulary ("tape", "frame", "cut", "head") that designers, developers, and product people can
  share.

Nearest prior art: statecharts (XState), the Elm architecture, server-driven UI (Airbnb, Lyft),
HATEOAS. None of them make the journey the primary artifact, and none delegate presentation to a
generator.

### 2.2 Presentation-agnostic by construction
If frames only declare intent and components, then screen size, medium, and visual style are
renderer concerns. This is the right separation and it is the same separation that made responsive
design and design tokens valuable. The difference is that here the "design system" can be a prompt
plus a seed.

### 2.3 Thin client, server-rendered
One player for every platform. Cloud gaming and pixel streaming (Stadia, GeForce Now, Unreal Pixel
Streaming) already proved the transport, the input loop, and the economics at scale. Videotape can
reuse that playbook instead of inventing it.

### 2.4 Timing
Real-time generation is crossing the "faster than playback" line in public products (see
[03-landscape.md](03-landscape.md)): sub-50 ms per frame at 720p to 1080p, with vendors quoting
single-digit dollars per hour of sustained stream. The cost curve is pointed the right way.

---

## 3. Where the pitch over-reaches (and what the design must do about it)

### 3.1 "The client is nothing more than a video player"
A UI is not only pixels plus click coordinates. It needs text entry with IME and autocorrect, a
caret, selection, clipboard, scrolling with inertia, focus order, keyboard navigation, screen-reader
semantics, find-in-page, zoom, localization. A pixels-only player either re-implements all of this
badly or loses it.

**Design response:** the player hosts a transparent **content layer** of real DOM nodes positioned
over the generated picture (inputs, buttons, text), driven by the frame spec. The DOM *is* the
accessibility tree. The generated layer sits underneath. See spec §8.

### 3.2 "The model renders the state"
A dashboard that shows a balance must show the right balance 100% of the time. Models render
approximate text, drift between frames, and give you no map of what is where.

**Design response:** the principle **"the model never renders a fact."** Data-bearing content
(text, numbers, labels, inputs) is composited deterministically from the frame spec. The generator
receives a wireframe and a scene description, never user data. See spec §6 and §10.

### 3.3 "A refresh fixes glitches"
Acceptable on a landing page. Not acceptable when the password field moved 40 px between two
frames, or when a region that should be a button rendered as decoration.

**Design response:** layout conditioning. Hit regions are decided *before* generation by the layout
engine and the generator is conditioned on them (wireframe as ControlNet-style input, masks for
reserved regions). A validation pass checks reserved regions (contrast, texture) and re-rolls or
falls back to a flat fill. Same seed plus same spec gives the same picture, and that picture is
cached. "Refresh" becomes an explicit, cheap **re-roll**, and curated renders can later be
**pinned** as canonical.

### 3.4 "Generated in real time for every user"
Real-time streams cost roughly one GPU per concurrent viewer today. Vendors quote a few dollars per
hour per stream; list prices on serverless marketplaces are higher. Fine for a demo, ruinous for a
free web product, and unnecessary for most screens, which are still.

**Design response:** **generation as compilation.** A frame's scene layer is rendered once per
(frame, viewport class, style, seed) and cached; a transition is rendered once per edge. Most
sessions are cache hits that cost nothing. Real-time generation is reserved for an opt-in `live`
renderer and for ambient motion. Think static-site generator first, game engine later.

### 3.5 "Composition rules are a detail for later"
They are the spine. The layout engine's output is the wireframe that conditions the generator, the
hit-map the player uses, the positions of the content layer, and the accessibility tree. Without
it nothing composes.

**Design response:** a small, explicit layout model in v1: viewport classes, layout archetypes,
named slots, safe areas. Figma-style per-device frames come later on top of the same model.

### 3.6 "Each click starts a new tape"
True as a model, but it means the graph of tapes is a graph of *edges*, and each edge is a
transition the user will wait for. The pitch does not say where the latency goes.

**Design response:** a transition budget. Because the graph is static, the engine prefetches the
renders and cuts for every outgoing edge of the current frame. A cut that is not ready by the
budget is replaced by a deterministic crossfade, never by a spinner.

---

## 4. Risk register

Likelihood and impact are for v1 as specified in the spec. "Signal" is what to watch to know the
risk is materialising.

| ID | Risk | L | I | Mitigation in v1 | Signal |
|----|------|---|---|-------------------|--------|
| R1 | **Interactive fidelity.** Text, carets, exact values, and widget behaviour cannot be produced by the generator. | High | High | Content layer of native DOM over the picture; model never renders facts. | Any text or number visible to the user that came from the generator. |
| R2 | **Spatial instability.** Regions move or change role between renders. | High | High | Layout engine fixes regions first; generator is conditioned on the wireframe; region validation and re-roll; flat fallback per region. | Re-roll rate per frame; validation failure rate. |
| R3 | **Transition latency.** Click to next frame feels slow. | High | Med | Prefetch along tape edges; cached cuts; native immediate feedback (focus, caret, pressed state); crossfade fallback within a 300 ms budget. | p95 click-to-frame; fallback rate. |
| R4 | **Cost per session.** Generation per user is too expensive. | High | High for product, Low for demo | Cache keyed on viewport class, not pixel size; ahead-of-time rendering; live mode opt-in only. | Cache hit rate; cost per 5-minute session. |
| R5 | **Accessibility and platform conventions.** Screen readers, copy, find, zoom, RTL, i18n. | High | High | DOM content layer is the a11y tree; native inputs; stated as a design principle and tested. | Lighthouse / axe results on the demo. |
| R6 | **Identity drift.** Same app looks different across sessions or frames. | Med | Med | Style packs: seed, palette, reference image, optional LoRA; cache; snapshot tests. | Visual diff between renders of the same key. |
| R7 | **Model and vendor churn.** Backends change IDs, pricing, or disappear. | High | Med | Renderer plugin interface; `flat` renderer as reference; at least one open-weights path. | Any package that imports a vendor SDK outside `renderers/`. |
| R8 | **Hallucinated or misleading UI.** The picture shows a button that is not one, or vice versa; prompt injection via data. | Med | High | Only declared components are interactive; hit-map comes from the spec, never from pixels; user data never enters a prompt. | Any pixel-derived interactivity. |
| R9 | **Bandwidth.** Streaming video to every client. | Med | Med | v1 ships stills plus short cuts (kilobytes, not megabits); streams only in live mode. | Bytes per session. |
| R10 | **Testability.** Generated output is not deterministic. | Med | Med | Fixed seeds; `flat` renderer in CI; per-region visual diff tolerances. | Flaky visual tests. |
| R11 | **Engine black hole.** The "hardest part" absorbs all effort and nothing ships. | High | High | v1 defined as a working loop with AI off first; strict non-goals; renderers are plugins added in order. | Weeks without a runnable demo. |
| R12 | **Privacy.** Input goes to the server at keystroke granularity. | Med | Med | Values are sent on commit (blur/submit) unless a frame opts into live validation; TLS; no retention of rendered sessions. | Any per-keystroke upload not requested by the frame. |
| R13 | **Licensing.** Model weights and training data terms. | Low | Med | Prefer Apache-2.0 weights; record licence per backend in `03-landscape.md`. | A backend without a recorded licence. |
| R14 | **Uncanny UX.** Users distrust a UI that looks different each visit. | Med | Med | Cache makes the same app look the same; style packs; pinned renders in v1.5. | User feedback on the demo. |
| R15 | **Over-generation.** Developers put facts into scene prompts because it is easy. | Med | High | `scene` is static text or a function of declared flavour data only; a lint rule flags bound user values in prompts. | Lint findings. |

---

## 5. The bet, stated precisely

> **Generation owns form. Code owns facts. Layout owns space.**

- *Form*: backgrounds, chrome, materials, mood, ambient motion, transitions. Produced by a generator
  conditioned on the wireframe and a style pack. Cached.
- *Facts*: every string, number, image, and input the user must be able to trust or operate.
  Rendered deterministically on the content layer from the frame spec.
- *Space*: viewport class, archetype, slots, safe areas. Decided by the layout engine before any
  pixel is generated; the same wireframe conditions the generator and positions the facts.

**The ratchet.** Each milestone moves one more category from the deterministic side to the generated
side, in this order: backgrounds and scenes → panels and chrome → ambient motion → transitions →
button and field *surfaces* (labels still deterministic) → live full-screen video with burned-in
facts. Each step is measurable as the share of screen area that is generated, and each step can be
reverted per frame if quality is not there yet.

This is what keeps the project honest: the demo can look like the vision from day one, while every
fact on screen is correct and every interaction is native.

---

## 6. Prior art worth studying

- **Interactive video / world models:** Genie 3 (DeepMind), Oasis and MirageLSD and Lucy 2 (Decart),
  Odyssey-2, Matrix-Game 2.0 and 3.5 (open weights), Self-Forcing and its descendants (Krea Realtime
  14B, StreamDiffusionV2, LongLive). They answer "can video be generated faster than it plays?"
  (yes) and "can user input steer it?" (yes, for camera and movement, not for UI semantics).
- **Wireframe-conditioned GUI generation:** UI-Diffuser (Stable Diffusion + ControlNet on Rico
  wireframes), ControlGUI (text + wireframe + visual flow). This is the exact shape of the `still`
  renderer.
- **Pixel streaming:** Unreal Pixel Streaming, Stadia, GeForce Now. Transport, input, and session
  economics.
- **Server-driven UI and statecharts:** Airbnb Ghost, Lyft SDUI, XState. The authoring model.
- **Video editors:** CapCut, Premiere keyframes and stills. The mental model for cuts and ambient
  loops.

---

## 7. Recommendation

Build the hybrid, in this order, and do not skip the first step:

1. **The loop with AI off.** Tapes → layout → flat render → player → events → next frame. This
   proves the authoring model and gives you a regression harness forever.
2. **Generated stills.** Layout-conditioned image generation for the scene layer, cached.
3. **Generated cuts.** First-and-last-frame video between frames, prefetched along edges.
4. **Live.** A renderer plugin that streams real-time video over WebRTC, opt-in per frame.

The spec in [02-spec-v1.md](02-spec-v1.md) defines steps 1 to 3 as v1 and step 4 as an interface
with a stretch implementation.
