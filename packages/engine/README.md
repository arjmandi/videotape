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
