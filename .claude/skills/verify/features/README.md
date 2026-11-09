# videotape verification map

This directory is the maintained source for verifying what a videotape user can observe. The user is an app developer who writes `screenplay.py`, runs `videotape shots <dir>` to list its shots, and runs `videotape render <dir> --model stand-in` to render them into a tape. TapePlayer's user is the person who then clicks through that tape on a Mac. Read this index before driving, then use the matching feature file as the recipe.

## Baseline preconditions

- `.claude/skills/verify/scripts/vt-verify launch` has printed `ready:` in this checkout.
- `.claude/skills/verify/scripts/vt-verify doctor` exits 0 with only `ok` and `info` lines.
- `RUN=.verify/runs/<UTC timestamp>` is set once for the session.
- `examples/surf_shop/screenplay.py` is unchanged from git, unless the change under test edits it.

## Driving conventions

- Every CLI drive goes through `vt-verify run "$RUN" <name> -- shots <dir>` or `vt-verify run "$RUN" <name> -- render <dir> --model stand-in`. Use the journey's name as `<name>` so artifacts map to journeys.
- TapePlayer drives go through `vt-verify player-build "$RUN"` and `vt-verify player-test "$RUN"`, or through a person at the screen, as [player.md](./player.md) says.
- Treat every command and quoted string as literal.
- Assert on exact lines from `$RUN/<name>.stdout`, `$RUN/<name>.stderr` and `$RUN/<name>.exit`.
- Fixtures live in `.claude/skills/verify/fixtures/`. Never edit one to make a journey pass.

## Proof and skip reporting

- CLI proof is the command, the asserted stdout or stderr lines, and the exit code, all read from `$RUN`.
- TapePlayer proof is the same files for `player-build` and `player-test`, plus the screenshot `player-test` exports, or what the user reported for a journey a person drives.
- Name the feature ID with every artifact you cite.
- Report a journey you could not run with the attempted command and the unmet precondition.
- Do not report a journey as verified through a different screenplay than the one its file names.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with vt-verify` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, commands, required state, and observable proof.

## Features

- [Shot list](./shot-list.md) covers the surf shop's six shots: order, modes, and exact prompts.
- [Authoring a screenplay](./authoring.md) covers what a developer's own screenplay controls: custom moves, plain-name actions, scenes without text or buttons, and a return to an already-keyed scene.
- [Screenplay errors](./screenplay-errors.md) covers each mistake the CLI rejects with `error:` and exit 1.
- [Render](./render.md) covers rendering the surf shop into a tape: the first render, the cached rerun, the cascade after editing one line, the files in `tape/`, and the dailies page.
- [Player](./player.md) covers the TapePlayer macOS app: building it, clicking through the surf shop tape, hotspots, Start Over, File > Open, a bad tape, and the window's shape.
