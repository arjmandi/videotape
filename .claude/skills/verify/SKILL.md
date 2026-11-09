---
name: verify
description: Drive the videotape CLI (`videotape shots <dir>`) the way an app developer does, and capture the command, stdout, stderr and exit code as proof. Use after any change to the videotape package, the CLI, or a screenplay under examples/, before claiming the shot list, prompts, or screenplay errors behave.
---

# Verify videotape

videotape turns a screenplay (`<dir>/screenplay.py`) into the ordered shots a video model would render. The only user surface is one short-lived CLI command, `videotape shots <dir>`. There is no server, port, database or browser. A drive is one command run, and its proof is the captured terminal output and exit code.

All commands below run from the repo root. The helper is `.claude/skills/verify/scripts/vt-verify`; call it by that path.

## Launch

Run once per checkout, and again after `pyproject.toml` or `uv.lock` changes:

```bash
.claude/skills/verify/scripts/vt-verify launch
```

Ready means it prints `ready: videotape CLI installed in <repo>/.venv`. It runs `uv sync`, which creates `.venv` on Python 3.12 (pinned by `.python-version`) and installs the package in editable mode, so later source edits need no relaunch. Teardown is nothing: no process outlives a drive.

## Doctor

Read-only. Run it first, and again whenever output looks wrong:

```bash
.claude/skills/verify/scripts/vt-verify doctor
```

Every line must start with `ok` or `info`, and the exit code must be 0. It never calls `uv`, which would create or sync `.venv`. It checks that `.venv/bin/videotape` exists, that `.venv/bin/python` imports `videotape` from this checkout's `videotape/__init__.py` on Python 3.12, and that `videotape --help` exits 0. The `info build` line names the commit and flags uncommitted changes to the package; put it in your report so the proof names what it ran against.

## Drive

Pick a run directory once per verification session and reuse it for every drive:

```bash
RUN=.verify/runs/$(date -u +%Y%m%dT%H%M%SZ)
.claude/skills/verify/scripts/vt-verify run "$RUN" <name> -- shots <screenplay-dir>
```

`run` invokes the installed `.venv/bin/videotape <args>`, the command a developer gets from `uv sync`, and writes, under `$RUN`:

- `<name>.cmd` holds the exact videotape command.
- `<name>.stdout` and `<name>.stderr` hold the output.
- `<name>.exit` holds the exit code.
- `<name>.build` holds the commit hash.
- `<name>.screenplay.py` copies the screenplay that was driven, when the directory has one.

It prints a one-line summary. Read the files to assert; the summary is not proof.

Screenplays to drive:

- `examples/surf_shop` is the shipped example. Its expected output is in [features/shot-list.md](features/shot-list.md).
- `.claude/skills/verify/fixtures/<name>` holds verification screenplays, one per journey in the feature map. Do not edit a fixture to make a journey pass.
- For a new case, write `screenplay.py` into a fresh directory `"${TMPDIR:-/tmp}"/videotape-verify-<name>`, drive it, and delete that directory in cleanup. `run` keeps a copy of the screenplay with the evidence.

Keep `$RUN` from the `date` line above. Don't rebuild it from `ls` output: on this machine `ls` is aliased to a tool that prefixes icons, and the evidence lands in a stray, un-ignored directory.

Runs share nothing but the read-only `.venv`, so drives can run side by side. Never run `launch` while another agent is driving, because `uv sync` rewrites `.venv`.

Read [features/README.md](features/README.md) before driving, then follow the feature file that matches the change.

## Evidence

Proof lives in `$RUN` (`.verify/runs/<timestamp>/`, gitignored) and survives cleanup. A proof:

- drives the real command a developer types, `videotape shots <dir>`, through `vt-verify run`, never by importing `plan` or `load` in a Python snippet;
- quotes the asserted lines from `<name>.stdout` or `<name>.stderr` together with `<name>.exit`;
- for a screenplay you wrote, includes its `<name>.screenplay.py` copy so the reader sees the input;
- names the `info build` line from doctor.

`uv run pytest` is a separate check. A passing suite does not replace a drive.

## Cleanup

```bash
find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'videotape-verify-*' -exec rm -rf {} +
```

This removes only scratch screenplay dirs, so name yours `"${TMPDIR:-/tmp}"/videotape-verify-<something>`. Use `find`, not a bare glob, because zsh errors on a glob with no match. Never delete `.verify/runs/`, fixtures, or `examples/`. There are no processes to stop.

## Helpers

- `.claude/skills/verify/scripts/vt-verify launch` installs the CLI.
- `.claude/skills/verify/scripts/vt-verify doctor` runs the read-only health check.
- `.claude/skills/verify/scripts/vt-verify run <run-dir> <name> -- <videotape args...>` runs one drive and captures its evidence.
