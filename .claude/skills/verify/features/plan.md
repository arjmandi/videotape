# Plan

`videotape plan`, run in an app's project, walks every state the app can reach, breadth first from the first scene, before anything renders. It prints one line with the app's title, its version and its counts, then a table with each scene's states and the moves out of them, then `0 errors, N warnings`, then the estimate for the project's model: its name, the shots, the calls from one take each up to `takes` in `[tool.videotape]` (4 unless set), and their price, `free` for a model that bills per call nothing, or a range at the model's price per second, one price when `takes` is 1. A state is a scene with its arguments. A render draws one key for each state and one move for each action, so the shots are the states plus the moves. With `--story <name>` it checks that story as well, and the first line names the story and its version after the app's. With `--model <name>` it checks the story's prompts against that model's limit and not the project's model's, and the estimate is that model's. A project that names no model gets no estimate line. The plan writes no file.

## Sub-features

- `plan-contrail` prints Contrail's 11 scenes, 58 states, 58 keys, 102 moves and 160 shots, then the stand-in's estimate, and exits 0.
- `plan-story` prints the same table for each of Contrail's stories, under a first line that names the story, with `0 errors, 0 warnings` against every model, and each model's estimate.
- `plan-readme` prints the same through the README's own command, `uv run videotape plan` in `examples/contrail`.
- `plan-subfolder` finds the project from a folder inside it and prints the same.
- `plan-types` checks the example in pyright's strict mode with `uv run pyright contrail`, with 0 errors.
- `plan-cafe` prints the cafe fixture's 3 scenes, 5 states and 6 moves in its story, `chalk`.
- `plan-warning` prints each `VT211` warning to stderr, still prints the table, and exits 0.

## How to get to it (user POV)

- In `examples/contrail`, run `uv run videotape plan`, or `uv run videotape plan --story terminal` to check a story too.
- In any project, or a folder inside one, run `videotape plan`, with `--story <name>` to check a story too.
- In `examples/contrail`, run `uv run pyright contrail` to type-check the screenplay against videotape's types.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.

- **Contrail.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" plan-contrail examples/contrail -- plan`. `$RUN/plan-contrail.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:
  ```
  Contrail 0.1.0: 11 scenes, 58 states, 58 keys, 102 moves, 160 shots

  scene        states   moves out
  home              1           4
  search            1           7
  not_found         1           1
  no_flights        3           3
  dates             3           9
  results           9          36
  flight           18          18
  booked           18          18
  my_trips          1           4
  trip              2           0
  profile           1           2

  0 errors, 0 warnings
  stand-in: 160 shots, 160 to 640 calls, free
  ```
- **Story.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" plan-story examples/contrail -- plan --story terminal`. `.exit` is `0`, `.stderr` is empty, the first `.stdout` line is `Contrail 0.1.0 + terminal 1.0.0: 11 scenes, 58 states, 58 keys, 102 moves, 160 shots`, and every other line is as in `plan-contrail`, ending `0 errors, 0 warnings` and `stand-in: 160 shots, 160 to 640 calls, free`. With `--story posters` the first line is `Contrail 0.1.0 + posters 1.0.0: 11 scenes, 58 states, 58 keys, 102 moves, 160 shots`. Each story also prints `0 errors, 0 warnings` with `--model wan2.2-5b` added, then `wan2.2-5b: 160 shots, 160 to 640 calls, free`, and with `--model wan3.0`, then `wan3.0: 160 shots, 160 to 640 calls, $80.00 to $320.00 at $0.10/s`. With `--model wan3.0` and no `--story`, `.exit` is `1` and `.stderr` is `error: --model sets the prompt limit for a story's prompts, so pass --story with it`.
- **README command.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" plan-readme -C examples/contrail -- uv run videotape plan`. `.exit` is `0`, and `cmp "$RUN/plan-contrail.stdout" "$RUN/plan-readme.stdout"` prints nothing.
- **Subfolder.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" plan-subfolder examples/contrail/data -- plan`. `.exit` is `0`, and `cmp "$RUN/plan-contrail.stdout" "$RUN/plan-subfolder.stdout"` prints nothing.
- **Types.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" plan-types -C examples/contrail -- uv run pyright contrail`. `.exit` is `0` and the last `.stdout` line is `0 errors, 0 warnings, 0 informations`. pyright's wrapper prints a line above it when PyPI has a newer pyright. `examples/contrail/pyproject.toml` sets `typeCheckingMode = "strict"` under `[tool.pyright]`, so this is the strict check.
- **Cafe.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" plan-cafe tests/fixtures/cafe -- plan --story chalk`. `.exit` is `0` and `.stdout` is exactly:
  ```
  Corner Cafe 0.3.0 + chalk 1.0.0: 3 scenes, 5 states, 5 keys, 6 moves, 11 shots

  scene        states   moves out
  menu              1           2
  order             2           2
  thanks            2           2

  0 errors, 0 warnings
  stand-in: 11 shots, 11 to 44 calls, free
  ```
- **Warning.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" plan-warning tests/fixtures/errors/vt211 -- plan`. `.exit` is `0`, the first `.stdout` line is `Cafe 0.1.0: 1 scene, 1 state, 1 key, 0 moves, 1 shot`, the last is `0 errors, 2 warnings` (the fixture names no model, so there is no estimate line), and `.stderr` is exactly:
  ```
  warning VT211 home(): the line "Café Lumière" has the characters è é
  fix: write it with plain ASCII letters, digits, spaces, and . , ' ? ! $ % ( ) : -
  warning VT211 home(): the line "We open every single day of the week at seven in the morning sharp." has 14 words
  fix: shorten it to 12 words or fewer
  ```
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` lines, and the empty `cmp` for `plan-readme` and `plan-subfolder`.

## Gotchas

- pyright 1.1.414 has no `--strict` option, so `uv run pyright --strict contrail` prints `Unexpected option --strict.` and exits 4. Drive `uv run pyright contrail`, which is strict because of the project's `[tool.pyright]` table.
- Contrail's numbers come from `examples/contrail/data/*.json`. A change to the data changes them. `uv run pytest tests/test_contrail.py` counts the same numbers from the JSON files without the plan.
- `vt-verify run` uses the repo's `.venv`. The README's commands use `uv run`, which uses `examples/contrail/.venv`. Both install the same source in editable mode, so they print the same.
- When the plan finds an error it prints nothing to stdout and exits 1. [errors.md](./errors.md) covers each one.
- A state's name appears in a render's shot lines, in `videotape shots` and in `tape.json`, not in the plan's table. It reads as the call that names the state, so the state of a scene without arguments is `home()`. [render.md](./render.md) and [stories.md](./stories.md) show them.
- A plan without `--story` checks no story, so a broken story passes it. `render` and `shots` always check theirs first.
- The plan reads a model's prompt limit and its price without building the model, so `--model wan2.2-5b` needs neither the wan extra nor a GPU, and `--model wan3.0`, `--model minimax-h3` and `--model gemini-omni-flash-1.2` need no `FAL_KEY`.
- The estimate's calls are the shots times one to `takes`, since a shot stops at the first take that passes. `wan2.2-5b` reads `free` because its calls cost nothing per call; the GPU it needs is billed by the hour through `scripts/runpod-render`, whose pod lines the ledger holds.
- `takes = 2` in `[tool.videotape]` changes the estimate to `160 to 320 calls`. `--takes` is a render flag, not a plan flag.
