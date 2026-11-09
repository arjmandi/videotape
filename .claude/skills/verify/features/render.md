# Render

`videotape render <dir> --model stand-in` renders every shot of the screenplay into `<dir>/tape/`. Each shot gets three takes, and the best take by its checks is kept. The command prints one line per shot saying whether it rendered or came from cache and which take it kept, then a summary line. The tape holds `tape.json`, one key image per scene, one clip per shot, and `dailies.html` for reviewing the takes. A second run reuses every take, and editing one line re-renders only the shots that depend on it.

## Sub-features

- `render-first` renders six shots of three takes each from no `tape/`, prints a line per shot and `rendered 6 of 6 shots`, and exits 0.
- `render-cached` reruns with no model calls. Every shot prints `cached`, and `tape.json` and the keys stay byte-identical.
- `render-cascade` re-renders only the shot that lands on an edited scene and the shots that start or end on that scene's key.
- `render-outputs` writes `tape.json`, `keys/<scene>.png`, and `moves/*.mp4` as H.264 yuv420p clips at 1280x704 and 24 fps.
- `render-dailies` writes `dailies.html`, which shows each shot's three takes, the kept one, each take's checks, and the cache status, in light and dark.
- `render-model` rejects an unknown `--model` with a usage error.

## How to get to it (user POV)

- Run `videotape render examples/surf_shop --model stand-in` from the repo root, then open `examples/surf_shop/tape/dailies.html`.
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
- **Outputs.** After `render-first`, run `command ls examples/surf_shop/tape/keys examples/surf_shop/tape/moves`. It lists `entrance.png gallery.png login.png signup.png welcome.png` and `entrance--browse-as-guest.mp4 entrance--create-an-account.mp4 entrance--i-have-an-account.mp4 opening.mp4 signup--sign-up.mp4 welcome--enter-shop.mp4`. Run `for f in examples/surf_shop/tape/moves/*.mp4; do ffprobe -v error -select_streams v -show_entries stream=codec_name,width,height,pix_fmt,r_frame_rate -of csv=p=0 "$f"; done`. Every line is `h264,1280,704,yuv420p,24/1`. Run `.venv/bin/python -c 'import json; t = json.load(open("examples/surf_shop/tape/tape.json")); print(t["size"], t["fps"], t["opening"]); [print(n, s["key"], [(h["label"], h["move"], h["box"] is not None) for h in s["hotspots"]]) for n, s in t["scenes"].items()]; [print(m, v) for m, v in t["moves"].items()]'`. It prints `{'width': 1280, 'height': 704} 24 {'clip': 'moves/opening.mp4', 'lands': 'welcome'}`, then one line per scene with its `keys/<scene>.png`. `welcome` has one hotspot, `entrance` has three, and `signup` has one, each with a box (`True`) and a move named `<scene>--<label slug>`. `login` and `gallery` have none. Then five moves, each `{'clip': 'moves/<move>.mp4', 'lands': ...}`.
- **Dailies.** Run `grep -c '<section class="shot"' examples/surf_shop/tape/dailies.html` and `grep -c 'badge kept' examples/surf_shop/tape/dailies.html`. Both print `6`. Run `.claude/skills/verify/scripts/vt-verify screenshot "$RUN" render-dailies examples/surf_shop/tape/dailies.html` and read `$RUN/render-dailies.light.png` and `$RUN/render-dailies.dark.png`. Each shows a page headed `Brushstroke Surf Co. dailies`. Under it are shot cards headed like `2. welcome -> entrance "Enter shop" (image-to-video)`, each with three takes. One take per card has a coloured frame and a `kept` badge. Each take lists its checks with a tick or cross: `button "..."` found or missing, `text "..."` with a CER, and `start` or `end` with a difference. Cards for shots 1 to 5 end with the key image they gave their scene.
- **Unknown model.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" render-model -- render examples/surf_shop --model sora`. `.exit` is `2` and `.stderr` contains `invalid choice: 'sora'`.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` lines. Also cite the `shasum` diff for `render-cached`, the `.screenplay.py` copy for `render-cascade`, and both screenshots for `render-dailies`.

## Gotchas

- The take cache is keyed on the prompt, the start and end key images, the model name and the seed. It is not keyed on the stand-in's code. After changing how the stand-in draws or encodes, delete `tape/takes/` (or the whole `tape/`) before rendering, or old takes come back from cache.
- Kept take numbers come from the stand-in's flaws, which are derived from a hash of the prompt and seed. A prompt change, such as a new look or close, changes them. Re-run `render-first` and update the expected lines rather than treating that as a regression. Seed 3 is always clean, so an exit of `1` with `fail:` lines on stderr is a regression.
- `render-first` needs no `tape/`. If one exists, every line says `cached` and the summary says `rendered 0 of 6 shots`.
- The cascade copy must include `tape/` from a previous render. Without it every shot renders.
- A first render takes about 7 seconds and a cached one about 4 seconds on an Apple-silicon Mac. Most of it is ffmpeg process startup for the per-take checks.
- `ls` on this machine is aliased to a tool that prefixes icons. Use `command ls` when you assert on file names.
- The summary prints the tape path as you passed the directory, relative or absolute. The scratch path under `$TMPDIR` prints without the double slash that `"${TMPDIR:-/tmp}"/...` expands to on macOS.
