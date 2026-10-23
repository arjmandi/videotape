# Videotape Python SDK (skeleton)

The first v2 code: an app written as in [06-getting-started.md](../../docs/06-getting-started.md)
becomes intent JSON, and `videotape check` checks it. There is no engine, transport, or runtime
yet.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

```python
import videotape as vt

class Credentials(vt.Record):
    username: str
    password: vt.Secret
```

## What exists

- **Records and fields** (`videotape.records`, `videotape.values`): `vt.Record` on Pydantic v2;
  `vt.Text(lines=)`, `vt.Secret`, `vt.Money`, `vt.Image`, `vt.Video`, `vt.Audio`, `vt.RichText`,
  `vt.Series`, `vt.Page`; `vt.Field(...)` with the options of 06 §4, `vt.State(...)`,
  `vt.pick("tape")`, and `vt.t(...)`. `Deal.amount` on the class is a field reference.
- **Intent** (`videotape.intent`, `videotape.outcomes`): `vt.tape`, `vt.frame`, `vt.text`,
  `vt.show`, `vt.action`, `vt.after`, `vt.hub`, `vt.destination`, `vt.copy`, `vt.app`, and the
  outcomes `jump`, `goto`, `back`, `stay`, `call`, `done`, `open`, `download`. Builders raise at
  once on what they cannot hold (a wrong type, a malformed id or address).
- **Intent JSON** (`app.intent()`, `videotape.serialize`): deterministic JSON with each record's
  JSON Schema (Pydantic's, with Videotape's options under `x-vt`), the built-in types under
  `types`, tapes, frames, components derived from the records plus explicit overrides, actions,
  handlers, loaders, and the edges of the journey graph. Its own schema is published as
  [`intent.schema.json`](src/videotape/intent.schema.json) (`python -m videotape.spec`).
- **Decisions** (`videotape.decisions`): handlers and loaders are plain async functions, read
  with `typing.get_type_hints` when the intent is built (so postponed annotations and forward
  references work). Parameters after `ctx` are documents by record type, a move's target, or a
  loader's arguments; the return type is the handler's edges (`vt.Jump["dashboard"]`,
  `vt.Goto["x"]`, unions, `vt.Stay`, `vt.Back`, `vt.Call["x"]`, `vt.Done`, `vt.Open`,
  `vt.Download`), plus the `Stay` every handler has because it may `raise vt.Reject(message)`.
  `await vt.invoke(handler, ctx, **documents)` calls one as `decide` will and returns the outcome
  record: the outcome's JSON, or `{"type": "reject", "message": ...}`; an outcome the return type
  does not declare raises `vt.UndeclaredOutcome`.

## The intent document

```text
format     "videotape.intent/2"
app, entry, world, hub
tapes      [{id, entry, frames: [{id, purpose, shows, edit, enter, submit, components, actions, ...}]}]
records    {Name: JSON Schema + x-vt}       references: #/records/Name, #/types/vt.Name
types      {vt.RichText: ..., vt.Image: ...}
handlers   {name: {...}}    loaders {name: {...}}
edges      [{from, to, type, tape | frame, via}]
```

- A frame's `id` is its `id=`, or one derived from its purpose (`"sign-in"`, marked
  `derived_id`); graph nodes are `tape/id`.
- Components: what the frame adds (`vt.text`, and `vt.show` of a field no record derives) comes
  first, in the order written; then the fields of the record it shows, then of the record it
  edits. Records nest (`components`), and so do collections (`item.components`). Each component
  has `affordances` from the closed set of 05 §6.4, derived from its type and whether the frame
  shows or edits it. `vt.show(ref, ...)` overrides every derived component for that field.
- `State` fields are not components; they are listed as `states` where they occur.
- Edges come from static outcomes (actions, `select=`, `press=`, `pick`, timers) and, from
  milestone 3, from handlers' return types. A hub's edges are not listed: `hub` implies an edge
  from every frame to every destination.

## Readings of the design

Where 05 or 06 leave a choice open, the SDK reads them like this:

- Every record has `id: str | None` (05 §6.2: documents are keyed by type and id; 06 builds
  `Workspace(id=...)` without declaring it). A record that is something's identity declares
  `id: str` itself.
- A field typed `X | None` is not required, also without a default (06 §4: "`| None`: required or
  optional"). Pydantic v2 would make it required, so the record's metaclass adds `None` as the
  default before Pydantic reads the class.
- `vt.Money` is an amount with a currency (`vt.Money("12.50", "EUR")`, or
  `{"amount": "12.50", "currency": "EUR"}` in JSON). It compares with numbers by amount, which
  is what makes `vt.Field(ge=0)` work.
- `vt.Secret` is a `str` with a masked repr, so `auth.login(c.username, c.password)` works as 06
  writes it and the value stays out of logs.
- `vt.RichText` is the closed model of 05 §6.1 (paragraphs, emphasis, links, lists, code,
  mentions). A plain `str` becomes paragraphs; `from_markdown` reads the part of Markdown the
  model can hold.

## Deviations from 05 and 06

- **A field's `pages=` loader must be defined before the record that names it.** 06 §5.5 shows
  `Feed` before `feed_page`; Python evaluates `vt.Field(pages=feed_page)` when the class body
  runs, so the order cannot work.
- **`vt.Text` needs `lines=`.** `vt.Text(lines=(1, 6))` returns `Annotated[str, ...]`; a bare
  `vt.Text` is a function, not a type.
- **`submit=` also takes `vt.action(label, handler)`** when the primary action's label is not the
  purpose. 06 §8.1 presses "Send" on the frame whose purpose is "Read and reply" (§9.4) without
  saying where "Send" comes from.
- **`vt.show` takes events as `on_<event>=`** (`on_ended=`, as 06 §9.2 writes, and `on_play=`,
  `on_progress=`, `on_error=`, `on_change=`), the media surface's events of 05 §11.
