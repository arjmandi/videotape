---
name: verify
description: Drive the videotape CLI in an app's project (`videotape new <name>`, `videotape doctor`, `videotape plan [--story <name>]`, `videotape shots --story <name> [--state <state>]`, `videotape explain <code>`, `videotape render --story <name> [--model <name>] [--takes N] [--cap-usd N] [--out <tape>]`, `videotape retake "<state>" --story <name> [--takes N]`, `videotape accept "<state>" <code> --story <name> --reason "<why>"`, `videotape dailies --story <name>`, `videotape play --story <name>`, `videotape publish --story <name>` and `videotape diff <tape> <tape>`) the way an app developer does, and build and test the TapePlayer macOS app that plays a rendered tape. Capture the command, stdout, stderr, exit code and rendered tape as proof. Use after any change to the videotape package, the CLI, a screenplay, its data or its stories under examples/, scripts/, or clients/macos/, before claiming a new project and doctor's checks, the plan and its estimate, the prompts and their sources, the error codes, the rendered tape and dailies, the cap and the resume, a retake or an accept, what made a tape, the checks, the Wan renders, the reader test, the developer's guide in README.md and its words test, a published app and videotape.lock, or TapePlayer behave.
---

# Verify videotape

videotape lets a developer write an app as a screenplay: typed records, scenes that are functions of their arguments, and a closed set of elements. The screenplay holds the app's words and nothing of its looks. A story holds the looks: one TOML file under `stories/` in the project, named by its file. An app lives in a project, the folder whose `pyproject.toml` names the screenplay in `[tool.videotape]`. Every command but `new`, `doctor`, `explain` and `diff` runs inside the project and finds it from the working directory upward, so no command takes a folder.

- `videotape new <name>` writes a project to start from into a new or empty folder `<name>/`: a `pyproject.toml` that depends on videotape from where it was installed, a screenplay of two scenes over a table of three steps, `stories/starter.toml`, `.env.example` and `.gitignore`. The starter renders clean with the stand-in; see [features/project.md](features/project.md).
- `videotape doctor` prints one line per check, `ok   VT10x <what>`, or `fail VT10x <what>` over `  fix: <fix>`, and exits 1 when one fails: the Python, ffmpeg and ffprobe, and Xcode for TapePlayer, and in a project the API key its model needs and the GPU its checks need. It is not `vt-verify doctor`, which checks this checkout.
- `videotape plan` walks every state the app can reach and prints each scene's states and moves, then the estimate for the project's model: the shots, the calls from one take each up to the limit, and their price. `--story <name>` also checks that story, and `--model <name>` checks its prompts against that model's limit.
- `videotape shots --story <name>` prints every shot's prompt, one clause to a line with the clause's source beside it. `--state <state>` prints one state's key and the moves that leave it. `render` and `shots` print the story check's warnings to stderr, as `plan` does.
- `videotape explain <code>` prints the long form of a code: `VT101` to `VT105` for doctor's checks, `VT106` and `VT107` for a project's `pyproject.toml`, `VT201` to `VT211` for a screenplay and its data, `VT301` to `VT309` but `VT305` for a story, `VT401` to `VT404` for a render, `VT501`, `VT502`, `VT503` and `VT508` for a check, `VT603` for TapePlayer's build, and `VT305`, `VT601`, `VT602` and `VT604` for publish.
- `videotape render --story <name>` draws a key for each state and a move for each action into `tapes/<name>/` in the project, with the model that `[tool.videotape]` names. Each shot films one take at a time, seeds 1, 2, 3 and on, and stops at the first take that passes every check, up to `takes` in `[tool.videotape]` (4 unless set) or `--takes N`. Shots that do not depend on each other film at once, up to the model's limit. It prints one line per shot as it finishes, the totals, and each failing shot with the command to run next, and exits 1 when a kept take fails a check nobody accepted. Run again, it resumes from every take on disk. `--model` names another model, `--out <tape>` writes another tape, and `--cap-usd N` caps what a model that bills per call may spend, which `cap_usd` in `[tool.videotape]` also sets. `tape.json` carries each state's words and search beside its hotspots, and a `made` block that says which screenplay, code, data, story, model and engine made the tape.
- `videotape retake "<state>" --story <name>` films new takes of that state's key, with seeds after the highest it has tried, and keeps the best of all its takes; `--takes N` films N of them. A move is named `"<state> -> <state>"`, or by its full title when two moves join the same states. The moves pinned to a key that changed render again.
- `videotape accept "<state>" <code> --story <name> --reason "<why>"` records a failing check of the shot's kept take as accepted in the tape's record, so the dailies show it as accepted and `render` passes it while it keeps that take. A check that is not failing is refused, and nothing is recorded.
- `videotape dailies --story <name>` rewrites a tape's `dailies.html` from its `dailies.json` and the project's `ledger.jsonl`, and opens it with the default browser. `--out <tape>` names a tape that `render --out` wrote. Set `BROWSER=true` to open nothing.
- `videotape play --story <name>` builds TapePlayer in Release from the source the package carries, `clients/macos` in this checkout and `videotape/macos` in an installed wheel, into `~/Library/Caches/videotape/player/<hash>/TapePlayer.app` (`$VIDEOTAPE_CACHE_DIR` in place of `~/Library/Caches/videotape` when set), once per version of that source, and prints `built TapePlayer in <s> s` when it builds. Then it opens the tape in the app and prints the `open` command. A failed build is `VT603`. It takes over the screen, so never run it yourself; `uv run pytest tests/test_play.py` proves the build into the cache, the cached hit, `VT603` and the command, with the build and the launcher injected.
- `videotape publish --story <name>` makes the story's tape into `dist/<Title>-<story>.app` in the project, TapePlayer named `<Title> (<Story>)` with the tape inside it and each clip encoded as HEVC, signs it ad hoc and says so, zips it to `dist/<Title>-<story>.zip`, records its label, id and hashes in `videotape.lock`, and prints the app's path and size, the label and the id. Publishing the same tape again leaves the lock as it is. It refuses a tape out of date with its sources (`VT601`), failing checks nobody accepted (`VT602`), a label the lock holds with another id (`VT305`), a player that does not build (`VT603`), and an encoded last frame that fails a check its key passed (`VT604`). `--out <tape>` names a tape that `render --out` wrote. Never open the app it makes yourself; see [features/publish.md](features/publish.md).
- `videotape diff <tape> <tape>` says whether two tapes are of the same app and the same story, and how many states and moves they share.

The stand-in model needs no GPU, and its own reader checks its keys. `--model wan2.2-5b` renders with Wan 2.2 and needs a CUDA GPU, which `scripts/runpod-render` rents on Runpod; see [features/gpu-render.md](features/gpu-render.md). `--model wan3.0` renders with Wan 3.0 on fal, which bills per call and needs `FAL_KEY`; see [features/wan3-render.md](features/wan3-render.md). Qwen3-VL-8B checks the keys of both. `scripts/reader-test` asks Claude what Contrail does from its screenplay alone; see [features/reader-test.md](features/reader-test.md). `README.md` at the repo root is the developer's guide, whose whole files and commands `tests/test_guide.py` holds to `examples/contrail` and runs, and `scripts/words-test` asks Claude where the help texts and error messages name a concept by another word than the guide's words section; see [features/guide.md](features/guide.md). There is no server, port or database. A drive is one command run. Its proof is the captured terminal output and exit code, plus the files a render writes and a screenshot of the dailies page.

TapePlayer (`clients/macos/`) is the macOS app a person uses to click through a rendered tape. `vt-verify player-build` builds it into `clients/macos/build/` without opening anything; `play` builds its own copy in the cache. `vt-verify player-press` loads a tape with the player's own loader and presses hotspots by label, types into a search bar and goes back, also without a window. `vt-verify player-test` runs its unit tests and five UI tests that take over the real mouse and screen, so ask the user before running it. One of them walks a copy of a published app, which `--published <app>` names, and it is skipped without it.

Run the helper from the repo root. It is `.claude/skills/verify/scripts/vt-verify`; call it by that path.

## Launch

Run once per checkout, and again after a `pyproject.toml` or `uv.lock` changes:

```bash
.claude/skills/verify/scripts/vt-verify launch
```

Ready means it prints `ready: videotape CLI installed in <repo>/.venv and <repo>/examples/contrail/.venv`. It runs `uv sync` for the repo, which creates `.venv` on Python 3.12 (pinned by `.python-version`) and installs the package in editable mode, and `uv sync` for `examples/contrail`, whose own `.venv` holds videotape and pyright. Later source edits need no relaunch. Teardown is nothing: no process outlives a drive.

For a model other than the stand-in, run `.claude/skills/verify/scripts/vt-verify launch qwen` instead. It runs `uv sync --extra qwen` in the repo, which adds torch and transformers, and prints `ready: videotape CLI installed in <repo>/.venv with the qwen extra`. For `--model wan2.2-5b`, run `.claude/skills/verify/scripts/vt-verify launch wan`, which adds diffusers and what VideoX-Fun imports on top. A plain `launch` uninstalls the extras again.

## Doctor

Read-only. Run it first, and again whenever output looks wrong:

```bash
.claude/skills/verify/scripts/vt-verify doctor
```

Every line must start with `ok` or `info`, and the exit code must be 0. It never calls `uv`, which would create or sync a `.venv`. It checks that ffmpeg is on PATH (render needs it), that `.venv/bin/videotape` exists, that `.venv/bin/python` imports `videotape` from this checkout's `videotape/__init__.py` on Python 3.12, that `videotape --help` exits 0, and that `examples/contrail/.venv/bin/videotape` exists. The `info Xcode` line says whether the TapePlayer helpers can run. The `info qwen` line says whether the qwen extra is installed, which device Qwen3-VL-8B would run on, and whether its weights are cached. The first Qwen run downloads 17.5 GB when they are not. The `info build` line names the commit and flags uncommitted changes to the package, `examples/`, `scripts/` or `clients/macos/`; put it in your report so the proof names what it ran against.

## Drive

Pick a run directory once per verification session and reuse it for every drive:

```bash
RUN=.verify/runs/$(date -u +%Y%m%dT%H%M%SZ)
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- plan --story <story>
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- shots --story <story>
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- render --story <story>
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- retake "<state>" --story <story>
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- accept "<state>" VT503 --story <story> --reason "<why>"
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- dailies --story <story>
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- diff tapes/<story> tapes/<other-story>
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> . -- explain VT208
```

`vt-verify run` does not set `BROWSER`, so export `BROWSER=true` in the shell before a `dailies` drive, or the page opens in the user's browser. Never drive `play`: it opens TapePlayer on the screen.

`run` changes into `<project-dir>` and invokes the repo's `.venv/bin/videotape <args>`, and writes, under `$RUN`:

- `<name>.cmd` holds the exact command, starting with `cd <project-dir> &&`.
- `<name>.stdout` and `<name>.stderr` hold the output.
- `<name>.exit` holds the exit code.
- `<name>.build` holds the commit hash.
- `<name>.project/` copies the Python, JSON and TOML files of a project outside the checkout.

It prints a one-line summary. Read the files to assert; the summary is not proof.

`exec` captures any other command the same way, and `-C <dir>` runs it in a folder. Use it for the guide's own commands in `README.md`, which go through `uv run` in a project such as the example:

```bash
.claude/skills/verify/scripts/vt-verify exec "$RUN" <name> -C examples/contrail -- uv run videotape plan --story terminal
```

TapePlayer drives use the same `$RUN`:

```bash
.claude/skills/verify/scripts/vt-verify player-build "$RUN"
.claude/skills/verify/scripts/vt-verify player-press "$RUN" examples/contrail/tapes/terminal "Where to?" "Seattle (SEA)"
.claude/skills/verify/scripts/vt-verify player-test "$RUN"
.claude/skills/verify/scripts/vt-verify player-cuts "$RUN"
```

Each writes `player-build.*`, `player-press.*`, `player-test.*` or `player-cuts.*` under `$RUN` like `run` does. `player-test` also keeps the result bundle as `player-test.xcresult` and exports its screenshot into `player-test.attachments/`. Ask the user before `player-test`, `player-cuts` and any journey that opens TapePlayer, because they take over the screen. [features/player.md](features/player.md) lists the journeys.

Projects to drive:

- `examples/contrail` is the shipped example, a flight booking app with 58 states and two stories, `terminal` and `posters`. Its expected output is in [features/plan.md](features/plan.md) and [features/stories.md](features/stories.md).
- `tests/fixtures/cafe` is a small app with 5 states and one story, `chalk`, for the render journeys that need a copy or an edit.
- `tests/fixtures/errors/vt201` to `vt211` and `vt301` to `vt309` hold one project per code a plan can raise. Each `vt3xx` project has one story, `neon`, except `vt309`, whose only story is `glow`. The render's and the checks' codes need a model and have no fixture; the render tests force each one. Do not edit a fixture to make a journey pass.
- For a new case, write a project into a fresh directory `"${TMPDIR:-/tmp}"/videotape-verify-<name>`, drive it, and delete that directory in cleanup. A project is a `pyproject.toml` with `[tool.videotape] screenplay = "app:app"` beside an `app.py`, and a render also needs a story, such as `stories/bare.toml` with a `version` and a `look`. `run` keeps a copy of its files with the evidence.

Keep `$RUN` from the `date` line above. Don't rebuild it from `ls` output: on this machine `ls` is aliased to a tool that prefixes icons, and the evidence lands in a stray, un-ignored directory.

Runs share nothing but the read-only `.venv`, so drives of different projects can run side by side. Never run `launch` while another agent is driving, because `uv sync` rewrites `.venv`.

Read [features/README.md](features/README.md) before driving, then follow the feature file that matches the change.

## Evidence

Proof lives in `$RUN` (`.verify/runs/<timestamp>/`, gitignored) and survives cleanup. A proof:

- drives the real command a developer types, such as `videotape plan --story terminal` or `videotape render --story terminal` in the project, through `vt-verify run`, never by importing `plan`, `render`, a story or an eye in a Python snippet;
- quotes the asserted lines from `<name>.stdout` or `<name>.stderr` together with `<name>.exit`;
- for a project you wrote, includes its `<name>.project/` copy so the reader sees the input;
- names the `info build` line from doctor.

`uv run pytest` is a separate check. A passing suite does not replace a drive. `uv run --python 3.14 pytest` from the repo root runs it on Python 3.14 as well. `uv run pytest -m qwen` runs the slow tests that load Qwen3-VL-8B. Run them alone, never beside another process that loads the model. `uv run pytest -m player` runs the guide's commands with TapePlayer opened on the screen, so ask the user first.

## Cleanup

```bash
find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'videotape-verify-*' -exec rm -rf {} +
```

This removes only scratch projects, so name yours `"${TMPDIR:-/tmp}"/videotape-verify-<something>`. Use `find`, not a bare glob, because zsh errors on a glob with no match. Never delete `.verify/runs/`, fixtures, or `examples/`. The one exception is a stand-in tape: `examples/contrail/tapes/` and the project's `ledger.jsonl` are generated and gitignored, and the first-render journey removes both on purpose when the ledger names no Wan take. A tape whose ledger lines name a Wan model cost money. Never delete it, its lines in `ledger.jsonl`, or its `takes/`, and never render it again. There are no processes to stop.

## Helpers

- `.claude/skills/verify/scripts/vt-verify launch [qwen|wan]` installs the CLI in the repo and the example, or the repo's CLI with the qwen extra, or the wan and qwen extras.
- `.claude/skills/verify/scripts/vt-verify doctor` runs the read-only health check.
- `.claude/skills/verify/scripts/vt-verify run <run-dir> <name> <project-dir> -- <videotape args...>` runs one drive in a project and captures its evidence.
- `.claude/skills/verify/scripts/vt-verify exec <run-dir> <name> [-C <dir>] -- <command...>` captures any other command the same way, such as `uv run pyright contrail` or `scripts/runpod-render`.
- `.claude/skills/verify/scripts/vt-verify screenshot <run-dir> <name> <html-file> [height]` captures a page with headless Chrome as `<name>.light.png` and `<name>.dark.png`, 1280 pixels wide and `height` pixels tall, 2400 by default. The cafe's dailies page needs about 11000. It needs Google Chrome in `/Applications`, and doctor reports whether it is there.
- `.claude/skills/verify/scripts/vt-verify player-build <run-dir>` runs `clients/macos/build.sh` and captures it as `player-build.*`. It needs Xcode, and doctor reports whether it is there.
- `.claude/skills/verify/scripts/vt-verify player-press <run-dir> <tape-dir> [<label>...]` loads the tape with TapeKit, presses each label's hotspot in turn through TapeKit's player, and captures the states it rests on as `player-press.*`. A label that ends in `*` matches the first hotspot whose label begins with the rest. `--type <text>` types into the resting state's search bar and `--back` goes back, in the order given. It opens no window.
- `.claude/skills/verify/scripts/vt-verify player-test <run-dir> [--published <app>] [<xcodebuild args...>]` runs `clients/macos/test.sh` and captures it as `player-test.*`, with the result bundle and its exported screenshot. `--published <app>` passes the app to `test.sh --published`, which copies it into a new temporary folder outside the checkout, clears what macOS keeps for its bundle id, and hands the copy's path to the UI test that walks a published app. Arguments after it go to `xcodebuild`, such as `-only-testing:<test>`. It takes over the mouse and screen.
- `.claude/skills/verify/scripts/vt-verify player-cuts <run-dir> [cuts]` measures every cut between clips for a flash, against a control that must flash, and captures it as `player-cuts.*`. It plays a window on screen for about a minute on a stand-in tape, and proportionally longer for longer clips, such as Wan's 81-frame clips.
