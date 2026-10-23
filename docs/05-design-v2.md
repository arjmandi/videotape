# Videotape: UI as a Game — Design v2

**Date:** 2026-10-23 · **Status:** draft; core decisions taken (§2); no v2 code yet ·
**Supersedes:** the concept of [02-spec-v1.md](02-spec-v1.md) · **Evidence:**
[03-landscape.md](03-landscape.md) · **Prototype:** tag `prototype-0`

---

## 0. Why a v2

Prototype-0 built the v1 spec faithfully and showed that it is not new: a thin client over a server
is server-driven UI, and a generated background behind ordinary controls is a skin. A first v2 draft
framed the fix as "generated video with controls in it". That framing was wrong too: a pipeline of
video, stills, and video again has no state and no geometry, so it can only guess afterwards whether
the pixels agree with the controls.

A game does not guess. A game engine holds the state of the world, the geometry of every object,
the camera, the text, and the input, and the picture is a rendering of that state. That is the
property an interface needs.

## 1. The thesis

> **Videotape is a UI engine that plays apps the way a game engine plays games.** Developers declare
> what the app must do (journeys, components, data, handlers) in TypeScript or Python. Designers
> declare the world it lives in. The device reports its screen. A scene runtime composes the app
> into a live, interactive scene, renders it with generated worlds, streams it to a thin native
> client on any platform, and guarantees that every control is real, every fact is exact, and every
> keyboard and screen reader works.

- **A game, not necessarily 3D.** "Game" means a live render with state, geometry, and input. A
  world can be flat, layered 2.5D, or full 3D. The goal is not depth for its own sake; it is the
  freedom to make better interfaces with less maintenance, on every screen.
- **Generative UI by rendering, not by code.** Generative-UI projects write front-end code on the
  fly. Videotape writes no front-end code at any time: there is a declaration of intent, a world,
  and an engine that plays them.
- **Native apps from day one.** One app, exported to iOS, Android, desktop, and the web, later to
  watches and TVs. The OS integration layer works like Electron or other cross-platform shells; the
  interaction layer works like a live game.
- **Built for next year's models.** Real-time world generation will become ordinary. The engine is
  where those models plug in, and the harness is what makes them behave as interfaces.

**What makes it different from Unity and other game engines:** it is built for apps. Journeys are
the program, every screen size is composed rather than designed, text input uses the platform's own
editors, and accessibility is first-class. A game engine has none of these.

## 2. Decisions taken

| # | Decision | Consequence |
|---|----------|-------------|
| A | The engine runs on servers, cloud-gaming style, and streams to clients. A client-side engine comes later. | Clients stay thin and identical across platforms; GPU cost per session and network latency are first-order concerns (§11, §17). |
| B | Our own scene runtime, built on a TypeScript web engine. | One language with the TypeScript SDK; the same runtime can later run on devices; the engine choice is an experiment (E1). |
| C | Platform text input and platform accessibility are first-class. | Clients host native editors and native accessibility trees; this is the differentiator from game engines. |
| D | Not necessarily 3D. | Worlds come in three kinds (§7); most apps will start in 2D or 2.5D. |
| E | Facts are drawn by the engine as real text in the world, from code. | Exact and immersive at once; generative layers never repaint them (§12). |
| F | Touch and click are raycasts against declared objects. | Geometry decides interactivity, never pixels (§10). |
| G | The first milestone delivers apps and user flows, without OS capabilities such as camera or files. The exporter compiles those later. | M1 scope (§15). |
| H | SDKs for TypeScript and Python from the start; the app talks to the engine over a language-neutral protocol. | Handlers run in the app's own process, in its own language (§6). |

## 3. Goals, non-goals, success criteria

### 3.1 Goals
- **G1 Intent-only authoring** in TypeScript or Python: no layout, style, screen, or routing code.
- **G2 Any screen.** Continuous composition for any size and orientation; breakdown and merge of
  frames are designed in now and built after M1.
- **G3 Live and interactive.** The app is a running scene, streamed; feedback is immediate.
- **G4 Generated worlds and embodied controls.** Components appear as objects of a generated world,
  under affordance contracts.
- **G5 Exact facts.** Every string, number, and value is rendered by the engine from code.
- **G6 Platform text input and accessibility** on every client.
- **G7 Native apps from day one** through the exporter.
- **G8 A measurable harness:** grounding, legibility, latency, cost per session, and fallback rates.

### 3.2 Non-goals for M1
OS capabilities (camera, files, location, notifications, payments); on-device rendering; the live
neural layers (L2, L3); offline use; watch and TV clients.

### 3.3 Success criteria for M1
- **S1** A Python developer writes the demo app (landing, docs, sign-in, dashboard, report) with no
  layout or front-end code.
- **S2** `videotape export` produces working clients for the web, iOS, Android, and desktop from that
  one app.
- **S3** On each client, a tester signs in and reads the report, by touch, by keyboard only, and with
  the platform screen reader.
- **S4** Rotating a phone or resizing a window recomposes the scene without a reload; a tiny canvas
  stays operable (minimum targets met; content that does not fit scrolls within the shot until
  breakdown arrives in M3).
- **S5** Typing uses the platform editor: IME, autofill, and password managers work.
- **S6** The whole loop runs with generation off in CI.
- **S7** Input-to-photon latency, sessions per GPU, and cost per active hour are measured and
  reported.

## 4. Vocabulary

| Term | Meaning |
|------|---------|
| **App** | What a developer ships: intent, handlers, services, and a world reference. |
| **Intent** | Tapes, frames, components (with roles, importance, groups, relations), data binds, handlers. |
| **World** | The designer's declaration: kind (2D, 2.5D, 3D), prompt, materials, references, embodiment hints. |
| **Context** | What a client reports: screen size and density, orientation, input methods, preferences, network. |
| **Engine** | The server: journey runtime, composer, embodier, scene runtime, generation layers, grounder, streamer. |
| **Scene runtime** | Our runtime on a TypeScript web engine: scene graph, cameras, text, input, render passes. |
| **Shot** | What is on screen at once: one frame, a step of one, or several merged. |
| **Composition** | The composer's plan for a context: shots, placements, derived steps. |
| **Embodiment** | The world object (prop) a component appears as, with its affordance contract. |
| **Object map** | Object id ↔ component ↔ screen-space bounds and input surfaces, per streamed frame. |
| **Client** | The exported native shell: stream player, local feedback, native text, native accessibility, OS bridge. |
| **Exporter** | Builds clients for each platform from one app. |
| **App protocol** | Engine ↔ app process: intent registration, handler calls, enter hooks. |
| **Client protocol** | Engine ↔ client: media stream plus a data channel for input, context, object map, accessibility. |
| **Layer** | L0 engine with default assets · L1 generated assets · L2 live restyle · L3 world model. |

## 5. Architecture

```
 APP PROCESS (TypeScript or Python)                    WORLD (designer)
 tapes · handlers · services                              │
        │  App protocol (intent, handler calls)           │
        ▼                                                 ▼
 ┌───────────────────────────────── ENGINE (server, GPU) ─────────────────────────────────┐
 │ Journey runtime ─► Composer ─► Embodier ─► Scene runtime ─────────► Generation layers  │
 │ reels, values,     any screen,  props and   scene graph, cameras,    L1 assets · L2      │
 │ derived steps      breakdown,   contracts   in-world text, raycasts, restyle · L3 world  │
 │                    merge                    render passes            model               │
 │                                                    │                      │             │
 │                                             Grounder ◄────────────────────┘             │
 │                                                    │                                    │
 │                                             GPU encoder ─► WebRTC                       │
 └────────────────────────────────────────────────────┬───────────────────────────────────┘
          video (and audio)  ▼                        ▲  input, text, context, a11y actions
          data: object map, input surfaces, accessibility tree, feedback hints
 ┌────────────────────── CLIENT (exported: web · iOS · Android · desktop · later watch, TV) ┐
 │ stream player · local feedback · native editor on input surfaces · native accessibility │
 │ tree · context reporting · OS bridge (camera, files, … after M1)                        │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Loops and budgets**

| Loop | Trigger | Work | Budget |
|------|---------|------|--------|
| Feedback | Touch, click, key | Client highlights the object under the finger from the object map; the native editor takes keystrokes | Next client frame |
| Interaction | Input reaches the engine | Raycast, state change, animation, handler call when needed | Input-to-photon ≤ 100 ms on a good network (target, E2) |
| Composition | Screen change, navigation, data change | Recompose, move objects, reframe the camera | ≤ 300 ms to settle |
| Generation | New world, new embodiment, new shot | L1 assets ahead of time; L2 and L3 live when enabled | L1 offline; L2/L3 per their own budgets |

## 6. Intent and SDKs

Intent keeps v1's tapes, frames, actions (`goto`, `jump`, `back`, `stay`), binds, handlers, and enter
hooks, and drops every presentation field (`layout`, `slot`, `rect`, templates). Components declare
what they are for: `role` (heading, primary, secondary, navigation, status, supporting),
`importance` (required, normal, optional), `group` (with `keepTogether`), `order`, and `relations`
(`labels`, `summarises`, `dependsOn`, `follows`). Frames declare a one-line `purpose`, and later
`breakdown` and `merge` policies with hooks.

Intent is data. It serialises to JSON with a published schema, so any language can produce it.
Handlers are code and stay in the app's process: the engine calls them over the **app protocol**.

```python
from videotape import app, tape, frame, text, input, button, jump, stay, handler

async def submit(ctx):
    user = await ctx.services.auth.login(ctx.values["username"], ctx.values["password"])
    if user:
        return jump("dashboard", {"user": user})
    return stay({"login.error": "Wrong credentials"})

login = tape("login", frames=[
    frame("form", purpose="Sign in", components=[
        text("title", "Welcome back", role="heading"),
        input("username", label="Username", required=True),
        input("password", label="Password", type="secret", required=True),
        text("error", bind="login.error", role="status"),
        button("submit", "Sign in", role="primary", on={"press": "submit"}),
    ], on={"submit": handler(submit, outcomes=[jump("dashboard"), stay()])}),
])

videotape = app(entry="landing", tapes=[landing, login, dashboard, report], world="dusk-studio")
```

**App protocol** (sketch): the app process connects out to the engine (so apps run anywhere), sends
`register` with its intent JSON and handler names, and then answers `handler`, `enter`, and
`flavour` calls with actions and data patches. Secrets arrive once and are never stored, logged, or
rendered, as in v1. The TypeScript SDK can also run in the engine's process for local development.

## 7. Worlds and generation layers

A world says where the app lives:

```ts
world("dusk-studio", {
  kind: "2.5d",                      // "2d" | "2.5d" | "3d"
  prompt: "A recording studio at dusk: warm wood, tape machines, soft amber light, quiet.",
  palette: { base: "#1c1612", ink: "#f4ead9", accent: "#ff8a3d" },
  references: ["worlds/studio/ref-1.jpg"],
  embody: { "button.primary": "a lit console key", list: "tape reels on a shelf, one per item" },
});
```

| World kind | What it is | Generated with |
|------------|------------|----------------|
| **2D** | Flat surfaces and props, like a well-made card game | Image models: backgrounds, props, materials |
| **2.5D** | Layers at depths with parallax, a camera that can push and pan | Image models with depth or layer output; outpainting for oversize plates |
| **3D** | Meshes or Gaussian splats with colliders | World-generation models that export engine assets |

Generation layers, each optional and each measured by the harness:

| Layer | What generation does | Status |
|-------|----------------------|--------|
| **L0** | Nothing: default and procedural assets. Generation off, CI, every fallback. | M1 |
| **L1** | Worlds and props generated once as assets, rendered live by the engine at full frame rate | M2; the main path |
| **L2** | A live neural restyle over the engine's render (video to video), conditioned on depth and object ids | M3; per session, costly |
| **L3** | A real-time world model renders the scene from the engine's state and actions | When models accept state conditioning and expose APIs |

What the landscape says today ([03-landscape.md](03-landscape.md) §7, checked 2026-10-23):

- **L1 is usable now.** World Labs' Marble has a self-serve World API: a 3D world in about 5 minutes
  for about $1.20–2.50, with SPZ splats, a collider mesh, and metric scale. For 2.5D sets,
  Qwen-Image-Layered (layered RGBA) and Depth Anything 3 (depth) are Apache-2.0. Tencent's
  HunyuanWorld licence excludes the EU, the UK, and South Korea.
- **L2 is usable, with a constraint.** Hosted video-to-video (Decart's Lucy Restyle 2 at $0.01 a
  second, Lucy 2.5 at $0.02, 720p) takes a video stream and a prompt, not depth or object ids. The
  engine therefore renders a conditioning view designed for it, and composites text after it (§12).
  At $36–72 per stream-hour, L2 is a premium layer, not a default.
- **L3 is not ready for products.** Genie 3 has no API; Odyssey-2 Pro has one with no published
  price; open weights such as Waypoint-1.5 (Apache-2.0) run on one consumer GPU. L3 is an
  experiment, not a dependency.

**Coherence.** Before generating, a critic compares the world with the intent (domain, density,
tone) and warns about strained pairings. It warns; it does not block.

## 8. Context and composition

The client measures and streams context; the engine detects nothing:

```ts
interface Context {
  screen: { w: number; h: number; dpr: number };          // CSS px, continuous
  pointer: "coarse" | "fine" | "none";
  inputs: Array<"touch" | "mouse" | "keyboard" | "crown" | "remote" | "voice">;
  prefers: { reducedMotion: boolean; colorScheme: "dark" | "light"; textScale: number };
  locale: string;
  network: { rttMs: number; kbps: number };
}
```

The **composer** is a pure function of (intent around the current frame, context, embodiment sizes)
and returns a composition in under 50 ms:

- **Capacity.** Every component has a minimum footprint for the context: legibility and target
  minimums (for example 44 px touch targets), label length, embodiment size, and the user's text
  scale. The screen has a usable area after margins and pinned items.
- **One shot** when it fits: placements by role, relation, and reading order, scored for proximity of
  related items, reach of the primary action, and room for the world's subject.
- **Breakdown** when it does not (after M1): steps that keep groups whole and order intact, with the
  title pinned and the primary action on the last step; values are buffered and handed to the
  original handler unchanged. Developers can opt out or adjust the plan with hooks.
- **Merge** when there is room (after M1): declared neighbours share one shot; an edge between them
  becomes a change of focus, not a cut.
- **Stability.** Object identity persists across compositions; hysteresis prevents reshuffles; the
  scene runtime animates moves.
- **Static guarantees.** `videotape check` runs the composer for reference screens (watch, phone
  portrait and landscape, tablet, desktop, wall) and verifies edges, reachability, and minimums.

In M1 the composer delivers continuous composition for any screen; a shot whose content does not
fit scrolls within itself. Breakdown and merge follow in M3.

## 9. Embodiment

Each placed component gets a prop of the world:

```ts
interface Embodiment {
  component: string;
  prop: string;                          // a prefab id, or a description to generate one from
  affordance: { press?: true; write?: { lines: number }; read?: { maxChars: number }; choose?: { options: number } };
  textSurface?: string;                  // which face of the prop carries the component's text
  minSize: { w: number; h: number };     // CSS px at the reference screen
  states: Partial<Record<"hover" | "pressed" | "focused" | "disabled" | "error", string>>; // animations or variants
  fallback: "plain";
}
```

A language model proposes embodiments per (world, kind, role) at build time; results are cached and
reviewable, and designers and developers can override them. Within a tape, the same kind and role
keep the same prop. Every prop has a plain fallback the world can always host.

## 10. Scene runtime

Our own runtime on a TypeScript web engine (the engine is chosen in E1). Its job:

- Build and update the scene graph from compositions: props, layers or meshes, lights, cameras.
- Render **text from code** in the world (signed-distance-field text on prop surfaces), with the
  world's materials applied as long as legibility holds.
- **Hit-test by raycast** against declared objects' colliders. Undeclared geometry is never
  interactive.
- Animate states (hover, pressed, focus, disabled, error) and composition changes.
- Produce render passes: colour, depth, object ids, a **facts-free** colour pass (for L2 and L3), and
  the text pass composited last.
- Run headless on GPU servers, many sessions per GPU, at an adaptive frame rate (idle scenes drop
  their rate). None of the candidate engines renders pixels in plain Node, so server rendering means
  a GPU-backed headless Chromium, or Babylon Native ([03-landscape.md](03-landscape.md) §7.3).
- Run deterministically in CI with L0 assets.

## 11. Streaming and the client

**Server side.** Each session renders on a GPU, is encoded on the GPU, and is sent over WebRTC.
Input, text, context, and accessibility actions come back on a data channel.

**The client** is the same small program on every platform:

| Duty | How |
|------|-----|
| Show the stream | Hardware video decode; letterbox nothing (the composer composes for the real screen) |
| Immediate feedback | Highlight the object under the finger from the object map before the engine's frame arrives |
| Text input | While a field is focused, a **native editor** sits on the field's input surface (position, size, and transform from the object map), styled to the world. Caret, selection, IME, autofill, and password managers are the platform's own. Values travel per the commit policy; the engine renders committed text in the world. Secret fields use secure entry; the engine only ever draws masking dots. |
| Accessibility | A **native accessibility tree** from intent (roles, names, states, actions) with bounds from the object map: virtual views on Android, accessibility elements on iOS, ARIA on the web, platform APIs on desktop. Screen-reader actions become engine events. |
| Context | Measures and streams screen, input methods, preferences, and network |
| Resilience | Keeps the last frame and the accessibility tree on a dropped connection; reconnects and resumes the reel |
| OS bridge (after M1) | Executes capability requests (camera, files, location, notifications, share, biometrics, payments) and returns results |

## 12. Facts

- Every string and value is rendered by the engine from code, as real text on the prop that carries
  it. Generation never draws facts.
- Generative layers (L2, L3) receive the facts-free pass; the text pass is composited after them, so
  a restyle can never garble a number, and user data never reaches a generative model.
- Hosted L2 services return video, so the compositing happens on the engine: the restyled stream
  comes back, the text pass is composited using the engine's depth, and the result is re-encoded for
  the client. That adds a network leg to every frame while L2 is on (Q14, E6).
- If a surface cannot carry text legibly, the engine adds a backing to that surface and the harness
  records it.

## 13. Grounding harness

| Layer | What is checked | When |
|-------|-----------------|------|
| L1 | Props read as their affordance (vision-language judge); text surfaces are legible under the world's materials (measured in the engine's own buffers, exactly); no lettering painted into generated assets (OCR) | At build time, per asset |
| L2, L3 | Each object still appears where the object-id pass says (per-object correspondence); nothing control-like or text-like appears outside the map (OCR, detector); objects do not drift between frames | Sampled live |
| All | Input-to-photon latency, composition settle time, frame rate, cost per active hour, fallback rate | Continuous |

Failures fall back per object (plain prop), per layer (drop L2 or L3 for the session), or to L0. The
same checks over reference apps, worlds, and screens form the evaluation suite that tracks model
progress.

## 14. Protocols, sketched

**Client protocol** (WebRTC media plus a data channel):

| Direction | Message | Carries |
|-----------|---------|---------|
| C→S | `hello`, `context` | Session resume token, context, then context deltas |
| C→S | `input` | Pointer, touch, key, crown, and remote events in stream coordinates, with the frame they were made against |
| C→S | `text` | Editor commits and changes per the commit policy; composition state for live preview |
| C→S | `a11y` | Screen-reader actions on accessibility nodes |
| S→C | `objects` | Object map for the current frame: bounds, input surfaces, feedback hints |
| S→C | `tree` | The accessibility tree and its changes |
| S→C | `editor` | Open, style, move, and close the native editor for a focused field |
| S↔C | `capability` (after M1) | Requests to the OS bridge and their results |

**App protocol** (WebSocket or HTTP/2, JSON): `register` (intent, handlers, services manifest),
`handler` and `enter` calls with their results, `log`.

Both keep prototype-0's protections: events validated against what is on screen, sequence and
version guards, secrets kept out of logs and storage.

## 15. Milestones

Experiments first, then milestones, each ending in something runnable.

| # | Experiment | Answers |
|---|------------|---------|
| E1 | Engine bake-off: candidate TypeScript web engines rendering headless on a server GPU, with SDF text, raycasts, and render passes | Which engine; frame time; text quality |
| E2 | Streaming: GPU encode and WebRTC to web, iOS, and Android test clients | Input-to-photon latency; sessions per GPU; cost per active hour |
| E3 | Native editor over a stream on iOS, Android, and the web | IME, autofill, and password managers across the seam |
| E4 | Native accessibility trees from intent on iOS, Android, and the web | VoiceOver and TalkBack parity |
| E5 | Python SDK over the app protocol with the demo app | Ergonomics; handler latency |
| E6 | L2 round trip: the engine's facts-free view through a hosted restyle and back, text composited, re-encoded | Added latency; legibility; whether controls stay recognisable; cost per stream-hour |

| Milestone | Delivers | Done when |
|-----------|----------|-----------|
| **M1 Apps and flows** | Scene runtime (L0), continuous composer, streaming, clients exported for web, iOS, Android, desktop, native text and accessibility, TypeScript and Python SDKs, two sample apps, CI with generation off | S1–S7 |
| **M2 Generated worlds** | L1 worlds and props (2D, 2.5D, then 3D), embodiment, coherence critic, asset harness | The demo runs in two worlds that both pass the harness |
| **M3 Adaptive composition and live looks** | Breakdown and merge with hooks; L2 live restyle with grounding | A 20-field form breaks into steps on a watch-sized screen; L2 holds grounding |
| **M4 Native capabilities** | Capabilities through the exporter's OS bridge; an on-device engine option | Camera and file flows work on iOS and Android |
| Later | L3 world models; watch and TV clients | — |

## 16. What carries over from prototype-0

| Prototype-0 part | In v2 |
|------------------|-------|
| Tape model, actions, binds, handlers, enter hooks, `check`, graph | Kept; presentation fields removed; becomes the JSON intent the SDKs produce |
| VTP sessions, event validation, sequence and render guards, resume, secrets handling | Kept in the client and app protocols |
| Engine reels, handler runtime, budgets and fallbacks, renderer host | Kept; the renderer host becomes the generation-layer host |
| Cache keys that cover every input; validator versions and re-checks | Kept for generated assets |
| OCR lettering check, legibility checks, attempt logs, contact sheets | Kept in the asset harness |
| fal image renderer and its findings | Kept for 2D and 2.5D asset generation |
| Layout engine (templates, slots, three classes) | Replaced by the composer; its touch-target rules and free-space search are reused |
| Player (DOM over a picture) | Replaced by the client; its keyboard and accessibility tests become client tests |

Lessons from the live runs ([03-landscape.md](03-landscape.md) §2) that still apply: image-to-image
follows structure only at moderate strength and ignores placement at high strength; a model shown
something that looks like a UI paints one, with fake text; OCR separates lettering from scenery
cleanly; whole-region measures miss small objects; generation takes seconds, not milliseconds, so the
live path must not wait on it; backends fail in ordinary ways and the engine must fail once and fall
back.

## 17. Risks

| Risk | Mitigation |
|------|------------|
| Streaming latency makes the app feel remote | Local feedback from the object map; native editors; servers near users; on-device engine later (M4) |
| GPU cost per session | L0 and L1 are cheap to render; many sessions per GPU; adaptive frame rate; L2 and L3 only where they pay |
| Data use and battery on mobile | Adaptive frame rate and bitrate; idle scenes nearly free to encode |
| No offline use | Accepted for M1; the on-device engine removes it later |
| App store acceptance of apps whose interface is streamed | Check Apple's and Google's current review guidelines before M1 exports (Q11) |
| Text input and accessibility gaps across platforms | E3 and E4 before M1; parity tests per client in CI |
| Game-like interfaces are harder to learn | Affordance contracts and judge; consistent props per world; plain mode always available |
| Vendor dependency for generation | Layers are plugins; L0 always works; open-weights paths tracked in the landscape |
| L2 costs $36–144 per stream-hour at today's prices | L2 off by default; enabled per app or per session where it pays; L1 carries the look |
| No WebRTC client for watchOS found | Watch clients come after M1, over another transport if needed (Q15) |
| Provider terms change or conflict (World Labs' own documents disagree on commercial rights and credit expiry) | Confirm terms in writing before shipping; keep an open-weights alternative per layer |

## 18. Open questions

Each has the default this document assumes.

| # | Question | Default |
|---|----------|---------|
| Q1 | M1 clients: the web client inside native shells (system web views), or native players per platform from the start? | Web client in native shells for M1: fastest path to every store, and system web views give platform editors and accessibility; native players when performance or watches require them. |
| Q2 | Server rendering: GPU-backed headless Chromium, or Babylon Native? (Plain Node renders no pixels with any candidate.) | Headless Chromium, so the same engine code can later run on devices; Babylon Native if E1 shows Chromium too costly per session. |
| Q3 | Which TypeScript web engine? | Babylon.js unless E1 says otherwise: it ships an object-id and depth G-buffer, GPU picking, SDF and MSDF text, and SPZ splats. PlayCanvas is the runner-up; three.js needs add-ons for ids and text. |
| Q4 | Who runs engines: a hosted Videotape cloud, self-hosted containers, or both? | Self-hosted container first; hosted later. |
| Q5 | Sessions per GPU and cost per active hour to aim for? | Set by E2; L0 and L1 should allow many sessions per GPU. |
| Q6 | Which world kind does M2 start with? | 2.5D: cheap to generate, fits most apps, already proven with image models; 3D next. |
| Q7 | Which provider for L1 3D worlds, and for L2? | Marble for 3D worlds, after World Labs confirms commercial terms in writing; Decart's Lucy Restyle 2 for the L2 trial (E6); HunyuanWorld only where its licence applies (not the EU, UK, or South Korea). |
| Q8 | Does the engine break frames down by default (opt-out with hooks) or only where developers opt in? | By default, with opt-out and hooks (M3). |
| Q9 | May the composer infer merges from the graph? | No: declared merges only, for now. |
| Q10 | One world per app, per tape, or per context? | Per app, overridable per tape. |
| Q11 | Do Apple's and Google's current guidelines accept apps whose interface is streamed? | To be checked before M1 exports; the plan assumes yes with a native shell that owns text input, accessibility, and OS integration. |
| Q12 | Which model proposes embodiments and runs the coherence critic? | A Claude model at build time, cached and reviewable. |
| Q13 | Is a plain mode (plain props, no world) always available to users? | Yes, as an accessibility and trust feature. |
| Q14 | With L2 on, where are text and controls composited: on the engine (an extra network leg, thin clients unchanged) or on the client (lower latency, a client that renders a UI layer)? | On the engine; revisit after E6 measures the latency. |
| Q15 | Watches: no WebRTC client for watchOS was found. Which transport and client for watch apps? | Decided when watch clients are planned (after M1); a native watch client over a simpler transport is the likely path. |
