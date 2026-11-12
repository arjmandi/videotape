---
name: verify
description: Drive the videotape CLI in an app's project (`videotape plan`, `videotape explain <code>`, `videotape render [--model <name>] [--takes N] [--out <tape>]` and `videotape dailies`) the way an app developer does, and build and test the TapePlayer macOS app that plays a rendered tape. Capture the command, stdout, stderr, exit code and rendered tape as proof. Use after any change to the videotape package, the CLI, a screenplay or its data under examples/, scripts/, or clients/macos/, before claiming the plan, the error codes, the rendered tape and dailies, the checks, the Wan renders, the reader test, or TapePlayer behave.
---

# Verify videotape

videotape lets a developer write an app as a screenplay: typed records, scenes that are functions of their arguments, and a closed set of elements. An app lives in a project, the folder whose `pyproject.toml` names the screenplay in `[tool.videotape]`. Every command runs inside the project and finds it from the working directory upward, so no command takes a folder.

- `videotape plan` walks every state the app can reach and prints each scene's states and moves.
- `videotape explain <code>` prints the long form of an error code, `VT201` to `VT211`.
- `videotape render` draws a key for each state and a move for each action into `tape/` in the project, with the model that `[tool.videotape]` names, and writes `dailies.html` there for review. `--model` names another model, `--takes N` sets the takes per shot, and `--out <tape>` writes another tape.
- `videotape dailies` rewrites a tape's dailies page from its record and the project's `ledger.jsonl`.

The stand-in model needs no GPU, and its own reader checks its keys. `--model wan2.2-5b` renders with Wan 2.2 and needs a CUDA GPU, which `scripts/runpod-render` rents on Runpod; see [features/gpu-render.md](features/gpu-render.md). `--model wan3.0` renders with Wan 3.0 on fal, which bills per call and needs `FAL_KEY`; see [features/wan3-render.md](features/wan3-render.md). Qwen3-VL-8B checks the keys of both. `scripts/reader-test` asks Claude what Contrail does from its screenplay alone; see [features/reader-test.md](features/reader-test.md). There is no server, port or database. A drive is one command run. Its proof is the captured terminal output and exit code, plus the files a render writes and a screenshot of the dailies page.

TapePlayer (`clients/macos/`) is the macOS app a person uses to click through a rendered tape. `vt-verify player-build` builds it without opening anything. `vt-verify player-press` loads a tape with the player's own loader and presses hotspots by label, also without a window. `vt-verify player-test` runs its unit tests and three UI tests that take over the real mouse and screen, so ask the user before running it.

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
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- plan
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> <project-dir> -- render
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> . -- explain VT208
```

`run` changes into `<project-dir>` and invokes the repo's `.venv/bin/videotape <args>`, and writes, under `$RUN`:

- `<name>.cmd` holds the exact command, starting with `cd <project-dir> &&`.
- `<name>.stdout` and `<name>.stderr` hold the output.
- `<name>.exit` holds the exit code.
- `<name>.build` holds the commit hash.
- `<name>.project/` copies the Python, JSON and TOML files of a project outside the checkout.

It prints a one-line summary. Read the files to assert; the summary is not proof.

`exec` captures any other command the same way, and `-C <dir>` runs it in a folder. Use it for the README's own commands, which go through `uv run` in the example:

```bash
.claude/skills/verify/scripts/vt-verify exec "$RUN" <name> -C examples/contrail -- uv run videotape plan
```

TapePlayer drives use the same `$RUN`:

```bash
.claude/skills/verify/scripts/vt-verify player-build "$RUN"
.claude/skills/verify/scripts/vt-verify player-press "$RUN" examples/contrail/tape "Where to?" "Seattle (SEA)"
.claude/skills/verify/scripts/vt-verify player-test "$RUN"
.claude/skills/verify/scripts/vt-verify player-cuts "$RUN"
```

Each writes `player-build.*`, `player-press.*`, `player-test.*` or `player-cuts.*` under `$RUN` like `run` does. `player-test` also keeps the result bundle as `player-test.xcresult` and exports its screenshot into `player-test.attachments/`. Ask the user before `player-test`, `player-cuts` and any journey that opens TapePlayer, because they take over the screen. [features/player.md](features/player.md) lists the journeys.

Projects to drive:

- `examples/contrail` is the shipped example, a flight booking app with 58 states. Its expected output is in [features/plan.md](features/plan.md).
- `tests/fixtures/cafe` is a small app with 5 states, for the render journeys that need a copy or an edit.
- `tests/fixtures/errors/vt201` to `vt211` hold one project per error code. Do not edit a fixture to make a journey pass.
- For a new case, write a project into a fresh directory `"${TMPDIR:-/tmp}"/videotape-verify-<name>`, drive it, and delete that directory in cleanup. A project is a `pyproject.toml` with `[tool.videotape] screenplay = "app:app"` beside an `app.py`. `run` keeps a copy of its files with the evidence.

Keep `$RUN` from the `date` line above. Don't rebuild it from `ls` output: on this machine `ls` is aliased to a tool that prefixes icons, and the evidence lands in a stray, un-ignored directory.

Runs share nothing but the read-only `.venv`, so drives of different projects can run side by side. Never run `launch` while another agent is driving, because `uv sync` rewrites `.venv`.

Read [features/README.md](features/README.md) before driving, then follow the feature file that matches the change.

## Evidence

Proof lives in `$RUN` (`.verify/runs/<timestamp>/`, gitignored) and survives cleanup. A proof:

- drives the real command a developer types, `videotape plan` or `videotape render` in the project, through `vt-verify run`, never by importing `plan`, `render` or an eye in a Python snippet;
- quotes the asserted lines from `<name>.stdout` or `<name>.stderr` together with `<name>.exit`;
- for a project you wrote, includes its `<name>.project/` copy so the reader sees the input;
- names the `info build` line from doctor.

`uv run pytest` is a separate check. A passing suite does not replace a drive. `uv run pytest -m qwen` runs the slow tests that load Qwen3-VL-8B. Run them alone, never beside another process that loads the model.

## Cleanup

```bash
find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'videotape-verify-*' -exec rm -rf {} +
```

This removes only scratch projects, so name yours `"${TMPDIR:-/tmp}"/videotape-verify-<something>`. Use `find`, not a bare glob, because zsh errors on a glob with no match. Never delete `.verify/runs/`, fixtures, or `examples/`. The one exception is a stand-in tape: `examples/contrail/tape` and the project's `ledger.jsonl` are generated and gitignored, and the first-render journey removes both on purpose when the ledger names no Wan take. A tape whose ledger lines name a Wan model cost money. Never delete it, its lines in `ledger.jsonl`, or its `takes/`, and never render it again. There are no processes to stop.

## Helpers

- `.claude/skills/verify/scripts/vt-verify launch [qwen|wan]` installs the CLI in the repo and the example, or the repo's CLI with the qwen extra, or the wan and qwen extras.
- `.claude/skills/verify/scripts/vt-verify doctor` runs the read-only health check.
- `.claude/skills/verify/scripts/vt-verify run <run-dir> <name> <project-dir> -- <videotape args...>` runs one drive in a project and captures its evidence.
- `.claude/skills/verify/scripts/vt-verify exec <run-dir> <name> [-C <dir>] -- <command...>` captures any other command the same way, such as `uv run pyright contrail` or `scripts/runpod-render`.
- `.claude/skills/verify/scripts/vt-verify screenshot <run-dir> <name> <html-file> [height]` captures a page with headless Chrome as `<name>.light.png` and `<name>.dark.png`, 1280 pixels wide and `height` pixels tall, 2400 by default. The cafe's dailies page needs about 7400. It needs Google Chrome in `/Applications`, and doctor reports whether it is there.
- `.claude/skills/verify/scripts/vt-verify player-build <run-dir>` runs `clients/macos/build.sh` and captures it as `player-build.*`. It needs Xcode, and doctor reports whether it is there.
- `.claude/skills/verify/scripts/vt-verify player-press <run-dir> <tape-dir> [<label>...]` loads the tape with TapeKit, presses each label's hotspot in turn through TapeKit's player, and captures the states it rests on as `player-press.*`. A label that ends in `*` matches the first hotspot whose label begins with the rest. It opens no window.
- `.claude/skills/verify/scripts/vt-verify player-test <run-dir>` runs `clients/macos/test.sh` and captures it as `player-test.*`, with the result bundle and its exported screenshot. It takes over the mouse and screen.
- `.claude/skills/verify/scripts/vt-verify player-cuts <run-dir> [cuts]` measures every cut between clips for a flash, against a control that must flash, and captures it as `player-cuts.*`. It plays a window on screen for about a minute on a stand-in tape, and proportionally longer for longer clips, such as Wan's 81-frame clips.
