# Videotape engine core (headless)

The first piece of the v2 engine ([05-design-v2.md](../../docs/05-design-v2.md) §5): it plays a
Python app's journeys and documents through the app protocol, with no composer, no rendering, no
scene state, and no clients. It covers experiments E5 and E10 (05 §15).

```bash
npx -y pnpm@9.15.0 install
npx -y pnpm@9.15.0 --filter @videotape/engine test
```

## Intent

`loadIntent(json)` reads the intent document the SDK produces (`videotape intent module:app`),
validates it against the schema the Python SDK publishes
([`intent.schema.json`](../../sdk/python/src/videotape/intent.schema.json), read from the SDK's
tree so the two cannot drift), and resolves every name the runtime looks up: tapes, frames,
handlers, loaders, records, hub destinations, and `under`. The engine never trusts its input to
have passed `videotape check`. `Records` validates documents, fields, and list items against the
records' JSON Schemas (Ajv, draft 2020-12) and keys the record items of lists.

The tests read intents generated from the SDK's sample apps (`test/fixtures/*.intent.json`);
`npx -y pnpm@9.15.0 --filter @videotape/engine intents` regenerates them, and a test fails when
they are out of date.

## The app protocol

JSON text frames over a WebSocket; the app process connects out to the engine's `/app` endpoint
(`videotape serve module:app --engine ws://host:port/app`). Every message has a type `t`. Every
message from the app is validated (zod) before the engine reads it; a malformed one is answered
with `error` and dropped, and its content is never echoed or logged.

| Direction | Message | Carries |
|-----------|---------|---------|
| app → engine | `register` | `v` (1), `intent` (the intent JSON), `sdk` (`language`, `version`) |
| engine → app | `registered` / `error` | the app's name / a `code` (`bad_intent`, `refused`, `bad_message`, `not_registered`) and a message; a refused app is disconnected |
| engine → app | `load` | `id`, `loader`, `session`, `user`, `args` (the tape's arguments), `documents` (earlier frames' documents the loader takes, by parameter) |
| engine → app | `page` | `id`, `loader`, `session`, `user`, `cursor`, `documents` |
| engine → app | `decide` | `id`, `handler`, `session`, `user`, `documents` (by parameter), `values` (a call's `result`) |
| app → engine | `result` | `id`, and one of `outcome`, `reject: {message}`, `documents: [{record, value}]`, `page: {items, next}`, `error: {type, message}`, `stale: [{doc, have}]` |
| app → engine | `sync` | `changes: [{doc, ops}]`, and `decision` when they are tentative under a decision |
| engine → app | `sync` | `changes: [{doc, version, from, ops}` or `{doc, version, value}` or `{doc, version, from, origin: "app"}]`, `drop: [doc]`: keeps the app's mirror current |
| app → engine | `forget` | `docs`: the app dropped its copies of these |
| app → engine | `fetch` / engine → app `fetched` | `id`, `docs` / `id`, `documents: [{doc, version, value}]`: a copy the app asks for (`await vt.docs.fetch(...)`) |
| app → engine | `log` | `level`, `message`, `logger`: the app's log lines, scrubbed of secrets by the SDK and again by the engine |
| app → engine | `ping` / engine → app `pong` | keepalive |

**Documents on the wire.** A shared document is addressed as `{record, id}` (its `vt.Id`), a
session's own as `{record, local}` with a key the engine chose. A document's value is its record's
JSON, and each record item of a list carries its key as `"@key"`: its `vt.Id` when it has one, or a
key the engine (`~e…`) or the SDK (`~<process>.<n>`) minted. An item keeps its first key after it is
saved with an Id (Q55). A `documents` entry is `{ref, version}`, plus `value` (the whole document)
only when the app does not hold that version (below); one that is an item of a list also has `path`
and `record`. `user` is `{record, id, value}`, the record `sign_in=` passed, and an outcome that
signs in carries `sign_in` in that shape.

**The app's mirror (Q53, Q57, Q68).** The app keeps a copy of the confirmed value of every document
a request has sent it, and the engine records which confirmed version it holds (`src/mirror.ts`;
`videotape/mirror.py` on the app's side). A request names a document by reference and confirmed
version, and sends it whole only when the app does not hold that version; the app answers with
changes only, so the cost of a decision does not grow with the document. Every confirmed change
reaches the app's copy as `sync`: ops from the version it holds (a user's edit, a decision once it
is confirmed), or the whole value when no ops describe it (a reload). Tentative changes never reach
it, so a rollback needs nothing. When a copy does not line up (a version gap, a change from
elsewhere while the app's own are in flight, an op that does not fit), the app drops it and says
`forget`; when a request names a version the app does not hold, it answers `stale` without running
anything, and the engine asks once more with those documents whole. A document the engine drops is
dropped from the mirror (`drop`). Records with secret fields are never mirrored: a decision gets
them whole, with its secrets. `vt.docs[Record, id]` is the app's copy when it holds one, so it
reads as well as writes.

**Each decision on its own copy (Q68).** A handler never receives the mirror's record: each
decision gets its own copy of the confirmed value, tracked under it, so it sees the confirmed values
and its own changes, never another decision's pending ones (the screen still shows every pending
change, and the engine applies each decision's changes on top of what was confirmed meanwhile).
The copy has its own records and lists, and a list's items are copied in only when the handler
reaches one, so a decision that only appends copies nothing. Plain values (`vt.RichText`,
`vt.Money`, `vt.Series`) are shared with the mirror, which is safe because they are immutable
(Q71): a handler assigns a new one, and every change is an op.
Changes made outside any decision go through the mirror's own records, are confirmed at once, and
come back as an echo with the version they reached (`origin: "app"`), or the whole value if the
engine refused any of them.

**Ops.** A path is a list of field names and `{"key": ...}` segments for items of lists of records.

| Op | Meaning |
|----|---------|
| `{op: "set", path, value}` | assignment; a list of plain values, or a reordered list, is set whole |
| `{op: "insert", path, key, value, at}` | `append` (`at: "end"`), `prepend` (`"start"`), or `insert` (`{before: key}`); the key is the item's from now on |
| `{op: "remove", path, key \| id}` | remove the item with this key, or with this `vt.Id` (from `vt.docs`) |
| `{op: "replace", path, key \| id, value}` | replace an item; the new item keeps the old one's key |

**Tentative and confirmed (Q54).** While a handler runs, the SDK sends each change as it is made:
the changes of one event-loop turn travel as one `sync` with the decision's id. The decision's
`result` confirms them; an `error` or a `reject` rolls them back. A change made outside a running
decision (`vt.docs` from a service, or work a handler started in the background and left running)
is the app's own change: sent without `decision`, applied at once, never tentative. The SDK sends
all of a decision's changes before its result, and the WebSocket keeps that order.

**Secrets.** A secret travels from the client to the engine only with the press that submits it,
is merged into the edited document of that one `decide`, and is dropped when the decision ends.
The SDK never sends a secret field back (ops and dumps skip them), and both ends scrub the secret
values in play from errors and log lines.

## The journey runtime

`Engine` plays one app: it listens for the app process (`engine.listen()`), and `engine.open()`
starts a session at the entry, at a tape (tests), or at the frame an address opens. A session
walks a **reel** (`src/journey.ts`): the step it is on (a frame of a *tape visit*, which carries the
tape's arguments and the documents its frames share), the history back to its root, the calls it
is inside, and each hub destination's saved history.

| Outcome | What the reel does |
|---------|--------------------|
| `jump(tape, **args)` | pushes the step on the history and starts a new visit of `tape` with `args` |
| `goto(frame)` | pushes the step and moves to `frame` in the same visit: same arguments, same documents |
| `back()` | pops the history; from a call's first frame it leaves the call without a result |
| `stay()` | nothing moves; the documents already carry the change |
| `call(tape, then=)` | keeps the caller, its history, and its root aside, and starts `tape` with an empty history and no hub |
| `done(result)` | returns to the caller, then calls `then=` with `result` at the caller's frame |
| `sign_in=` / `sign_out=` | sets or clears the session's user (`ctx.user`) and starts a fresh history at the target |
| `open`, `download`, `copy` | hands the client an effect; nothing moves |

**History roots.** The entry, a sign-in or sign-out target, a hub destination's first frame (by
its door), and a frame opened by its address, which gets the destination its intent names
(`under`) beneath it, entered when the user goes back to it. Back is offered only where there is
history (or a call to leave) and the frame does not say `back=False`. The hub shows where the
history began at a destination, outside calls, unless the frame says `hub=False`. Each
destination keeps its own history; the current destination's door starts it over.

**Across devices (Q62, Q69, Q70).** A session runs on a device (`open({device})`, a fresh one by
default). A signed-in session's journey is kept (`src/journeys.ts`) by user and device every time
it moves, for the app's `keep_journeys` (`vt.app(keep_journeys=timedelta(days=30))`, carried in the
intent as seconds; 30 days by default), and it outlives the session. Only the position and history
are kept: which tape visits, at which frames, with which tape arguments, the root, open calls, and
each hub destination's saved history; never a document. A sign-in on any device resumes the user's
most recent kept journey, whichever device made it: the same places in new tape visits, none of
them entered, so each frame's loader runs again when the user gets there and documents come fresh
from the app; the devices then go their own ways. After a release, a kept journey resumes at the
deepest place in its history that the intent still has, with the history beneath it: places that
are gone are dropped, a call none of whose places survive is left, and a saved hub history keeps
what survives of it; only when nothing survives does the sign-in land where it points (Q73). A sign-in whose outcome says `resume=False`
(`vt.jump("home", sign_in=user, resume=False)`, as after a password change) lands where it points
(Q70). A session opened already signed in (`user`) resumes the same way, unless it opens at an
address or a tape. A sign-out forgets the user's journey on that device. Anonymous sessions keep
prototype-0's resume by token, for 10 minutes after the client goes away.

**A durable journey store** (the `JourneyStore` interface; `MemoryJourneys` keeps them in memory
here) needs: journeys keyed by app, user, and device, each replaced whole on save
(last writer wins per device) with the time it was saved; the user's most recent journey in one
read; expiry after `keep_journeys`; forgetting a device's journey on sign-out and all of a user's
on account deletion; and the release (tape versions, 05 §7.1) a journey was saved under, so a
resume can tell when its places changed (this engine checks each place against the intent it plays,
Q73). It holds no documents, but tape arguments are part of the position (a
conversation id, a search term), so it is the user's data: kept per region, encrypted at rest,
and named in the privacy labels.

**Inputs** stand in for the client protocol until it exists: `fill` (a field of the edited
record), `press` (an action by id: `submit`, `action:<n>`, `select:<field>`, `press:<field>`; an
`item` key for actions on items; `secrets` for the secret fields it submits), `back`, and `hub`.
Each carries a `seq`, which must grow, and the frame version it was made against; a replayed or
stale input, an unknown action or field, a value of the wrong shape, an item that is not in the
list, or a secret for a field that is not secret is dropped, logged without its content, and
reported to the session as `dropped`. Fills are answered at once; presses run one at a time.

**Decisions.** A submit first validates the edited record (with the secrets it carries) against
its schema, and reports problems by field without calling the app. A handler receives the
frame's documents by parameter (an item for an action on items, `result` for a `then=`), and its
outcome is checked against the outcomes its intent declares before it plays: anything else is
refused as an error. A `Reject` stays and shows its message as the frame's error status; a
raised error or an app that is gone or too slow (30 s) stays with the engine's own message. After
every press that carried secrets the session tells the client to clear those fields (Q58).

**Changes and drafts (Q72).** A fill of a field with an `on_change` handler (on the frame, or on a
`vt.show`) runs that handler as a decision on the frame, after the decisions queued before it and
only while the frame is still on screen, unless the field commits only with the submit
(`commit="submit"`) or the fill left it invalid. That is how a search updates its results, and how
an app keeps drafts: the engine never keeps an edited document beyond its session, so an app that
wants drafts to last saves them from `on_change` in its own services and returns the saved draft
from the frame's loader as the edited document's starting value (the journeys test app does both).

**Failed loaders (Q65).** A move enters its frame (runs the loader) before it shows it, and inputs
are read against the frame on screen meanwhile. When the loader fails on the way (a jump, a goto, a
call, a door, back to a destination beneath a linked frame), the move does not happen: the reel
and the signed-in user go back to where they were, and the engine's message shows as the error
status of the frame the user is on. Only an entry or an address, where there is nowhere to stay,
enters the frame with its defaults and the error.

## Documents

`DocumentStore` (`src/documents.ts`) holds every document a reel holds. A loaded document whose
record has a `vt.Id` that is set is held once, as `{record, id}`, shared by every session that
loads it; anything else is a session's own (`{record, local}`): records without an Id, an Id not
yet set, every edited document, and shown lists. A tape visit holds its documents, so they live
while the visit is on the reel (the step, the history, a call's caller, a destination's saved
history) and are dropped when the last holder lets go. A loader that returns a document already
held refreshes it: the app is the source of truth.

Each document keeps its **confirmed** value and, on top, the **tentative layers** of decisions
still running, in the order their `sync`s arrived; readers see the confirmed value with every layer
applied. When a decision returns, its layers fold into the confirmed value; when it raises or
rejects, they are dropped. A change confirmed meanwhile (a user's edit, `vt.docs` from the app)
lands in the confirmed value and the open layers are applied again on top, so interleaved
decisions keep each other's changes. Every op is validated against the record before it lands
(a user's own edit only for its shape: a constraint it breaks is reported as `invalid` instead).

**Fan-out.** Showing a document is subscribing to it: every session whose frame shows (or edits) a
changed document hears `{t: "doc", ref, record, state, version, decision}`, where `state` is
`tentative`, `confirmed`, or `rolledback`. A session's own documents reach that session alone.

## The headless driver

`Headless` (`src/driver.ts`) plays journeys without a client, standing where a client will: it
numbers its inputs, names the frame it saw, keeps secrets in a client-side buffer (as a platform's
secure editor does) until the submit that sends them, and clears them when the session says so.

```ts
const engine = new Engine();
await engine.listen({ port: 8787 });          // then: videotape serve app:app --engine ws://127.0.0.1:8787/app
await engine.ready();
const s = await Headless.open(engine, { tape: "login" });
await s.fill({ username: "ada@example.com", password: "nope" });
await s.press("Sign in");
s.at("login"); s.error; s.secret("password"); s.doc("Credentials"); s.reel;
```

It reads the reel (`reel`, `place`, `at`), the frame (`view`: actions, fields, documents,
status), the documents (`doc`, `items`, `tentative`, and `changes`, each document as it was at every
change the session heard), the status (`error`, `invalid`, `pending`), `user`, `effects`, and
`dropped`; it acts with `fill`, `press` (by label or id, with `item` for actions on items),
`select`, `back`, and `door`. `Headless.open` takes `address`, `tape` and `args`, `user` (start
signed in, as 06 §8.1's `play(..., user=)`), and `device` (Q62); a third argument
`{ snapshots: false }` records changes without copying the document, for measurements.
`test/done.test.ts` plays the brief's "done when" with it, and `test/devices.test.ts` plays a
journey across devices.

## Latency (E5, E10)

`npx -y pnpm@9.15.0 --filter @videotape/engine latency` (bench/latency.ts) plays the sample apps'
Python processes over a local WebSocket, 300 times after 30 warm-ups, with the driver keeping no
document snapshots. On an Apple-silicon Mac, Node 20.18, Python 3.14 (2026-10-24), p50 / p95:

| What | Before the mirror (8185a75) | With the mirror and a copy per decision (13adf46) |
|------|-----------------------------|----------------------------------------------------|
| A local change: a fill until the session hears it | 0.017 / 0.028 ms | 0.038 / 0.049 ms |
| A decision with no service call (journeys' Wave): press → outcome played | 0.31 / 0.41 ms | 0.33 / 0.45 ms |
| relay's Send, 32–131 messages: press → shown in the other session, tentative | 2.02 / 2.84 ms | 0.40 / 0.61 ms |
| relay's Send, 32–131 messages: press → confirmed in the other session | 3.51 / 4.39 ms | 1.64 / 1.76 ms |
| relay's Send, 232–331 messages: press → shown in the other session, tentative | 5.91 / 7.07 ms | 0.61 / 1.07 ms |
| relay's Send, 232–331 messages: press → confirmed in the other session | 7.87 / 9.18 ms | 1.86 / 2.33 ms |

relay's fake service waits 1 ms inside Send, which is most of what is left. Before the mirror a
decide carried the conversation whole both ways, and the SDK validated it into records each time, so
Send grew with the conversation; now it names it by version. Each decision's own copy (Q68) costs
what its records and lists cost to copy, with list items copied only when the handler reaches them:
about 0.2 ms more at 300 messages for Send, which only appends (a full copy of every record measured
1.89 → 2.64 ms). The local change gained some 20 µs: a fill to a document the app holds is also
sent to the app.

## Decisions (05 §18.2)

The protocol details 05 left open were decided as Q53–Q73 (05 §18.2, on `design/v2` at `bb41cfc`).
Where each lives here:

| Q | Decision | Here |
|---|----------|------|
| Q53 | The app keeps a mirror of the documents its handlers touch, kept current by engine → app `sync` | The app's mirror; `src/mirror.ts`, `videotape/mirror.py` |
| Q54 | A decision's changes are confirmed by its result and rolled back by a raise or `Reject`; background work writes through `vt.docs`, never tentative | Tentative and confirmed; `Engine.sync` |
| Q55 | List items keyed by `vt.Id` or a minted key; an item keeps its first key after it is saved | Documents on the wire; `Records.assignKeys`, `tracking.key_of` |
| Q56 | Documents live while the history holds their tape; loaders run when a frame is entered forward, not on back | Documents; `Session.enter` |
| Q57 | A `decide` carries references and versions, and the answer carries changes only | The app's mirror; latency table |
| Q58 | Secrets are cleared after any press that carried them, not after a validation failure before the app | Decisions (journey runtime) |
| Q59 | An undeclared outcome is refused as an error and rolled back | Decisions (journey runtime) |
| Q60 | The hub as tab bars: one history per destination, the current door starts over; doors in calls or on `hub=False` frames are dropped | History roots |
| Q61 | Back from a call's first frame ends it without a result or `then=`; `check` warns about `done` in a tape no call enters | `Reel.back`; the SDK's `done-without-call` |
| Q62 | `sign_in`/`sign_out` on `stay`, `goto`, or `back` reset history there; reels keyed by user and device, resuming across devices | Across devices; `Session.play` |
| Q63 | A submit validates before the app, per field; a fill that breaks a constraint is kept and shown invalid; one of the wrong shape is dropped | Decisions (journey runtime) |
| Q64 | `fill`, `press`, `back`, `hub` with action ids and frame versions, a stand-in kept for the test driver | Inputs |
| Q65 | Failures show the engine's own message; a failed loader keeps the user in place, except at an entry or address | Failed loaders |
| Q66 | One app per engine; a reconnecting app replaces the old connection; a new intent keeps sessions in development | `Engine.registered`; releases side by side come with the release pipeline |
| Q67 | A record a handler creates must validate; only its `vt.Id` may be missing | The SDK notes what is missing on Pydantic's `ValidationError` |
| Q68 | Each decision works on its own copy: the confirmed values plus its own changes, never another decision's pending ones | Each decision on its own copy; `Tracker.working`; the mirror holds confirmed values |
| Q69 | Signed-in journeys kept 30 days by default (`keep_journeys=`), positions and history only; any device resumes the most recent | Across devices; a durable journey store; `src/journeys.ts` |
| Q70 | A sign-in resumes the user's journey unless the outcome says `resume=False` | Across devices; the SDK's `resume=` |
| Q71 | `RichText`, `Money`, and `Series` are immutable; a handler assigns a new value | The SDK's `values`: frozen sequences that say what to do instead, and builders |
| Q72 | Drafts stay per session; an app keeps them in its own services, loaded as the edited document's starting value and saved on change | Changes and drafts; `on_change` runs on a committed change |
| Q73 | A kept journey resumes at the deepest place in its history a release still has; the sign-in's target only if none survives | Across devices; `Reel.resume` |

**New questions**, from building Q71–Q73:

- **Q-V How often `on_change` runs.** A field with `commit="change"` runs its `on_change` handler on
  every committed change, so saving a draft calls the app's services at every keystroke the client
  commits. Should the engine wait for a pause in typing before it runs `on_change`, or is pacing the
  client protocol's commit policy?
- **Q-W Handlers on an unfinished edited document.** A handler receives the edited document as a
  record, which must validate (Q67), so an `on_change` handler cannot save a draft while a required
  field is still empty: the decision fails. Should an edited document reach handlers before it is
  complete (its required fields optional until the submit), or should a record meant for drafts give
  every field a default?

**Not built** (per the brief): the composer, embodiment, scene state, rendering, streaming,
clients and the client protocol, release, and the TypeScript SDK. Also not built here: timers
(`after=`), moves (`to=`), picks (`vt.pick`), debouncing `on_change`, paging requests from a client
(the protocol's `page` message and the SDK's answer exist), list documents in handlers, and the
deleted-account case of 05 §6.2.
