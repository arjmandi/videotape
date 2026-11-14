# Errors

Every logical error in a screenplay or its data prints a code, a place and a fix. `videotape plan` prints `error <code> <place>: <message>` and `fix: <what to do>` to stderr, prints nothing to stdout, and exits 1. The place is a file and line, or a state. `videotape render` stops on the same error before it draws anything. `videotape explain <code>` prints the code's long form with an example and its fix. `VT211` is a warning, and the plan goes on. A folder that is no project gets a plain `error:` line.

## Sub-features

- `errors-vt201` rejects a screenplay with no scenes.
- `errors-vt202` rejects a `to=` that holds the scene itself and not a state.
- `errors-vt203` reports a scene that raised, with the state and the line.
- `errors-vt204` rejects a scene that no action reaches.
- `errors-vt205` rejects a data file that is missing.
- `errors-vt206` rejects a record with a value of the wrong type, naming the file, the record's position and the field.
- `errors-vt207` rejects a query that names a field its records lack, and lists the fields they have.
- `errors-vt208` rejects a `get()` that matched no row.
- `errors-vt209` rejects two actions in one state with one label.
- `errors-vt210` stops a plan that reaches more states than `max_states`.
- `errors-render` stops a render on the same error, with no `tape/` and no `ledger.jsonl` written.
- `errors-explain` prints a code's long form, and rejects a code that does not exist.
- `errors-no-project` rejects a folder whose `pyproject.toml` has no `[tool.videotape]` table.

## How to get to it (user POV)

- Run `videotape plan` in a project with one of the mistakes above. Each has a fixture project under `tests/fixtures/errors/`.
- Run `videotape explain VT207` anywhere.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- The fixtures named below are unchanged from git.

- **Each code.** For each code, run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-<code> tests/fixtures/errors/<code> -- plan` with the code in lower case, such as `vt201`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is exactly these two lines:

  | Fixture | `.stderr` |
  | --- | --- |
  | `vt201` | `error VT201 app.py:3: the screenplay has no scenes`<br>`fix: add a scene with @app.scene; the first one is where the app opens` |
  | `vt202` | `error VT202 app.py:8: the to= of Button "Open" is the scene detail itself, not a state, in state home()`<br>`fix: call the scene to name a state, as in detail()` |
  | `vt203` | `error VT203 app.py:13: the scene raised ZeroDivisionError: integer division or modulo by zero, in state split(0)`<br>`fix: make the scene build for these arguments, or keep this state out of every to=` |
  | `vt204` | `error VT204 app.py:11: no action reaches the scene help`<br>`fix: lead to it from a scene that is reached, as in to=help(), or delete it` |
  | `vt205` | `error VT205 app.py:9: no data file at drinks.json`<br>`fix: create it, or correct the path; "drinks.json" is relative to the folder of pyproject.toml` |
  | `vt206` | `error VT206 drinks.json:3: record 2 field "price" is "six", not a whole number`<br>`fix: write a whole number` |
  | `vt207` | `error VT207 app.py:15: Drink has no field "cost", in state home()`<br>`fix: name one of its fields: name, price` |
  | `vt208` | `error VT208 app.py:15: get(name='Mocha') matched no Drink from drinks.json, in state home()`<br>`fix: ask for a row the data holds, or count the matches with where(...).count()` |
  | `vt209` | `error VT209 home(): two actions have the label "Open"`<br>`fix: give each action its own label` |
  | `vt210` | `error VT210 count(5): the plan reached more than 5 states`<br>`fix: take a scene's arguments from the data, which ends, or raise max_states in [tool.videotape]` |
- **Render.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-render tests/fixtures/errors/vt204 -- render --model stand-in`. `.exit` is `1`, `.stdout` is empty, `.stderr` is the two `vt204` lines above, and `command ls tests/fixtures/errors/vt204` lists only `app.py` and `pyproject.toml`.
- **Explain.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-explain . -- explain VT207`. `.exit` is `0` and `.stdout` is exactly:
  ```
  VT207: a query names a field its records don't have

  where, order_by, get, distinct, min, and sum take the names of a record's fields, and so does key=. This name is not one of them. The error lists the fields the records do have.

  Example:
      flights.where(dest="SEA")

  Fix:
      flights.where(destination="SEA")
  ```
  With `explain VT999` instead, `.exit` is `2` and `.stderr` ends with `videotape explain: error: argument code: invalid choice: 'VT999' (choose from VT201, VT202, VT203, VT204, VT205, VT206, VT207, VT208, VT209, VT210, VT211)`.
- **No project.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-no-project . -- plan`, which runs in the repo root. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: pyproject.toml has no [tool.videotape] table; add one with screenplay = "module:app"`.
- **Proof.** For each journey cite `.cmd`, `.exit` and `.stderr`. `uv run pytest tests/test_errors.py tests/test_data.py` proves the rest: every code has an `explain` entry, and `VT206` names a missing field, an unknown field, each wrong type and a repeated key.

## Gotchas

- Exit code `2` with a `usage:` line means the arguments were wrong, not that the screenplay was rejected. Recheck the command.
- A place is relative to the working directory, which is the project, so `app.py:8` and `drinks.json:3` name files in the fixture.
- The plan stops at the first error it meets, in walk order. A state that cannot be built hides its actions, so nothing after it could be trusted.
- `VT203`'s message quotes Python's own exception text. Python 3.12, which `.python-version` pins and `vt-verify run` uses, says `integer division or modulo by zero`. Python 3.14 says `division by zero`, so `tests/test_errors.py` takes the text from the Python it runs on.
- The `vt210` fixture sets `max_states = 5` in its `pyproject.toml`. Without that line the limit is 500.
- `vt-verify run` sets `PYTHONDONTWRITEBYTECODE=1`, so a drive leaves no `__pycache__` in a fixture. A fixture declares no dependencies, so `uv run videotape plan` typed by hand in one fails with ``error: Failed to spawn: `videotape` `` and leaves a `.venv` and a `uv.lock` there. Use `vt-verify run`.
