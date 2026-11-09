---
name: verify
description: Drive the videotape CLI (`videotape shots <dir>`, `videotape render <dir> --model stand-in [--checks qwen3-vl-8b]` and `videotape check <dir>/tape --checks <name>`) the way an app developer does, and build and test the TapePlayer macOS app that plays a rendered tape. Capture the command, stdout, stderr, exit code and rendered tape as proof. Use after any change to the videotape package, the CLI, a screenplay under examples/, or clients/macos/, before claiming the shot list, prompts, screenplay errors, the rendered tape and dailies, the checks, or TapePlayer behave.
---

# Verify videotape

videotape turns a screenplay (`<dir>/screenplay.py`) into the ordered shots a video model renders, and renders them into a tape of clips. The user surface is four short-lived CLI commands. `videotape shots <dir>` lists the shots. `videotape render <dir> --model stand-in [--takes N]` renders them with a stand-in model into `<dir>/tape/` and writes `dailies.html` there for review. `--model wan2.2-5b` renders with Wan 2.2 and needs a CUDA GPU, which `scripts/runpod-render <dir> --cap-usd <n>` rents on Runpod; see [features/gpu-render.md](features/gpu-render.md). `videotape check <dir>/tape --checks <name>` reads every key and scores it against its scene. The checks are `stand-in`, which decodes the stand-in's own font, or `qwen3-vl-8b`, which runs the vision model Qwen3-VL-8B on the pixels, and `render` takes the same `--checks`. `videotape dailies <dir>` rewrites the dailies page from its record and the ledger. There is no server, port or database. A drive is one command run. Its proof is the captured terminal output and exit code, plus the files a render writes and a screenshot of the dailies page.

TapePlayer (`clients/macos/`) is the macOS app a person uses to click through a rendered tape. `vt-verify player-build` builds it without opening anything. `vt-verify player-test` runs its unit tests and four UI tests that take over the real mouse and screen, so ask the user before running it.

All commands below run from the repo root. The helper is `.claude/skills/verify/scripts/vt-verify`; call it by that path.

## Launch

Run once per checkout, and again after `pyproject.toml` or `uv.lock` changes:

```bash
.claude/skills/verify/scripts/vt-verify launch
```

Ready means it prints `ready: videotape CLI installed in <repo>/.venv`. It runs `uv sync`, which creates `.venv` on Python 3.12 (pinned by `.python-version`) and installs the package in editable mode, so later source edits need no relaunch. Teardown is nothing: no process outlives a drive.

For `--checks qwen3-vl-8b`, run `.claude/skills/verify/scripts/vt-verify launch qwen` instead. It runs `uv sync --extra qwen`, which adds torch and transformers, and prints `ready: videotape CLI installed in <repo>/.venv with the qwen extra`. For `--model wan2.2-5b`, run `.claude/skills/verify/scripts/vt-verify launch wan`, which adds diffusers and what VideoX-Fun imports on top. A plain `launch` uninstalls the extras again.

## Doctor

Read-only. Run it first, and again whenever output looks wrong:

```bash
.claude/skills/verify/scripts/vt-verify doctor
```

Every line must start with `ok` or `info`, and the exit code must be 0. It never calls `uv`, which would create or sync `.venv`. It checks that ffmpeg is on PATH (render needs it), that `.venv/bin/videotape` exists, that `.venv/bin/python` imports `videotape` from this checkout's `videotape/__init__.py` on Python 3.12, and that `videotape --help` exits 0. The `info Xcode` line says whether the TapePlayer helpers can run. The `info qwen` line says whether the qwen extra is installed, which device `qwen3-vl-8b` would run on, and whether its weights are cached. The first Qwen run downloads 17.5 GB when they are not. The `info build` line names the commit and flags uncommitted changes to the package or `clients/macos/`; put it in your report so the proof names what it ran against.

## Drive

Pick a run directory once per verification session and reuse it for every drive:

```bash
RUN=.verify/runs/$(date -u +%Y%m%dT%H%M%SZ)
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> -- shots <screenplay-dir>
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> -- render <screenplay-dir> --model stand-in
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> -- check <screenplay-dir>/tape --checks qwen3-vl-8b
```

`run` invokes the installed `.venv/bin/videotape <args>`, the command a developer gets from `uv sync`, and writes, under `$RUN`:

- `<name>.cmd` holds the exact videotape command.
- `<name>.stdout` and `<name>.stderr` hold the output.
- `<name>.exit` holds the exit code.
- `<name>.build` holds the commit hash.
- `<name>.screenplay.py` copies the screenplay that was driven, when the directory has one.

It prints a one-line summary. Read the files to assert; the summary is not proof.

TapePlayer drives use the same `$RUN`:

```bash
.claude/skills/verify/scripts/vt-verify player-build "$RUN"
.claude/skills/verify/scripts/vt-verify player-test "$RUN"
.claude/skills/verify/scripts/vt-verify player-cuts "$RUN"
```

Each writes `player-build.*`, `player-test.*` or `player-cuts.*` under `$RUN` like `run` does. `player-test` also keeps the result bundle as `player-test.xcresult` and exports its screenshot into `player-test.attachments/`. Ask the user before `player-test`, `player-cuts` and any journey that opens TapePlayer, because they take over the screen. [features/player.md](features/player.md) lists the journeys.

Screenplays to drive:

- `examples/surf_shop` is the shipped example. Its expected output is in [features/shot-list.md](features/shot-list.md).
- `.claude/skills/verify/fixtures/<name>` holds verification screenplays, one per journey in the feature map. Do not edit a fixture to make a journey pass.
- For a new case, write `screenplay.py` into a fresh directory `"${TMPDIR:-/tmp}"/videotape-verify-<name>`, drive it, and delete that directory in cleanup. `run` keeps a copy of the screenplay with the evidence.

Keep `$RUN` from the `date` line above. Don't rebuild it from `ls` output: on this machine `ls` is aliased to a tool that prefixes icons, and the evidence lands in a stray, un-ignored directory.

Runs share nothing but the read-only `.venv`, so drives can run side by side. Never run `launch` while another agent is driving, because `uv sync` rewrites `.venv`.

Read [features/README.md](features/README.md) before driving, then follow the feature file that matches the change.

## Evidence

Proof lives in `$RUN` (`.verify/runs/<timestamp>/`, gitignored) and survives cleanup. A proof:

- drives the real command a developer types, `videotape shots <dir>`, `videotape render <dir> --model stand-in` or `videotape check <dir>/tape --checks <name>`, through `vt-verify run`, never by importing `plan`, `load`, `render` or an eye in a Python snippet;
- quotes the asserted lines from `<name>.stdout` or `<name>.stderr` together with `<name>.exit`;
- for a screenplay you wrote, includes its `<name>.screenplay.py` copy so the reader sees the input;
- names the `info build` line from doctor.

`uv run pytest` is a separate check. A passing suite does not replace a drive. `uv run pytest -m qwen` runs the slow tests that load Qwen3-VL-8B. Run them alone, never beside another process that loads the model.

## Cleanup

```bash
find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'videotape-verify-*' -exec rm -rf {} +
```

This removes only scratch screenplay dirs, so name yours `"${TMPDIR:-/tmp}"/videotape-verify-<something>`. Use `find`, not a bare glob, because zsh errors on a glob with no match. Never delete `.verify/runs/`, fixtures, or `examples/`. The one exception is `examples/surf_shop/tape`, which is generated and gitignored, and which the first-render journey removes on purpose. There are no processes to stop.

## Helpers

- `.claude/skills/verify/scripts/vt-verify launch [qwen|wan]` installs the CLI, with the qwen extra, or the wan and qwen extras, when asked.
- `.claude/skills/verify/scripts/vt-verify doctor` runs the read-only health check.
- `.claude/skills/verify/scripts/vt-verify run <run-dir> <name> -- <videotape args...>` runs one drive and captures its evidence.
- `.claude/skills/verify/scripts/vt-verify exec <run-dir> <name> -- <command...>` captures any other command the same way, such as `scripts/runpod-render`.
- `.claude/skills/verify/scripts/vt-verify screenshot <run-dir> <name> <html-file>` captures a page with headless Chrome as `<name>.light.png` and `<name>.dark.png`. It needs Google Chrome in `/Applications`, and doctor reports whether it is there.
- `.claude/skills/verify/scripts/vt-verify player-build <run-dir>` runs `clients/macos/build.sh` and captures it as `player-build.*`. It needs Xcode, and doctor reports whether it is there.
- `.claude/skills/verify/scripts/vt-verify player-test <run-dir>` runs `clients/macos/test.sh` and captures it as `player-test.*`, with the result bundle and its exported screenshot. It takes over the mouse and screen.
- `.claude/skills/verify/scripts/vt-verify player-cuts <run-dir> [cuts]` measures every cut between clips for a flash, against a control that must flash, and captures it as `player-cuts.*`. It plays a window on screen for about a minute on a stand-in tape, and proportionally longer for longer clips, such as Wan's 81-frame clips.
