# videotape verification map

This directory is the maintained source for verifying what a videotape user can observe. The user is an app developer who writes a screenplay and its data in a project, and the app's looks as stories under `stories/`. They run `videotape plan` there to walk the app's states, `videotape shots --story <name>` to read the prompts, and `videotape render --story <name>` to draw the app in that story into a tape. TapePlayer's user is the person who then clicks through that tape on a Mac. Read this index before driving, then use the matching feature file as the recipe.

## Baseline preconditions

- `.claude/skills/verify/scripts/vt-verify launch` has printed `ready:` in this checkout.
- `.claude/skills/verify/scripts/vt-verify doctor` exits 0 with only `ok` and `info` lines.
- `RUN=.verify/runs/<UTC timestamp>` is set once for the session.
- `git diff --quiet -- examples/contrail tests/fixtures` exits 0, unless the change under test edits them.

## Driving conventions

- Every CLI drive goes through `vt-verify run "$RUN" <name> <project-dir> -- <videotape args>`, which runs the command inside the project. Use the journey's name as `<name>` so artifacts map to journeys.
- The README's commands in `examples/contrail`, and the scripts under `scripts/`, go through `vt-verify exec "$RUN" <name> [-C <dir>] -- <command>`.
- TapePlayer drives go through `vt-verify player-build "$RUN"`, `vt-verify player-press "$RUN" <tape-dir> <label>...`, `vt-verify player-test "$RUN"` and `vt-verify player-cuts "$RUN"`, or through a person at the screen, as [player.md](./player.md) says.
- Treat every command and quoted string as literal.
- Assert on exact lines from `$RUN/<name>.stdout`, `$RUN/<name>.stderr` and `$RUN/<name>.exit`.
- Fixtures live in `tests/fixtures/`, where the test suite uses them too. Never edit one to make a journey pass.

## Proof and skip reporting

- CLI proof is the command, the asserted stdout or stderr lines, and the exit code, all read from `$RUN`.
- TapePlayer proof is the same files for `player-build`, `player-press`, `player-test` and `player-cuts`, plus the screenshot `player-test` exports, or what the user reported for a journey a person drives.
- Name the feature ID with every artifact you cite.
- Report a journey you could not run with the attempted command and the unmet precondition.
- Do not report a journey as verified through a different project than the one its file names.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with vt-verify` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, commands, required state, and observable proof.

## Features

- [Plan](./plan.md) covers `videotape plan` on Contrail: its 11 scenes, 58 states and 102 moves, the same with `--story`, through `uv run` and from a subfolder, the strict type check of the example, the cafe fixture, and a warning.
- [Stories](./stories.md) covers an app's looks: the story file, `videotape shots` and the source of every clause of a prompt, `--state`, a story or a state the project does not have, the `made` block and label in `tape.json`, `videotape diff`, and what a change to a story or the data renders again.
- [Errors](./errors.md) covers each logical error the plan rejects, `VT201` to `VT210` in a screenplay or its data and `VT301` to `VT306` in a story, with its code, place and fix, the warnings `VT211`, `VT304` and `VT307`, `videotape explain`, and a folder that is not a project.
- [Render](./render.md) covers rendering Contrail in a story with the stand-in: the first render of 58 keys then 102 moves, the cached rerun, the files in `tapes/<story>/`, the ledger in the project, and the dailies page. The cafe fixture covers the cascade after an edit, one take per shot, another tape with `--out`, and an unknown model.
- [Player](./player.md) covers the TapePlayer macOS app: building it, booking a flight through each Contrail tape with and without a window, cuts between clips, hotspots, Start Over, File > Open, a bad tape, and the window's shape.
- [GPU render](./gpu-render.md) covers rendering with Wan 2.2 on a rented Runpod GPU through `scripts/runpod-render --story <name>`, run inside the project: the dry run, the refusals, the local `--model wan2.2-5b` errors, the paid runs behind the user's cap, `--out`, and the ledger.
- [Wan 3.0 render](./wan3-render.md) covers rendering with Wan 3.0 on fal into another tape of the project: the missing-key error, the requests and answers the tests prove, the paid run behind the user's cap, the price line, the cached rerun, and the ledger.
- [Reader test](./reader-test.md) covers `scripts/reader-test`: the missing-key error, the requests and answers the tests prove, and the paid run behind the user's cap.
