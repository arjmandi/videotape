# Review: where the leverage is in design v2

**Date:** 2026-10-23 · **Status:** Q24–Q30 decided (yes to all seven) and folded into
[05-design-v2.md](05-design-v2.md) the same day; kept for the argument · **Reviews:** [05-design-v2.md](05-design-v2.md),
[06-getting-started.md](06-getting-started.md), [07-review-from-apps.md](07-review-from-apps.md), and
the `prototype-0` code the intent model comes from

The brief for this review: find the places in the design where a small change buys a large gain,
on two axes. Writing an app must be easy, concise, and complete. What comes out must be powerful
enough to astonish. Each proposal below (P1–P8) says what it changes, what it buys on each axis,
what it costs, and which findings of 07 it absorbs. §7 lists the decisions (Q24–Q30).

---

## 0. The short version

1. **The spine is right and should not move.** The journey is the program; the engine owns state,
   geometry, text, and input; generation owns the look in layers; a release is a generation; text
   input and accessibility are the platform's own; everything runs with generation off. Nothing
   below trades against these, except P8, which is flagged.

2. **The authoring side is about to grow one parameter per finding.** 07 is right that the intent
   model is a form model, and each of its proposals is right on its own. Adopted one by one they
   produce components with fifteen keyword arguments and a stringly-typed state language
   (`bind="item.author.name"`, `vt.item("id")`, `vt.append(...)`, `optimistic={...}`,
   `live=[...]`). The leverage is to stand intent on three things a developer already has:
   **types** (P1), **documents** (P2), and **decisions** (P3), with **affordances** as the open end
   of the vocabulary (P4). Fifteen of 07's findings then fall out of one mechanism each instead of
   needing a parameter each. The demo's sign-in becomes four lines of intent and a five-line
   handler.

3. **The output side describes a themed widget set in a generated room.** A button is a console
   key, a list is a shelf of reels. That is a skin, which is what v1 was rejected for. The game in
   "UI as a Game" is not the props. It is space, camera, light, motion, and a world that answers.
   **The tape graph is already a level map** (P5): frames are places, edges are camera moves, and
   every transition, resize, rotation, breakdown, and merge becomes a camera decision instead of a
   layout. **The world reacts to the journey** (P6) through a response table the embodier writes
   once per release.

4. **Release time is where the intelligence goes; runtime is where the math goes.** The design
   decided this (decision I, Q12). Pull it further (P7): reference stagings per screen class, the
   premium look baked from L2 into L1 assets so every client has it, including iOS, and two or
   three hand-built L0 worlds beautiful enough that the first `videotape dev` is the pitch.

5. **One trade to decide, flagged as such.** The design already renders scene state on the device
   on iOS (K) and in development (F26), and plans it for Android and desktop in M4. Make scene
   state the product on every client and keep the stream as a bootstrap and as the premium path
   for L2 and L3 (P8). It trades against decision A's "streams cloud-gaming style". It removes F1,
   F2, F18, and F20 and most of the GPU-cost and latency risk. §4 argues it; Q24 is yours.

## 1. What is strong and must not move

| Strength | Where | Why it matters |
|----------|-------|----------------|
| Journey first: the graph is the program | §1, §6 | Static checks, exhaustive tests, prefetch, store manifests, and now the level map (P5) all read from it |
| Facts from code, interactivity from geometry | Decisions E, F; §10, §12 | The two rules that make a generated interface trustworthy |
| Platform text and accessibility | Decision C; §11 | The differentiator from game engines; nothing here touches it |
| A release is a generation; no model in the click path | Decision I; Q12 | Cost per release, not per user; determinism at runtime |
| Everything works with generation off | S6; L0 | How it is tested and how it fails |
| Two SDKs over one protocol; handlers in the app's process | Decision H | The app keeps its language and its data |
| The grounding harness | §13 | Measures the thing everyone will doubt |

## 2. Authoring: three things a developer already has

The sign-in example in 05 §6 is thirteen lines of components plus a handler that declares its
outcomes twice, once in the body and once in `outcomes=`. The CRM form in 06 §8.5 is eight
component calls with thirty-one keyword arguments, most of which restate what a `Deal` class would
say. The code tells the engine what it could have read.

### 2.1 P1. Types are the vocabulary

A record type already says what the engine needs. Field names give labels, and message keys for
F13. Kinds give affordances: `str` writes, `Money` writes with a currency, an `Enum` chooses,
`date` picks a day, `bool` toggles, `list[X]` is a collection, `Image` and `Video` are facts,
`RichText` is formatted text, `Series` is a chart. Constraints give validation: required unless
`| None`; `ge`, `le`, `pattern`, `max_length`. Structure gives grouping: a nested record is a
group, and a reference to another record is a pick that returns one (F5).

**Proposal.** In both SDKs, components are projections of typed fields. Python uses Pydantic
models and TypeScript uses Zod schemas; both already emit JSON Schema, and the intent JSON carries
it. A frame names the record it shows (`shows=`) or edits (`edit=`), and the engine derives the
components. Explicit components stay for what differs: `components=[vt.show(Deal.amount,
role="heading")]` overrides the derived one for that field; a label slug or an explicit id names
the rest. References are references and strings are text, which settles F27.

Before (06 §8.5):

```python
new_deal = vt.tape("new_deal", frames=[
    vt.frame("form", purpose="Create a deal", components=[
        vt.input("name", label="Deal name", required=True, group="basics"),
        vt.button("company", bind="deal.company.name", label="Company", group="basics",
                  on_press=vt.call("pick_company", then=company_picked)),
        vt.input("amount", label="Amount", type="money", currency="deal.currency", min=0, group="basics"),
        vt.select("stage", label="Stage", options="stages", group="basics"),
        vt.date("close", label="Expected close", group="dates"),
        vt.select("owner", label="Owner", options="team", group="people"),
        vt.input("notes", label="Notes", lines=(3, 12), importance="optional"),
        vt.button("save", "Create deal", role="primary", on_press=create_deal),
    ]),
])
```

After:

```python
class Deal(vt.Record):
    name: str
    company: Company = vt.pick("pick_company")           # a call that returns a Company (F5)
    amount: vt.Money = vt.Field(ge=0)
    stage: Stage                                          # an Enum: a choice
    close: date | None = vt.Field(group="dates")
    owner: User = vt.Field(group="people", options=team)
    notes: vt.Text(lines=(3, 12)) | None = vt.Field(importance="optional")

new_deal = vt.tape("new_deal", [vt.frame("Create a deal", edit=Deal, submit=create_deal)])
```

The frame's purpose is one sentence that does three jobs: it is the frame's accessible title, the
label of its primary action unless another is given, and (P5) the brief for its place in the
world.

Collections (F4) follow. `shows=list[Deal]` is a collection whose item template, comparable
fields, shape (table, cards, column, one at a time), empty state, and accessible table all come
from `Deal`; `group_by=Deal.stage` makes a board. Validation (F11) runs in the engine from the
constraints, without a handler. Labels are message keys named after the fields (F13). `Image`,
`Video`, `RichText`, and `Series` make F15, F17, and F19 types rather than kinds.

**Buys.** Writing: a form is a class; the demo's five frames come to roughly forty lines.
Completeness: every field is declared once, with its constraints, and nothing about it is
restated in a frame. Output: the composer knows types, not just kinds, so it can choose shapes (a
table of comparable fields, a card of mixed ones), and the embodier can embody a `Money`
differently from a `str`.
**Costs.** SDK work only. The intent JSON gains a schema per record; the composer and the embodier
read types. No protocol change.
**Absorbs.** F4, F5 (picks), F9 (`| None`; `visible=` bound to a `bool` field), F11, F13, F15,
F17, F19, F27.

### 2.2 P2. Documents are the state

The reel store is a JSON object addressed by dotted paths and changed by patches. 07 adds to it a
patch algebra (`append`, `prepend`, `replace`, `remove`, `increment`), placeholders (`vt.item`,
`vt.data`, `vt.value`, `vt.key`), optimistic patches declared on handlers, topics with `publish`,
and `live=[...]` on frames. Five mechanisms for one thing: state changed and the screen must
follow.

**Proposal.** A frame shows typed documents. The engine holds each document once, keyed by its type
and id; every session showing it is subscribed; a change made anywhere (a handler in any session,
the app process, a timer) reaches every screen that shows it. A handler receives the documents its
frame shows as typed objects, resolved by annotation the way FastAPI resolves parameters. It
mutates them with ordinary code, and the SDK sends the changes as they happen. Every change is
shown as it is made and marked tentative until the handler returns; if the handler raises, the
engine rolls them back. That is F11's optimistic patch without a declaration. `shows=` documents
are shared by identity; `edit=` documents belong to the session (a draft, a form). The `enter`
loader returns the document, and the engine dedupes it by id.

Before (06 §8.4, abridged):

```python
@vt.handler(outcomes=[vt.stay()],
            optimistic={"messages": vt.append({"key": vt.key(), "text": vt.value("draft"),
                                               "mine": True, "pending": True}),
                        "draft": ""})
async def send(ctx):
    msg = await db.send(ctx.data["conversation"]["id"], ctx.user.id, ctx.values["draft"], key=ctx.key)
    await app.publish(f"conversation:{msg.conversation_id}", {"messages": vt.append(msg.public())})
    return vt.stay()

vt.frame("messages", purpose="Read and reply", enter=load_thread,
         live=["conversation:{conversation.id}"], components=[
    vt.collection("messages", source=vt.pages(older_messages), order="oldest-first", anchor="end",
                  item=message, item_states=["mine", "pending", "unread"], actions=[...]),
    vt.input("draft", label="Message", lines=(1, 6), group="reply"),
    vt.button("send", "Send", role="primary", on_press=send, group="reply"),
])
```

After:

```python
class Message(vt.Record):
    author: User
    text: vt.RichText
    sent_at: datetime = vt.Field(format="time", importance="optional")
    pending: bool = vt.State(False)                       # a state props may show; never drawn as text

class Conversation(vt.Record):
    title: str = vt.Field(role="heading")
    messages: list[Message] = vt.Field(anchor="end", pages=older_messages)
    typing: str | None = vt.Field(role="status", importance="optional")

class Draft(vt.Record):
    text: vt.Text(lines=(1, 6)) = ""

async def send(ctx, conv: Conversation, draft: Draft) -> vt.Stay:
    msg = conv.messages.append(Message(author=ctx.user, text=draft.text, pending=True))
    draft.text = ""                                       # both on screen now, in every session showing conv
    msg.update(await db.send(conv.id, ctx.user.id, msg.text), pending=False)
    return vt.stay()

thread = vt.tape("thread", [
    vt.frame("Read and reply", shows=Conversation, edit=Draft, submit=send,
             address="/c/{id}", enter=load_thread, actions=[
                 vt.action("Reply", start_reply, on=Message, gesture="swipe-trailing"),
                 vt.action("Copy", vt.copy(Message.text), on=Message),
             ]),
])

# anywhere in the app process, when another user's message arrives
vt.docs[Conversation, cid].messages.append(incoming)
```

**Buys.** Writing: no paths, no patch algebra, no placeholders, no optimistic declarations, no
topics. Interaction without the app: sorting, filtering, selecting, local search, and validation
act on the document in the engine; only decisions and writes call Python, which answers the
latency behind F11 in general. Output: the world can react to the document (P6), because the
engine knows what changed, not only that a patch arrived. Testing: a journey test mutates a
document and asserts on it.
**Costs.** The engine gains a document store with subscriptions, tentative writes, confirmation,
and rollback. This is the shape of Replicache, Convex, and Liveblocks; it is known work, and it is
smaller than the five mechanisms it replaces. The app protocol gains `sync` (deltas both ways) and
loses handler-returned patches and `publish`.
**Absorbs.** F6, F7 (`ctx.user`; documents keyed by user), F11, F24 (a document carries the tape
version it was loaded under), F27 (placeholders).

### 2.3 P3. Decisions are the handlers

A handler returns where the journey goes. The design declares the edges twice: in the body and in
`outcomes=[...]`. And every handler that can fail declares `stay()` and patches an error path.

**Proposal.** The return type is the declaration. Python reads it from the annotation at
registration (`-> vt.Jump["dashboard"]`). The TypeScript SDK reads it from the compiler at build,
since `vt.jump("dashboard")` already has the type `Jump<"dashboard">`. Any handler may
`raise vt.Reject("...")`: the journey stays, the frame shows the message as its error status, and
secrets are cleared. A `Stay` edge is therefore implied for every handler, and most signatures
name only where they go.

```python
class Credentials(vt.Record):
    username: str
    password: vt.Secret

async def sign_in(ctx, c: Credentials) -> vt.Jump["dashboard"]:
    user = await auth.login(c.username, c.password)
    if user is None:
        raise vt.Reject("Wrong credentials")
    return vt.jump("dashboard", user=user, sign_in=user.id)

login = vt.tape("login", [vt.frame("Sign in", title="Welcome back", edit=Credentials, submit=sign_in)])
```

Four lines of intent, a five-line handler, and `videotape check` still knows every edge.

The TypeScript side reads the same way:

```ts
const Credentials = vt.record({ username: z.string(), password: vt.secret() });
const signIn = vt.handler(async (ctx, c: z.infer<typeof Credentials>) => {
  const user = await auth.login(c.username, c.password);
  if (!user) throw vt.reject("Wrong credentials");
  return vt.jump("dashboard", { user, signIn: user.id });   // Jump<"dashboard">, read at build
});
export const login = vt.tape("login", [vt.frame("Sign in", { title: "Welcome back", edit: Credentials, submit: signIn })]);
```

**Buys.** Writing: no duplicated outcomes; errors are exceptions. Completeness: the graph is still
static and complete.
**Costs.** A build step for the TypeScript SDK, which the exporter needs anyway.

### 2.4 P4. Affordances keep the vocabulary open

07's F25 asks for custom components as TypeScript plugins. Most "custom components" are not new
interaction; they are a new prop, or a new arrangement, for known interaction. The harness (§13)
already judges props by affordance. Make authoring use the same words.

**Proposal.** A component is a type, a role, and a set of affordances. The closed set of
affordances is the engine's contract: `read`, `write`, `press`, `choose` (one or many), `adjust`
(a range), `move` (an item to a target), `scroll`, `play`, and later `pick` (from the OS). Kinds
are names for common combinations. A slider is a number with `adjust`. A board is `list[Deal]`
grouped by `Deal.stage` with `move(Deal → Stage)`. A seat picker is `list[Seat]` with
`choose(many)` on a spatial prop. A story is an `Image` with `press` on its leading and trailing
thirds. Actions declare the affordance they need (`to=Stage` makes a `move`). A custom component
is then one of two things: a new prop with known affordances, which is a world-pack entry and
needs no code; or a new affordance, which is rare and is an engine plugin (F25 as proposed, for
that case only).

**Buys.** Completeness without growth: the vocabulary is a product of three small sets, not a
list. Output: the embodier can embody any combination, and the harness checks what it embodied
against the same words.
**Costs.** The embodiment interface in §9 already has `affordance`; it gains `adjust`, `move`,
`scroll`, `play`.
**Absorbs.** F10 (actions declare an affordance and a gesture hint), F16 (`play` is the native
media surface), F25 (mostly).

### 2.5 The mental model, in three words

> **Types, places, decisions.** Types say what exists; the engine derives inputs, lists,
> validation, labels, and the accessibility tree from them. Places (frames) say what is on stage
> and what can be done there. Decisions (handlers) say where the journey goes. The engine stages
> it in a world: the graph is the level, the camera travels the journey, and the world reacts.

That paragraph is the whole SDK. Recounted with P1–P4, the five apps of 06 §8 lose roughly two
thirds of their lines, and every line that remains is intent.

## 3. Output: the game in "UI as a Game"

The thesis says a game engine holds state, geometry, camera, text, and input. The design delivers
state, geometry, text, and input. The camera gets one line in §5 ("reframe the camera"). Yet the
camera is what makes a game feel like a place rather than a set of screens, and it is also the
cheapest thing in the engine.

### 3.1 P5. The graph is the level

**Proposal.** Frames are places in the world; edges are camera paths between them.
`videotape release` adds a level-layout step: it reads the tape graph and the frames' purposes,
drafts the world's brief from them, lays the places out in the generated world's free space
(against the collider mesh), and computes a camera path per edge. Designers then direct a world
the app already implies, rather than declaring one from nothing. The composer works at two scales.
The **stage** is fixed per release: which place a frame lives in and which props stand there. The
**shot** is continuous per context: the camera position, direction, and focal length that fill
this screen with the required props, keep text legible at that distance for this density and text
scale, and keep the primary action within reach. The arrangement within the stage changes only
when no camera satisfies the constraints, with hysteresis.

What the journey's actions become:

| Journey | Camera |
|---------|--------|
| `goto`, `jump` | A dolly along the edge's path; a cut through a doorway when the target tape has its own world (Q10) |
| `back` | The same path, reversed |
| `hub` | A hall whose doors are the destinations; switching destination is a turn |
| `call` and `done` | A lean toward a side table and back; the sheet is a prop on it |
| Rotate the phone | The camera turns (already in §8) |
| Resize the window | The camera pulls back or pushes in; the stage does not move |
| Breakdown (M3) | Close-ups along the stage in order, title pinned |
| Merge (M3) | A wider shot that holds two neighbouring places |

A sketch of what the release step would print for the demo:

```
$ videotape release --dry-run
world      dusk-studio (3d): 7 places from 7 frames in 7 tapes
  landing/intro        "Say what Hello is and lead to sign-in"   the lobby, console in view
  login/form           "Sign in"                                 the mixing console
  workspace/overview   "See your projects"                       the control room, screens on the wall
  report/view          "Read one report"                         a desk with one lamp
  ...
paths      landing→login: walk to the console (2.1 s) · login→workspace: through the glass (1.6 s) · ...
```

**Buys.** Output: every transition is a move through one continuous space; the user builds a map
of the app the way a player learns a level; resize, rotation, breakdown, and merge are camera
decisions and look like one thing. Writing: nothing, it is derived; the developer's purposes
become the brief. Engine: object identity across compositions is trivial, because props stay and
the camera moves, so the §8 "stability" problem mostly disappears. It also closes a gap in §9:
`minSize` is in CSS pixels and worlds are metric; the camera solver is where the two meet.
**Costs.** A level-layout step at release (a 3D graph layout in free space, with the embodier
proposing which station suits which purpose); camera paths (splines against the collider mesh); a
camera solver in the composer. Large apps need districts: a tape is a room, its frames are
stations, a hub is a hall. One world per app with worlds per tape (Q10) already allows it.
**Risk.** The world generator must produce enough distinct stations. Marble takes multi-image and
panorama inputs and `marble-1.1-plus` sizes the world dynamically, so the brief can ask for the
stations by name. Measured in E8.

### 3.2 P6. The world reacts

Props have widget states (`hover`, `pressed`, `focused`, `disabled`, `error`). A game answers more
than that. A key lights. Reels turn while the server thinks. The room comes up when you sign in. A
meter flickers when you are refused. Something on the shelf moves when a message lands.

**Proposal.** The embodier writes a **response table** per release: journey event → world
response. The events are the same for every app and are all enumerable from the graph and the
documents: frame entered and left; press; handler pending; outcome taken; rejected; validation
failed; document changed, item added or removed; selection; idle. The responses are animations of
existing props, lights, and the world itself, with optional sound. L0 ships a default table, so
generation-off still answers. Nothing is per user, and it runs on iOS.

Add **atmosphere binds**: numbers and enums from documents and context may drive the world's
parameters (light, time of day, weather, camera energy, ambient motion), never strings, and never
as the only carrier of a fact. `prefers.colorScheme` is the time of day; `reducedMotion` holds the
world still; `textScale` brings the camera closer. This is v1's `flavour` generalised, with its
lint kept: no path an input writes reaches the world.

**Buys.** Output: the part of a game that people remember, for the price of animation clips on
assets that already exist. Writing: one optional line per frame, if any.
**Costs.** A response-table step in the embodier; animation and parameter support in the scene
runtime, which Babylon has.

### 3.3 P7. Release time is where the intelligence goes

Decision I and Q12 put generation and the embodier at release and keep models out of the click
path. Three more things belong there.

**Reference stagings.** For each (frame, reference screen class), the embodier proposes a staging
at release: an arrangement and a camera. The runtime composer interpolates between the two nearest
stagings by aspect ratio and enforces the constraints. Creativity offline, guarantees online.
`videotape check` gains a picture per reference screen.

**Bake the premium look.** L2 costs $36–144 per stream-hour, and iOS never sees it (K). Run L2, or
a strong image model, over the reference renders at release, and bake what it did into the world
pack: a colour grade (a 3D LUT) per place; a relit panorama; re-coloured splats; props re-textured
by back-projecting the restyled views with the engine's depth and object-id passes (the multi-view
texture-synthesis family: TEXTure and Text2Tex, 2023). L1 then carries most of L2's look at no
per-session cost, on every client. Live L2 remains for effects that depend on motion. E9 measures
how close the baked look gets to the live one.

**A beautiful L0.** L0 is what every developer sees first and what plain mode shows every user. If
it is grey boxes, the astonishing part is behind a release and a bill. Hand-build two or three
procedural worlds (the plain one; a studio; a desk) with real materials, lighting, and response
tables, so that `videotape dev` with generation off already looks like a game. The first run is
the pitch.

**Buys.** Output: the premium look for everyone, including iOS; composition that looks designed on
every screen; a first impression that sells. Cost per session: unchanged.
**Costs.** Offline pipelines. The LUT and panorama bakes are a day's work; per-prop texture baking
is a research-adjacent pipeline and goes second. The L0 worlds are design work before M1.

## 4. The system: scene state is the product

Flagged as a trade against decision A ("the engine runs on servers, cloud-gaming style, and
streams"), as the vision rule requires.

Today the design has two renderers. Streamed clients (web, Android, desktop) receive video; iOS
receives scene state and renders it with Babylon Native (K); `videotape dev` is to render scene
state in the browser with Babylon.js (F26); M4 plans an on-device engine for Android and desktop.
Four of 07's findings are consequences of the stream alone: text through a lossy encoder (F1),
scrolling a round trip late (F2), nothing selectable (F18), a GPU held by an idle session (F20).
So are the first three risks in §17 and the mobile-data figure in 06 §8.3.

**P8. Proposal.** Scene state is what the engine produces for every client. Clients render it:
Babylon.js on the web, which is its home; Babylon Native on Android and desktop, the same build as
iOS. The engine keeps everything else: journey, documents, composition, embodiment, the app
protocol, the accessibility tree. The stream remains for three cases. **Bootstrap:** stream the
first seconds while the world pack downloads, then hand off to the local renderer; same runtime,
same scene state, parity by construction. **Premium:** sessions with L2 or L3, which must render
on the server. **Weak devices.** Sessions per GPU then count L2 and L3 sessions only.

| | Decision A as written | P8 |
|-|-----------------------|----|
| Text | Through a 4:2:0 encoder; E2 must prove it legible | Drawn on the device, exact |
| Scroll and drag | A round trip late; needs local frame shifting | Local |
| Selection, copy, find | From glyph positions sent per frame | Native, local |
| Idle session | Holds a GPU | Costs nothing; render on demand |
| Latency | ≤ 100 ms target on a good network | Local for interaction; one round trip for decisions, as on iOS |
| Mobile data | About 2.25 GB per hour of scrolling at 5 Mbps | The pack once per release, then deltas |
| Cost per session | A share of a GPU | None; L2 and L3 sessions as today |
| Client | Thin and identical | A renderer, as iOS already is; one codebase for all four |
| First seconds | Immediate | Immediate, via the bootstrap stream |
| Offline | None | Reconnect screens and the last scene are real; journeys still need the engine |

**What it costs.** Finishing M4's on-device engine for Android and desktop in M1, which is the iOS
build on other targets; a bootstrap handoff in the client; the pack download budget E7 already
sets. **What it keeps.** The engine on the server as the source of truth; L2 and L3 exactly as
designed; the store rules unchanged (scene state and packs are data, and iOS already passes this
way). **What it loses.** The sentence "streams cloud-gaming style" in the thesis; the
pixel-identical client across platforms. **Why now.** M1 builds Babylon Native shells for iOS
regardless. Making the stream good enough for text and scrolling (F1, F2) is harder than finishing
the renderer for the other three platforms, and the web needs no shell at all.

## 5. Intent is an agent surface

The same derivation that gives the accessibility tree (§11) and crawler HTML (F21) gives a tool
surface: every frame is a tool with typed inputs (P1) and declared outcomes (P3), and every action
has a name and a label (F10). An assistant, a voice input (`voice` is already in `Context`), or a
test agent can drive any Videotape app with no extra authoring. "Built for next year's models"
(§1) then covers how apps are driven, not only how they are drawn. One paragraph in §6, no new
mechanism.

## 6. Small corrections to 05

- §8 calls the composer a pure function and then gives it hysteresis. It is a function of the
  previous composition too; say so. Under P5 the previous composition is mostly a camera.
- §9 `minSize` is in CSS pixels at the reference screen; worlds are metric (Marble exports
  `metric_scale_factor`). The bridge is the camera solver (P5); write it down.
- §9 "within a tape, the same kind and role keep the same prop." Make it per world, with per-place
  variants, or the map (P5) cannot be learned.
- §9 `states` lists widget states only; journey events (P6) belong beside them.
- Decision K says iOS gets L0 and L1 only. After P7's baking, L1 carries most of L2's look, so the
  limitation is narrower than it reads.
- §6's Python sample imports `input`, which shadows the built-in; 06 already uses
  `import videotape as vt`.
- §14 app protocol: `register`, `handler`, `enter`, `log` become `register`, `decide` (handler
  calls), `load`, `sync`, `log` under P2.

## 7. Questions to decide

Numbered after 07's Q16–Q23. The recommendation comes first.

| # | Question | Recommendation | Alternatives |
|---|----------|----------------|--------------|
| Q24 | Scene state on every client, with the stream as bootstrap and premium path (P8)? Trades against decision A | Yes | Keep A; treat F1, F2, F18, F20 as engineering; measure in E2; revisit at M4 |
| Q25 | Typed records as the component vocabulary in both SDKs (P1)? | Yes | Keep explicit components and add 07's parameters one by one |
| Q26 | Documents replace the store, patches, placeholders, topics, and optimistic declarations (P2)? | Yes; redesign the app protocol around `sync` | Keep the store; add 07's five mechanisms |
| Q27 | Return types declare outcomes; `Reject` replaces error patches (P3)? | Yes | Keep `outcomes=` |
| Q28 | The graph lays out the world; the composer gains stage and shot (P5)? | Yes; a level-layout step in `release`, a camera solver in the composer, measured in E8 | Place props per shot as designed; transitions stay cuts |
| Q29 | Response tables and atmosphere binds (P6)? | Yes; a default table in L0 | Widget states only |
| Q30 | Stagings, baked look, and hand-built L0 worlds at release (P7)? | Yes; LUT and panorama bakes first, textures after E9 | Live L2 only; L0 as boxes |

P4 (affordances), §5 (the agent surface), and the corrections in §6 have no real alternative and
can go in as they are.

## 8. What would change in the design

If the recommendations are adopted:

- **§1 Thesis.** "Streams cloud-gaming style" becomes "delivers scene state to a native client on
  any platform, streamed where a session needs the server's render". "Built for next year's
  models" includes being driven by them (§5 here).
- **§2 Decisions.** A becomes P8. New decisions: L (types are the vocabulary), M (documents are
  the state), N (the graph is the level), O (the world reacts; the release writes the response
  table).
- **§5 Architecture.** The engine's output is scene state; the GPU encoder and WebRTC move into a
  "stream" box used for bootstrap, L2, L3, and weak devices. Loops: interaction is local;
  decisions are one round trip.
- **§6 Intent and SDKs.** Records, `shows` and `edit`, documents, return-type outcomes, `Reject`,
  affordances; the three-word model as the opening paragraph.
- **§7.1 Releases.** Level layout, stagings, the response table, and baking join the steps; the
  world pack carries places, camera paths, stagings, the response table, and baked looks.
- **§8 Composition.** Stage and shot; the camera solver; stagings interpolated.
- **§9 Embodiment.** Affordances extended; journey events; the metric bridge.
- **§10 Scene runtime.** Runs on every client; the server runs it for streamed sessions.
- **§11 Streaming and the client.** The bootstrap handoff; the stream as a path, not the platform.
- **§14 Protocols.** App protocol: `sync`, `decide`, `load`. Client protocol: `scene` on every
  client; `objects` only for streamed sessions.
- **§15 Experiments and milestones.** E8: level layout and camera paths in a Marble world. E9:
  baking a restyle into a LUT, a panorama, and textures. E10: the document loop (fan-out,
  tentative writes, rollback). M1 delivers the on-device renderer on four platforms; M4 keeps
  capabilities and loses the renderer.
- **§17 Risks.** F1, F2, F18, F20 leave. "The pack download before the first local render" and
  "the world generator yields too few stations" arrive.

## 9. Not covered

Pricing and hosting of the engine (Q4); sound design beyond a mention; how designers edit a world
pack (Marble's editor and SuperSplat exist; the loop is "edit the pack, not the CSS"); games built
on Videotape; permissions for the agent surface (§5).
