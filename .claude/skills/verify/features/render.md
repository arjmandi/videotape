# Render

`videotape render <dir> --model stand-in` renders every shot of the screenplay into `<dir>/tape/`. Each shot gets three takes, or `--takes N` of them, and the best take by its checks is kept. `--checks stand-in`, the default, scores takes with the stand-in's own font decoder. `--checks qwen3-vl-8b` scores them with Qwen3-VL-8B, which also places the hotspots. The command prints one line per shot saying whether it rendered or came from cache and which take it kept, then a summary line. The tape holds `tape.json`, one key image per scene, one clip per shot, a render-time sidecar per take, `ledger.jsonl`, `dailies.json`, and `dailies.html` for reviewing the keys and takes. A second run reuses every take, and editing one line re-renders only the shots that depend on it.

## Sub-features

- `render-first` renders six shots of three takes each from no `tape/`, prints a line per shot and `rendered 6 of 6 shots`, and exits 0.
- `render-takes` renders one take per shot with `--takes 1`, prints `rendered 1 take, kept take 1` per shot, exits 1 with `fail:` lines for the shots whose only take carries a stand-in flaw, and rejects `--takes 0` with a usage error.
- `render-cached` reruns with no model calls. Every shot prints `cached`, and `tape.json` and the keys stay byte-identical.
- `render-cascade` re-renders every shot that lands on the edited scene, and the shots that start or end on that scene's key when the edit changes that key.
- `render-outputs` writes `tape.json`, `keys/<scene>.png`, `moves/*.mp4` as H.264 yuv420p clips at 1280x704 and 24 fps, a `takes/<key>.json` sidecar with each take's render seconds and GPU, and `ledger.jsonl` with one line per filmed take.
- `render-dailies` writes `dailies.json` and `dailies.html`. The page opens with a Keys section that shows each scene's key, its checks, its seams (each move leaving the key with its first-frame difference, and each first-and-last-frame move entering it with its last-frame difference) and the render time of the shot that gave the key, then shows each shot's three takes, the kept one, each take's checks, seconds and cache status, in light and dark. The summary line ends with the ledger totals.
- `render-checks` renders with `--checks qwen3-vl-8b`. It keeps the same takes as the stand-in checks, puts every hotspot within IoU 0.75 of the stand-in's, and a second run reads nothing.
- `render-model` rejects an unknown `--model` or `--checks` with a usage error. `--model wan2.2-5b` is covered in [gpu-render.md](./gpu-render.md).

## How to get to it (user POV)

- Run `videotape render examples/surf_shop --model stand-in` from the repo root, then open `examples/surf_shop/tape/dailies.html`.
- Add `--checks qwen3-vl-8b` to score takes and place hotspots with Qwen3-VL-8B, after `uv sync --extra qwen`.
- Edit a line in a screenplay and run the same command again.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold, including the doctor's `ok   ffmpeg` line.
- `git diff --quiet -- examples/surf_shop` exits 0.
- For `render-first`, `examples/surf_shop/tape` does not exist. Run `rm -rf examples/surf_shop/tape` first. It is generated and gitignored.

- **First render.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" render-first -- render examples/surf_shop --model stand-in`. `$RUN/render-first.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:
  ```
  1. opening -> welcome  rendered 3 takes, kept take 1
  2. welcome -> entrance "Enter shop"  rendered 3 takes, kept take 1
  3. entrance -> login "I have an account"  rendered 3 takes, kept take 2
  4. entrance -> signup "Create an account"  rendered 3 takes, kept take 1
  5. entrance -> gallery "Browse as guest"  rendered 3 takes, kept take 2
  6. signup -> login "Sign up"  rendered 3 takes, kept take 2
  rendered 6 of 6 shots -> examples/surf_shop/tape
  ```
- **One take per shot.** Run `S="${TMPDIR:-/tmp}"/videotape-verify-takes; rm -rf "$S"; cp -R examples/surf_shop "$S"; rm -rf "$S/tape"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-takes -- render "$S" --model stand-in --takes 1`. Every shot line ends `rendered 1 take, kept take 1` and the last `.stdout` line starts `rendered 6 of 6 shots`. `.exit` is `1`, because with one take there is no better take to keep and the stand-in's seed-1 takes carry flaws for some prompts. `.stderr` is exactly these four lines:
  ```
  fail: 3. entrance -> login "I have an account"  kept take 1 fails text "Password": read "Passwxrd", CER 0.125
  fail: 5. entrance -> gallery "Browse as guest"  kept take 1 fails start: difference 0.289
  fail: 6. signup -> login "Sign up"  kept take 1 fails text "Password": read "Passwxrd", CER 0.125
  fail: 6. signup -> login "Sign up"  kept take 1 fails start: difference 0.290
  ```
  Then run the same with `--takes 0` as `render-takes-zero`. `.exit` is `2` and `.stderr` ends with `videotape render: error: argument --takes: must be at least 1, got 0`.
- **Second render, cached.** Run `shasum examples/surf_shop/tape/tape.json examples/surf_shop/tape/keys/*.png > "$RUN/render-cached.before"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-cached -- render examples/surf_shop --model stand-in`. `.exit` is `0`, every shot line ends in `cached, kept take N` with the same N as `render-first`, and the last line is `rendered 0 of 6 shots -> examples/surf_shop/tape`. Then `shasum examples/surf_shop/tape/tape.json examples/surf_shop/tape/keys/*.png | diff "$RUN/render-cached.before" -` prints nothing and exits 0.
- **Edit one line.** Needs the tape from `render-first`. Run `S="${TMPDIR:-/tmp}"/videotape-verify-render; rm -rf "$S"; cp -R examples/surf_shop "$S"; perl -pi -e 's/"Create your account"/"Open your account"/' "$S/screenplay.py"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-cascade -- render "$S" --model stand-in`. `.exit` is `0` and the shot lines are exactly:
  ```
  1. opening -> welcome  cached, kept take 1
  2. welcome -> entrance "Enter shop"  cached, kept take 1
  3. entrance -> login "I have an account"  cached, kept take 2
  4. entrance -> signup "Create an account"  rendered 3 takes, kept take 2
  5. entrance -> gallery "Browse as guest"  cached, kept take 2
  6. signup -> login "Sign up"  rendered 3 takes, kept take 2
  ```
  The last line starts with `rendered 2 of 6 shots -> ` and ends with `videotape-verify-render/tape`. `$RUN/render-cascade.screenplay.py` shows the edited line.
- **Outputs.** After `render-first`, run `command ls examples/surf_shop/tape/keys examples/surf_shop/tape/moves`. It lists `entrance.png gallery.png login.png signup.png welcome.png` and `entrance--browse-as-guest.mp4 entrance--create-an-account.mp4 entrance--i-have-an-account.mp4 opening.mp4 signup--sign-up.mp4 welcome--enter-shop.mp4`. `command ls examples/surf_shop/tape/takes | grep -c '\.json$'` prints `18`, one sidecar per take, each a JSON object with `seconds` above 0 and `gpu` of `cpu`. `grep -c '"kind": "take"' examples/surf_shop/tape/ledger.jsonl` prints `18`. Run `for f in examples/surf_shop/tape/moves/*.mp4; do ffprobe -v error -select_streams v -show_entries stream=codec_name,width,height,pix_fmt,r_frame_rate -of csv=p=0 "$f"; done`. Every line is `h264,1280,704,yuv420p,24/1`. Run `.venv/bin/python -c 'import json; t = json.load(open("examples/surf_shop/tape/tape.json")); print(t["size"], t["fps"], t["opening"]); [print(n, s["key"], [(h["label"], h["move"], h["box"] is not None) for h in s["hotspots"]]) for n, s in t["scenes"].items()]; [print(m, v) for m, v in t["moves"].items()]'`. It prints `{'width': 1280, 'height': 704} 24 {'clip': 'moves/opening.mp4', 'lands': 'welcome'}`, then one line per scene with its `keys/<scene>.png`. `welcome` has one hotspot, `entrance` has three, and `signup` has one, each with a box (`True`) and a move named `<scene>--<label slug>`. `login` and `gallery` have none. Then five moves, each `{'clip': 'moves/<move>.mp4', 'lands': ...}`.
- **Dailies.** Run `grep -c '<section class="shot"' examples/surf_shop/tape/dailies.html` and `grep -c 'badge kept' examples/surf_shop/tape/dailies.html`. Both print `6`. `grep -o '<span class="note">[^<]*' | head -1` on the same file prints `<span class="note">5 keys checked by stand-in, all passing`, `grep -o 'seam: leaves by' | wc -l` prints `5` and `grep -o 'seam: enters by' | wc -l` prints `1` (the surf shop's one first-and-last-frame move, `signup--sign-up`, lands on `login`), `grep -o 'Rendered by ' | wc -l` prints `5`, and `examples/surf_shop/tape/dailies.json` exists. Each key card is one line of HTML, so count with `grep -o`, not `grep -c`. After `render-cached`, `grep -c '>from cache<'` on the same file prints `6`, `grep -c 'its key: the last frame of take'` prints `5`, and `grep -o '<p class="summary">[^<]*'` is `<p class="summary">6 shots, 0 rendered this run, 6 from cache. Ledger: ` followed by the GPU seconds, such as `3.4 GPU seconds, 0.0 pod hours, $0.00.` Run `.claude/skills/verify/scripts/vt-verify screenshot "$RUN" render-dailies examples/surf_shop/tape/dailies.html` and read `$RUN/render-dailies.light.png` and `$RUN/render-dailies.dark.png`. Each shows a page headed `Brushstroke Surf Co. dailies` and the summary line with the ledger totals. Under it is a card headed `Keys` with five key cards, one per scene, each with its key image, a `stand-in` badge, its checks, its `seam:` lines with a difference each, and a `Rendered by <move>: the kept take in N s, all its takes in N s on cpu.` note. Then come shot cards headed like `2. welcome -> entrance "Enter shop" (image-to-video)`, each with three takes. One take per card has a coloured frame and a `kept` badge, and every take shows a seconds badge. Each take lists its checks with a tick or cross. A `button "..."` is `found at` a box or `not found`, a `text "..."` shows what was `read` and its CER, and `start` or `end` shows a difference. Cards 1 and 2 end with the key image they gave their scene. The 2400-pixel-tall capture cuts off in card 3, so the greps above stand in for cards 3 to 6. The dark capture has a dark background and light text.
- **Qwen checks.** Needs `render-first`, `vt-verify launch qwen`, and doctor's `info qwen extra installed` line. Run `cp examples/surf_shop/tape/tape.json "$RUN/render-checks.stand-in.json"`, then `time .claude/skills/verify/scripts/vt-verify run "$RUN" render-checks -- render examples/surf_shop --model stand-in --checks qwen3-vl-8b`. `.exit` is `0` and `.stdout` is the six shot lines of `render-cached`, with the same kept takes, and `rendered 0 of 6 shots -> examples/surf_shop/tape`. It takes about 90 seconds on an M3 Max, mostly loading the model and reading the eleven distinct last frames that the eighteen takes end on. Then compare each hotspot box in `examples/surf_shop/tape/tape.json` with the same hotspot in `$RUN/render-checks.stand-in.json`. Every IoU is at least 0.75, and on MPS they run from 0.834 to 0.978. Run the same render again as `render-checks-again`. It takes about 5 seconds, `.stderr` is empty because no model loads, and `tape.json` and the keys are byte-identical.
- **Unknown model.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" render-model -- render examples/surf_shop --model sora`. `.exit` is `2` and `.stderr` contains `invalid choice: 'sora'`. With `--model stand-in --checks sora` instead, `.exit` is also `2` and `.stderr` contains `argument --checks: invalid choice: 'sora'`.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` lines. Also cite the `shasum` diff for `render-cached`, the `.screenplay.py` copy for `render-cascade`, both screenshots for `render-dailies`, and the hotspot IoUs and `time` output for `render-checks`.

## Gotchas

- The take cache is keyed on the shot's mode, the prompt, the start and end key images, the model name, the seed and, for a model that has them, its generation settings; the stand-in has none, so its keys are unchanged from earlier versions. It is not keyed on the checks, so switching `--checks` re-scores every take and renders nothing. It is not keyed on the stand-in's code. After changing how the stand-in draws or encodes, delete `tape/takes/` (or the whole `tape/`) before rendering, or old takes come back from cache.
- `--takes` changes which seeds exist, not the cache key, so `--takes 1` on a tape rendered with three takes keeps only seed 1 per shot. When that changes a kept take, the key it gave changes too and the shots that start or end on it re-render.
- `tape/ledger.jsonl` is append-only. A render appends a line per take it films; a cached run appends nothing. Delete the tape, not the ledger, to start over.
- Kept take numbers come from the stand-in's flaws, which are derived from a hash of the prompt and seed. A prompt change, such as a new look or close, changes them. Re-run `render-first` and update the expected lines rather than treating that as a regression. Seed 3 is always clean, so an exit of `1` with `fail:` lines on stderr is a regression.
- `render-first` needs no `tape/`. If one exists, every line says `cached` and the summary says `rendered 0 of 6 shots`.
- The cascade copy must include `tape/` from a previous render. Without it every shot renders.
- A first render takes about 7 seconds and a cached one about 4 seconds on an Apple-silicon Mac. Most of it is ffmpeg process startup for the per-take checks.
- Qwen readings are cached in `tape/looks/` by frame pixels. Delete that folder to make `render-checks` read again. [check.md](./check.md) has the other Qwen gotchas.
- `ls` on this machine is aliased to a tool that prefixes icons. Use `command ls` when you assert on file names.
- The summary prints the tape path as you passed the directory, relative or absolute. The scratch path under `$TMPDIR` prints without the double slash that `"${TMPDIR:-/tmp}"/...` expands to on macOS.
