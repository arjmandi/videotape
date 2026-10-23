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
| app → engine | `result` | `id`, and one of `outcome`, `reject: {message}`, `documents: [{record, value}]`, `page: {items, next}`, `error: {type, message}` |
| app → engine | `sync` | `changes: [{doc, ops}]`, and `decision` when they are tentative under a decision |
| app → engine | `log` | `level`, `message`, `logger`: the app's log lines, scrubbed of secrets by the SDK and again by the engine |
| app → engine | `ping` / engine → app `pong` | keepalive |

**Documents on the wire.** A shared document is addressed as `{record, id}` (its `vt.Id`), a
session's own as `{record, local}` with a key the engine chose. A document's value is its record's
JSON, and each record item of a list carries its key as `"@key"`: its `vt.Id` when it has one, or a
key the engine (`~e…`) or the SDK (`~<process>.<n>`) minted. A `documents` entry that is an item
of a list also has `path` and `record`. `user` is `{record, id, value}`, the record `sign_in=`
passed, and an outcome that signs in carries `sign_in` in that shape.

**Ops.** A path is a list of field names and `{"key": ...}` segments for items of lists of records.

| Op | Meaning |
|----|---------|
| `{op: "set", path, value}` | assignment; a list of plain values, or a reordered list, is set whole |
| `{op: "insert", path, key, value, at}` | `append` (`at: "end"`), `prepend` (`"start"`), or `insert` (`{before: key}`); the key is the item's from now on |
| `{op: "remove", path, key \| id}` | remove the item with this key, or with this `vt.Id` (from `vt.docs`) |
| `{op: "replace", path, key \| id, value}` | replace an item; the new item keeps the old one's key |

**Tentative and confirmed.** While a handler runs, the SDK sends each change as it is made: the
changes of one event-loop turn travel as one `sync` with the decision's id. The decision's
`result` confirms them; an `error` or a `reject` rolls them back. A `sync` without `decision`
(`vt.docs` outside a handler) is confirmed at once. The SDK sends all of a decision's changes
before its result, and the WebSocket keeps that order.

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
every press that carried secrets the session tells the client to clear those fields.

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
`select`, `back`, and `door`. `Headless.open` takes `address`, `tape` and `args`, and `user` (start
signed in, as 06 §8.1's `play(..., user=)`). `test/done.test.ts` plays the brief's "done when"
with it.

## Latency (E5, E10)

`npx -y pnpm@9.15.0 --filter @videotape/engine latency` (bench/latency.ts) plays the sample apps'
Python processes over a local WebSocket, 300 times after 30 warm-ups. On an Apple-silicon Mac,
Node 20.18, Python 3.14 (2026-10-24):

| What | p50 | p95 | p99 |
|------|-----|-----|-----|
| A local change: a fill until the session hears the document change | 0.024 ms | 0.047 ms | 0.070 ms |
| A decision (journeys' Wave, no service call): press → change shown, tentative | 0.32 ms | 0.46 ms | 0.85 ms |
| The same: press → outcome played, confirmed | 0.36 ms | 0.52 ms | 0.90 ms |
| relay's Send (its fake service waits 1 ms), 32–131 messages: press → shown in the other session | 2.1 ms | 3.5 ms | 3.6 ms |
| The same: press → confirmed in the other session | 3.6 ms | 5.2 ms | 5.5 ms |
| relay's Send, 232–331 messages: press → shown in the other session | 6.5 ms | 8.3 ms | 12.7 ms |
| The same: press → confirmed in the other session | 8.7 ms | 11.9 ms | 15.4 ms |

The engine's own work is small; a decision costs what moving its documents costs. A `decide` carries
every document the handler takes, whole, and the SDK validates them into records, so Send slows
as the conversation grows (Q-E below).

## Decisions this engine took, as questions for the design

05 leaves these open; the engine decided them as written here, and they are open to the design.

- **Q-A Engine → app `sync`.** 05 §6.6 says `sync` goes both ways. The engine sends documents
  whole with each `load` and `decide` and never sends `sync` to the app, so the app process keeps
  no copy and `vt.docs[...]` is a write-only handle (reading a field raises). Should the app keep a
  mirror of the documents it touches, kept current by engine → app `sync`, so decides carry refs?
- **Q-B Confirmation.** A decision's tentative changes are confirmed by its `result` (an outcome),
  not by a `sync` of its own; an error or a `Reject` rolls them back. Changes after the result
  (a handler's background task) are not sent.
- **Q-C Keys.** List items of records are keyed by their `vt.Id`, else by a key the engine (`~e…`)
  or the SDK (`~<process>.<n>`) mints; ops address items by key (or by Id from `vt.docs`); lists
  of plain values change whole. An item keeps the key it was added with, even after the app saves
  it with an Id. A reload whose value differs re-keys items without an Id.
- **Q-D Lifetime.** Documents live while a reel holds their tape visit (the step, the history,
  calls, saved hub histories), not only while shown, so back returns to documents kept current,
  without running the loader again. Loaders run on entering a frame by jump, goto, call, address,
  or a destination's first door; not on back, done, or a door that restores a saved history.
- **Q-E Cost of a decide.** Each decide sends its documents whole both ways in JSON (see the
  latency table). Paging (`@vt.pages`) bounds a list, but nothing yet bounds what a decide carries.
- **Q-F Secrets.** A secret travels only with the submit press, merged into that decide's edited
  document, and the session tells the client to clear every secret field after any press that
  carried secrets (success, reject, or error). Should a validation failure before the app clear
  them too? Here it does not: they never left the client's editor.
- **Q-G Undeclared outcomes.** A handler's outcome that its intent does not declare is refused as
  an error and its changes rolled back (05 §6.3: `check` and the engine agree by construction).
- **Q-H Hub.** Each destination keeps its own history; the current destination's door starts it
  over (as tab bars do); a jump into a destination's tape keeps history and the hub. A press on a
  hub door inside a call, or on a `hub=False` frame, is dropped.
- **Q-I Calls.** Back from a call's first frame ends the call without a result and without calling
  `then=`. `done` outside a call is ignored.
- **Q-J Identity without moving.** `sign_in=`/`sign_out=` on `stay`, `goto`, or `back` reset the
  history where the reel lands. Reels are resumable by token (prototype-0's resume); keying reels by
  user and device so a journey resumes on another device (05 §6.2) is not built.
- **Q-K Validation.** A submit validates the edited record with its secrets before the app, and
  reports problems by field; other handler actions do not. A fill of the wrong JSON shape is
  dropped; a fill that breaks a constraint is kept and reported (`invalid`).
- **Q-L Inputs.** Until the client protocol exists, sessions take `fill`, `press`, `back`, and
  `hub` with a `seq` and the frame version (the scene version's stand-in), and say `dropped` with a
  reason. Action ids are `submit`, `action:<n>`, `select:<field>`, `press:<field>`.
- **Q-M Errors.** A raised handler, a failed loader, and an app that is gone or slower than 30 s
  show the engine's own message as the frame's error status, never the app's exception text. A
  failed loader enters the frame with defaults.
- **Q-N One app.** An engine plays one app. A new connection from the same app replaces the old
  one; another app is refused while sessions exist. A new intent keeps the sessions and, when the
  records did not change, the documents.
- **Q-O `Message.sent_at`.** 06 §9.4's `send` builds a `Message` without `sent_at`, which the
  guide declares required; the relay fixture makes it optional. Should a record a handler creates
  be allowed to lack required fields until the app saves it, as `vt.Id` is?

**Not built** (per the brief): the composer, embodiment, scene state, rendering, streaming,
clients and the client protocol, release, and the TypeScript SDK. Also not built here: timers
(`after=`), `on_change` handlers, moves (`to=`), picks (`vt.pick`), paging requests from a client
(the protocol's `page` message and the SDK's answer exist), list documents in handlers, and
cross-device resume.
