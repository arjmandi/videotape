# Videotape: UI as a Game — Design v2

**Date:** 2026-10-23 · **Status:** draft; core decisions taken (§2, §18); no v2 code yet ·
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
> into a live, interactive scene, renders it with generated worlds, delivers it to a thin native
> client on any platform (streamed as video, or on iOS rendered on the device), and guarantees that
> every control is real, every fact is exact, and every keyboard and screen reader works.

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
| A | The engine runs on servers, cloud-gaming style, and streams to clients on the web, Android, and desktop. iOS is the exception (K). A client-side engine for other platforms comes later. | Streamed clients stay thin and identical; GPU cost per session and network latency are first-order concerns (§11, §17). |
| B | Our own scene runtime, built on Babylon.js, rendered on servers by Babylon Native. | One language with the TypeScript SDK; no browser per session; the same runtime runs on iOS devices through Babylon Native's iOS target (K; E1 confirms Linux GPU servers, E7 iPhones). |
| C | Platform text input and platform accessibility are first-class. | Clients host native editors and native accessibility trees; this is the differentiator from game engines. |
| D | Not necessarily 3D. | Worlds come in three kinds (§7); most apps will start in 2D or 2.5D. |
| E | Facts are drawn by the engine as real text in the world, from code. | Exact and immersive at once; generative layers never repaint them (§12). |
| F | Touch and click are raycasts against declared objects. | Geometry decides interactivity, never pixels (§10). |
| G | The first milestone delivers apps and user flows, without OS capabilities such as camera or files. The exporter compiles those later. | M1 scope (§15). |
| H | SDKs for TypeScript and Python from the start; the app talks to the engine over a language-neutral protocol. | Handlers run in the app's own process, in its own language (§6). |
| I | A release is a generation. Worlds and props are generated once per release and shared by every user until the next generation. | Generated-asset cost is per release, not per user; only live layers (L2, L3) cost per session (§7.1). |
| J | Worlds start in 3D. | One world asset serves every screen shape: phones, watches, and wide screens get camera moves and recomposition, never regeneration. |
| K | iOS clients render on device from M1. The engine on the server keeps the journey, composition, embodiment, and the app protocol, and sends **scene state** instead of video; the scene runtime on the iPhone (Babylon Native, Metal) renders it, hit-tests it, and animates it. | Apple's 4.2.7(e) against thin clients for cloud apps no longer reads on us (Q11). iOS sessions use no server GPU. One runtime runs in two places, kept in step by a parity check (§13). iOS gets L0 and L1 only: no L2 or L3, which render on servers. |

## 3. Goals, non-goals, success criteria

### 3.1 Goals
- **G1 Intent-only authoring** in TypeScript or Python: no layout, style, screen, or routing code.
- **G2 Any screen.** Continuous composition for any size and orientation; breakdown and merge of
  frames are designed in now and built after M1.
- **G3 Live and interactive.** The app is a running scene, streamed or, on iOS, rendered on the
  device; feedback is immediate.
- **G4 Generated worlds and embodied controls.** Components appear as objects of a generated world,
  under affordance contracts.
- **G5 Exact facts.** Every string, number, and value is rendered by the engine from code.
- **G6 Platform text input and accessibility** on every client.
- **G7 Native apps from day one** through the exporter.
- **G8 A measurable harness:** grounding, legibility, latency, cost per session, and fallback rates.

### 3.2 Non-goals for M1
OS capabilities (camera, files, location, notifications, payments); on-device rendering outside
iOS; the live neural layers (L2, L3); offline use; watch and TV clients.

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
  reported for streamed clients; frame time, memory, and world-pack load time on reference iPhones.

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
| **Object map** | Object id ↔ component ↔ screen-space bounds and input surfaces, per streamed frame; iOS clients compute their own. |
| **Scene state** | What the scene runtime is built from: objects, props by world-pack id, placements, text, states, camera. In process on servers; sent to iOS clients instead of video. |
| **Client** | The exported native shell: stream player (on iOS, the scene runtime), local feedback, native text, native accessibility, OS bridge. |
| **Exporter** | Builds clients for each platform from one app. |
| **App protocol** | Engine ↔ app process: intent registration, handler calls, enter hooks. |
| **Client protocol** | Engine ↔ client: a media stream (scene state on iOS) plus a data channel for input, context, object map, accessibility. |
| **Layer** | L0 engine with default assets · L1 generated assets · L2 live restyle · L3 world model. |

## 5. Architecture

```
 APP PROCESS (TypeScript or Python)                    WORLD (designer)
 tapes · handlers · services                              │
        │  App protocol (intent, handler calls)           │
        ▼                                                 ▼
 ┌───────────────────────────────── ENGINE (server, GPU) ──────────────────────────────────┐
 │ Journey runtime ─► Composer ─► Embodier ─► Scene runtime ─────────► Generation layers   │
 │ reels, values,     any screen,  props and   scene graph, cameras,    L1 assets · L2     │
 │ derived steps      breakdown,   contracts   in-world text, raycasts, restyle · L3 world │
 │                    merge                    render passes            model              │
 │                                                    │                      │             │
 │                                             Grounder ◄────────────────────┘             │
 │                                                    │                                    │
 │                                             GPU encoder ─► WebRTC                       │
 └────────────────────────────────────────────────────┬────────────────────────────────────┘
          video (and audio)  ▼                        ▲  input, text, context, a11y actions
          data: object map, input surfaces, accessibility tree, feedback hints
 ┌────────────────────── CLIENT (exported: web · Android · desktop · later watch, TV) ─────┐
 │ stream player · local feedback · native editor on input surfaces · native accessibility │
 │ tree · context reporting · OS bridge (camera, files, … after M1)                        │
 └─────────────────────────────────────────────────────────────────────────────────────────┘
```

On iOS (decision K) the engine stops before rendering and sends scene state instead of video:

```
 ENGINE (server, no GPU per session)                                    iOS CLIENT (exported)
 Journey runtime ─► Composer ─► Embodier ── scene state, world pack ──► Scene runtime on Babylon
                                         ◄── actions on objects, text,  Native (Metal): render,
                                             context, a11y actions      raycast, animate, text
                                                                        native editor · native
                                                                        accessibility · OS bridge
```

**Loops and budgets**

| Loop | Trigger | Work | Budget |
|------|---------|------|--------|
| Feedback | Touch, click, key | Client highlights the object under the finger from the object map (on iOS, raycasts and plays the state animation itself); the native editor takes keystrokes | Next client frame |
| Interaction | Input reaches the engine | Raycast, state change, animation, handler call when needed | Input-to-photon ≤ 100 ms on a good network (target, E2); on iOS, one round trip plus the handler |
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
| **L2** | A live neural restyle over the engine's render (video to video), conditioned on depth and object ids | M3; per session, costly; streamed clients only |
| **L3** | A real-time world model renders the scene from the engine's state and actions | When models accept state conditioning and expose APIs; streamed clients only |

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

### 7.1 When generation happens: releases

A release in Videotape is what a front-end deploy is today, and it is the only time L1 generation
runs:

1. `videotape release` reads the app's intent and world.
2. The coherence critic and the embodier (a Claude model) run once and produce the embodiment table.
3. The world and any missing props are generated (Marble for 3D worlds), and the asset harness
   checks them.
4. The result is a versioned **world pack** (assets, colliders, embodiment table, harness report)
   that every engine loads and every user shares. iOS clients download it once per release and
   cache it; it carries phone-weight variants (Marble's 500k-splat export or its textured mesh)
   within a size budget set in E7.

Generation runs again only when something gives it a reason:

| Trigger | What regenerates |
|---------|------------------|
| A release that changes intent (new frames, new component kinds or roles) | Only the props and embodiments that changed |
| A release that changes the world | The world pack |
| A failed harness check or a reported glitch | That one asset, as a patch release |
| A provider or model upgrade | Opt-in, as a new release |
| Declared flavour variants (a night variant, a pro-plan mood) | Each variant once, at release |

**A release that adds features also needs a store update.** The stores accept server-side changes
to content and presentation, not features switched on after review (§11.1). `videotape release`
sorts each change. Presentation (worlds, props, composition, copy, style, and changes inside a
reviewed tape) ships from the server alone. Features (new tapes, new capabilities, new kinds of
purchase) go into the feature manifest and reach store users only with new shell builds and
review notes. Where the stores draw the line is not written down, so this default is
conservative. Web clients have no store and take both at once.

At runtime, L1 never generates: a missing or failing asset falls back to its plain prop until the
next release. Screen changes never regenerate anything; the camera and the composer adapt the
existing world. The costs that grow with users are the stream itself (not on iOS, which renders on
the device) and the live layers (L2, L3), which are per session and per minute.

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

Our own runtime on Babylon.js (Q3). Its input is scene state, the composer's and embodier's output:
in process on servers, and over the client protocol on iOS. Its job:

- Build and update the scene graph from scene state: props, layers or meshes, lights, cameras.
- Render **text from code** in the world (signed-distance-field text on prop surfaces), with the
  world's materials applied as long as legibility holds.
- **Hit-test by raycast** against declared objects' colliders. Undeclared geometry is never
  interactive.
- Animate states (hover, pressed, focus, disabled, error) and composition changes.
- Produce render passes: colour, depth, object ids, a **facts-free** colour pass (for L2 and L3), and
  the text pass composited last.
- Run headless on GPU servers, many sessions per GPU, at an adaptive frame rate (idle scenes drop
  their rate). None of the candidate engines renders pixels in plain Node; the runtime renders on
  servers with Babylon Native ([03-landscape.md](03-landscape.md) §7.3), and E1 confirms it runs
  headless on Linux GPU servers at the needed session density. Headless Chromium is the fallback.
- Run on iPhones through Babylon Native's iOS target (Metal), the same code built into the iOS
  client, rendering on demand so an idle scene costs no battery (E7).
- Run deterministically in CI with L0 assets.

## 11. Streaming and the client

**Server side.** For streamed clients (web, Android, desktop), each session renders on a GPU, is
encoded on the GPU, and is sent over WebRTC. For iOS clients, the engine sends scene state over a
WebSocket and renders nothing. Input, text, context, and accessibility actions come back on the
data channel or the WebSocket.

**The client** is the same small program on every platform, with one difference: streamed clients
play video, and the iOS client is a native shell around Babylon Native that runs the scene runtime
on the device.

| Duty | How |
|------|-----|
| Show the app | Streamed: hardware video decode; letterbox nothing (the composer composes for the real screen). iOS: the scene runtime renders scene state on the device, with the world pack cached per release |
| Immediate feedback | Streamed: highlight the object under the finger from the object map before the engine's frame arrives. iOS: raycast locally and play the pressed or focused state at once |
| Text input | While a field is focused, a **native editor** sits on the field's input surface (position, size, and transform from the object map, or on iOS from the local scene), styled to the world. Caret, selection, IME, autofill, and password managers are the platform's own. Values travel per the commit policy; the engine renders committed text in the world. Secret fields use secure entry; the engine only ever draws masking dots. |
| Accessibility | A **native accessibility tree** from intent (roles, names, states, actions) with bounds from the object map: virtual views on Android, accessibility elements on iOS, ARIA on the web, platform APIs on desktop. Screen-reader actions become engine events. |
| Context | Measures and streams screen, input methods, preferences, and network |
| Resilience | Keeps the last frame (on iOS, the live scene) and the accessibility tree on a dropped connection; reconnects and resumes the reel |
| OS bridge (after M1) | Executes capability requests (camera, files, location, notifications, share, biometrics, payments) and returns results |

### 11.1 Store rules for exported clients

Exports pass store review. Apple's App Store, Google Play, and the Microsoft Store were checked
against their current rules ([03-landscape.md](03-landscape.md) §8). Google Play and the Microsoft
Store have no rule against streamed interfaces. Apple's 4.2.7(e) says "Thin clients for
cloud-based apps are not appropriate for the App Store", and its 4.7 allows streaming only for
games, so iOS clients render on the device (decision K, Q11). Every exported client follows these
rules:

| Rule | Design | Source |
|------|--------|--------|
| Bundled client | The client (the web client, or on iOS the scene runtime) ships inside the binary and updates through the store; the shell never loads our website. | Apple 4.2; Play Spam |
| Data, not code, on iOS | Scene state and world packs are data and resources; the runtime that reads them is in the binary, and no code is downloaded. | Apple 2.5.2; DPLA 3.3.1(B) |
| Feature manifest | Each shell build carries the list of features it was reviewed with (tapes, capabilities, purchase kinds) and sends it in `hello`. The engine serves only those features, to reviewers and users alike (§7.1). | Apple 2.3.1(a), 2.5.19; Play Deceptive Behavior; Microsoft 10.2.2 |
| One app per shell | A shell plays one app. A catalogue of apps in one binary is out of scope. | Apple 4.7.1–4.7.5 |
| The owner submits | The exporter produces a project that the app's owner signs and submits from their own developer account. | Apple 4.2.6, 4.3(a); Play Repetitive Content |
| Purchases | Digital goods are sold only through the shell (StoreKit, Play Billing) as a capability after M1; the engine's UI never takes payment for them. Storefront rules are server configuration. M1 apps sell nothing. | Apple 3.1.1; Play Payments; Microsoft 10.8.1 |
| Accounts and privacy | Sign in with Apple wherever social sign-in is offered; in-app account deletion; a privacy policy link; consent before user content reaches a third-party model (L2 providers); a "report this screen" action. | Apple 4.8, 5.1.1, 5.1.2(i); Play account deletion, AI-generated content |
| Offline | Native offline, reconnect, and error screens in the shell, never only in the engine's UI. | Apple §4; Play functionality |
| Mac | Distributed directly (Developer ID, notarised) by default. The Mac App Store's 2.4.5(iv) also forbids downloaded resources that significantly change the app, which a new world pack may do. | Apple 2.4.5 |

## 12. Facts

- Every string and value is rendered by the engine from code, as real text on the prop that carries
  it. Generation never draws facts. On iOS the device's scene runtime draws the strings the engine
  sends, with the same text renderer.
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
| iOS renderer | Parity with the server render for reference scenes (object-id pass, hit targets, text legibility); frame time, memory, and world-pack load time on reference iPhones | CI, per release |
| All | Input-to-photon latency, composition settle time, frame rate, cost per active hour, fallback rate | Continuous |

Failures fall back per object (plain prop), per layer (drop L2 or L3 for the session), or to L0. The
same checks over reference apps, worlds, and screens form the evaluation suite that tracks model
progress.

## 14. Protocols, sketched

**Client protocol** (streamed clients: WebRTC media plus a data channel; iOS: a WebSocket):

| Direction | Message | Carries |
|-----------|---------|---------|
| C→S | `hello`, `context` | Session resume token, shell build and feature manifest, world-pack version (iOS), context, then context deltas |
| C→S | `input` | Pointer, touch, key, crown, and remote events in stream coordinates, with the frame they were made against; on iOS, actions on object ids from the local raycast, with the scene version they were made against |
| C→S | `text` | Editor commits and changes per the commit policy; composition state for live preview |
| C→S | `a11y` | Screen-reader actions on accessibility nodes |
| S→C | `objects` | Object map for the current frame: bounds, input surfaces, feedback hints (streamed clients) |
| S→C | `scene` | Scene state, a snapshot and then deltas: objects, props by world-pack id, placements, text, states, camera, animations (iOS) |
| S→C | `pack` | The world pack's version and where to fetch it (iOS) |
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
| E1 | Babylon.js on Babylon Native, headless on a Linux GPU server: SDF/MSDF text, raycasts, object-id and depth passes, splats; headless Chromium as the comparison | That Babylon Native works there; frame time; sessions per GPU; text quality |
| E2 | Streaming: GPU encode and WebRTC to web, Android, and desktop test clients | Input-to-photon latency; sessions per GPU; cost per active hour |
| E3 | Native editor over a stream on Android and the web, and over the local scene on iOS | IME, autofill, and password managers across the seam |
| E4 | Native accessibility trees from intent on iOS, Android, and the web | VoiceOver and TalkBack parity |
| E5 | Python SDK over the app protocol with the demo app | Ergonomics; handler latency |
| E6 | L2 round trip: the engine's facts-free view through a hosted restyle and back, text composited, re-encoded | Added latency; legibility; whether controls stay recognisable; cost per stream-hour |
| E7 | iOS on-device renderer: Babylon Native in an iOS shell, fed scene state by a server engine; MSDF text, raycasts, splats, a Marble world pack, the native editor and VoiceOver over the local scene | That Babylon Native renders splats on iOS; frame time, memory, heat, and battery on the oldest supported iPhone; world-pack size budget and load time; parity with the server render |

| Milestone | Delivers | Done when |
|-----------|----------|-----------|
| **M1 Apps and flows** | Scene runtime (L0) on servers and on iPhones, continuous composer, streaming to web, Android, and desktop, scene state to iOS, clients exported for all four under the store rules (§11.1), native text and accessibility, TypeScript and Python SDKs, two sample apps, CI with generation off; the iOS client passes an external TestFlight review | S1–S7 |
| **M2 Generated worlds** | `videotape release` and world packs, with phone-weight variants for iOS; L1 3D worlds (Marble) and props, then 2.5D and 2D; embodiment; coherence critic; asset harness | The demo runs in two 3D worlds that both pass the harness, on every reference screen and reference iPhone without regeneration |
| **M3 Adaptive composition and live looks** | Breakdown and merge with hooks; L2 live restyle with grounding on streamed clients | A 20-field form breaks into steps on a watch-sized screen; L2 holds grounding |
| **M4 Native capabilities** | Capabilities through the exporter's OS bridge; the on-device engine for Android and desktop | Camera and file flows work on iOS and Android |
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
| Streaming latency makes the app feel remote | Local feedback from the object map; native editors; servers near users; on-device rendering on iOS now, elsewhere later (M4) |
| GPU cost per session | L0 and L1 are cheap to render; many sessions per GPU; adaptive frame rate; L2 and L3 only where they pay; iOS sessions use no server GPU |
| Data use and battery on mobile | Adaptive frame rate and bitrate; idle scenes nearly free to encode |
| No offline use | Accepted for M1; the on-device engine removes it later |
| Apple reads the iOS client as a thin client anyway, because the server drives the scene | It renders, hit-tests, and animates on the device like any game client, with native text, accessibility, and offline screens (§11.1); an external TestFlight review in M1 |
| iPhones cannot carry generated worlds (splats on older devices, memory, heat, battery, download size) | E7 before M1; phone-weight variants in the world pack (fewer splats or a textured mesh); rendering on demand; plain props as the fallback |
| The server and iOS renders drift apart (Linux GPU and Metal backends) | One runtime codebase; a parity check per release (§13) |
| iOS users never see L2 or L3 | Accepted for now (decision K); L1 carries the look. Revisit when on-device models or Apple's rules allow |
| Server-side feature changes read as hidden features (Apple 2.5.19, Play Deceptive Behavior) | A feature manifest per shell build; feature releases ship with shell updates and review notes (§7.1, §11.1) |
| Text input and accessibility gaps across platforms | E3 and E4 before M1; parity tests per client in CI |
| Game-like interfaces are harder to learn | Affordance contracts and judge; consistent props per world; plain mode always available |
| Vendor dependency for generation | Layers are plugins; L0 always works; open-weights paths tracked in the landscape |
| L2 costs $36–144 per stream-hour at today's prices | L2 off by default; enabled per app or per session where it pays; L1 carries the look |
| No WebRTC client for watchOS found | Watch clients come after M1, over another transport if needed (Q15) |
| Provider terms change or conflict (World Labs' own documents disagree on commercial rights and credit expiry) | Confirm terms in writing before shipping; keep an open-weights alternative per layer |

## 18. Decisions on the open questions (2026-10-23)

| # | Question | Decision |
|---|----------|----------|
| Q1 | How are the M1 clients built? | The web client inside native shells (a system web view on Android, a desktop shell). On iOS, a native shell around Babylon Native that renders on the device (Q11). Native players elsewhere later, where performance or watches need them. |
| Q2 | How does the engine render on servers? | Babylon Native, with headless Chromium as the fallback if E1 finds a blocker. Babylon Native also renders on iPhones (Q11). |
| Q3 | Which TypeScript web engine? | Babylon.js. |
| Q4 | Who runs engines? | Self-hosted containers first; a hosted Videotape cloud later. |
| Q5 | GPU density and cost targets for L0 and L1? | Measured in E2, then set. |
| Q6 | Which world kind first? | 3D (decision J), generated once per release (decision I). |
| Q7 | Providers for L1 3D worlds and L2? | Marble for 3D worlds, after World Labs confirms commercial terms in writing; Decart's Lucy Restyle 2 for the L2 trial (E6). |
| Q8 | Breakdown policy (M3)? | By default, with opt-out and hooks. |
| Q9 | Merges (M3)? | Declared merges only. |
| Q10 | Worlds per app? | One per app, overridable per tape; each generated per release. |
| Q11 | Do app stores accept streamed interfaces? | Researched from the official guidelines ([03-landscape.md](03-landscape.md) §8). Google Play and the Microsoft Store: yes, under the rules in §11.1. Apple: 4.2.7(e) says thin clients for cloud apps do not belong on the App Store, so iOS clients render on device from M1 with Babylon Native, fed scene state by the engine, with L0 and L1 but no L2 (decision K). Streaming stays the path on the web, Android, and desktop. On every store, server-side change covers presentation; new features need a store update (§7.1). |
| Q12 | Which model for embodiment and coherence, and when? | A Claude model at release time; results live in the world pack; no language model in the click path. |
| Q13 | Plain mode? | Always available to users, and the automatic fallback. |
| Q14 | With L2 on, where are text and controls composited? | On the engine; revisited after E6 measures the extra leg. |
| Q15 | Watch transport and client? | Decided when watch clients are planned, after M1. |
