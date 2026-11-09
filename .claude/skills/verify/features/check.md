# Check

`videotape check <tape-dir> --checks <name>` reads every key of a rendered tape and scores it against its scene in the `screenplay.py` next to the tape. It prints each scene in screenplay order, then one line per button with its box in pixels or `not found`, then one line per line and label with what was read back and its CER. It ends with a summary line naming `dailies.html`, whose Keys section it rewrites with the same results. `--checks stand-in`, the default, decodes the stand-in model's own font. `--checks qwen3-vl-8b` runs the vision model Qwen3-VL-8B on the pixels. A failing check prints a `fail:` line on stderr and exits 1, like `render`.

## Sub-features

- `check-stand-in` scores the surf shop's five keys with the stand-in checks, prints every scene, and exits 0 with `checked 5 keys with stand-in, all passing`.
- `check-qwen` scores the same keys with Qwen3-VL-8B. Every button is found and every line and label reads back at CER 0.000.
- `check-qwen-cached` reruns the Qwen check. It loads no model, reads nothing new, prints the same lines, and takes under a second.
- `check-dailies` rewrites the Keys section of `dailies.html` with each key image, the checks that scored it, and its items, and keeps the shot cards.
- `check-fail` reports a key that shows the wrong scene with a `fail:` line and exit 1.
- `check-errors` rejects a directory with no `tape.json` and a tape with no screenplay beside it with `error:` and exit 1, and an unknown `--checks` with a usage error.
- `check-no-extra` rejects `--checks qwen3-vl-8b` without the qwen extra with an `error:` line that names `uv sync --extra qwen`.

## How to get to it (user POV)

- Run `videotape render examples/surf_shop --model stand-in`, then `videotape check examples/surf_shop/tape --checks qwen3-vl-8b` from the repo root, then open `examples/surf_shop/tape/dailies.html`.
- Run `uv sync --extra qwen` once before the first Qwen check. The first Qwen run downloads 17.5 GB of weights from Hugging Face if they are not cached.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `examples/surf_shop/tape` holds a stand-in render from `render-first` in [render.md](./render.md), and `git diff --quiet -- examples/surf_shop` exits 0.
- For the Qwen journeys, `.claude/skills/verify/scripts/vt-verify launch qwen` has printed `ready:` and doctor prints `info qwen extra installed (...); qwen3-vl-8b checks run on mps` or `on cuda`.
- For `check-qwen`, `examples/surf_shop/tape/looks` does not exist. Run `rm -rf examples/surf_shop/tape/looks` first. It holds cached readings.

- **Stand-in checks.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" check-stand-in -- check examples/surf_shop/tape --checks stand-in`. `.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:
  ```
  welcome  keys/welcome.png
    button "Enter shop"  found at 510,392 260x52
    text "Brushstroke Surf Co."  read "Brushstroke Surf Co.", CER 0.000
    text "Hand-painted surfboards from California"  read "Hand-painted surfboards from California", CER 0.000
    text "Enter shop"  read "Enter shop", CER 0.000
  entrance  keys/entrance.png
    button "I have an account"  found at 426,392 428x52
    button "Create an account"  found at 426,456 428x52
    button "Browse as guest"  found at 450,520 380x52
    text "How would you like to come in?"  read "How would you like to come in?", CER 0.000
    text "I have an account"  read "I have an account", CER 0.000
    text "Create an account"  read "Create an account", CER 0.000
    text "Browse as guest"  read "Browse as guest", CER 0.000
  login  keys/login.png
    text "Log in"  read "Log in", CER 0.000
    text "Email"  read "Email", CER 0.000
    text "Password"  read "Password", CER 0.000
  signup  keys/signup.png
    button "Sign up"  found at 546,392 188x52
    text "Create your account"  read "Create your account", CER 0.000
    text "Email"  read "Email", CER 0.000
    text "Password"  read "Password", CER 0.000
    text "Sign up"  read "Sign up", CER 0.000
  gallery  keys/gallery.png
    text "The gallery"  read "The gallery", CER 0.000
  checked 5 keys with stand-in, all passing -> examples/surf_shop/tape/dailies.html
  ```
- **Qwen checks.** Run `time .claude/skills/verify/scripts/vt-verify run "$RUN" check-qwen -- check examples/surf_shop/tape --checks qwen3-vl-8b`. `.exit` is `0`. `.stdout` has the same 26 lines as `check-stand-in` except the summary, which reads `checked 5 keys with qwen3-vl-8b, all passing -> examples/surf_shop/tape/dailies.html`, and the five button lines. Every text line still ends `CER 0.000`. On an M3 Max on MPS the button lines are `found at 509,391 261x53`, `found at 425,389 428x51`, `found at 425,458 428x51`, `found at 448,525 381x51` and `found at 544,389 191x51`, each within a few pixels of the stand-in's box. `.stderr` holds only the weight loading progress bar and torch's `Redirects are currently not supported in MacOs` notice. It takes about 70 seconds, most of it loading the model and reading five keys at about 11 seconds each. `command ls examples/surf_shop/tape/looks | wc -l` prints `5`.
- **Cached Qwen checks.** Needs `check-qwen`. Run `command ls -l examples/surf_shop/tape/looks > "$RUN/check-qwen-cached.before"`, then `time .claude/skills/verify/scripts/vt-verify run "$RUN" check-qwen-cached -- check examples/surf_shop/tape --checks qwen3-vl-8b`. `.exit` is `0`, `.stderr` is empty, `diff "$RUN/check-qwen.stdout" "$RUN/check-qwen-cached.stdout"` prints nothing, `command ls -l examples/surf_shop/tape/looks | diff "$RUN/check-qwen-cached.before" -` prints nothing, and `time` reports under a second.
- **Dailies.** After `check-qwen`, run `grep -o '<span class="note">[^<]*' examples/surf_shop/tape/dailies.html`. It prints `<span class="note">5 keys checked by qwen3-vl-8b, all passing`. `grep -c '<section class="shot"' examples/surf_shop/tape/dailies.html` still prints `6`. Run `.claude/skills/verify/scripts/vt-verify screenshot "$RUN" check-dailies examples/surf_shop/tape/dailies.html` and read `$RUN/check-dailies.light.png` and `$RUN/check-dailies.dark.png`. Under the summary line a card headed `Keys` notes `5 keys checked by qwen3-vl-8b, all passing`. It holds five key cards, `welcome`, `entrance`, `login`, `signup` and `gallery`, each with its key image, a `qwen3-vl-8b` badge, and a ticked list of `button "..."` with `found at ...` and `text "..."` with `read "...", CER 0.000`. The shot cards follow below.
- **A failing key.** Run `S="${TMPDIR:-/tmp}"/videotape-verify-check; rm -rf "$S"; cp -R examples/surf_shop "$S"; cp "$S/tape/keys/login.png" "$S/tape/keys/gallery.png"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" check-fail -- check "$S/tape"`. `.exit` is `1`, the last `.stdout` line starts `checked 5 keys with stand-in, 1 failing -> `, and `.stderr` is one line that starts `fail: gallery  text "The gallery": read "`.
- **Errors.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" check-no-tape -- check examples/surf_shop`. `.exit` is `1` and `.stderr` is `error: no tape.json in examples/surf_shop; render the screenplay first, then pass its tape directory`. Run `S="${TMPDIR:-/tmp}"/videotape-verify-check-alone; rm -rf "$S"; mkdir -p "$S"; cp -R examples/surf_shop/tape "$S/tape"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" check-no-screenplay -- check "$S/tape"`. `.exit` is `1` and `.stderr` starts `error: no screenplay.py in ` and ends `videotape-verify-check-alone`. Run `.claude/skills/verify/scripts/vt-verify run "$RUN" check-unknown -- check examples/surf_shop/tape --checks tesseract`. `.exit` is `2` and `.stderr` contains `invalid choice: 'tesseract'`.
- **No qwen extra.** Run `uv run --isolated --no-project --with-editable . videotape check examples/surf_shop/tape --checks qwen3-vl-8b; echo "exit $?"`, which runs the CLI in a throwaway environment without the extra. After uv's own `Installed 1 package` line it prints `error: qwen3-vl-8b needs the qwen extra; install it with uv sync --extra qwen` and `exit 1`.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` or `.stderr` lines. Also cite the `time` output for `check-qwen` and `check-qwen-cached`, both diffs for `check-qwen-cached`, and both screenshots for `check-dailies`.

## Gotchas

- `vt-verify launch` without `qwen` runs a plain `uv sync`, which uninstalls the qwen extra. Run `vt-verify launch qwen` again before a Qwen journey.
- Pass the tape directory, `examples/surf_shop/tape`, not the screenplay directory. The screenplay is read from the tape's parent.
- Readings are cached in `tape/looks/` by the frame's pixels, the model and the prompt. A rerun of `check-qwen` without deleting `looks/` reads nothing and proves only the cache.
- A `render --checks qwen3-vl-8b` reads the same key pixels, so a check after it also reads nothing. Delete `tape/looks/` to force fresh readings.
- Only one process should load Qwen3-VL-8B at a time. The weights take 17.5 GB of memory, and two at once on a 36 GB Mac swap hard.
- Button boxes from Qwen come back on a 0 to 1000 grid and land a few pixels from the stand-in's drawn box. Compare them with the IoU bound in `tests/test_qwen.py`, not for exact equality, and expect small shifts on CUDA.
- `check` exits `1` with `error: no dailies.json` on a tape rendered before the dailies record existed. Render it again. Every take comes from cache.
