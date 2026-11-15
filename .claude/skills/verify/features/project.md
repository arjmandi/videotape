# Project

A developer starts an app with `videotape new <name>`, run in any folder, which writes a project into a new or empty folder `<name>/`: `pyproject.toml`, `<name>/__init__.py`, `<name>/screenplay.py`, `data/steps.json`, `stories/starter.toml`, `.env.example` and `.gitignore`. The `pyproject.toml` names the app, version `0.1.0`, and one dependency, videotape from where the running videotape was installed: `videotape @ file:///<folder>` from a folder, `videotape @ git+<url>@<commit>` from git, or `videotape==<version>` from an index. Its `[tool.videotape]` names the screenplay `<name>.screenplay:app`, `model = "wan3.0"`, `takes = 4` and `cap_usd = 200`. The screenplay, titled from the name, has two scenes, `home()` with a button to `todo()` and `todo()` with a list of the three steps in `data/steps.json` and a button back. The starter plans with no warning and renders clean with the stand-in. `videotape doctor`, run anywhere, prints one line per check, `ok   <code> <what>`, or `fail <code> <what>` over `  fix: <fix>`, and exits 1 when one fails: `VT101` the Python against videotape's `requires-python`, `VT102` ffmpeg and ffprobe on PATH, and `VT103` Xcode for TapePlayer. In a project it also checks `VT104`, the key the project's model needs, from the environment or the project's `.env`, and `VT105`, the GPU its checks need. A project with a wrong value fails its `VT107` after the machine's lines. `scripts/quickstart-test` runs the whole quickstart from an empty folder with fresh caches and times it.

## Sub-features

- `project-new` writes the starter and prints `made <name>: ...` and the four commands to run next.
- `project-refuse` refuses a folder that is not empty and a name that cannot name a Python package, and writes nothing.
- `project-starter` plans the starter in its story with no warning, and renders it with the stand-in at 4 takes with no failure.
- `project-dependency` names videotape from where it was installed, proven by `uv run pytest tests/test_new.py`.
- `project-doctor` prints the machine's three checks and the project's two, and fails `VT104` when the starter's `FAL_KEY` is not set.
- `project-doctor-machine` prints only the machine's checks outside a project.
- `project-doctor-fails` fails each check on a made-up machine, proven by `uv run pytest tests/test_doctor.py`.
- `project-quickstart` runs `new`, `cd`, `doctor`, `render` and `play` from an empty folder with no uv or videotape cache, then `publish`, which is not one of the steps to a played tape, and reports each step's time and TapePlayer's first build apart.

## How to get to it (user POV)

- In an empty folder, run `uvx --from <checkout or git URL> videotape new <name>`, then `cd <name>`, `uv run videotape doctor`, `uv run videotape render --story starter --model stand-in` and `uv run videotape play --story starter`.
- In any folder with videotape installed, run `videotape doctor`.
- Copy `.env.example` to `.env` and set `FAL_KEY` there, then run `uv run videotape doctor` again.
- From the repo root, run `scripts/quickstart-test`, or `scripts/quickstart-test --skip-play` to skip play.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `P="${TMPDIR:-/tmp}"/videotape-verify-new` is a new, empty folder: `rm -rf "$P" && mkdir -p "$P"`.
- `M="${TMPDIR:-/tmp}"/videotape-verify-machine` is an empty folder outside any project: `mkdir -p "$M"`.

- **New.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" project-new "$P" -- new shop`. `.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:

  ```
  made shop: a screenplay of two scenes, a data table, and the story starter
  next:
    cd shop
    uv run videotape doctor
    uv run videotape render --story starter --model stand-in
    uv run videotape play --story starter
  ```

  `cd "$P/shop" && find . -type f | sort` lists `./.env.example`, `./.gitignore`, `./data/steps.json`, `./pyproject.toml`, `./shop/__init__.py`, `./shop/screenplay.py` and `./stories/starter.toml`. `grep videotape "$P/shop/pyproject.toml"` prints `dependencies = ["videotape @ file://<repo>"]` and `[tool.videotape]`, since this checkout's videotape is installed from its folder.
- **Refusals.** Run the same command again as `project-new-again`. `.exit` is `1` and `.stderr` is exactly `error: shop is not an empty folder; new writes a project only into a new or empty one`. With `-- new my-shop` as `project-new-name`, `.exit` is `1` and `.stderr` is `error: "my-shop" cannot name a project: it names the project in pyproject.toml and its Python package, so it starts with a letter, ends with a letter or digit, holds only ASCII letters, digits and _, and is not a Python keyword, as in my_app`, and `command ls "$P"` lists only `shop`.
- **Starter.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" project-plan "$P/shop" -- plan --story starter`. `.exit` is `0`, the first `.stdout` line is `Shop 0.1.0 + starter 1.0.0: 2 scenes, 2 states, 2 keys, 2 moves, 4 shots`, and the last two are `0 errors, 0 warnings` and `wan3.0: 4 shots, 4 to 16 calls, $2.00 to $8.00 at $0.10/s`. Then run it with `-- render --story starter --model stand-in` as `project-render`. `.exit` is `0`, `.stderr` is empty, every shot line reads `passed`, and the last line starts `4 shots, ` and ends `-> tapes/starter`.
- **Doctor in the starter.** Run `env -u FAL_KEY .claude/skills/verify/scripts/vt-verify run "$RUN" project-doctor "$P/shop" -- doctor`. `.exit` is `1`, `.stderr` is empty, and `.stdout` is:

  ```
  ok   VT101 Python 3.12.12, and videotape needs >=3.12
  ok   VT102 ffmpeg and ffprobe are on PATH
  ok   VT103 Xcode 27.0, at /Applications/Xcode.app/Contents/Developer, for TapePlayer
  fail VT104 wan3.0 needs FAL_KEY, and it is not in the environment or .env
    fix: copy .env.example to .env and set FAL_KEY there, or export it
  fail VT105 wan3.0's checks run Qwen3-VL-8B through videotape's qwen extra, which is not installed here
    fix: in pyproject.toml, put [qwen] right after videotape in dependencies, as in "videotape[qwen] @ file:///Users/me/videotape-p1p" or "videotape[qwen]==0.1.0", then run uv sync
  ```

  The Python and Xcode versions are this machine's. `vt-verify run` runs the repo's `.venv`, which has no qwen extra after a plain `launch`. After `launch qwen` the last line is `ok   VT105 Apple silicon and videotape's qwen extra, for wan3.0's checks`, with no fix line. With `examples/contrail` as the folder, as `project-doctor-contrail`, `.exit` is `0` and the last two lines are `ok   VT104 stand-in needs no API key` and `ok   VT105 stand-in's checks need no GPU`.
- **Doctor outside a project.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" project-doctor-machine "$M" -- doctor`. `.exit` is `0` and `.stdout` is the first three lines above.
- **Fails.** Run `uv run pytest tests/test_doctor.py -v`. Each of `VT101` to `VT105` fails on a machine made up of scripts on PATH, a monkeypatched platform, and torch hidden from imports, and each code's `explain` example is one of its failing lines. `VT105` fails on a platform with neither Apple silicon nor `nvidia-smi`, and, with its example and fix, without the qwen extra. A blank `FAL_KEY=` in `.env` counts as no key, and a wrong `model` fails `VT107` after the machine's lines.
- **Quickstart.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" project-quickstart -- env -u FAL_KEY scripts/quickstart-test --skip-play`. `.exit` is `0`. `.stdout` echoes each step after `$ `, with the output of `new`, of `doctor` with only `VT104` and the qwen extra's `VT105` failing, and of the render and the publish, which builds TapePlayer and ends `videotape.lock holds the label now; commit it`, then a table of the five steps run with their seconds, the publish line naming `TapePlayer's first build <s> s`, then `5 steps to a played tape, at most 5` and `<s> s to a rendered tape without TapePlayer's first build, at most 300 s`. Without `--skip-play` it also runs play before publish, which builds TapePlayer, opens it on the screen and quits it; the play line then names the first build, and publish uses the cached player. Driven on 2026-11-15 with the user's yes: `5 steps to a played tape, at most 5` and `5.3 s to a played tape without TapePlayer's first build, at most 300 s`.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted lines, and for `project-new` the file list.

## Gotchas

- `scripts/quickstart-test` without `--skip-play` opens TapePlayer on the screen. Ask the user first, and wait for a yes.
- `vt-verify run` copies the `.py`, `.json` and `.toml` files two levels under a folder outside the checkout into the evidence, so run doctor outside a project in an empty folder such as `$M`, never in `$TMPDIR` itself.
- `vt-verify run` runs this checkout's `.venv/bin/videotape`, so the `file://` dependency in a project it makes names this checkout. `uvx --from <checkout>` installs the same.
- uv rebuilds a `file://` dependency only when its `pyproject.toml` changes, so a project made from this checkout keeps the videotape it first built after the package's code changes. `scripts/quickstart-test` uses a fresh uv cache, so it always builds the code as it is.
- `VT105` checks what a Wan model's eye, Qwen3-VL-8B, needs. It reads the platform for Apple silicon, and PATH for `nvidia-smi`, a CUDA GPU's tool, and then whether torch and transformers import, which videotape's qwen extra installs. A project that `new` writes leaves the extra out, so its doctor fails `VT105` until `[qwen]` follows `videotape` in its `dependencies` and `uv sync` runs.
- doctor never prints a key's value, only its name.
