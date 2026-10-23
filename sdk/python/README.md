# Videotape Python SDK (skeleton)

The first v2 code. An app written as in [06-getting-started.md](../../docs/06-getting-started.md)
becomes intent JSON, and `videotape check` checks it. There is no engine, app-protocol
transport, documents runtime, or composer yet.

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
| `values` | The built-in types: `vt.Text(lines=)`, `vt.Secret`, `vt.Money`, `vt.Image`, `vt.Video`, `vt.Audio`, `vt.RichText`, `vt.Series`, `vt.Page`, and `vt.t(...)` |
| `records` | `vt.Record` on Pydantic v2; `vt.Field(...)` with the options of 06 §4, `vt.State(...)`, `vt.pick("tape")`; `Deal.amount` on the class is a field reference |
| `outcomes` | `jump`, `goto`, `back`, `stay`, `call`, `done`, `open`, `download`, `copy`, and their types for return annotations (`vt.Jump["dashboard"]`) |
| `intent` | `vt.tape`, `vt.frame`, `vt.text`, `vt.show`, `vt.action`, `vt.after`, `vt.hub`, `vt.destination`, `vt.app`. Builders raise at once on what they cannot hold (a wrong type, a malformed id or address) |
| `derive` | What a frame derives from its records: components, affordances, states, and every place where something happens |
| `decisions` | Reads handlers and loaders with `typing.get_type_hints`; `vt.Reject`, `vt.Context`, `vt.invoke` |
| `serialize` | `app.intent()`: the deterministic intent JSON |
| `spec` | The intent document's JSON Schema, published as [`intent.schema.json`](src/videotape/intent.schema.json) |
| `graph`, `check`, `cli` | The journey graph (ported from prototype-0), the check rules, and the `videotape` command |

**Decisions.** Handlers and loaders are plain async functions. Their annotations are read when
the intent is built, so postponed annotations and forward references work. A handler's
parameters after `ctx` are documents by record type, or a move's target; a loader's are its
arguments by name. A handler's return type is its edges: `vt.Jump["x"]`, `vt.Goto["x"]`,
unions, `vt.Stay`, `vt.Back`, `vt.Call["x"]`, `vt.Done`, `vt.Open`, `vt.Download`. Every handler
also has the `Stay` that `raise vt.Reject(message)` takes. `await vt.invoke(handler, ctx,
**documents)` calls a handler the way `decide` will. Documents are passed by parameter name, as
records or as their JSON, and validated against their records. It returns the outcome record:
the outcome's JSON, or `{"type": "reject", "message": ...}`. An outcome the return type does not
declare raises `vt.UndeclaredOutcome`.

## The intent document

```text
format     "videotape.intent/2"
app, entry, world, hub
tapes      [{id, entry, frames: [{id, purpose, title, address, public, shows, edit, enter,
                                  submit, components, states, actions, on_change, after}]}]
records    {Name: JSON Schema with x-vt}     references: #/records/Name, #/types/vt.Name
types      {vt.RichText: ..., vt.Series: ...}
handlers   {name: {params, outcomes}}
loaders    {name: {params, returns}}
edges      [{from, to, type, tape | frame, via}]
```

- **Records** are Pydantic's JSON Schema. Each property's `x-vt` carries its kind
  (`{"type": "text", "lines": [1, 6]}`, `{"type": "record", "record": "Company"}`,
  `{"type": "collection", "item": ...}`) and its options (`role`, `select`, `pages`, ...). Enums
  are in `records` too; the built-in types are under `types`.
- **Frames.** A frame's `id` is its `id=`, or one derived from its purpose (`"sign-in"`, marked
  `derived_id`). Graph nodes are `tape/id`.
- **Components.** What the frame adds comes first, in the order written: `vt.text`, and
  `vt.show` of a field no record derives. Then come the fields of the record it shows, then of
  the record it edits. Records nest (`components`), and collections nest too
  (`item.components`). Each component has `affordances` from the closed set of 05 §6.4,
  derived from its type and whether the frame shows or edits it. `vt.show(ref, ...)` overrides
  every derived component for that field (`override: true`). `State` fields are listed as
  `states`, never as components.
- **Edges** come from static outcomes (actions, `select=`, `press=`, picks, timers) and from
  handlers' return types. `via` says where each one comes from: `{"action": "Sign in"}`,
  `{"submit": "Sign in", "handler": "sign_in"}`, `{"select": "Workspace.projects"}`. `back` and
  `done` have no `to`. A hub's edges are not listed: `hub` implies an edge from every frame to
  every destination.
- The output is deterministic, across processes and hash seeds. Tapes, frames, components,
  actions, and edges keep the order they were written in. Records, handlers, and loaders are
  sorted by name.

## `videotape check`

| Code | Level | Finds | From |
|------|-------|-------|------|
| `unreadable-record` | error | a record names a type that is not defined | v2 |
| `duplicate-id` | error | two tapes, frames, addresses, handlers, loaders, or records share a name | v1 |
| `unknown-entry` | error | the app's entry tape does not exist | v1 |
| `unknown-tape` | error | an action, a handler's return type, a pick, or the hub names a tape that does not exist | v1 |
| `unknown-frame` | error | a goto names a frame its tape does not have | v1 |
| `goto-unnamed-frame` | error | a goto reaches a frame that has no `id=` | v2 |
| `unreadable-return` | error | a handler's return type cannot be read, so its edges are unknown | v1 (was a warning) |
| `unknown-document` | error | a handler takes a record its frame neither shows nor edits | v2 |
| `on-unshown-record` | error | an action is `on=` a record its frame does not show | v2 |
| `secret-shown` | error | a frame shows a field of secret type | v1 (`secret-bind`) |
| `address-param` | error | an address has a parameter the frame's loader does not take | v2 |
| `public-without-address` | error | a public frame has no address | v2 |
| `loader-returns` | error | a frame's loader returns something other than what the frame shows | v2 |
| `unknown-field` | error | a field reference names a record the frame neither shows nor edits | v2 |
| `not-bool` | error | `visible=` or `hidden=` names a field that is not a bool | v2 |
| `bad-event` | error | `vt.show` listens for an event its field cannot report | v1 |
| `unknown-argument` | error | a jump or call passes an argument the target's loader does not take | v2 |
| `missing-argument` | error | a jump, call, or hub destination leaves out an argument the target's loader needs | v2 |
| `multiple-primary` | warning | a frame has more than one primary action | v1 |
| `unused-edit` | warning | a frame edits a record, but nothing receives it | v1 (`unused-values`) |
| `unreachable-frame` | warning | a frame cannot be reached from the entry | v1 |
| `no-exit` | warning | a frame has no way out (a dead end) | v1 |
| `closed-cycle` | warning | frames form a cycle the journey cannot leave | v1 |

Every rule has a broken fixture in `tests/fixtures/broken/` that trips that rule and no other.
The 06 §2.2 sign-in app and the five §9 apps are in `tests/fixtures/`, completed just enough to
import. Each completion is marked "filled in". All six serialise, validate against the
published schema, and check clean.

v1's rules about layouts, styles, slots, and `bind` paths are gone with those concepts. Running
the composer on the reference screens (05 §8) waits for the composer.

## Readings of the design

Where 05 or 06 leave a choice open, the SDK reads them like this:

- Every record has `id: str | None` (05 §6.2: documents are keyed by type and id; 06 builds
  `Workspace(id=...)` without declaring it). A record that is something's identity declares
  `id: str` itself.
- A field typed `X | None` is not required, even without a default (06 §4: "`| None`: required
  or optional"). Pydantic v2 would make it required, so the record's metaclass adds `None` as the
  default before Pydantic reads the class.
- `vt.Money` is an amount with a currency: `vt.Money("12.50", "EUR")`, or
  `{"amount": "12.50", "currency": "EUR"}` in JSON. It compares with numbers by amount, which is
  what makes `vt.Field(ge=0)` work.
- `vt.Secret` is a `str` with a masked repr, so `auth.login(c.username, c.password)` works as
  06 writes it, and the value stays out of logs.
- `vt.RichText` is the closed model of 05 §6.1: paragraphs, emphasis, links, lists, code, and
  mentions. A plain `str` becomes paragraphs; `from_markdown` reads the part of Markdown the
  model can hold.
- A field reference means that field wherever its record occurs in the frame. `vt.show(Channel.name)`
  on a frame that shows `Watch` (whose `channel` is a `Channel`) overrides `Watch.channel.name`.
- A handler may take any record nested in what its frame shows or edits. `on=` may name any
  such record.
- `vt.done(Company)` in an action returns the item the action is on.
- `shows=list[Deal]` is wrapped in one collection component.
- A hub is everywhere: every frame has an edge to every destination.
- Media events are `vt.show(..., on_ended=)` as 06 §9.2 writes them, and also `on_play=`,
  `on_progress=`, `on_error=` (05 §11), plus `on_change=` for edited fields.
- `invoke` also calls plain (non-async) functions.
- A handler may return `vt.stay()` without declaring it, since every handler has the implied
  `Stay`. Any other undeclared outcome is refused.

## Deviations from 05 and 06

- **A field's `pages=` loader is defined before the record that names it.** 06 §5.5 shows
  `Feed` before `feed_page`. Python evaluates `vt.Field(pages=feed_page)` when the class body
  runs, so that order cannot work.
- **`vt.Text` needs `lines=`.** `vt.Text(lines=(1, 6))` returns `Annotated[str, ...]`. A bare
  `vt.Text` is a function, not a type.
- **`submit=` also takes `vt.action(label, handler)`**, for when the primary action's label is
  not the purpose. 06 §8.1 presses "Send" on a frame whose purpose is "Read and reply" (§9.4),
  without saying where "Send" comes from.
- **`vt.t(...)` in a `str` field keeps only its key.** 06 §9.1 builds
  `Dashboard(greeting=vt.t("dashboard.hello", name=...))`. Pydantic turns a `str` subclass into a
  plain `str`, so the document holds `"dashboard.hello"` and loses `name`. `vt.t` works where
  intent holds text (`vt.text`, labels, `Reject`).
- **`vt.docs[...]` raises `NotImplementedError`.** Documents need the engine. 06 §9.4's
  module-level `vt.docs[...]` line is a function in the fixture, because it runs when a message
  arrives.

## Open design questions the code surfaced

1. **Is the platform's back an edge?** `check` counts only declared edges, as v1 did. 06 §9.1's
   report frame (only "Export CSV") and docs frame (only links to itself) are then dead ends, so
   the fixture adds a `vt.back()` and a "Sign in" action. If the browser's or the OS's back
   counts, every frame reached by a jump has an exit and `no-exit` almost never fires.
2. **Where is the hub?** The checker puts it on every frame. That is why the four hub apps have
   no dead ends; it would also hide real ones. Is the hub on frames outside its destinations'
   tapes, or before sign-in?
3. **`vt.Jump["dashboard"]` and static tools.** Linters and type checkers read a string inside
   a subscripted annotation as a forward reference: ruff and pyflakes report F821 (undefined
   name `dashboard`). Under `from __future__ import annotations`, ruff's UP037 autofix strips
   the quotes and breaks the handler (`check` then reports `unreadable-return`). `vt.Text(lines=...)`
   is a call in an annotation, which type checkers reject. Checker-friendly spellings exist
   (`vt.Jump[Literal["dashboard"]]`, `Annotated[str, vt.Lines(1, 6)]`), at the cost of 06's
   brevity.
4. **Arguments in handlers' outcomes are invisible to `check`.** 06 §2.2's `sign_in` returns
   `vt.jump("workspace", user=...)`, but `load_workspace(ctx)` (§5.1) takes no `user`. The return
   type names the tape and not the arguments, so only static outcomes' arguments are checked.
5. **Edit forms with required hidden fields.** CRM's `new_deal` edits `Deal`, whose
   `id: str = vt.Field(show=False)` is required, so the form can never validate as written.
   Should forms validate only shown fields, should the engine assign ids, or should the form be
   its own record?
6. **Stable frame ids.** A frame without `id=` gets an id derived from its purpose. 05 §7.1
   wants places to keep their positions across releases, but rewording a purpose renames the
   node. Should every frame need an `id`?
7. **What receives a call's result?** 06 §6's `company_picked(ctx, d)` reads `ctx.result`, but
   nothing names it as the continuation of `vt.pick` or `vt.call`. The SDK reads a pick as
   filling its field with no handler, and leaves `vt.call`'s continuation open.
8. **Which document is meant when a record occurs twice?** On 06 §9.1's docs frame, `Entry`
   occurs in both `Page.toc` and `Search.results`. A handler that takes an `Entry` (or a
   `vt.show(Entry.title)`) cannot say which one. Today a reference means every occurrence.
9. **`vt.t` in documents** needs a representation in documents and `sync` (deviation 4): a
   `{"t": ..., "params": ...}` value does not fit a field typed `str`.
10. **Lists in edit records.** The affordances have no "add an item" or "remove an item", so a
    `list[X]` in an edited record is read and scrolled only.

## Not built

Per the brief: the engine, the app protocol's transport (`register`, `load`, `decide`, `sync`),
the documents runtime (`vt.docs`, list `append` returning the item, `prepend`, `replace`), the
composer and its reference screens, `vt.testing.play`, `vt.world`, `videotape new`, `dev`,
`graph`, `release`, `export`, and `serve`, and the TypeScript SDK.
