# Videotape Python SDK (skeleton)

The first v2 code. An app written as in [06-getting-started.md](../../docs/06-getting-started.md)
becomes intent JSON, `videotape check` checks it, and `videotape serve` serves it to the engine
core in [`packages/engine`](../../packages/engine) over the app protocol. There is no composer yet.

The SDK follows the design as decided on `design/v2` at `df3e343`: 05 §6.1–§6.4, and §18.1,
which decides the questions and deviations this skeleton raised in four rounds (Q31–Q52). This
branch does not contain those commits, so `docs/` here still shows the earlier draft.

```bash
cd sdk/python
python3 -m venv .venv                 # Python 3.11 or later
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

```bash
.venv/bin/videotape intent app:app --app-dir tests/fixtures/hello   # the intent JSON
.venv/bin/videotape check app:app --app-dir tests/fixtures/hello    # diagnostics; exit 1 on errors
.venv/bin/videotape check crm --app-dir tests/fixtures/apps --json  # diagnostics as JSON
.venv/bin/videotape schema                                          # the intent document's JSON Schema
.venv/bin/videotape serve app:app --app-dir tests/fixtures/hello --engine ws://127.0.0.1:8787/app
```

`module:app` names a module and the `vt.app(...)` in it (`app` when left out). The module is
imported from the current directory, or from `--app-dir`. `check` exits 0 when there are only
warnings, 1 on errors, and 2 when it cannot load the app.

## What exists

| Module | What it does |
|--------|--------------|
| `values` | The built-in types: `vt.Id`, `vt.Text`, `vt.Secret`, `vt.Money`, `vt.Image`, `vt.Video`, `vt.Audio`, `vt.RichText`, `vt.Series`, `vt.Page`, and `vt.t(...)` |
| `records` | `vt.Record` on Pydantic v2; `vt.Field(...)` with the options of 06 §4, `vt.State(...)`, `vt.pick("tape")`, `@vt.pages(Record.field)`; `Deal.amount` on the class is a field reference, and `Deal.company.name` chains into a nested record |
| `outcomes` | `jump`, `goto`, `back`, `stay`, `call(tape, then=)`, `done`, `open`, `download`, `copy`. Wherever a tape is named (outcomes, `vt.destination`, `vt.app(entry=)`, `vt.pick`), the tape itself or its id works |
| `intent` | `vt.tape`, `vt.frame` (`shows=` one record or a list, `back=`, `hub=`, `under=`), `vt.text`, `vt.show` (with `on=`), `vt.action`, `vt.after`, `vt.hub`, `vt.destination`, `vt.app`. Builders raise at once on what they cannot hold (a wrong type, a malformed id or address) |
| `derive` | What a frame derives from its records: components, affordances, states, how often it holds each record, and every place where something happens |
| `decisions` | Reads handlers' parameters with `typing.get_type_hints` and their edges from their bodies; `@vt.outcomes`, `vt.Reject`, `vt.Context`, `vt.invoke` |
| `serialize` | `app.intent()`: the deterministic intent JSON |
| `spec` | The intent document's JSON Schema, published as [`intent.schema.json`](src/videotape/intent.schema.json) |
| `graph`, `check`, `cli` | The journey graph (ported from prototype-0) with history roots, back, and the hub; the check rules; the `videotape` command |
| `serve` | The app protocol's client: `register`, then `load`, `page`, and `decide` answered with the app's loaders and handlers (as `vt.invoke` calls them), `sync` for document changes, `log` for the app's log lines, scrubbed of secrets. The shapes are in [`packages/engine/README.md`](../../packages/engine/README.md) |
| `tracking` | The documents a handler receives are tracked: each assignment and list change (`append` returns the item; `prepend`, `insert`, `remove`, `pop`, `replace` by `vt.Id`) becomes a `sync` op in the same event-loop turn, tentative under the decision; secret fields are never sent |
| `documents` | `vt.docs[Record, id]`: a write handle on a document the engine holds, for code outside handlers; its changes are confirmed at once (tentative inside a handler) |

**Records and frames.** A frame shows the records the user reads (`shows=Page`, or
`shows=[Page, Results]`) and edits the one the user writes. A record with a `vt.Id` field is a
document the engine holds once by that id; the id is never shown and not required until the app
saves the record. A shown record without one is the session's own, such as a handler's search
results. The `enter` loader returns one document or a tuple. Every shown record needs a source
when its frame is entered: the loader, an earlier frame of the tape, or defaults for every
required field (Q47). `X | None` is not required. A record refuses copy: `vt.t(...)` lives in intent
(`vt.text(vt.t("dashboard.hello", name=Dashboard.first_name))`), where its parameters may be
field references. `vt.Text` is multi-line text, one to six lines unless `vt.Field(lines=...)`
says otherwise. A list's paging loader is registered after its record with `@vt.pages(Feed.posts)`
and takes the `cursor`, and optionally the document that holds the list.

**Decisions.** Handlers and loaders are plain async functions. A handler's parameters after `ctx`
are documents by record type, a move's target, or, for a call's continuation, `result`. Its edges
are read from its body when the intent is built: each `return` of an outcome, under whatever name
the module imports videotape as, through conditional expressions, and not into nested functions.
The tape or frame is a literal, or a name or dotted name from the handler's module: a string
constant, or the tape itself (`return vt.jump(dashboard)`), never a local variable. The names of the outcome's keyword arguments are read
too, and `sign_in=` or `sign_out=` marks an outcome that resets history. Where a return cannot be
read (a tape named by a variable, an outcome a helper builds, a function without source),
`@vt.outcomes(vt.jump("dashboard", page=...))` declares the edges. Every handler also has the
`Stay` that `raise vt.Reject(message)` takes. Arguments belong to the tape a jump or call enters:
any frame's loader in it may take them by name, and the documents its earlier frames show, edit,
or load by annotation. `vt.goto` takes none.

`await vt.invoke(handler, ctx, **documents)` calls a handler the way `decide` will. Documents are
passed by parameter name, as records or as their JSON, and validated against their records. It
returns the outcome record: the outcome's JSON, or `{"type": "reject", "message": ...}`. An
outcome the body does not show raises `vt.UndeclaredOutcome`. A `sign_in=` that is not a record
with its `vt.Id` set raises `TypeError`.

## The intent document

```text
format     "videotape.intent/2"
app, entry, world, hub
tapes      [{id, frames: [{id?, purpose, title, address, public, shows: [...], edit, enter, submit,
                           components, states, actions, on_change, after, back, hub, root, under}]}]
records    {Name: JSON Schema with x-vt}     references: #/records/Name, #/types/vt.Name
types      {vt.RichText: ..., vt.Series: ...}
handlers   {name: {params, outcomes: [{type, tape | frame, args, resets_history, then}]}}
loaders    {name: {params, returns: [...]}}
edges      [{from, to, type, tape | frame, resets_history, signs_in, via}]
```

- **Records** are Pydantic's JSON Schema. Each property's `x-vt` carries its kind
  (`{"type": "text", "lines": [1, 6]}`, `{"type": "id"}`, `{"type": "record", "record": "Company"}`,
  `{"type": "collection", "item": ...}`) and its options (`role`, `select`, `pages`,
  `min_items`, ...). A record's own `x-vt` names its identity field (`{"type": "record", "id": "slug"}`).
  Enums are in `records` too; the built-in types are under `types`.
- **Places.** A place is its tape plus the frame's `id=`. A one-frame tape needs no frame id;
  graph nodes are `tape` or `tape/id`. A tape's first frame is where it starts.
- **Components.** What the frame adds comes first, in the order written: `vt.text`, and
  `vt.show` of a field no record derives. Then come the fields of the record it shows, then of
  the record it edits. Records nest (`components`), and collections nest too
  (`item.components`). Each component has `affordances` from the closed set of 05 §6.4 (`read`,
  `write`, `press`, `choose`, `adjust`, `move`, `add`, `remove`, `scroll`, `play`), derived from
  its type and whether the frame shows or edits it; `many: true` marks `choose(many)`.
  `vt.show(ref, ...)` overrides every derived component for that field (`override: true`).
  `State` fields are listed as `states`, never as components.
- **Edges** come from static outcomes (actions, `select=`, `press=`, picks, timers), from the
  outcomes handlers return, and from a call's `then=` handler, which runs at the calling frame.
  `via` says where each one comes from: `{"action": "Sign in"}`,
  `{"submit": "Sign in", "handler": "sign_in"}`, `{"then": "confirm_delete", "handler": "delete_confirmed"}`.
  `back` and `done` have no `to`. The platform's back and the hub's doors are implied, not
  listed: frames carry `root` (`"always"`, or `"sometimes"` where something also enters them
  with history), `back: false`, and `hub: false` instead. A frame opened by its address in a hub
  app carries `under`, the destination tape the engine puts beneath it, which the engine uses as
  given (Q52).
- The output is deterministic, across processes and hash seeds. Tapes, frames, components,
  actions, and edges keep the order they were written in. Records, handlers, and loaders are
  sorted by name.

## `videotape check`

| Code | Level | Finds | From |
|------|-------|-------|------|
| `bad-record` | error | a record cannot be read: an undefined type, two `vt.Id` fields, or an option on the wrong type | v2 |
| `duplicate-id` | error | two tapes, frames, addresses, handlers, loaders, or records share a name | v1 |
| `unknown-entry` | error | the app's entry tape does not exist | v1 |
| `unknown-tape` | error | an outcome, a pick, or the hub names a tape that does not exist | v1 |
| `unknown-frame` | error | a goto names a frame its tape does not have | v1 |
| `unnamed-frame` | error | a frame in a tape of several has no `id=` | Q36 |
| `unreadable-outcome` | error | a handler returns an outcome its body does not say, and has no `@vt.outcomes` | Q33 |
| `then-without-result` | error | a call's `then=` handler takes no `result` parameter | Q37 |
| `unknown-document` | error | a handler takes a record its frame neither shows nor edits; a loader takes one no earlier frame of its tape has | v2, Q46 |
| `ambiguous-record` | error | a record is named by its type where the frame holds it more than once | Q38 |
| `on-unshown-record` | error | an action is `on=` a record its frame does not show | v2 |
| `secret-shown` | error | a frame shows a field of secret type | v1 (`secret-bind`) |
| `hidden-required` | error | an edit frame hides a required field other than its `vt.Id` | Q35 |
| `edited-select` | error | a list in an edited record has `select=`; lists the user navigates are shown | Q42 |
| `address-param` | error | an address has a parameter no loader in its tape takes | v2, Q46 |
| `bad-under` | error | `under=` on a frame without an address or in an app without a hub, or naming a tape that is not a hub destination that reaches the frame | Q52 |
| `address-standalone` | error | a frame opened by its address needs arguments or documents its address does not supply | Q48 |
| `unsourced-record` | error | a shown record has no source: no loader returns it, no earlier frame has it, and it has required fields | Q47 |
| `public-without-address` | error | a public frame has no address | v2 |
| `loader-returns` | error | a loader returns a document its frame neither shows nor edits, or a page of something its list does not hold | v2, Q42 |
| `unknown-field` | error | a field reference names a record the frame neither shows nor edits | v2 |
| `not-bool` | error | `visible=` or `hidden=` names a field that is not a bool | v2 |
| `bad-event` | error | `vt.show` listens for an event its field cannot report | v1 |
| `unknown-argument` | error | a jump or call passes an argument no loader or address in the tape it enters takes | Q34, Q46 |
| `missing-argument` | error | a jump, call, or hub destination leaves out an argument a loader in the tape needs | Q34, Q46 |
| `back-on-root` | error | an explicit back on a frame that is a history root on every path; it is no way out | Q44 |
| `back-on-root-sometimes` | warning | an explicit back on a frame that is a history root on some paths, where the client hides it | Q44 |
| `multiple-primary` | warning | a frame has more than one primary action | v1 |
| `unused-edit` | warning | a frame edits a record, but nothing receives it | v1 (`unused-values`) |
| `unreachable-frame` | warning | a frame cannot be reached from the entry | v1 |
| `no-exit` | warning | a frame has no declared way out, no back, and no hub doors (a dead end) | v1, Q31, Q32, Q49 |
| `closed-cycle` | warning | frames form a group the journey cannot leave, unless it holds the entry, a sign-in target, or a hub destination | v1, Q51 |

**History and the hub (Q31, Q32, Q44, Q48, Q49).** The history roots are the app's entry, each
hub destination's first frame, wherever an outcome with `sign_in` or `sign_out` lands, and a frame
opened by its address when no hub destination reaches it. With a hub, a destination is put beneath
a linked frame instead, so back and the hub work there: its `under=`, or else the first destination
in hub order that reaches it. The SDK writes that destination into the intent as the frame's
`under`, so `check` and the engine agree by construction.
Back is a way out only where a frame has history on every path to it: never on a root, even one
that is a root on some paths only, and never with `back=False`. One computation (`graph.journey`)
serves dead ends and explicit backs alike: an explicit `vt.back()` on a frame that is a root on
every path is an error and no way out, and on a root on some paths a warning. A frame shows the
hub's doors when every root its history can begin at is a hub destination, reached along jumps and
gotos that do not sign in or out, never through a call; `hub=False` hides them. Frames opened by
their address count as reachable.

**Closed cycles (Q51).** A group of frames with no way out of the group is reported, except where
it holds the entry, a sign-in target, or a hub destination: after a fresh start, that group is the
app the user came for, not a trap. A group that only a sign-out leads into is reported.

Every rule has a broken fixture in `tests/fixtures/broken/` that trips that rule and no other;
`tests/fixtures/clean/` holds apps that check clean because of an exception (Q51's fresh starts).
The 06 §2.2 sign-in app and the five §9 apps are in `tests/fixtures/`, written as 06 now writes
them on `design/v2` and completed just enough to import. Each completion is marked "filled in".
All six serialise, validate against the published schema, and check clean.

v1's rules about layouts, styles, slots, and `bind` paths are gone with those concepts. Running
the composer on the reference screens (05 §8) waits for the composer.

## Readings of the design

Where 05 or 06 leave a choice open, the SDK reads them like this:

- **Field options mean their own item (Q38).** In `toc: list[Entry] = vt.Field(select=vt.jump("docs", page=Entry.slug))`,
  `Entry` means the toc's item, and so does the field's own record. A handler used there, or in
  an action `on=` a record, receives that item. Anywhere else, a record named by its type must be
  held once by the frame's documents. A chained reference (`Customer.billing.city`) is resolved
  from its root record, so it names one document even where its own record occurs twice.
- **`on=` in `vt.show` names a list (Q41).** It must hold records, and the shown field must be a
  field of its items; for a single nested record, the reference is chained instead.
- **Roots on some paths (Q44).** A root that something also enters with history keeps the
  platform's back off for dead-end checks, conservatively, and its explicit `vt.back()` counts as
  a way out (it works on the paths with history); `check` warns about it.
- **Tape arguments (Q46).** A jump is checked against the union of its tape's loaders' and
  addresses' parameters, and against every loader's required ones. A loader's record parameters
  are documents, not arguments: each must be shown, edited, or loaded by an earlier frame of the
  tape. A loader's own return must be one of its frame's documents.
- **Tape names (Q45).** Only module-level names resolve: a local variable or a closure's variable
  needs `@vt.outcomes`, even when a global has the same name. A dotted name resolves through
  attributes (`Tapes.settings`). In a goto, a frame object with an `id` names that frame.
- **Sources (Q47).** An earlier frame of the tape counts as a source when it shows, edits, or
  loads the record. A loader whose return the SDK cannot read (no annotation) may return anything,
  so its frame's records are taken as sourced. A list document (`shows=list[Deal]`) starts empty.
- **Linked frames (Q48).** "Its loader may take only address parameters": the SDK lets a loader
  also take parameters that have defaults, since the default supplies them when a link opens the
  frame. A shown record only an earlier frame supplies is an `address-standalone` error there. A
  destination "can reach" a linked frame along jumps and gotos that keep history, without passing
  another root, the same walk that places the hub's doors.
- **Identity.** `vt.Id` takes a string or an integer and holds it as a string. `sign_in=` is
  checked when the handler runs (`vt.invoke`); statically, the SDK only sees that an outcome
  signs in. In `@vt.outcomes`, `sign_in=True` stands for the user.
- `vt.Money` is an amount with a currency (`{"amount": "12.50", "currency": "EUR"}` in JSON); it
  compares with numbers by amount, which is what makes `vt.Field(ge=0)` work.
- `vt.Secret` is a `str` with a masked repr, so `auth.login(c.username, c.password)` works as
  06 writes it, and the value stays out of logs.
- `vt.RichText` is the closed model of 05 §6.1. A plain `str` becomes paragraphs;
  `from_markdown` reads the part of Markdown the model can hold.
- `vt.done(Company)` in an action returns the item; `shows=list[Deal]` is one list document,
  wrapped in one collection component, while `shows=[Page, Results]` is two documents.
- Media events are `vt.show(..., on_ended=)` as 06 §9.2 writes them, and also `on_play=`,
  `on_progress=`, `on_error=` (05 §11), plus `on_change=` for edited fields.
- `invoke` also calls plain (non-async) functions, and allows an undeclared `vt.stay()`, since
  every handler has the implied `Stay`.

## Deviations from 05 and 06, settled

The five deviations the first skeleton listed are settled in 05 §18.1 and implemented:

- **Paging** is `@vt.pages(Record.field)`, registered after the record; `pages=` is gone from
  `vt.Field` and raises a `TypeError` that says so.
- **`vt.Text`** is a type used bare; `lines=` is a `vt.Field` option.
- **`submit=vt.action(label, handler)`** is the decided spelling for a primary action whose label
  is not the purpose.
- **Copy in documents** is replaced by Q39: a record refuses `vt.t(...)`, and copy with
  parameters lives in intent.
- **`vt.docs[...]`** still raises `NotImplementedError` until the engine exists; 06 now shows it
  inside the functions that receive outside events, and so do the fixtures.

There are no deviations from 05 or 06 as they stand at `df3e343`.

## The questions this skeleton raised, decided

| Asked | Decided (05 §18.1) | In the SDK |
|-------|--------------------|------------|
| 1. Is the platform's back an edge? | Q31: yes, from every frame with history | `graph.journey` adds back edges; roots and `back=False` have none |
| 2. Where is the hub? | Q32: where history began at a destination; never on calls | `graph.journey` adds the doors; `hub=False` |
| 3. `vt.Jump["x"]` and static tools | Q33: edges come from the handler's body | `decisions.read_body`, `@vt.outcomes`; the annotation form is gone |
| 4. Handler arguments invisible to `check` | Q34: read from the body and matched; `sign_in=` takes the user's record | `unknown-argument`, `missing-argument` |
| 5. Edit forms with required hidden fields | Q35: `vt.Id`, and a rule | `vt.Id`; `hidden-required` |
| 6. Stable frame ids | Q36: tape plus `id=`; one-frame tapes need none | derived ids are gone; `unnamed-frame` |
| 7. What receives a call's result? | Q37: `call(tape, then=handler)`, as `result` | `vt.call(..., then=)`; `then-without-result` |
| 8. A record held twice | Q38: name the field (`on=Page.toc`) | `on=` takes a field; `ambiguous-record` |
| 9. `vt.t` in documents | Q39: copy lives in intent | records refuse `vt.t`; field references as parameters |
| 10. Lists in edit records | Q40: `add`, `remove`, `choose(many)` | list modes; `min_items=`, `max_items=` |
| 2.1 `vt.show` of a field of a record held twice | Q41: `vt.show(Entry.title, on=Page.toc)`; chains only into single nested records | `vt.show(..., on=)`; chained `FieldRef`s that refuse lists |
| 2.2 `select=` on an edited list | Q42: read data is shown, written data is edited; `shows=` takes a list | `shows=[...]`, tuple returns; `edited-select` |
| 2.3 References versus owned items | Q43: by spelling, never by ids | `list_mode` reads `vt.pick`, `options=`, and Enums |
| 2.4 `vt.back()` on a history root | Q44: an error where always a root, a warning where sometimes | `back-on-root`, `back-on-root-sometimes`; `root: "always" \| "sometimes"` |
| 2.5 Tape names in constants | Q45: resolved against the handler's module; a tape object works | `place_name`; `vt.jump(tape)` |
| 2.6 `goto` and loaders | Q46: arguments belong to the tape; `goto` takes none | tape-level argument checks; loaders take earlier frames' documents |
| 3.1 Shown records nothing loads | Q47: every shown record needs a source | `unsourced-record` |
| 3.2 Entering a tape by a later frame's address | Q48: the frame stands on its own; with a hub, the first destination that reaches it goes beneath it | `address-standalone`; `graph.journey` places address entries |
| 3.3 Back on roots on some paths | Q49: back counts only where a frame has history on every path | one computation for dead ends and explicit backs |
| 3.4 Tape objects beyond outcomes | Q50: the tape or its id wherever a tape is named | `vt.destination`, `vt.app(entry=)`, `vt.pick` take tapes |
| 4.1 Closed cycles after a fresh start | Q51: a group holding a sign-in target or a hub destination is no trap | `closed_cycles(g, fresh)`; sign-out targets are not fresh starts |
| 4.2 Where the linked frame's destination is decided | Q52: by the SDK, carried in the intent as `under`; `under=` overrides | `vt.frame(under=)`; `under` in the intent and schema; `bad-under` |

## Open questions

None. Every question the skeleton raised is decided in 05 §18.1 (Q31–Q52), and this work surfaced
no new ones.

## Not built

The composer and its reference screens, `vt.testing.play` (the engine's headless driver plays
journeys from TypeScript for now), `vt.world`, `videotape new`, `dev`, `graph`, `release`, and
`export`, and the TypeScript SDK. `vt.docs` writes and does not read (engine question Q-A).
