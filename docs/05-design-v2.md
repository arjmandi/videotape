# Videotape: UI as a Game — Design v2

**Date:** 2026-10-23 · **Status:** draft; core decisions taken (§2, §18), including the leverage
review's Q24–Q30; no v2 code yet · **Supersedes:** the concept of [02-spec-v1.md](02-spec-v1.md) ·
**Evidence:** [03-landscape.md](03-landscape.md) · **Prototype:** tag `prototype-0` · **Reviews:**
[07-review-from-apps.md](07-review-from-apps.md) (Q17–Q21 still open),
[08-leverage-review.md](08-leverage-review.md) (folded in)

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
> what the app must do (types, places, decisions) in TypeScript or Python. Designers direct the
> world it lives in. The device reports its screen. The engine composes the app into a live,
> interactive scene in a generated world and sends the scene to a native client on any platform,
> which renders it on the device (or plays a stream where a session needs the server's render), and
> guarantees that every control is real, every fact is exact, and every keyboard and screen reader
> works.

- **A game, not necessarily 3D.** "Game" means a live render with state, geometry, a camera, and
  input. A world can be flat, layered 2.5D, or full 3D. The goal is not depth for its own sake; it
  is the freedom to make better interfaces with less maintenance, on every screen.
- **The graph is the level.** The journey graph developers declare is laid out in the world at
  release: frames are places, edges are camera paths, and the world reacts to the journey (§8,
  §9.1). Transitions, rotation, resizing, breakdown, and merge are camera decisions, not layouts.
- **Generative UI by rendering, not by code.** Generative-UI projects write front-end code on the
  fly. Videotape writes no front-end code at any time: there is a declaration of intent, a world,
  and an engine that plays them.
- **Native apps from day one.** One app, exported to iOS, Android, desktop, and the web, later to
  watches and TVs. The OS integration layer works like Electron or other cross-platform shells; the
  interaction layer works like a live game, rendered on the device.
- **Built for next year's models.** Real-time world generation will become ordinary. The engine is
  where those models plug in, and the harness is what makes them behave as interfaces. Intent is
  also how models drive apps: every frame is a tool with typed inputs and declared outcomes (§6.5).

**What makes it different from Unity and other game engines:** it is built for apps. Journeys are
the program, state is typed documents the engine renders reactively, every screen size is composed
rather than designed, text input uses the platform's own editors, and accessibility is first-class.
A game engine has none of these.

## 2. Decisions taken

| # | Decision | Consequence |
|---|----------|-------------|
| A | The engine runs on servers and produces **scene state**; every client renders it on the device (Babylon.js on the web, Babylon Native on iOS, Android, and desktop). The server renders and streams only where a session needs it: the first seconds while the world pack downloads (bootstrap), sessions with L2 or L3, and weak devices. Decided as Q24 (2026-10-23) over the first draft's cloud-gaming default. | Interaction is local and text is exact on every client; GPU cost and latency are first-order concerns only on the streamed paths (§11, §17). Clients carry a renderer and one world pack per release (§7.1). |
| B | Our own scene runtime, built on Babylon.js. It runs on devices (Babylon.js in browsers, Babylon Native elsewhere) and on servers by Babylon Native for streamed sessions. | One language with the TypeScript SDK; one runtime in every place it runs, kept in step by a parity check (§13); E1 confirms Linux GPU servers, E7 devices. |
| C | Platform text input and platform accessibility are first-class. | Clients host native editors and native accessibility trees; this is the differentiator from game engines. |
| D | Not necessarily 3D. | Worlds come in three kinds (§7); most apps will start in 2D or 2.5D. |
| E | Facts are drawn by the engine as real text in the world, from code. Images and media from data are facts too: shown exactly, never generated or restyled. | Exact and immersive at once; generative layers never repaint them (§12). |
| F | Touch and click are raycasts against declared objects. | Geometry decides interactivity, never pixels (§10). |
| G | The first milestone delivers apps and user flows, without OS capabilities such as camera or files. The exporter compiles those later. | M1 scope (§15). |
| H | SDKs for TypeScript and Python from the start; the app talks to the engine over a language-neutral protocol. | Handlers run in the app's own process, in its own language (§6). |
| I | A release is a generation. Worlds and props are generated once per release and shared by every user until the next generation. | Generated-asset cost is per release, not per user; only live layers (L2, L3) cost per session (§7.1). |
| J | Worlds start in 3D. | One world asset serves every screen shape: phones, watches, and wide screens get camera moves and recomposition, never regeneration. |
| K | Rendering on the device began as the iOS exception to the cloud-gaming default, after Apple's 4.2.7(e) (Q11); A now makes it the rule for every client. The engine keeps the journey, documents, composition, embodiment, and the app protocol, and sends scene state; the device renders, hit-tests, and animates it. | Apple's rule no longer reads on us; no server GPU per ordinary session. L2 and L3 remain server-rendered and streamed (§7). |
| L | Types are the vocabulary. Components are projections of typed records (Pydantic in Python, Zod in TypeScript); a frame names the record it shows or edits and the engine derives inputs, lists, validation, labels, and the accessibility tree. Handlers' edges are the outcomes their bodies return, read by the SDK, and handlers fail with `Reject`. | Intent stays data: the JSON carries the records' schemas and the edges. Explicit components remain for what differs (§6). |
| M | Documents are the state. A frame shows typed documents the engine holds once and syncs to every session showing them; handlers mutate them with ordinary code; changes show at once and roll back if the handler raises. | The reel store, patches, placeholders, topics, and optimistic declarations are gone; the app protocol gains `sync` (§6.2, §14). |
| N | The graph is the level. At release the journey graph is laid out in the world: frames are places, edges are camera paths. The composer chooses the shot (a camera) per context and moves props only when no camera will do. | Transitions are camera moves; object identity is stable; `size` in metres meets pixels in the camera solver (§8). |
| O | The world reacts. The embodier writes a response table per release (journey event → world response), and the world's parameters may follow numbers from documents and context, never strings. L0 ships a default table. | The feedback of a game at the cost of animation on existing assets; runs on every client (§9.1). |
| P | The release bakes the look. Reference stagings per screen class, the premium look (L2) baked into L1 assets, and hand-built L0 worlds that look finished with generation off. | Every client gets most of L2's look at no per-session cost; `videotape dev` is the pitch (§7.2). |

## 3. Goals, non-goals, success criteria

### 3.1 Goals
- **G1 Intent-only authoring** in TypeScript or Python, as types, places, and decisions: no layout,
  style, screen, or routing code.
- **G2 Any screen.** Continuous composition for any size and orientation, camera first; breakdown
  and merge of frames are designed in now and built after M1.
- **G3 Live and interactive.** The app is a running scene rendered on the device; interaction is
  local and a decision is one round trip.
- **G4 Generated worlds, embodied controls, and a camera.** Components appear as objects of a
  generated world under affordance contracts; frames are places in it and edges are camera paths;
  the world reacts to the journey.
- **G5 Exact facts.** Every string, number, value, image, and medium is rendered by the engine from
  code.
- **G6 Platform text input and accessibility** on every client.
- **G7 Native apps from day one** through the exporter.
- **G8 A measurable harness:** grounding, legibility, latency, cost per session, fallback rates, and
  renderer parity.
- **G9 Release-time intelligence, runtime math.** No model in the click path; everything that needs
  judgement lands in the world pack.

### 3.2 Non-goals for M1
OS capabilities (camera, files, location, notifications, payments; opening a link and a web download
are in M1, §6.3); DRM and casting; the live neural layers (L2, L3) and the streamed paths that carry
them; offline journeys; watch and TV clients.

### 3.3 Success criteria for M1
- **S1** A Python developer writes the demo app (landing, docs, sign-in, dashboard, report) as
  records, frames, and handlers, with no layout or front-end code.
- **S2** `videotape export` produces working clients for the web, iOS, Android, and desktop from that
  one app.
- **S3** On each client, a tester signs in and reads the report, by touch, by keyboard only, and with
  the platform screen reader.
- **S4** Rotating a phone or resizing a window moves the camera, and props only when it must, without
  a reload; a tiny canvas stays operable (minimum targets met; content that does not fit scrolls
  within the shot, locally, until breakdown arrives in M3).
- **S5** Typing uses the platform editor: IME, autofill, and password managers work.
- **S6** The whole loop runs with generation off in CI.
- **S7** Frame time, memory, battery, and world-pack load time on reference phones and laptops, and
  the round-trip latency of a decision, are measured and reported; the streamed paths are measured
  when they are built (E1, E2).
- **S8** With generation off, the demo's frames are places in one hand-built L0 world and every
  transition is a camera move; the world answers presses, pending decisions, and rejections.

## 4. Vocabulary

| Term | Meaning |
|------|---------|
| **App** | What a developer ships: records, intent, handlers, services, and a world reference. |
| **Record** | A typed data model (Pydantic, Zod) the engine derives components from: labels, affordances, validation, groups, collections. |
| **Intent** | Tapes, frames (with purposes, what they show and edit, actions), components where they differ from the records, the handlers' edges. |
| **Document** | A record instance the engine holds once and syncs to every session showing it; shared by identity, or the session's own. |
| **World** | The designer's direction: kind (2D, 2.5D, 3D), prompt, materials, references, embodiment hints; drafted from the app. |
| **Context** | What a client reports: screen size and density, insets, orientation, input methods, preferences, network. |
| **Engine** | The server: journey runtime, documents, composer, embodier, scene state, app protocol; for streamed sessions also the scene runtime, generation layers, grounder, and streamer. |
| **Scene runtime** | Our runtime on Babylon: scene graph, cameras, text, input, render passes. On every client; on servers for streamed sessions. |
| **Place** | Where a frame lives in the world, fixed per release by the level layout and identified by its tape and the frame's `id`; edges between frames are camera paths. |
| **History root** | A frame with no back: the app's entry, a hub destination's first frame, or the target of a sign-in or sign-out. |
| **Stage** and **shot** | The stage is a frame's place and props; the shot is the camera the composer chooses for a context. |
| **Staging** | A reference arrangement and camera per frame and screen class, proposed at release; the composer interpolates between stagings. |
| **Composition** | The composer's plan for a context: shot, camera, placements, derived steps. |
| **Embodiment** | The world object (prop) a component appears as, with its affordance contract and responses. |
| **Surface** | A flat, camera-facing prop the world styles, for dense content; plain mode is a world of surfaces. |
| **Native surface** | A platform view the client places on a prop's face: the text editor, the media player; later web views and maps. |
| **Response table** | Journey event → world response, written at release: the world's answers to the journey. |
| **Scene state** | What the scene runtime is built from: places, camera, props by world-pack id, placements, text, states, responses. Sent to every client; in process on servers for streamed sessions. |
| **World pack** | The versioned result of a release: assets, colliders, places and camera paths, embodiment table, stagings, response table, baked looks, harness report. |
| **Object map** | Object id ↔ component ↔ screen-space bounds and input surfaces, per frame, on the streamed paths; clients that render compute their own. |
| **Client** | The exported native shell: the scene runtime, local feedback, native text, native accessibility, OS bridge, and a stream player for the streamed paths. |
| **Streamed paths** | Sessions the server renders and streams: the bootstrap while a pack downloads, L2 and L3 sessions, weak devices. |
| **Exporter** | Builds clients for each platform from one app. |
| **App protocol** | Engine ↔ app process: `register`, `load`, `decide`, `sync`. |
| **Client protocol** | Engine ↔ client: scene state and a data channel for actions, text, context, accessibility; media and an object map on the streamed paths. |
| **Layer** | L0 engine with default assets · L1 generated assets, with the baked look · L2 live restyle · L3 world model. |

## 5. Architecture

```
 APP PROCESS (TypeScript or Python)                    WORLD (designer directs; drafted from the app)
 records · tapes · handlers · services                      │
        │  App protocol: register · load · decide · sync    │
        ▼                                                   ▼
 ┌─────────────────────────────────── ENGINE (server) ──────────────────────────────────────┐
 │ Journey runtime ─► Documents ─► Composer ─► Embodier ─► Scene state                       │
 │ reels, edges,      typed, shared,  stage and shot,  props,       places, camera, props,   │
 │ Reject             synced          camera first     responses    text, states, responses  │
 │                                                                         │                 │
 │ Streamed paths only (bootstrap · L2 · L3 · weak devices):               ▼                 │
 │ Scene runtime ─► generation layers (L2, L3) ─► Grounder ─► GPU encoder ─► WebRTC          │
 └────────────────────────────────────────┬─────────────────────────────────────────────────┘
      scene state (snapshot, deltas),      ▼       ▲  actions on objects, text, context, a11y
      world pack once per release                  │  (media and object map on the streamed paths)
 ┌──────────────── CLIENT (exported: web · iOS · Android · desktop · later watch, TV) ───────┐
 │ scene runtime (Babylon.js on the web, Babylon Native elsewhere): render, raycast, animate │
 │ native editor on input surfaces · native accessibility tree · context · OS bridge         │
 │ stream player for the streamed paths                                                      │
 └───────────────────────────────────────────────────────────────────────────────────────────┘
```

The engine stops at scene state. A client renders it with the same runtime the server would use,
so the picture is the same wherever it is made; the streamed paths exist for the first seconds of a
heavy session, for the live layers, and for devices that cannot render (§11).

**Loops and budgets**

| Loop | Trigger | Work | Budget |
|------|---------|------|--------|
| Feedback | Touch, click, key, scroll, drag | The client raycasts locally and plays the pressed or focused response at once; scrolling and dragging move locally; the native editor takes keystrokes | Next client frame |
| Interaction | Input reaches the engine | A document or state change, a composition change, a handler call when a decision is needed | Local on the device for what the document can answer; one round trip plus the handler for a decision |
| Composition | Screen change, navigation, data change | Choose the shot (the camera first), move props only when no camera will do; on navigation, travel the edge's camera path | ≤ 300 ms to settle; camera moves run at frame rate |
| Generation | A release | Level layout, embodiment, stagings, response table, assets, baking (§7.1); L2 and L3 live when enabled | Release time; L2/L3 per their own budgets |

## 6. Intent and SDKs

Intent is data. It serialises to JSON with a published schema, so any language can produce it.
Handlers are code and stay in the app's process; the engine calls them over the **app protocol**.
What a developer writes fits in three words:

> **Types, places, decisions.** Types say what exists; the engine derives inputs, lists,
> validation, labels, and the accessibility tree from them. Places (frames) say what is on stage
> and what can be done there. Decisions (handlers) say where the journey goes. The engine stages
> it in a world: the graph is the level, the camera travels the journey, and the world reacts.

Intent keeps v1's tapes, frames, actions (`goto`, `jump`, `back`, `stay`), handlers, and enter
hooks; drops every presentation field (`layout`, `slot`, `rect`, templates); and replaces the
reel's string-addressed store with typed records and documents (decisions L and M). This section
gives the model; the SDK's spellings (field options, `vt.show`, `vt.action`, loaders, the testing
API) are shown in [06-getting-started.md](06-getting-started.md).

### 6.1 Records: types are the vocabulary

A record type (a Pydantic model in Python, a Zod schema in TypeScript; both emit JSON Schema, and
the intent JSON carries it) already says what the engine needs:

| The type says | The engine derives |
|---------------|--------------------|
| Field names | Labels, as message keys named after the fields, with ICU plurals and the locale from context |
| `str`, `vt.Text`, `vt.Secret`, `vt.Money`, `int`, `float`, `date`, `bool`, an `Enum` | The affordance (`write`, `choose`, `adjust`) and the input kind; `vt.Text` is multi-line, one to six lines unless `lines=` says otherwise; a secret reaches the handler once and is never stored or drawn |
| `vt.Id` | The document's identity, by which the engine holds it, syncs it, and keys list items. Never shown, and not required until the app saves the record: an edited document, or an item a handler adds, has none until then and the engine keys it meanwhile. A shown record without an `Id` field is the session's own |
| `Image`, `Video`, `Audio`, `RichText`, `Series` | Facts, shown exactly and never generated or restyled (decision E). `RichText` is a closed model (paragraphs, emphasis, links, lists, code, mentions) drawn by the text engine, with links as actions; `Series` is a chart drawn from data, with a table as its accessible form |
| `\| None`; `Field(ge=, le=, pattern=, max_length=)` | Required or not; validation the engine runs without a handler |
| A nested record | A group kept together |
| A reference to another record | A pick: a call to a tape that returns one (§6.3) |
| `list[X]` | A collection: item template, comparable fields, shape (table, cards, column, one at a time), empty state, paging, and an accessible table, all from `X`; `group_by=X.field` makes a board. In an edited record it is editable (§6.4) |
| `vt.State(...)` fields | Item states props may show (`pending`, `unread`, `mine`), never drawn as text |

A frame names the records it **shows**, which the user reads, and the one it **edits**, which the
user writes, and the engine derives the components. `shows=` takes one record or a list. A list in
a shown record is navigated (`select=`); a list in an edited record is edited (§6.4). Explicit components remain for what differs:
`components=[vt.show(Deal.amount, role="heading")]` overrides the derived one for that field and
adds anything the record does not carry. References are references (`Deal.amount`) and strings are
text; nothing is a path. A reference to a record type (`on=Entry`) means that record wherever the
frame's documents hold it, which must be once; where they hold it twice, the reference names the
field that holds it (`on=Page.toc`), and `check` reports an ambiguous one. The same `on=` says
which items a shown field belongs to: `vt.show(Entry.title, on=Page.toc)`. A chained reference
reaches into a single nested record (`Deal.company.name`); lists are reached with `on=`, which type
checkers accept. Inside a field's own options, a reference to its item type means that item. Components still declare what they are for: `role` (heading, primary,
secondary, navigation, status, supporting), `importance` (required, normal, optional), `group`,
`order`, and `relations` (`labels`, `summarises`, `dependsOn`, `follows`); the record supplies
defaults for all of them. `visible=` and `hidden=` take a `bool` field, never an expression.

A component is embodied as a prop of the world or placed on a **surface**: a flat, camera-facing
panel that the world styles and that is itself a prop (a glass pane, a clipboard, a monitor on the
console). The embodier assigns prop or surface per component at release, so the choice is in the
embodiment table and reviewable; the defaults send collections with three or more comparable
fields, long text, and transcripts to surfaces and everything else to props; `surface=True` or
`False` overrides per component. Plain mode is the world in which every prop is a surface (Q17).

A frame's **purpose** is one sentence that does three jobs: the frame's accessible title, the label
of its primary action unless `submit=vt.action(label, handler)` gives another, and the brief for
the frame's place in the world (§7.1). The purpose is free text and can be reworded at will: a
frame's identity is its tape and its `id`. A tape with one frame needs no frame id, since the tape
is the place; a tape with several frames gives each an `id`, which `goto` needs anyway. A frame may declare an `address` (`"/c/{id}"`), which names it for the web's history,
bookmarks, deep links, and app links; addresses count as features in the manifest (§11.1). A frame
with an address may be `public`: reachable without sign-in and served to crawlers and link-preview
bots as semantic HTML built from the same intent and documents as its accessibility tree, with its
records as structured data, and, from M2, a preview image rendered from its staging at release
(Q19).

**Copy and data.** Documents hold data; copy lives in intent. A literal string in intent is the
default text of a message key named after where it sits. `vt.t(key, **params)` is copy with
parameters, and its parameters may be field references, which the engine fills:
`vt.text(vt.t("dashboard.hello", name=Dashboard.first_name), role="heading")`. Copy that a
handler chooses at runtime is an `Enum` field, whose members are message keys; `Reject` takes a
string or `vt.t`. A `str` field is data, drawn as it is.

```python
import videotape as vt
from services import auth

class Credentials(vt.Record):
    username: str
    password: vt.Secret

async def sign_in(ctx, c: Credentials):
    user = await auth.login(c.username, c.password)
    if user is None:
        raise vt.Reject("Wrong credentials")       # stays; the frame shows the error; the secret is cleared
    return vt.jump("dashboard", sign_in=user)       # the edge, read from this line; history starts here

login = vt.tape("login", [vt.frame("Sign in", title="Welcome back", edit=Credentials, submit=sign_in)])
```

Four lines of intent and a five-line handler; `videotape check` knows every edge.

### 6.2 Documents: one state model

A frame shows typed documents. The engine holds each document once, keyed by its record type and
id; every session showing it is subscribed; a change made anywhere (a handler in any session, the
app process, a timer) reaches every screen that shows it. Shown documents with a `vt.Id` are shared by
identity and live while someone shows them; shown documents without one, and `edit=` documents,
belong to the session, such as a handler's search results. The `enter` loader returns the
documents it loads (one, or a tuple), and the engine dedupes them by id; the others start from
their defaults. Every shown record needs a source when its frame is entered: the frame's loader, an
earlier frame of the same tape, or defaults for each required field; `check` reports one with
none.

A handler receives the documents its frame shows as typed objects, resolved by annotation (as
FastAPI resolves parameters), and mutates them with ordinary code. The SDK sends each change as it
is made; the engine shows it at once and marks it tentative until the handler returns. If the
handler raises, the engine rolls the changes back. There is no patch algebra, no placeholder, no
topic, and no optimistic declaration.

```python
class Message(vt.Record):
    author: User
    text: vt.RichText
    sent_at: datetime = vt.Field(format="time", importance="optional")
    pending: bool = vt.State(False)

class Conversation(vt.Record):
    title: str = vt.Field(role="heading")
    id: vt.Id
    messages: list[Message] = vt.Field(anchor="end")
    typing: str | None = vt.Field(role="status", importance="optional")

class Draft(vt.Record):
    text: vt.Text = ""

@vt.pages(Conversation.messages)
async def older_messages(ctx, conv: Conversation, cursor: str | None) -> vt.Page[Message]:
    msgs, next_cursor = await db.messages(conv.id, before=cursor, limit=50)
    return vt.Page(msgs, next=next_cursor)

async def send(ctx, conv: Conversation, draft: Draft):
    msg = conv.messages.append(Message(author=ctx.user, text=draft.text, pending=True))
    draft.text = ""                                   # both on screen now, in every session showing conv
    msg.update(await db.send(conv.id, ctx.user.id, msg.text), pending=False)
    return vt.stay()

thread = vt.tape("thread", [
    vt.frame("Read and reply", shows=Conversation, edit=Draft, submit=vt.action("Send", send),
             address="/c/{id}", enter=load_thread, actions=[
                 vt.action("Reply", start_reply, on=Message, gesture="swipe-trailing"),
                 vt.action("Copy", vt.copy(Message.text), on=Message),
             ]),
])

async def deliver(conversation_id: str, incoming: Message):    # called by your service, anywhere in the app process
    vt.docs[Conversation, conversation_id].messages.append(incoming)
```

What the document can answer, the engine answers without the app: sorting, filtering, selection,
local search, validation, and every response of the world (§9.1). Only decisions and writes call
the app. Frames may run timers (`after=vt.after(seconds=5, then=next_slide)`).

**Identity.** An outcome may carry `sign_in=user`, the user's record with its `vt.Id`, or
`sign_out=True`; both reset the history (§6.3). Handlers and loaders then see `ctx.user`, that
record; reels are keyed by user and device, so a journey resumes on another device; the app
process can address a user's documents; a deleted account ends every session. Credentials stay with
the app. A document carries the tape version it was loaded under, so a release never changes a
journey under a user (§7.1).

### 6.3 Decisions: handlers and the journey

| Action | Meaning | Camera (§8) |
|--------|---------|-------------|
| `goto(frame)` | The next step in the same tape; it carries no arguments, since a tape's frames share its arguments and documents | A move along the stage |
| `jump(tape, **args)` | Switch journey; the current place goes on the history; the arguments belong to the tape, and any frame's loader in it may take them by name | A dolly along the edge's path |
| `back()` | Return to the previous place; also the platform's back gesture or button, the browser's back, and Escape | The same path, reversed |
| `stay()` | Remain; the document already carries any change | None |
| `hub(destinations)` | Top-level destinations, each a tape with its own history | A hall whose doors are the destinations |
| `call(tape, then=handler)` and `done(result)` | A detour that returns a value to `then=`'s handler, as its parameter `result`; without `then=` the value is dropped. `vt.pick(tape)` on a field is a call that fills the field and needs no handler | A lean toward a side table and back |
| `open(url)` | Open a link in the system browser or the platform's in-app browser view; links in `RichText` use it | None; the world waits |
| `download(name, data)` | Hand the user a file: the browser's download on the web (M1); the share sheet and Files elsewhere (M4) | None |

The edges of the journey graph are the static actions and the outcomes handlers return. The Python
SDK reads them from each handler's body at registration (`return vt.jump("dashboard")`), with
their keyword arguments; the TypeScript SDK reads the inferred return type at build, since
`vt.jump("dashboard")` has the type `Jump<"dashboard">`. Handlers carry no edge annotations, so
linters and type checkers read them as ordinary functions. A name in the tape's position is
resolved against the handler's module at registration, so a string constant works, and so does the
tape itself, a reference rather than a string (`return vt.jump(dashboard)`). Where a body still
cannot be read (a local variable, an outcome built by a helper), the handler declares its edges
with `@vt.outcomes(vt.jump("dashboard"))`, and `check` asks for it. Wherever a tape is named
(outcomes, actions, `vt.pick`, `vt.destination`, `vt.app(entry=)`), the tape itself or its id works;
the object catches a typo when the module loads, and inside a record, which comes before the tapes,
the id is what works. Any handler may
`raise vt.Reject("...")`: the journey stays, the frame shows the message as its error status, and
secrets are cleared, so a `Stay` edge is implied for every handler.

**History and the hub.** Every frame with history has a back edge to where the user came from. A
**history root** has none: the app's entry, the first frame of each hub destination, the target
of an outcome that signs in or out, which resets the history, and a frame opened by its address in
an app without a hub (below). `frame(back=False)` removes
back where returning would be wrong, such as after a payment. A frame shows the hub when its
history root is a hub destination; calls never show it; `frame(hub=False)` hides it for
full-screen moments such as stories. An explicit `vt.back()` is shown only where there is history:
on a frame that is a root on every path, `check` reports it as an error and it is never an exit;
on a frame that is a root on some paths, `check` warns and the client hides it there. One rule
covers both cases: back is a way out only where the frame has history on every path to it.

**Addresses open frames directly.** A frame opened by its address stands on its own: its address
and its loader supply everything it needs, since no earlier frame ran, and `check` reports one that
relies on other arguments or on earlier frames' documents. In an app with a hub, the engine puts
the first hub destination (in hub order) that can reach the frame beneath it, so back and the hub
work as if the user had navigated there, which is how phone apps open a linked conversation. In an
app without a hub, or where no destination reaches the frame, the frame is a history root.

**Tapes carry arguments.** A tape is one journey over the same documents. The jump that enters a
tape passes its arguments, and any frame's loader in the tape may take them, and the documents
its earlier frames loaded, by annotation. `goto` therefore carries no arguments, and a wizard's
steps share one draft.

`videotape check` knows every edge. It counts back as an exit only where the frame has history on
every path to it, and the hub's doors only where every root that reaches the frame is a
destination; a dead end is a frame with neither and with no declared way out. It matches each jump's arguments against the loaders and
addresses of the tape it enters, flags an edit frame that hides a required field, ambiguous record
references, and frames without an `id` in a tape of several, and runs the composer on the
reference screens (§8).

```ts
const Credentials = vt.record({ username: z.string(), password: vt.secret() });
const signIn = vt.handler(async (ctx, c: z.infer<typeof Credentials>) => {
  const user = await auth.login(c.username, c.password);
  if (!user) throw vt.reject("Wrong credentials");
  return vt.jump("dashboard", { signIn: user });            // Jump<"dashboard">, read at build
});
export const login = vt.tape("login", [vt.frame("Sign in", { title: "Welcome back", edit: Credentials, submit: signIn })]);
```

### 6.4 Affordances: the open end of the vocabulary

A component is a type, a role, and a set of affordances. The affordances are the engine's closed
contract: `read`, `write`, `press`, `choose` (one or many), `adjust` (a range), `move` (an item to
a target, or within its list), `add` and `remove` (items of a list), `scroll`, `play`, and, after
M1, `pick` (from the OS). A list in an edited record is editable, and its spelling says how. A
list of an `Enum`, or a list field with `vt.pick(...)` or `options=`, is a choice among existing
values: `choose(many)` (attendees, tags). Any other list of records is owned: `add`, `remove`, and
`move`, with `min_items` and `max_items` as constraints (line items). Whether the item record has
a `vt.Id` does not matter. `select=` on an edited list is a `check` error. Kinds are names for common
combinations: a slider is a number with `adjust`; a board is `list[Deal]` grouped by `Deal.stage`
with `move(Deal → Stage)`; a seat picker is `list[Seat]` with `choose(many)` on a spatial prop.
Named actions declare a label, the affordance they need (`to=Stage` makes a `move`), an optional
gesture hint, an optional key, and the record they act on (`on=Message`). Clients map hints to their
platform; every action is also an accessibility action and appears in a menu, so nothing is
gesture-only. A custom component is a new prop with known affordances (a world-pack entry, no code)
or, rarely, a new affordance, which is a **plugin**: it declares the affordance (its name, the
events it emits, the value it commits, its accessibility role and actions, gesture hints, a minimum
footprint) and ships TypeScript for the scene runtime that draws it and handles its input under the
runtime's rules: text only through the text renderer, interactivity only by raycast on declared
geometry, facts never generated. Plugins are compiled into the engine and into every shell, so they
are reviewed features in the manifest and never downloaded code; Python apps use them by name; the
embodier proposes a prop for a plugin's affordance like any other. The contract is designed in M2
and the first plugins (a timeline scrubber, a whiteboard) ship in M3 (Q23).

### 6.5 Intent is an agent surface

The derivation that gives the accessibility tree (§11) also gives a tool surface: every frame is a
tool with typed inputs and declared outcomes, and every action has a name. An assistant, a voice
input (`voice` is in `Context`), or a test agent can drive any Videotape app with no extra
authoring. Permissions for this surface are not designed yet.

### 6.6 App protocol

The app process connects out to the engine (so apps run anywhere), sends `register` with its intent
JSON (records, tapes, handler names, a services manifest), then answers `load` (enter hooks) and
`decide` (handler calls) and exchanges `sync` (document deltas both ways, tentative and confirmed).
Secrets arrive once and are never stored, logged, or rendered, as in v1. The TypeScript SDK can also
run in the engine's process for local development.

## 7. Worlds and generation layers

A world says where the app lives:

```ts
world("dusk-studio", {
  kind: "2.5d",                      // "2d" | "2.5d" | "3d"
  prompt: "A recording studio at dusk: warm wood, tape machines, soft amber light, quiet.",
  palette: { base: "#1c1612", ink: "#f4ead9", accent: "#ff8a3d" },
  references: ["worlds/studio/ref-1.jpg"],
  embody: { "button.primary": "a lit console key", list: "tape reels on a shelf, one per item" },
  surfaces: { reading: "warm paper under a lamp", data: "a glass pane over the console" },  // Q17
});
```

Designers direct a world the app already implies. `videotape world --draft` writes the first brief
from the tape graph, the frames' purposes, and the records (how many places, what each is for,
which objects exist), and the designer edits it; a world may name the stations it should contain.

| World kind | What it is | Generated with |
|------------|------------|----------------|
| **2D** | Flat surfaces and props, like a well-made card game | Image models: backgrounds, props, materials |
| **2.5D** | Layers at depths with parallax, a camera that can push and pan | Image models with depth or layer output; outpainting for oversize plates |
| **3D** | Meshes or Gaussian splats with colliders | World-generation models that export engine assets |

Generation layers, each optional and each measured by the harness:

| Layer | What generation does | Status |
|-------|----------------------|--------|
| **L0** | Nothing: default and procedural assets, hand-built to look finished (§7.2). Generation off, CI, every fallback, plain mode. | M1 |
| **L1** | Worlds and props generated once as assets, rendered live by the engine at full frame rate, with the look baked from L2 at release (§7.2) | M2; the main path |
| **L2** | A live neural restyle over the engine's render (video to video), conditioned on depth and object ids | M3; per session, costly; streamed sessions only |
| **L3** | A real-time world model renders the scene from the engine's state and actions | When models accept state conditioning and expose APIs; streamed sessions only |

What the landscape says today ([03-landscape.md](03-landscape.md) §7, checked 2026-10-23):

- **L1 is usable now.** World Labs' Marble has a self-serve World API: a 3D world in about 5 minutes
  for about $1.20–2.50, with SPZ splats, a collider mesh, and metric scale. For 2.5D sets,
  Qwen-Image-Layered (layered RGBA) and Depth Anything 3 (depth) are Apache-2.0. Tencent's
  HunyuanWorld licence excludes the EU, the UK, and South Korea.
- **L2 is usable, with a constraint.** Hosted video-to-video (Decart's Lucy Restyle 2 at $0.01 a
  second, Lucy 2.5 at $0.02, 720p) takes a video stream and a prompt, not depth or object ids. The
  engine therefore renders a conditioning view designed for it, and composites text after it (§12).
  At $36–72 per stream-hour, L2 is a premium layer, not a default; most of its look reaches every
  client through the bake (§7.2).
- **L3 is not ready for products.** Genie 3 has no API; Odyssey-2 Pro has one with no published
  price; open weights such as Waypoint-1.5 (Apache-2.0) run on one consumer GPU. L3 is an
  experiment, not a dependency.

**Coherence.** Before generating, a critic compares the world with the intent (domain, density,
tone) and warns about strained pairings. It warns; it does not block.

### 7.1 When generation happens: releases

A release in Videotape is what a front-end deploy is today, and it is the only time generation and
judgement run:

1. `videotape release` reads the app's intent, records, and world.
2. **Level layout** (decision N). The tape graph and the frames' purposes become the world's brief;
   places are laid out in the world's free space against the collider mesh, a tape as a room and
   its frames as stations, a hub as a hall; a camera path is computed per edge; a tape with its own
   world (Q10) joins through a doorway.
3. The coherence critic and the embodier (a Claude model) run once and produce the embodiment
   table, the **reference stagings** (an arrangement and a camera per frame and reference screen
   class), and the **response table** (§9.1).
4. The world and any missing props are generated (Marble for 3D worlds), and the asset harness
   checks them.
5. **Baking** (decision P). The premium look is run over the reference renders and captured into the
   pack: a colour grade per place, a relit panorama, re-coloured splats, and, after E9, prop
   textures back-projected with the depth and object-id passes.
6. The result is a versioned **world pack** (assets, colliders, places and camera paths, embodiment
   table, stagings, response table, baked looks, harness report) that every engine loads and every
   client downloads once per release and caches, in device-weight variants (Marble's 500k-splat
   export or its textured mesh) within the size budget set in E7.

Generation runs again only when something gives it a reason:

| Trigger | What regenerates |
|---------|------------------|
| A release that changes the graph (new frames or edges) | The level layout and camera paths; places that already exist keep their position where the graph allows, so the map stays familiar |
| A release that changes intent (new records, fields, roles) | Only the props, embodiments, stagings, and responses that changed |
| A release that changes the world | The world pack |
| A failed harness check or a reported glitch | That one asset, as a patch release |
| A provider or model upgrade | Opt-in, as a new release |
| Declared flavour variants (a night variant, a pro-plan mood) | Each variant once, at release |

**A release that adds features also needs a store update.** The stores accept server-side changes
to content and presentation, not features switched on after review (§11.1). `videotape release`
sorts each change. Presentation (worlds, props, composition, stagings, responses, copy, style, and
changes inside a reviewed tape) ships from the server alone. Features (new tapes, new addresses,
new capabilities, new kinds of purchase) go into the feature manifest and reach store users only
with new shell builds and review notes. Where the stores draw the line is not written down, so this
default is conservative. Web clients have no store and take both at once.

At runtime, L1 never generates: a missing or failing asset falls back to its plain prop until the
next release. Screen changes never regenerate anything; the camera and the composer adapt the
existing world. A reel finishes its current journey on the release it started on, so the engine
serves several releases side by side; a change that breaks a journey's steps bumps that tape's
version. The costs that grow with users are the streamed paths (§11) and the live layers (L2, L3),
per session and per minute; an ordinary session costs the engine no GPU.

### 7.2 Release time is where the intelligence goes

No model runs in the click path (Q12). Everything that needs judgement happens at release and
lands in the world pack; everything at runtime is deterministic:

| At release (judgement, seconds to minutes) | At runtime (math, milliseconds) |
|--------------------------------------------|----------------------------------|
| Level layout: places and camera paths from the graph | The shot: a camera that satisfies the constraints |
| Embodiment table: props and affordances per record field, kind, and role | Raycasts against those props |
| Reference stagings per frame and screen class | Interpolation by aspect ratio; constraint enforcement; hysteresis |
| Response table: journey event → world response | Playing the response |
| Baked look: L2 run over reference renders, captured as a colour grade per place, a relit panorama, re-coloured splats, and (after E9) prop textures | Rendering L1 at full frame rate, on every client |

L0 is what every developer sees first and what plain mode shows every user, so it is not boxes:
two or three hand-built procedural worlds (the plain one, a studio, a desk) with real materials,
lighting, stagings, and response tables ship with the engine. `videotape dev` with generation off
already looks like a game.

## 8. Context and composition

The client measures and streams context; the engine detects nothing:

```ts
interface Context {
  screen: { w: number; h: number; dpr: number };          // CSS px, continuous
  insets: { safe: Edges; keyboard: Edges; hinge?: Rect };  // what the OS and the keyboard take
  pointer: "coarse" | "fine" | "none";
  inputs: Array<"touch" | "mouse" | "keyboard" | "crown" | "remote" | "voice">;
  prefers: { reducedMotion: boolean; colorScheme: "dark" | "light"; textScale: number };
  locale: string;
  network: { rttMs: number; kbps: number };
  render: "local" | "stream";                              // what this client can do
}
```

The **composer** works at two scales (decision N).

**The stage** is fixed per release: the place a frame lives in and the props that stand there, from
the level layout and the embodiment table (§7.1).

**The shot** is continuous per context, and it is a camera first. The composer chooses a camera
position, direction, and focal length that fill the screen with the required props, keep text
legible at that distance for this density and text scale, keep the primary action within reach, and
leave room for the world's subject. It interpolates between the two reference stagings nearest in
aspect ratio and enforces the constraints; it moves props within the stage only when no camera
satisfies them, with hysteresis. This is where a prop's size in metres meets the screen's pixels.
The composer is a function of (the stage, context, the previous shot) and returns in under 50 ms.

- **Capacity.** Every component has a minimum footprint for the context: legibility and target
  minimums (for example 44 px touch targets), label length, embodiment size, and the user's text
  scale. The screen has a usable area after insets and pinned items; the keyboard opening is a
  context change the composer answers without moving anything else.
- **One shot** when it fits: a camera on the stage, scored for proximity of related items, reach of
  the primary action, reading order, and room for the world's subject.
- **Camera moves.** `goto` and `jump` travel the edge's camera path; `back` reverses it; a hub is a
  hall; a call leans to a side table (§6.3). Rotating a device turns the camera; resizing a window
  pulls it back or pushes it in. Object identity is stable because the props stay and the camera
  moves.
- **Breakdown** when it does not fit (after M1): close-ups along the stage in order, keeping groups
  whole, with the title pinned and the primary action on the last step; values stay in the
  session's document and reach the handler unchanged. Developers can opt out or adjust the plan
  with hooks.
- **Merge** when there is room (after M1): declared neighbours share a wider shot that holds both
  places; an edge between them becomes a change of focus, not a cut.
- **Surfaces.** A surface is a prop whose face always turns to the shot's camera; the camera solver
  sizes it to the screen, and its text gets the world's type and a backing when the material would
  not carry it (§12).
- **Right-to-left.** The composer mirrors reading order for right-to-left locales; the world does
  not mirror; text follows its script's direction.
- **Static guarantees.** `videotape check` runs the composer for reference screens (watch, phone
  portrait and landscape, tablet, desktop, wall), verifies edges, reachability, and minimums, and
  renders a picture per reference screen from the stagings.

In M1 the composer delivers continuous composition for any screen; a shot whose content does not
fit scrolls within itself, locally on the device. Breakdown and merge follow in M3.

## 9. Embodiment

Each placed component gets a prop of the world:

```ts
interface Embodiment {
  component: string;                     // a record field, a kind and role, or an explicit component
  prop: string;                          // a prefab id in the world pack, or a description to generate one from
  affordance: {
    read?: { maxChars: number }; write?: { lines: number }; press?: true;
    choose?: { options: number; many?: true }; adjust?: { min: number; max: number; step?: number };
    move?: { to: string }; add?: true; remove?: true; scroll?: true; play?: true;
  };
  textSurface?: string;                  // which face of the prop carries the component's text
  surface?: true;                        // a flat, camera-facing prop the world styles (Q17)
  size: { w: number; h: number };        // metres, in the world; the shot's camera turns them into pixels (§8)
  states: Partial<Record<"hover" | "pressed" | "focused" | "disabled" | "error", string>>; // animations or variants
  responses: Partial<Record<JourneyEvent, string>>;   // from the response table (§9.1)
  fallback: "plain";
}
```

A language model proposes embodiments per (world, record field or kind, role) at release; results
live in the world pack, reviewable, and designers and developers can override them. Within a world,
the same kind and role keep the same prop, with per-place variants, so the map stays learnable.
Every prop has a plain fallback the world can always host.

### 9.1 The world reacts

Props have widget states; a game answers more. The embodier writes a **response table** per
release: journey event → world response. The events are the same for every app and are enumerable
from the graph and the documents:

| Event | Example response in `dusk-studio` |
|-------|-----------------------------------|
| Frame entered, left | The camera arrives; the station's lights come up; the last one dims |
| Press | The key lights and clicks |
| Handler pending | The reels turn until the decision returns |
| Outcome taken | The room brightens (signed in); a door opens (a jump) |
| Rejected; validation failed | The meter flickers red; the strip shakes once |
| Document changed; item added or removed | A reel drops onto the shelf; a counter ticks |
| Selection | A spotlight narrows |
| Idle | Dust in the light; the hum |

Responses are animations of existing props, lights, and the world itself, with optional sound
(silent by default on phones, as the platforms expect); L0 ships a default table. **Atmosphere
binds** let numbers and enums from documents and context drive the world's parameters (light, time
of day, weather, camera energy, ambient motion): never strings, and never as the only carrier of a
fact. `prefers.colorScheme` is the time of day; `reducedMotion` holds the world still; `textScale`
brings the camera closer. v1's `flavour` lint stays: no field an input writes reaches the world.

## 10. Scene runtime

Our own runtime on Babylon.js (Q3). Its input is scene state, the composer's and embodier's output:
over the client protocol on every client, and in process on servers for streamed sessions. Its job:

- Build and update the scene graph from scene state: places, camera, props, layers or meshes,
  lights.
- Travel camera paths and play the response table's animations and the world's atmosphere.
- Render **text from code** in the world: shaped with HarfBuzz into signed-distance-field atlases
  on prop surfaces, with bidirectional runs, colour emoji, font fallback across scripts, line
  breaking, and glyph positions for carets and selection; the world's materials applied as long as
  legibility holds.
- **Hit-test by raycast** against declared objects' colliders. Undeclared geometry is never
  interactive.
- Animate states (hover, pressed, focus, disabled, error) and composition changes.
- Produce render passes: colour, depth, object ids, a **facts-free** colour pass (for L2, L3, and
  the bake), and the text pass composited last.
- Run on devices: Babylon.js in browsers (WebGPU, WebGL 2 fallback); Babylon Native on iOS (Metal),
  Android, and desktop; rendering on demand so an idle scene costs no battery (E7).
- Run headless on GPU servers for the streamed paths, many sessions per GPU, at an adaptive frame
  rate. None of the candidate engines renders pixels in plain Node; the server runs the runtime on
  Babylon Native ([03-landscape.md](03-landscape.md) §7.3), and E1 confirms it runs headless on
  Linux GPU servers at the needed session density. Headless Chromium is the fallback.
- Run deterministically in CI with L0 assets.

## 11. The client, and the streamed paths

**Every client renders.** The engine sends scene state over a WebSocket (a snapshot, then deltas)
and the world pack's version; the client fetches the pack once per release and renders the scene
on the device with the scene runtime: Babylon.js on the web, Babylon Native in the iOS, Android,
and desktop shells. Actions on objects (from the local raycast), text, context, and accessibility
actions go back on the same socket. One runtime runs everywhere, kept in step by the parity check
(§13).

**The streamed paths.** The server renders, encodes on the GPU, and streams over WebRTC, with an
object map on the data channel, in three cases. **Bootstrap:** the first seconds of a session while
a heavy world pack downloads; the client then hands off to its local renderer at a known scene
version, so the picture does not change. **Premium:** sessions with L2 or L3, which need the
server's render. **Weak devices:** chosen from the context. Sessions per GPU count these sessions
only.

**Public frames.** The web client's accessibility tree is DOM, so crawlers that run JavaScript read
the content as it is; for the rest, and for link previews, the engine serves `public` frames as
HTML (§6.1). Marketing sites that need more than that stay ordinary websites.

| Duty | How |
|------|-----|
| Show the app | Render scene state on the device; on the streamed paths, hardware video decode. Letterbox nothing: the composer composes for the real screen |
| Immediate feedback | Raycast locally and play the pressed or focused response at once; scroll and drag locally; on the streamed paths, highlight from the object map until the local renderer takes over |
| Text input | While a field is focused, a **native editor** sits on the field's input surface (position, size, and transform from the local scene, or from the object map on the streamed paths), styled to the world. Caret, selection, IME, autofill, and password managers are the platform's own. Values travel per the commit policy; the engine renders committed text in the world. Secret fields use secure entry; the engine only ever draws masking dots. |
| Native surfaces | The editor is one of a family. A **media surface** (video and audio, with captions, full screen, picture-in-picture, and background audio) sits on its prop's face, a screen in the world, as a flat rectangle with a perspective transform, never hidden behind world objects, and reports `play`, `progress`, `ended`, and `error` to the engine as actions. DRM and casting need entitlements and arrive with the M4 capabilities; web views and maps are M4 surfaces. |
| Selection, copy, find | Native selection over the local text runs; copy takes the exact string from the facts, never from pixels; find is an engine action bound to the platform's shortcut |
| Accessibility | A **native accessibility tree** from intent (roles, names, states, actions) with bounds from the local scene (or the object map): virtual views on Android, accessibility elements on iOS, ARIA on the web, platform APIs on desktop. Screen-reader actions become engine events. |
| Context | Measures and streams screen, insets, input methods, preferences, and network |
| Resilience | Keeps the live scene and the accessibility tree on a dropped connection; reconnects and resumes the reel; native offline and reconnect screens (§11.1) |
| Idle | Renders on demand; a backgrounded app disconnects and resumes on return; the server holds nothing but the reel |
| OS bridge (after M1) | Executes capability requests (camera, files, location, notifications, share, biometrics, payments) and returns results |

### 11.1 Store rules for exported clients

Exports pass store review. Apple's App Store, Google Play, and the Microsoft Store were checked
against their current rules ([03-landscape.md](03-landscape.md) §8). Google Play and the Microsoft
Store have no rule against streamed interfaces. Apple's 4.2.7(e) says "Thin clients for
cloud-based apps are not appropriate for the App Store", and its 4.7 allows streaming only for
games, so clients render on the device (decisions A and K). Every exported client follows these
rules:

| Rule | Design | Source |
|------|--------|--------|
| Bundled client | The shell and the scene runtime ship inside the binary and update through the store; the shell never loads our website. | Apple 4.2; Play Spam |
| Data, not code | Scene state and world packs are data and resources; the runtime that reads them is in the binary, and no code is downloaded, on every platform. | Apple 2.5.2; DPLA 3.3.1(B) |
| Feature manifest | Each shell build carries the list of features it was reviewed with (tapes, addresses, capabilities, purchase kinds) and sends it in `hello`. The engine serves only those features, to reviewers and users alike (§7.1). | Apple 2.3.1(a), 2.5.19; Play Deceptive Behavior; Microsoft 10.2.2 |
| One app per shell | A shell plays one app. A catalogue of apps in one binary is out of scope. | Apple 4.7.1–4.7.5 |
| The owner submits | The exporter produces a project that the app's owner signs and submits from their own developer account. | Apple 4.2.6, 4.3(a); Play Repetitive Content |
| Purchases | Digital goods are sold only through the shell (StoreKit, Play Billing) as a capability after M1; the engine's UI never takes payment for them. Storefront rules are server configuration. M1 apps sell nothing. A link that leads to a purchase outside the store is a purchase kind in the manifest, subject to each storefront's rules. | Apple 3.1.1, 3.1.1(a), 3.1.3; Play Payments; Microsoft 10.8.1 |
| Accounts and privacy | Sign in with Apple wherever social sign-in is offered; in-app account deletion; a privacy policy link; consent before user content reaches a third-party model (L2 providers); a "report this screen" action. | Apple 4.8, 5.1.1, 5.1.2(i); Play account deletion, AI-generated content |
| Offline | Native offline, reconnect, and error screens in the shell, never only in the engine's UI. | Apple §4; Play functionality |
| Mac | Distributed directly (Developer ID, notarised) by default. The Mac App Store's 2.4.5(iv) also forbids downloaded resources that significantly change the app, which a new world pack may do. | Apple 2.4.5 |

## 12. Facts

- Every string and value is rendered by the engine from code, as real text on the prop that carries
  it, by the same text renderer on every client. Images and media from data are shown exactly.
  Generation never draws facts.
- Generative layers (L2, L3) receive the facts-free pass; the text pass and the media are composited
  after them, so a restyle can never garble a number or a photo, and user data never reaches a
  generative model. The bake (§7.2) runs over facts-free renders for the same reason.
- Hosted L2 services return video, so the compositing happens on the engine: the restyled stream
  comes back, the text pass is composited using the engine's depth, and the result is re-encoded for
  the client. That adds a network leg to every frame while L2 is on (Q14, E6).
- If a surface cannot carry text legibly, the engine adds a backing to that surface and the harness
  records it.
- Every document a frame shows passes through the engine, so end-to-end encryption is not possible
  in this design: the engine reads what it composes. This is a stated limit (Q20). The engine keeps
  documents in memory for the duration of a journey, never persists or logs them, and never sends
  them to generation or to the bake; self-hosted engines (Q4) keep data residency with the app's
  owner, and privacy labels say so. Because clients render (decision A), a later path exists:
  documents could travel encrypted with keys only on devices, the client decrypting to render and
  reporting the metrics composition needs, which moves part of composition to the client. Not
  before M4.

## 13. Grounding harness

| Layer | What is checked | When |
|-------|-----------------|------|
| L1 | Props read as their affordance (vision-language judge); text surfaces are legible under the world's materials and the baked look (measured in the engine's own buffers, exactly); no lettering painted into generated assets (OCR) | At release, per asset |
| Level and responses | Every edge's camera path stays clear of colliders and arrives within budget; stagings meet the minimums on every reference screen; no response occludes a required prop | At release |
| L2, L3 | Each object still appears where the object-id pass says (per-object correspondence); nothing control-like or text-like appears outside the map (OCR, detector); objects do not drift between frames | Sampled live |
| Renderers | Parity across Babylon.js (web), Babylon Native (iOS, Android, desktop), and the server render for reference scenes (object-id pass, hit targets, text legibility); frame time, memory, battery, and world-pack load time on reference devices | CI, per release |
| All | Decision round-trip latency, composition settle time, frame rate, fallback rate; on the streamed paths, input-to-photon latency and cost per active hour | Continuous |

Failures fall back per object (plain prop), per layer (drop L2 or L3 for the session), or to L0. The
same checks over reference apps, worlds, and screens form the evaluation suite that tracks model
progress.

## 14. Protocols, sketched

**Client protocol** (every client: a WebSocket for scene state and data; the streamed paths add
WebRTC media and an object map):

| Direction | Message | Carries |
|-----------|---------|---------|
| C→S | `hello`, `context` | Session resume token, shell build and feature manifest, world-pack version, context (screen, insets, inputs, preferences, network, render capability), then context deltas |
| C→S | `input` | Actions on object ids from the local raycast, with the scene version they were made against; on the streamed paths, pointer, touch, key, crown, and remote events in stream coordinates with the frame they were made against |
| C→S | `text` | Editor commits and changes per the commit policy; composition state for live preview |
| C→S | `surface` | Events from native surfaces: `play`, `progress`, `ended`, `error` |
| C→S | `a11y` | Screen-reader actions on accessibility nodes |
| S→C | `scene` | Scene state, a snapshot and then deltas: places, camera and camera paths, props by world-pack id, placements, text, states, responses to play |
| S→C | `pack` | The world pack's version and where to fetch it |
| S→C | `objects` | Object map for the current frame (streamed paths only): bounds, input surfaces, feedback hints |
| S→C | `handoff` | The bootstrap stream ends; the client's renderer takes over at this scene version |
| S→C | `tree` | The accessibility tree and its changes |
| S→C | `surface` | Open, style, move, and close a native surface: the editor for a focused field, the media player for a `Video` or `Audio` |
| S↔C | `capability` (after M1) | Requests to the OS bridge and their results |

**App protocol** (WebSocket or HTTP/2, JSON): `register` (intent: records, tapes, handler names,
services manifest), `load` (enter hooks) and `decide` (handler calls) with their results, `sync`
(document deltas both ways, tentative and confirmed), `log`.

Both keep prototype-0's protections: events validated against what is on screen, sequence and
version guards, secrets kept out of logs and storage.

## 15. Milestones

Experiments first, then milestones, each ending in something runnable.

| # | Experiment | Answers | Before |
|---|------------|---------|--------|
| E1 | Babylon.js on Babylon Native, headless on a Linux GPU server: SDF text, raycasts, object-id and depth passes, splats; headless Chromium as the comparison | That the streamed paths work there; frame time; sessions per GPU; text quality | M2 |
| E2 | Streaming: GPU encode and WebRTC to web, Android, and desktop test clients, and the bootstrap handoff to the local renderer | Input-to-photon latency; sessions per GPU; cost per active hour; a handoff the eye does not see | M2 |
| E3 | Native editor and media surface over the local scene on the web, iOS, Android, and desktop | IME, autofill, and password managers across the seam; captions, full screen, and picture-in-picture on a world prop | M1 |
| E4 | Native accessibility trees from intent on iOS, Android, the web, and desktop | VoiceOver and TalkBack parity | M1 |
| E5 | Python SDK over the app protocol with the demo app: records, return-type edges, `Reject` | Ergonomics; decision latency | M1 |
| E6 | L2 round trip: the engine's facts-free view through a hosted restyle and back, text composited, re-encoded | Added latency; legibility; whether controls stay recognisable; cost per stream-hour | M3 |
| E7 | On-device renderer: Babylon.js in browsers and Babylon Native in iOS, Android, and desktop shells, fed scene state by a server engine; shaped text (Persian, Arabic, Hindi, Chinese, emoji), raycasts, splats, a Marble world pack, the native editor and screen readers over the local scene | Frame time, memory, heat, and battery on the oldest supported devices; world-pack size budget and load time; parity across renderers | M1 |
| E8 | Level layout and camera paths in a Marble world: a seven-frame app staged in one world, dollies between places, legibility by distance on a phone and a desktop | That one generated world holds an app's places; what the brief must ask for; camera budgets | M2 |
| E9 | Baking: L2 run over reference renders and captured as a colour grade, a relit panorama, and re-coloured splats; then prop textures by back-projection | How close the baked look gets to live L2; legibility after the bake | M2 (grade, panorama); M3 (textures) |
| E10 | The document loop: tentative writes, confirmation, rollback, fan-out to many sessions, paging | Latency of a local change and of a decision; correctness under failure | M1 |

| Milestone | Delivers | Done when |
|-----------|----------|-----------|
| **M1 Apps and flows** | Engine (journey runtime, documents, composer with stage and shot, embodier, scene state); scene runtime (L0) on the web, iOS, Android, and desktop, with hand-built L0 worlds; clients exported for all four under the store rules (§11.1); native text, native surfaces (editor, media), and accessibility; public frames served as HTML; `open` and web downloads; TypeScript and Python SDKs with records, documents, and return-type edges; two sample apps; CI with generation off; the iOS client passes an external TestFlight review | S1–S8 |
| **M2 Generated worlds** | `videotape release` and world packs: level layout, embodiment, stagings, response tables, Marble worlds and props, then 2.5D and 2D; coherence critic; asset harness; the baked look (grade and panorama); the bootstrap stream (E1, E2) for heavy packs; device-weight variants; preview images for public frames; the plugin contract for new affordances | The demo runs in two 3D worlds that both pass the harness, on every reference screen and device without regeneration; every transition is a camera move |
| **M3 Adaptive composition and live looks** | Breakdown and merge with hooks; L2 live restyle with grounding on streamed sessions; prop-texture baking; the first plugins (a timeline scrubber, a whiteboard) | A 20-field form breaks into steps on a watch-sized screen; L2 holds grounding; the baked look passes the harness |
| **M4 Native capabilities** | Capabilities through the exporter's OS bridge: camera, files, location, notifications, share, biometrics, payments; DRM and casting for media surfaces; web-view and map surfaces | Camera and file flows work on iOS and Android |
| Later | L3 world models; watch and TV clients; client-held keys for documents (§12) | — |

## 16. What carries over from prototype-0

| Prototype-0 part | In v2 |
|------------------|-------|
| Tape model, actions, handlers, enter hooks, `check`, graph | Kept; presentation fields removed; `bind` and the dotted-path store replaced by records and documents (§6); becomes the JSON intent the SDKs produce |
| VTP sessions, event validation, sequence and render guards, resume, secrets handling | Kept in the client and app protocols |
| Engine reels, handler runtime, budgets and fallbacks, renderer host | Kept; the renderer host becomes the release pipeline's generation host |
| Cache keys that cover every input; validator versions and re-checks | Kept for generated assets and bakes |
| OCR lettering check, legibility checks, attempt logs, contact sheets | Kept in the asset harness |
| `traceReads` proxy behind the flavour lint | Kept for atmosphere binds (§9.1) |
| fal image renderer and its findings | Kept for 2D and 2.5D asset generation |
| Layout engine (templates, slots, three classes) | Replaced by the composer; its touch-target rules and free-space search are reused (the latter for level layout) |
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
| The pack download delays the first local render | The bootstrap stream; small L0 worlds; device-weight variants; progressive pack loading |
| Streamed sessions (bootstrap, L2, L3) feel remote | Local feedback from the object map; the bootstrap hands off within seconds; servers near users |
| GPU cost of the streamed paths | Only bootstrap, L2, L3, and weak devices stream; adaptive frame rate; sessions per GPU counted for those alone |
| Battery and heat of rendering on phones | Render on demand; idle scenes cost nothing; device-weight packs; E7 sets the budgets |
| Journeys need the engine; no offline journeys | Accepted; the client keeps the live scene and shows native offline screens |
| Apple reads a client as a thin client anyway, because the server drives the scene | It renders, hit-tests, and animates on the device like any game client, with native text, accessibility, and offline screens (§11.1); an external TestFlight review in M1 |
| Devices cannot carry generated worlds (splats on older devices, memory, heat, download size) | E7 before M1; device-weight variants in the world pack (fewer splats or a textured mesh); rendering on demand; the bootstrap stream; plain props as the fallback |
| Renderers drift apart (Babylon.js on WebGPU and WebGL 2; Babylon Native on Metal, Vulkan, Direct3D, and the Linux server) | One runtime codebase; a parity check per release (§13) |
| Ordinary sessions never see live L2 or L3 | The bake carries most of L2 into L1 (§7.2); live L2 and L3 on streamed sessions where they pay |
| The world generator yields too few distinct stations for the graph | The brief asks for stations by name; multi-image and panorama inputs; a world per tape as rooms (Q10); E8 |
| A camera-first composer fails on extreme aspect ratios (watch, wall) | Props move within the stage when no camera will do; breakdown and merge in M3; `check` runs the reference screens |
| The document store becomes a database | Documents live in memory for the duration of a journey; the app's services remain the source of truth; the engine never persists facts |
| Every document passes through the engine: no end-to-end encryption; retention, residency, and privacy labels apply to the engine | A stated limit (§12); documents in memory only; self-hosting; the client-held-key path under Later |
| Server-side feature changes read as hidden features (Apple 2.5.19, Play Deceptive Behavior) | A feature manifest per shell build; feature releases ship with shell updates and review notes (§7.1, §11.1) |
| Text input and accessibility gaps across platforms | E3 and E4 before M1; parity tests per client in CI |
| Game-like interfaces are harder to learn | Affordance contracts and judge; consistent props per world; one world as the app's map (decision N); plain mode always available |
| Vendor dependency for generation | Layers are plugins; L0 always works; open-weights paths tracked in the landscape |
| L2 costs $36–144 per stream-hour at today's prices | L2 off by default; its look baked at release; enabled live per app or per session where it pays |
| No WebRTC client for watchOS found | Watch clients come after M1 and render locally; the streamed paths may need another transport (Q15) |
| Provider terms change or conflict (World Labs' own documents disagree on commercial rights and credit expiry) | Confirm terms in writing before shipping; keep an open-weights alternative per layer |

## 18. Decisions on the open questions (2026-10-23)

| # | Question | Decision |
|---|----------|----------|
| Q1 | How are the M1 clients built? | Babylon.js in the browser; native shells around Babylon Native on iOS, Android, and desktop; all render on the device (Q24). Native players for watches and TVs later. |
| Q2 | How does the engine render on servers? | Babylon Native, headless, for the streamed paths only (bootstrap, L2, L3, weak devices), with headless Chromium as the fallback if E1 finds a blocker. |
| Q3 | Which TypeScript web engine? | Babylon.js. |
| Q4 | Who runs engines? | Self-hosted containers first; a hosted Videotape cloud later. |
| Q5 | GPU density and cost targets for the streamed paths? | Measured in E2, then set. Ordinary sessions use no server GPU. |
| Q6 | Which world kind first? | 3D (decision J), generated once per release (decision I). |
| Q7 | Providers for L1 3D worlds and L2? | Marble for 3D worlds, after World Labs confirms commercial terms in writing; Decart's Lucy Restyle 2 for the L2 trial (E6) and the bake (E9). |
| Q8 | Breakdown policy (M3)? | By default, with opt-out and hooks. |
| Q9 | Merges (M3)? | Declared merges only. |
| Q10 | Worlds per app? | One per app, overridable per tape; each generated per release; a tape's own world joins the app's through a doorway (§7.1). |
| Q11 | Do app stores accept streamed interfaces? | Researched from the official guidelines ([03-landscape.md](03-landscape.md) §8). Google Play and the Microsoft Store: yes, under the rules in §11.1. Apple: 4.2.7(e) says thin clients for cloud apps do not belong on the App Store, so iOS was decided first to render on device (decision K); Q24 then made rendering on the device the rule for every client. On every store, server-side change covers presentation; new features need a store update (§7.1). |
| Q12 | Which model for embodiment and coherence, and when? | A Claude model at release time, which also writes the stagings and the response table; results live in the world pack; no language model in the click path. |
| Q13 | Plain mode? | Always available to users, and the automatic fallback; the plain L0 world is hand-built to look finished (§7.2). |
| Q14 | With L2 on, where are text and controls composited? | On the engine; revisited after E6 measures the extra leg. |
| Q15 | Watch transport and client? | Decided when watch clients are planned, after M1. |
| Q16 | On streamed clients, are surfaces drawn in the stream or by the client? ([07](07-review-from-apps.md)) | Decided by Q24: every client renders scene state, so surfaces are drawn by the client; the streamed paths carry them in the stream until the handoff. |
| Q17 | Should the composer place components on surfaces as well as props? | Yes. A surface is a flat, camera-facing prop the world styles; the embodier assigns prop or surface per component at release; collections with three or more comparable fields, long text, and transcripts default to surfaces; `surface=` overrides; plain mode is the world where every prop is a surface (§6.1, §8, §9). |
| Q18 | Native media surfaces in M1? | Yes: a media surface for `Video` and `Audio` with captions, full screen, picture-in-picture, and background audio, on the prop's face, reporting events as actions (§11, §14). DRM, casting, web views, and maps come with the M4 capabilities. |
| Q19 | Public pages and search engines? | Yes: `public` frames are served to crawlers and link-preview bots as semantic HTML from the same intent and documents as the accessibility tree, in M1; preview images from stagings in M2 (§6.1, §11). Marketing sites that need more stay ordinary websites. |
| Q20 | End-to-end encryption is impossible: accept it as a stated limit? | Yes, through M3: documents in memory only, never logged, persisted, or sent to generation or the bake; self-hosting keeps residency with the app's owner. A client-held-key path is recorded under Later (§12). |
| Q21 | Links and web downloads in M1? | Yes: `open(url)` on every client and `download` on the web (§6.3); files elsewhere with M4. A purchase link is a purchase kind in the manifest (§11.1). |
| Q22 | Does `videotape dev` render scene state in the browser? | Decided by Q24: yes, as production does. |
| Q23 | Custom components as TypeScript plugins compiled into the engine and the shells? | Yes, for new affordances only; a new prop needs no code (§6.4). The contract is designed in M2 and the first plugins ship in M3. |
| Q24 | Scene state on every client, with the stream as the bootstrap and premium path ([08](08-leverage-review.md) P8)? Trades against the first draft's decision A | Yes. Decision A rewritten, K generalised (§2, §5, §11, §14, §15). It also decides 07's Q16 (surfaces are drawn by the client) and Q22 (`videotape dev` renders scene state in the browser, as production does). |
| Q25 | Typed records as the component vocabulary in both SDKs (P1)? | Yes. Decision L; §6.1. Absorbs 07's F4, F5, F9, F11, F13, F15, F17, F19, F27. |
| Q26 | Documents replace the store, patches, placeholders, topics, and optimistic declarations (P2)? | Yes. Decision M; §6.2, §14. Absorbs F6, F7, F11, F24. |
| Q27 | Return types declare outcomes; `Reject` replaces error patches (P3)? | Yes, refined by Q33: the outcomes are read from the handler's body, not its annotation. §6.3. |
| Q28 | The graph lays out the world; the composer gains stage and shot (P5)? | Yes. Decision N; §7.1, §8; measured in E8. |
| Q29 | Response tables and atmosphere binds (P6)? | Yes. Decision O; §9.1; a default table in L0. |
| Q30 | Stagings, baked look, and hand-built L0 worlds at release (P7)? | Yes. Decision P; §7.2; grade and panorama first, prop textures after E9. |

### 18.1 Questions from the Python SDK (2026-10-23)

The SDK skeleton (`sdk/python`, branch `claude/python-sdk-skeleton-9a995f`) built §6 as written and
raised these in three rounds. Its numbering is in brackets, the later rounds as 2.n and 3.n.

| # | Question | Decision |
|---|----------|----------|
| Q31 | Is the platform's back an edge? [1] | Yes, from every frame with history; roots have none; `back=False` opts out; `check` counts it as an exit (§6.3). |
| Q32 | Where is the hub? [2] | On frames whose history root is a hub destination; never on calls; `hub=False` hides it (§6.3). |
| Q33 | Edge annotations such as `vt.Jump["dashboard"]` upset linters and type checkers. [3] | Edges are read from the handler's body; `@vt.outcomes(...)` where it cannot be read; the annotation is dropped (§6.3). |
| Q34 | An outcome's arguments are invisible to `check`. [4] | Read from the body and matched against the target's loader and address. `sign_in=` takes the user's record, and `ctx.user` is that record (§6.2, §6.3). |
| Q35 | An edit form whose record has a required hidden field can never validate. [5] | `vt.Id` is the identity type, not required in edited documents; `check` flags any other required field an edit frame hides (§6.1). |
| Q36 | Frame ids derived from purposes change when a purpose is reworded. [6] | A place is its tape plus the frame's `id`; one-frame tapes need none; multi-frame tapes name every frame (§6.1). |
| Q37 | What receives a call's result? [7] | `call(tape, then=handler)`, as the parameter `result`; `vt.pick` fills its field with no handler (§6.3). |
| Q38 | Which document is meant when a record occurs twice on a frame? [8] | Reference the field that holds it (`Page.toc`); `check` reports ambiguity (§6.1). |
| Q39 | How do documents hold translated copy with parameters? [9] | They don't: copy lives in intent, with field references as parameters; runtime copy is an `Enum` (§6.1). |
| Q40 | Lists in edited records cannot be edited. [10] | `add` and `remove` join the affordances; lists of choices are `choose(many)` (§6.4). |
| Q41 | How does `vt.show` name a field of a record held twice? [2.1] | `vt.show(Entry.title, on=Page.toc)`; chained references only into single nested records (`Deal.company.name`), since type checkers reject them through lists (§6.1). |
| Q42 | Does `select=` on a list in an edited record navigate or edit? [2.2] | Data the user reads is shown, data the user writes is edited; `shows=` takes a list; shown records without an Id are the session's own, so search results get their own shown record; `select=` on an edited list is an error (§6.1, §6.2). |
| Q43 | How are references told from owned items in an edited list? [2.3] | By spelling: `vt.pick(...)`, `options=`, or an `Enum` make a choice; any other list of records is owned; Ids do not matter (§6.4). |
| Q44 | Is an explicit back on a history root a way out? [2.4] | No: an error where the frame is always a root, a warning where it sometimes is; the client shows back only where there is history (§6.3). |
| Q45 | Tape names held in constants need `@vt.outcomes`. [2.5] | Names are resolved against the handler's module at registration; a string constant or the tape itself works (§6.3). |
| Q46 | `goto` carries no arguments, so a later frame's loader cannot get any. [2.6] | Arguments belong to the tape: the jump that enters it passes them, and every frame's loader in it may take them and earlier frames' documents (§6.3). |
| Q47 | A shown record that nothing loads, with a required field, can never start. [3.1] | Every shown record needs a source: the loader, an earlier frame of the tape, or defaults; `check` reports one without (§6.2). |
| Q48 | What does a deep link into a later frame of a tape get? [3.2] | The frame must stand on its own; in a hub app the first destination that reaches it goes beneath it; otherwise it is a root (§6.3). |
| Q49 | Is back a way out where a frame is a root on some paths only? [3.3] | No: back counts only where the frame has history on every path, for dead ends and explicit backs alike (§6.3). |
| Q50 | Should `vt.destination`, `vt.pick`, and `vt.app(entry=)` take tapes? [3.4] | Yes: the tape or its id wherever a tape is named; ids inside records, which come before tapes (§6.3). |

The SDK's five deviations are settled too. A paging loader is registered after its record with
`@vt.pages(Record.field)`, and `pages=` in a field is gone. `vt.Text` is a type, with `lines=` on
`vt.Field`. `submit=` takes a labelled action. `vt.t` in a `str` field is replaced by Q39. `vt.docs`
needs the engine, so the guide shows it inside the functions that receive outside events.

Also folded from [08](08-leverage-review.md) without a question of their own: affordances (P4,
§6.4), the agent surface (§6.5), and its corrections to §8, §9, and §14. From
[07](07-review-from-apps.md): the findings P1–P4 absorb are in §6; F8 (addresses), F12 (insets),
F14 (text shaping), and F18 (selection, now local) are folded as written; F1, F2, F20, and F26 are
moot under Q24; Q16–Q23 are decided above. Nothing from 07, 08, or the SDK remains open.
