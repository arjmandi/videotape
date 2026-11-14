# Errors

Every logical error in a screenplay, its data or a story prints a code, a place and a fix. `videotape plan` prints `error <code> <place>: <message>` and `fix: <what to do>` to stderr, prints nothing to stdout, and exits 1. The place is a file and line, a file, a state or a shot. `VT201` to `VT211` are a screenplay's and its data's. `VT301` to `VT307` are a story's, which `videotape plan --story <name>` checks. There is no `VT305`. `videotape render` stops on the same error before it draws anything, and `videotape shots` before it prints a prompt. `videotape explain <code>` prints the code's long form with an example and its fix. `VT211`, `VT304` and `VT307` are warnings, and the plan goes on. A folder that is no project gets a plain `error:` line.

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
- `errors-vt301` rejects a story with no version or no look.
- `errors-vt302` rejects a story that directs a scene the screenplay doesn't have, naming the line and the closest real scene.
- `errors-vt303` rejects a story that names an element type the screenplay doesn't use, naming the line and the closest real type.
- `errors-vt304` warns that a scene has no direction, so its keys get only the look.
- `errors-vt306` rejects a story that is not TOML, naming the line.
- `errors-vt307` warns that a prompt is longer than the model takes.
- `errors-render` stops a render on the same error, with no `tapes/` and no `ledger.jsonl` written.
- `errors-explain` prints a code's long form, and rejects a code that does not exist.
- `errors-no-project` rejects a folder whose `pyproject.toml` has no `[tool.videotape]` table.

## How to get to it (user POV)

- Run `videotape plan` in a project with one of a screenplay's mistakes above, or `videotape plan --story <name>` with one of a story's. Each has a fixture project under `tests/fixtures/errors/`.
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
- **Each story code.** For `vt301`, `vt302`, `vt303` and `vt306`, run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-<code> tests/fixtures/errors/<code> -- plan --story neon`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is exactly these two lines:

  | Fixture | `.stderr` |
  | --- | --- |
  | `vt301` | `error VT301 stories/neon.toml: the story has no look`<br>`fix: write look = "...", the look of the whole app in a sentence or two, above the first [heading]` |
  | `vt302` | `error VT302 stories/neon.toml:6: the story directs the scene detial, and the screenplay has no scene of that name`<br>`fix: write detail, the closest of the screenplay's scenes` |
  | `vt303` | `error VT303 stories/neon.toml:10: the story gives an appearance to the element type Buton, which the screenplay does not use`<br>`fix: write Button, the closest of the screenplay's element types` |
  | `vt306` | `error VT306 stories/neon.toml:2: the story is not TOML: Invalid value`<br>`fix: write each line as name = "words", under [scenes], [elements] or [moves], or above all three` |
- **Story warnings.** Run the same for `vt304` and `vt307`. `.exit` is `0`, the last `.stdout` line is `0 errors, 1 warning`, and `.stderr` is exactly these two lines:

  | Fixture | First `.stdout` line | `.stderr` |
  | --- | --- | --- |
  | `vt304` | `Shop 0.1.0 + neon 1.0.0: 2 scenes, 2 states, 2 keys, 1 move, 3 shots` | `warning VT304 stories/neon.toml: the scene detail has no direction, so its keys get only the look`<br>`fix: add detail = "..." under [scenes]` |
  | `vt307` | `Shop 0.1.0 + neon 1.0.0: 1 scene, 1 state, 1 key, 0 moves, 1 shot` | `warning VT307 key home(): the prompt is about 778 tokens long, and wan2.2-5b takes no more than 512`<br>`fix: shorten the look, the scene's direction or the appearances in stories/neon.toml, or show fewer lines in this state` |

  With `-- plan --story neon --model stand-in` in `vt307`, `.stderr` is empty and the last line is `0 errors, 0 warnings`, and the same with `--model wan3.0`.
- **Render.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-render tests/fixtures/errors/vt204 -- render --story neon --model stand-in`. `.exit` is `1`, `.stdout` is empty, `.stderr` is the two `vt204` lines above, and `command ls tests/fixtures/errors/vt204` lists only `app.py` and `pyproject.toml`. The screenplay's error comes before the story is looked for, so it does not matter that `vt204` has no story. Run the same in `tests/fixtures/errors/vt302` as `errors-render-story`. `.stderr` is the two `vt302` lines, and `command ls tests/fixtures/errors/vt302` lists only `app.py`, `pyproject.toml` and `stories`.
- **Explain.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-explain . -- explain VT207`. `.exit` is `0` and `.stdout` is exactly:
  ```
  VT207: a query names a field its records don't have

  where, order_by, get, distinct, min, and sum take the names of a record's fields, and so does key=. This name is not one of them. The error lists the fields the records do have.

  Example:
      flights.where(dest="SEA")

  Fix:
      flights.where(destination="SEA")
  ```
  With `explain VT303` instead, `.stdout` starts `VT303: a story names an element type the screenplay doesn't use` and its `Fix:` is `[elements]` over `Button = "a lit amber panel with bold black letters"`. With `explain VT305`, a code that does not exist, `.exit` is `2` and `.stderr` ends with `videotape explain: error: argument code: invalid choice: 'VT305' (choose from VT201, VT202, VT203, VT204, VT205, VT206, VT207, VT208, VT209, VT210, VT211, VT301, VT302, VT303, VT304, VT306, VT307)`.
- **No project.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-no-project . -- plan`, which runs in the repo root. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: pyproject.toml has no [tool.videotape] table; add one with screenplay = "module:app"`.
- **Proof.** For each journey cite `.cmd`, `.exit` and `.stderr`. `uv run pytest tests/test_errors.py tests/test_data.py tests/test_story.py` proves the rest: every code has an `explain` entry and a fixture, `VT206` names a missing field, an unknown field, each wrong type and a repeated key, and `VT301` names a version that is not in quotes.

## Gotchas

- Exit code `2` with a `usage:` line means the arguments were wrong, not that the screenplay was rejected. Recheck the command.
- A place is relative to the working directory, which is the project, so `app.py:8` and `drinks.json:3` name files in the fixture.
- The plan stops at the first error it meets, in walk order. A state that cannot be built hides its actions, so nothing after it could be trusted. A story is checked after the screenplay, so a story's error shows only once the screenplay plans.
- A story's place is its file from the project, with the line of the key when the key is written under its `[scenes]`, `[elements]` or `[moves]` heading. `VT301` names only the file, since what it reports is missing. `VT304` names only the file too.
- `VT306`'s message quotes Python's TOML reader. Python 3.12 and 3.14 both say `Invalid value` for words without quotes.
- `VT307` in the `vt307` fixture comes from its own `model = "wan2.2-5b"` in `[tool.videotape]`. The plan counts tokens without a tokenizer and counts high. umT5's own tokenizer makes 641 tokens of that prompt, which is also over 512.
- A `vt3xx` fixture's story is named `neon`. With another name the plan stops with `error: no story "<name>" in stories; the stories are neon`.
- `VT203`'s message quotes Python's own exception text. Python 3.12, which `.python-version` pins and `vt-verify run` uses, says `integer division or modulo by zero`. Python 3.14 says `division by zero`, so `tests/test_errors.py` takes the text from the Python it runs on.
- The `vt210` fixture sets `max_states = 5` in its `pyproject.toml`. Without that line the limit is 500.
- `vt-verify run` sets `PYTHONDONTWRITEBYTECODE=1`, so a drive leaves no `__pycache__` in a fixture. A fixture declares no dependencies, so `uv run videotape plan` typed by hand in one fails with ``error: Failed to spawn: `videotape` `` and leaves a `.venv` and a `uv.lock` there. Use `vt-verify run`.
