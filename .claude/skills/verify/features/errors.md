# Errors

Every mistake in a screenplay, its data or a story, and everything that goes wrong in a render or a check, has a code. `videotape plan` prints `error <code> <place>: <message>` and `fix: <what to do>` to stderr, prints nothing to stdout, and exits 1. The place is a file and line, a file, a state or a shot. `VT201` to `VT211` are a screenplay's and its data's. `VT301` to `VT309` are a story's, which `videotape plan --story <name>` checks. There is no `VT305`. `videotape render` stops on the same error before it draws anything, and `videotape shots` before it prints a prompt. `VT401` to `VT404` are a render's: it prints `error <code> <place>: <message>` and `next: <what to run>`, where the place is the shot and its take, the shot alone when ffmpeg fails or every take is corrupt, or `before the first call`. `VT501`, `VT502`, `VT503` and `VT508` are a check's, which a render's `fail:` lines and the dailies name. `videotape explain <code>` prints the code's long form with an example and its fix or next step. `VT211`, `VT304` and `VT307` are warnings, and the plan goes on; `render` and `shots` print them too. A folder that is no project is `VT106`, and a wrong value in `[tool.videotape]` is `VT107`, both placed at the `pyproject.toml`.

## Sub-features

- `errors-vt201` rejects a screenplay with no scenes.
- `errors-vt202` rejects a `to=` that holds the scene itself and not a state.
- `errors-vt203` reports a scene that raised, with the state and the line.
- `errors-vt204` rejects a scene that no action reaches.
- `errors-vt205` rejects a data file that is missing, or a path outside `data/`.
- `errors-vt206` rejects a record with a value of the wrong type, naming the file, the record's position and the field.
- `errors-vt207` rejects a query that names a field its records lack, and lists the fields they have.
- `errors-vt208` rejects a `get()` that matched no row.
- `errors-vt209` rejects two actions in one state with one label.
- `errors-vt210` stops a plan that reaches more states than `max_states`.
- `errors-vt301` rejects a story with no version or no look.
- `errors-vt302` rejects a story that directs a scene the screenplay doesn't have, naming the line and the closest real scene.
- `errors-vt303` rejects a story that names an element type the screenplay doesn't use, naming the line and the closest real type.
- `errors-vt304` warns that a scene has no direction, so its keys get only the look.
- `errors-vt306` rejects a story that is not TOML, or a table entry that is not words, naming the line.
- `errors-vt307` warns that a prompt is longer than the model takes.
- `errors-vt308` rejects a story that quotes words, with a straight or a curly double quote, naming the line.
- `errors-vt309` rejects a `--story` with no file under `stories/`, listing the stories there.
- `errors-render` and `errors-checks` are the render's `VT401` to `VT404` and the checks' `VT501`, `VT502`, `VT503` and `VT508`, proven by `uv run pytest tests/test_render.py tests/test_resume.py tests/test_retake.py`.
- `errors-render` stops a render on the same error, with no `tapes/` and no `ledger.jsonl` written.
- `errors-explain` prints a code's long form, and rejects a code that does not exist.
- `errors-no-project` rejects a folder whose `pyproject.toml` has no `[tool.videotape]` table, with `VT106`.
- `errors-project-value` rejects a wrong value in `[tool.videotape]` with `VT107`: a screenplay that is not `module:app` or not a `vt.Screenplay`, a model videotape doesn't have, a `max_states` or `takes` that is not a whole number, a `cap_usd` that is not dollars, or a file that is not TOML, proven by `uv run pytest tests/test_errors.py -k wrong_value`.

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
  | `vt205` | `error VT205 app.py:9: no data file at data/drinks.json`<br>`fix: create it, or correct the path; "data/drinks.json" is relative to the folder of pyproject.toml` |
  | `vt206` | `error VT206 data/drinks.json:3: record 2 field "price" is "six", not a whole number`<br>`fix: write a whole number` |
  | `vt207` | `error VT207 app.py:15: Drink has no field "cost", in state home()`<br>`fix: name one of its fields: name, price` |
  | `vt208` | `error VT208 app.py:15: get(name='Mocha') matched no Drink from data/drinks.json, in state home()`<br>`fix: ask for a row the data holds, or count the matches with where(...).count()` |
  | `vt209` | `error VT209 home(): two actions have the label "Open"`<br>`fix: give each action its own label` |
  | `vt210` | `error VT210 count(5): the plan reached more than 5 states`<br>`fix: take a scene's arguments from the data, which ends, or raise max_states in [tool.videotape]` |
- **Each story code.** For `vt301`, `vt302`, `vt303`, `vt306`, `vt308` and `vt309`, run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-<code> tests/fixtures/errors/<code> -- plan --story neon`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is exactly these two lines:

  | Fixture | `.stderr` |
  | --- | --- |
  | `vt301` | `error VT301 stories/neon.toml: the story has no look`<br>`fix: write look = "...", the look of the whole app in a sentence or two, above the first [heading]` |
  | `vt302` | `error VT302 stories/neon.toml:6: the story directs the scene detial, and the screenplay has no scene of that name`<br>`fix: write detail, the closest of the screenplay's scenes` |
  | `vt303` | `error VT303 stories/neon.toml:10: the story gives an appearance to the element type Buton, which the screenplay does not use`<br>`fix: write Button, the closest of the screenplay's element types` |
  | `vt306` | `error VT306 stories/neon.toml:2: the story is not TOML: Invalid value`<br>`fix: write each line as name = "words", under [scenes], [elements] or [moves], or above all three` |
  | `vt308` | `error VT308 stories/neon.toml:5: home under [scenes] quotes '“Open”.'`<br>`fix: take the quotes out; the screenplay owns every word on screen, so describe their look` |
  | `vt309` | `error VT309 stories: no story "neon"`<br>`fix: name one of the stories there, glow` |

  `vt309`'s only story is `stories/glow.toml`, so `--story neon` names one it does not have. A project with no `stories/` folder at all says `fix: add stories/neon.toml` instead, as `tests/fixtures/errors/vt211` does with `-- shots --story neon`.
- **Story warnings.** Run the same for `vt304` and `vt307`. `.exit` is `0`, `.stdout` ends with `0 errors, 1 warning`, which in `vt307` is followed by the estimate for the model its project names, `wan2.2-5b: 1 shot, 1 to 4 calls, free`, and `.stderr` is exactly these two lines:

  | Fixture | First `.stdout` line | `.stderr` |
  | --- | --- | --- |
  | `vt304` | `Shop 0.1.0 + neon 1.0.0: 2 scenes, 2 states, 2 keys, 1 move, 3 shots` | `warning VT304 stories/neon.toml: the scene detail has no direction, so its keys get only the look`<br>`fix: add detail = "..." under [scenes]` |
  | `vt307` | `Shop 0.1.0 + neon 1.0.0: 1 scene, 1 state, 1 key, 0 moves, 1 shot` | `warning VT307 key home(): the prompt is about 778 tokens long, and wan2.2-5b takes no more than 512`<br>`fix: shorten the look, the scene's direction or the appearances in stories/neon.toml, or show fewer lines in this state` |

  With `-- plan --story neon --model stand-in` in `vt307`, `.stderr` is empty and the last two lines are `0 errors, 0 warnings` and `stand-in: 1 shot, 1 to 4 calls, free`. With `--model wan3.0` the last line is `wan3.0: 1 shot, 1 to 4 calls, $0.50 to $2.00 at $0.10/s`; the plan prices the calls without making one, so it needs no `FAL_KEY`.
- **Render.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-render tests/fixtures/errors/vt204 -- render --story neon --model stand-in`. `.exit` is `1`, `.stdout` is empty, `.stderr` is the two `vt204` lines above, and `command ls tests/fixtures/errors/vt204` lists only `app.py` and `pyproject.toml`. The screenplay's error comes before the story is looked for, so it does not matter that `vt204` has no story. Run the same in `tests/fixtures/errors/vt302` as `errors-render-story`. `.stderr` is the two `vt302` lines, and `command ls tests/fixtures/errors/vt302` lists only `app.py`, `pyproject.toml` and `stories`.
- **A path outside data/.** Write a scratch project `P="${TMPDIR:-/tmp}"/videotape-verify-outside` with `pyproject.toml` holding `[tool.videotape]` and `screenplay = "app:app"`, an `app.py` that defines `class Drink(vt.Record, key="name")` with `name: str` and `price: int`, then `drinks = vt.table(Drink, "drinks.json")` and a `home` scene, and a `drinks.json` beside it. Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-outside-data "$P" -- plan`. `.exit` is `1` and `.stderr` is `error VT205 app.py:<line>: "drinks.json" is not under data/` over `fix: keep every data file under data/ in the project, as in data/drinks.json`.
- **Render codes.** `uv run pytest tests/test_render.py -k "vt401 or vt403 or vt404 or corrupt" -v` proves `VT401` (a model call failed: the provider's message and request, never a key, then `next: run the render again, which resumes; a request that was submitted is polled, not submitted again:` and the command), `VT403` (a corrupt take: downloaded again for a model that bills per call, else `error VT403 <shot> take <seed>: <file> did not decode to one frame: <ffmpeg's words>` over `next: nothing; seed <seed> is skipped from now on`, and the seed in the record's `corrupt`) and `VT404` (`ffmpeg is not on PATH` over `next: install ffmpeg, as in brew install ffmpeg, and run the render again`). `uv run pytest tests/test_resume.py -v` proves `VT402`: a paid model with no cap stops before the first call with `error VT402 before the first call: <model> bills per call, and no cap is set`, and a render under a cap stops with `error VT402 <shot> take <seed>: the next call would pass the cap of $<cap>, with $<spent> spent on this tape and $<reserved> reserved for the calls in flight, at the listed price of $<price> a call`, then `next: run the render again with a higher cap, which resumes, as in:` and the command with `--cap-usd` at twice the cap. The tests that raise `VT402`, `VT403` and `VT404` also match what render printed against the code's `explain` example and next step, with the shot, paths, hashes, numbers, the story and ffmpeg's words left open, so the two cannot drift.
- **Check codes.** `VT501` is an action not found, `VT502` a word misread, `VT503` an invented control and `VT508` a seam over 0.05. [render.md](./render.md) drives `VT502`, `VT503` and `VT508` on the cafe with one take per shot. The stand-in finds every action, so `uv run pytest tests/test_render.py -k do_not_find` proves `VT501`. Each `fail:` line reads `fail: <n>. <shot>  <code> <about>: <evidence>` with `  next: videotape retake "<state>" --story <story>` under it.
- **Explain.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-explain . -- explain VT207`. `.exit` is `0` and `.stdout` is exactly:
  ```
  VT207: a query names a field its records don't have

  where, order_by, get, distinct, min, and sum take the names of a record's fields, and so does key=. This name is not one of them. The error lists the fields the records do have.

  Example:
      flights.where(dest="SEA")

  Fix:
      flights.where(destination="SEA")
  ```
  With `explain VT303` instead, `.stdout` starts `VT303: a story names an element type the screenplay doesn't use` and its `Fix:` is `[elements]` over `Button = "a lit amber panel with bold black letters"`. With `explain VT402`, `.stdout` starts `VT402: the next call would pass the cap` and its last section is headed `Next:`, as every `VT4xx` and `VT5xx` entry's is, since those name what to run next rather than what to write. With `explain VT305`, a code that does not exist, `.exit` is `2` and `.stderr` ends with `videotape explain: error: argument code: invalid choice: 'VT305' (choose from VT101, VT102, VT103, VT104, VT105, VT106, VT107, VT201, VT202, VT203, VT204, VT205, VT206, VT207, VT208, VT209, VT210, VT211, VT301, VT302, VT303, VT304, VT306, VT307, VT308, VT309, VT401, VT402, VT403, VT404, VT501, VT502, VT503, VT508, VT603)`. `VT1xx` and `VT6xx` entries end with `Fix:`, as the plan's do.
- **No project.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-no-project . -- plan`, which runs in the repo root. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error VT106 pyproject.toml: has no [tool.videotape] table` over `fix: add one that names the screenplay, its module and the name of its vt.Screenplay: [tool.videotape] screenplay = "shop:app"`.
- **Proof.** For each journey cite `.cmd`, `.exit` and `.stderr`. `uv run pytest tests/test_errors.py tests/test_data.py tests/test_story.py` proves the rest: every code has an `explain` entry, every code a plan can raise has a fixture, `VT206` names a missing field, an unknown field, each wrong type and a repeated key, `VT301` names a version that is not in quotes, `VT306` names a table entry that is not words, and `VT308` finds a straight quote escaped in TOML, one in a literal string, and a curly one in a multi-line look.

## Gotchas

- Exit code `2` with a `usage:` line means the arguments were wrong, not that the screenplay was rejected. Recheck the command.
- A place is relative to the working directory, which is the project, so `app.py:8` and `data/drinks.json:3` name files in the fixture.
- The plan stops at the first error it meets, in walk order. A state that cannot be built hides its actions, so nothing after it could be trusted. A story is checked after the screenplay, so a story's error shows only once the screenplay plans.
- A story's place is its file from the project, with the line of the key when the key is written under its `[scenes]`, `[elements]` or `[moves]` heading. `VT301` names only the file, since what it reports is missing. `VT304` names only the file too.
- `VT306`'s message quotes Python's TOML reader. Python 3.12 and 3.14 both say `Invalid value` for words without quotes. A quote that never closes is found at the end of the file, and the error names the file's last line.
- `VT307` in the `vt307` fixture comes from its own `model = "wan2.2-5b"` in `[tool.videotape]`. The plan counts tokens without a tokenizer and counts high. umT5's own tokenizer makes 641 tokens of that prompt, which is also over 512.
- A `vt3xx` fixture's story is named `neon`, except `vt309`'s, which is `glow` so that `--story neon` is `VT309`. With another name the plan stops with `error VT309 stories: no story "<name>"` and `fix: name one of the stories there, neon`.
- `VT308` names the line by the words beside the quote, since a straight quote is escaped in the file. A story whose only quote sits alone in a value names the file without a line.
- A render's `VT403` is reported and the render goes on with the shot's next seed. When every take of the shot is corrupt, it stops the render with `error VT403 <shot>: every take of the shot is corrupt` and a next step that raises the takes or retakes the state. `VT401`, `VT402` and `VT404` stop it. The takes already filmed stay on disk and in the ledger, the record says `"complete": false`, and the next render resumes from them. A `VT401` on a request fal recorded beside its take, as `tests/test_wan3.py -k fails_for_good` drives, names that record in its next step, since only deleting it lets the render submit a new, paid take.
- `VT203`'s message quotes Python's own exception text. Python 3.12, which `.python-version` pins and `vt-verify run` uses, says `integer division or modulo by zero`. Python 3.14 says `division by zero`, so `tests/test_errors.py` takes the text from the Python it runs on.
- The `vt210` fixture sets `max_states = 5` in its `pyproject.toml`. Without that line the limit is 500.
- `vt-verify run` sets `PYTHONDONTWRITEBYTECODE=1`, so a drive leaves no `__pycache__` in a fixture. A fixture declares no dependencies, so `uv run videotape plan` typed by hand in one fails with ``error: Failed to spawn: `videotape` `` and leaves a `.venv` and a `uv.lock` there. Use `vt-verify run`.
