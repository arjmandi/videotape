# Videotape Python SDK (skeleton)

The first v2 code. An app written as in [06-getting-started.md](../../docs/06-getting-started.md)
becomes intent JSON, and `videotape check` checks it. There is no engine, app-protocol
transport, documents runtime, or composer yet.

The SDK follows the design as decided on `design/v2` at `2b28287`: 05 §6.1–§6.4, and §18.1,
which decides the questions and deviations this skeleton first raised (Q31–Q40). This branch
does not contain that commit, so `docs/` here still shows the earlier draft.

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
```

`module:app` names a module and the `vt.app(...)` in it (`app` when left out). The module is
imported from the current directory, or from `--app-dir`. `check` exits 0 when there are only
warnings, 1 on errors, and 2 when it cannot load the app.

## What exists

| Module | What it does |
|--------|--------------|
| `values` | The built-in types: `vt.Id`, `vt.Text`, `vt.Secret`, `vt.Money`, `vt.Image`, `vt.Video`, `vt.Audio`, `vt.RichText`, `vt.Series`, `vt.Page`, and `vt.t(...)` |
| `records` | `vt.Record` on Pydantic v2; `vt.Field(...)` with the options of 06 §4, `vt.State(...)`, `vt.pick("tape")`, `@vt.pages(Record.field)`; `Deal.amount` on the class is a field reference |
| `outcomes` | `jump`, `goto`, `back`, `stay`, `call(tape, then=)`, `done`, `open`, `download`, `copy` |
| `intent` | `vt.tape`, `vt.frame` (with `back=` and `hub=`), `vt.text`, `vt.show`, `vt.action`, `vt.after`, `vt.hub`, `vt.destination`, `vt.app`. Builders raise at once on what they cannot hold (a wrong type, a malformed id or address) |
| `derive` | What a frame derives from its records: components, affordances, states, how often it holds each record, and every place where something happens |
| `decisions` | Reads handlers' parameters with `typing.get_type_hints` and their edges from their bodies; `@vt.outcomes`, `vt.Reject`, `vt.Context`, `vt.invoke` |
| `serialize` | `app.intent()`: the deterministic intent JSON |
| `spec` | The intent document's JSON Schema, published as [`intent.schema.json`](src/videotape/intent.schema.json) |
| `graph`, `check`, `cli` | The journey graph (ported from prototype-0) with history roots, back, and the hub; the check rules; the `videotape` command |

**Records.** A record with a `vt.Id` field is a document the engine holds once by that id; the id
is never shown and not required until the app saves the record. A record without one is the
session's own. `X | None` is not required. A record refuses copy: `vt.t(...)` lives in intent
(`vt.text(vt.t("dashboard.hello", name=Dashboard.first_name))`), where its parameters may be
field references. `vt.Text` is multi-line text, one to six lines unless `vt.Field(lines=...)`
says otherwise. A list's paging loader is registered after its record with `@vt.pages(Feed.posts)`
and takes the `cursor`, and optionally the document that holds the list.

**Decisions.** Handlers and loaders are plain async functions. A handler's parameters after `ctx`
are documents by record type, a move's target, or, for a call's continuation, `result`. Its edges
are read from its body when the intent is built: each `return` of an outcome with a literal tape
or frame name, under whatever name the module imports videotape as, through conditional
expressions, and not into nested functions. The names of the outcome's keyword arguments are read
too, and `sign_in=` or `sign_out=` marks an outcome that resets history. Where a return cannot be
read (a tape named by a variable, an outcome a helper builds, a function without source),
`@vt.outcomes(vt.jump("dashboard", page=...))` declares the edges. Every handler also has the
`Stay` that `raise vt.Reject(message)` takes.

`await vt.invoke(handler, ctx, **documents)` calls a handler the way `decide` will. Documents are
passed by parameter name, as records or as their JSON, and validated against their records. It
returns the outcome record: the outcome's JSON, or `{"type": "reject", "message": ...}`. An
outcome the body does not show raises `vt.UndeclaredOutcome`. A `sign_in=` that is not a record
with its `vt.Id` set raises `TypeError`.

## The intent document

```text
format     "videotape.intent/2"
app, entry, world, hub
tapes      [{id, frames: [{id?, purpose, title, address, public, shows, edit, enter, submit,
                           components, states, actions, on_change, after, back, hub, root}]}]
records    {Name: JSON Schema with x-vt}     references: #/records/Name, #/types/vt.Name
types      {vt.RichText: ..., vt.Series: ...}
handlers   {name: {params, outcomes: [{type, tape | frame, args, resets_history, then}]}}
loaders    {name: {params, returns}}
edges      [{from, to, type, tape | frame, resets_history, via}]
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
  listed: frames carry `root`, `back: false`, and `hub: false` instead.
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
| `unknown-document` | error | a handler or paging loader takes a record its frame neither shows nor edits | v2 |
| `ambiguous-record` | error | a record is named by its type where the frame holds it more than once | Q38 |
| `on-unshown-record` | error | an action is `on=` a record its frame does not show | v2 |
| `secret-shown` | error | a frame shows a field of secret type | v1 (`secret-bind`) |
| `hidden-required` | error | an edit frame hides a required field other than its `vt.Id` | Q35 |
| `address-param` | error | an address has a parameter the frame's loader does not take | v2 |
| `public-without-address` | error | a public frame has no address | v2 |
| `loader-returns` | error | a loader returns something other than what its frame shows, or its list holds | v2 |
| `unknown-field` | error | a field reference names a record the frame neither shows nor edits | v2 |
| `not-bool` | error | `visible=` or `hidden=` names a field that is not a bool | v2 |
| `bad-event` | error | `vt.show` listens for an event its field cannot report | v1 |
| `unknown-argument` | error | an outcome passes an argument the target frame's loader and address do not take | Q34 |
| `missing-argument` | error | an outcome or hub destination leaves out an argument the target's loader needs | Q34 |
| `multiple-primary` | warning | a frame has more than one primary action | v1 |
| `unused-edit` | warning | a frame edits a record, but nothing receives it | v1 (`unused-values`) |
| `unreachable-frame` | warning | a frame cannot be reached from the entry | v1 |
| `no-exit` | warning | a frame has no declared way out, no back, and no hub doors (a dead end) | v1, Q31, Q32 |
| `closed-cycle` | warning | frames form a cycle the journey cannot leave | v1 |

**History and the hub (Q31, Q32).** Every frame has the platform's back, as an exit, except
history roots and frames with `back=False`. The roots are the app's entry, each hub
destination's first frame, and wherever an outcome with `sign_in` or `sign_out` lands. A frame
shows the hub's doors when every root its history can begin at is a hub destination. That root
is reached along jumps and gotos that do not sign in or out, and never through a call. A frame
with `hub=False` never shows them.

Every rule has a broken fixture in `tests/fixtures/broken/` that trips that rule and no other.
The 06 §2.2 sign-in app and the five §9 apps are in `tests/fixtures/`, written as 06 now writes
them on `design/v2` and completed just enough to import. Each completion is marked "filled in".
All six serialise, validate against the published schema, and check clean.

v1's rules about layouts, styles, slots, and `bind` paths are gone with those concepts. Running
the composer on the reference screens (05 §8) waits for the composer.

## Readings of the design

Where 05 or 06 leave a choice open, the SDK reads them like this:

- **References in a list (Q40).** In an edited record, a list of records that have a `vt.Id` is
  a list of references, so it is `choose(many)`; a list of records without one, or of plain
  values, takes `add`, `remove`, and `move`, and its items' fields are inputs. A list with
  `select=` is one to navigate, even in an edited record: 06 §9.1's `Search.results` is neither
  chosen from nor edited.
- **Field options mean their own item (Q38).** In `toc: list[Entry] = vt.Field(select=vt.jump("docs", page=Entry.slug))`,
  `Entry` means the toc's item, and so does the field's own record. A handler used there, or in
  an action `on=` a record, receives that item. Anywhere else, a record named by its type must be
  held once by the frame's documents.
- **Roots start their own history.** A hub destination's first frame is a root even when a plain
  jump reaches it, so the walk that finds where a frame's history began stops at every root.
- **Identity.** `vt.Id` takes a string or an integer and holds it as a string. `sign_in=` is
  checked when the handler runs (`vt.invoke`); statically, the SDK only sees that an outcome
  signs in. In `@vt.outcomes`, `sign_in=True` stands for the user.
- **Arguments.** An argument is accepted when the target frame's loader or its address takes
  it. A `goto` passes none, so a `goto` to a frame whose loader needs an argument is a
  `missing-argument`. `**kwargs` in an outcome leaves its arguments unchecked.
- `vt.Money` is an amount with a currency (`{"amount": "12.50", "currency": "EUR"}` in JSON); it
  compares with numbers by amount, which is what makes `vt.Field(ge=0)` work.
- `vt.Secret` is a `str` with a masked repr, so `auth.login(c.username, c.password)` works as
  06 writes it, and the value stays out of logs.
- `vt.RichText` is the closed model of 05 §6.1. A plain `str` becomes paragraphs;
  `from_markdown` reads the part of Markdown the model can hold.
- `vt.show(ref)` overrides that field wherever its record occurs on the frame; `vt.done(Company)`
  in an action returns the item; `shows=list[Deal]` is wrapped in one collection component.
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

There are no deviations from 05 or 06 as they stand at `2b28287`.

## The questions the first skeleton raised, decided

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

## Open questions this work surfaced

1. **`vt.show` of a field of a record held twice.** `on=Page.toc` names which `Entry` an action
   means, but `vt.show(Entry.title, ...)` on 06 §9.1's docs frame has no spelling that says which
   one. Today it is an `ambiguous-record`. Should `vt.show` take the holding field too
   (`vt.show(Page.toc, Entry.title)`), or a chained reference (`Page.toc.title`)?
2. **`select=` on an edited list.** The SDK reads it as a list to navigate, not to edit (see
   readings). Is that the intent of Q40, or should a search's results live in the shown record
   rather than the edited one?
3. **References versus owned items.** The SDK tells a list of references (`choose(many)`) from a
   list of owned items (add, remove, move) by whether the item record has a `vt.Id`. A record
   with an id can still be owned (line items saved with their order), so an explicit option may
   be needed.
4. **`vt.back()` on a history root.** An explicit back action on a root has nowhere to go, yet
   `check` counts it as a way out. Should that be a rule?
5. **Tape names in constants.** Q33 reads only literal names, so `return vt.jump(DASHBOARD)` with
   a module constant needs `@vt.outcomes`. Should the reader resolve module-level string
   constants?
6. **`goto` and loaders.** A `goto` carries no arguments, so the frame it reaches cannot have a
   loader that needs one. Should `goto` take arguments, or should such frames share the tape's
   loaded documents?

## Not built

Per the brief: the engine, the app protocol's transport (`register`, `load`, `decide`, `sync`),
the documents runtime (`vt.docs`, list `append` returning the item, `prepend`, `replace`), the
composer and its reference screens, `vt.testing.play`, `vt.world`, `videotape new`, `dev`,
`graph`, `release`, `export`, and `serve`, and the TypeScript SDK.
