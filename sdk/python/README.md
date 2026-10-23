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
