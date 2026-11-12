# Render

`videotape render`, run in an app's project, plans the app and then renders every shot into `tape/` in the project: a key for every state first, then a move for every action. It renders with the model that `[tool.videotape]` names, or the one `--model` names. Each shot gets three takes, or `--takes N` of them. A key keeps the take with the most hotspots found, then the lowest character error, then the lowest seed, and its last frame becomes the state's key image. A move is drawn between the two kept key images it joins and keeps the take whose first and last frames sit closest to them. The stand-in's own reader checks the stand-in's keys: it reads every line of the key, each occurrence of a repeated line included, and finds every action by its words. The command prints one line per shot saying whether it rendered or came from cache and which take it kept, then a summary line. The tape holds `tape.json` with one scene per state, one key image per state, the opening clip and one clip per move, a render-time sidecar per take, `dailies.json`, and `dailies.html` for reviewing the keys and takes. Every filmed take appends a line to `ledger.jsonl` in the project, naming its tape. A second run reuses every take, and editing one line re-renders only its key and the moves that start or end on that key. `--out <tape>` writes another tape of the same app. `tape.json` takes its size and frame rate from the kept clips, which for the stand-in are 1280x704 at 24 fps.

## Sub-features

- `render-first` renders Contrail's 160 shots of three takes each from no `tape/`, prints a line per shot and `rendered 160 of 160 shots -> tape`, and exits 0 with nothing on stderr.
- `render-cached` reruns with no model calls. Every shot prints `cached`, and `tape.json` and the keys stay byte-identical.
- `render-outputs` writes `tape.json`, `keys/<state>.png`, `moves/opening.mp4` and `moves/<state>--<words>.mp4` as H.264 yuv420p clips at 1280x704 and 24 fps, and a `takes/<hash>.json` sidecar with each take's render seconds and GPU.
- `render-ledger` appends one line per filmed take to `ledger.jsonl` in the project, each with `"tape": "tape"`, and `videotape dailies` rewrites the page with that tape's totals.
- `render-dailies` writes `dailies.json` and `dailies.html`. The page opens with a Keys section that shows the kept keys side by side, each with its checks, then shows each shot's three takes, the kept one, each take's checks, seconds and cache status. A move's card ends with its seams, flagged when over 0.05, and the render time. The summary line ends with the ledger totals and the tape's size, in light and dark. A take's clip loads and plays only while it is near the window.
- `render-cafe` renders the cafe fixture's 11 shots.
- `render-cascade` re-renders the key of the edited state and the moves that start or end on that key, and nothing else.
- `render-out` renders with `--out tape-b` into that folder, leaves `tape/` byte for byte as it was, and names `tape-b` in its ledger lines, so each tape's dailies total only its own takes.
- `render-takes` renders one take per shot with `--takes 1`, exits 1 with `fail:` lines for the shots whose only take carries a stand-in flaw, and rejects `--takes 0` with a usage error.
- `render-hotspots` lists a hotspot in `tape.json` only for an action the checks found on the kept key. A move whose action was not found still renders and is listed under `moves`, and `render` prints a `fail:` line for the hotspot and exits 1.
- `render-model` rejects an unknown `--model` with a usage error. `--model wan2.2-5b` is covered in [gpu-render.md](./gpu-render.md) and `--model wan3.0` in [wan3-render.md](./wan3-render.md).

## How to get to it (user POV)

- In `examples/contrail`, run `uv run videotape render`, then open `tape/dailies.html`.
- Edit a line of a screenplay or a value in its data and run the same command again.
- Add `--out tape-<name>` to keep a second tape of the same app beside the first.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold, including the doctor's `ok   ffmpeg` line.
- For `render-first`, `examples/contrail/tape` does not exist. It is generated and gitignored. Run `grep -L '"model": "wan' examples/contrail/ledger.jsonl` first. It prints the ledger's path when no Wan take is in it, and only then run `rm -rf examples/contrail/tape examples/contrail/ledger.jsonl`. When it prints nothing, a Wan render was paid for in this project: leave the ledger, and delete only `examples/contrail/tape` after checking that its `dailies.json` names `"checks": "stand-in"`.

- **First render.** Run `time .claude/skills/verify/scripts/vt-verify run "$RUN" render-first examples/contrail -- render`. It took 3 minutes 10 seconds on an M3 Max. `$RUN/render-first.exit` is `0`, `.stderr` is empty, and `.stdout` has 161 lines. `grep -c 'rendered 3 takes, kept take' "$RUN/render-first.stdout"` prints `160`, and `grep -c '^[0-9]*\. key ' "$RUN/render-first.stdout"` prints `58`. The first six lines, lines 58 to 60 and the last three are exactly:
  ```
  1. key home  rendered 3 takes, kept take 3
  2. key search  rendered 3 takes, kept take 2
  3. key trip(CT 100, 2026-12-18)  rendered 3 takes, kept take 3
  4. key my_trips  rendered 3 takes, kept take 2
  5. key profile  rendered 3 takes, kept take 2
  6. key not_found  rendered 3 takes, kept take 1
  58. key booked(CT 306, 2026-12-13)  rendered 3 takes, kept take 2
  59. home -> search "Where to?"  rendered 3 takes, kept take 1
  60. home -> trip(CT 100, 2026-12-18) "San Francisco to New York, Friday, December 18"  rendered 3 takes, kept take 1
  159. booked(CT 300, 2026-12-13) -> home "Done"  rendered 3 takes, kept take 1
  160. booked(CT 306, 2026-12-13) -> home "Done"  rendered 3 takes, kept take 1
  rendered 160 of 160 shots -> tape
  ```
- **Second render, cached.** Run `(cd examples/contrail && shasum tape/tape.json tape/keys/*.png) > "$RUN/render-cached.before"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-cached examples/contrail -- render`. It took 1 minute 50 seconds, because every take is read and checked again. `.exit` is `0`, `grep -c 'cached, kept take' "$RUN/render-cached.stdout"` prints `160` with the same kept takes as `render-first`, and the last line is `rendered 0 of 160 shots -> tape`. Then `(cd examples/contrail && shasum tape/tape.json tape/keys/*.png) | diff "$RUN/render-cached.before" -` prints nothing and exits 0, and `wc -l < examples/contrail/ledger.jsonl` still prints `480`.
- **Outputs.** After `render-first`, `command ls examples/contrail/tape` lists `dailies.html dailies.json keys moves takes tape.json`. `command ls examples/contrail/tape/keys | wc -l` prints `58` and names such as `dates-sea.png` and `booked-ct-100-2026-12-11.png`. `command ls examples/contrail/tape/moves | wc -l` prints `103`: `opening.mp4` and 102 moves such as `dates-sea--12.mp4` and `results-hnl-2026-12-11--9-00-am-to-12-35-pm.mp4`. `command ls examples/contrail/tape/takes | grep -c '\.json$'` prints `480`, one sidecar per take, each a JSON object with `seconds` above 0 and `gpu` of `cpu`. Run `for f in examples/contrail/tape/moves/*.mp4; do ffprobe -v error -select_streams v -show_entries stream=codec_name,width,height,pix_fmt,r_frame_rate -of csv=p=0 "$f"; done | sort | uniq -c`. It prints one line, `103 h264,1280,704,yuv420p,24/1`. Run `.venv/bin/python -c 'import json; t = json.load(open("examples/contrail/tape/tape.json")); print(t["size"], t["fps"], t["opening"]); print(len(t["scenes"]), len(t["moves"]), sum(len(s["hotspots"]) for s in t["scenes"].values())); s = t["scenes"]["dates(SEA)"]; print(s["key"], [(h["label"], h["move"]) for h in s["hotspots"]]); print(t["moves"]["dates-sea--12"]); print([n for n, s in t["scenes"].items() if not s["hotspots"]])'`. It prints `{'width': 1280, 'height': 704} 24 {'clip': 'moves/opening.mp4', 'lands': 'home'}`, then `58 102 102`, then `keys/dates-sea.png [('Friday, December 11, $99', 'dates-sea--11'), ('Saturday, December 12, $89', 'dates-sea--12'), ('Sunday, December 13, $109', 'dates-sea--13')]`, then `{'clip': 'moves/dates-sea--12.mp4', 'lands': 'results(SEA, 2026-12-12)'}`, then `['trip(CT 100, 2026-12-18)', 'trip(CT 500, 2027-01-08)']`, the two states with nothing to press.
- **Ledger.** `grep -c '"kind": "take"' examples/contrail/ledger.jsonl` and `grep -c '"tape": "tape"' examples/contrail/ledger.jsonl` both print `480`. `tail -n 1 examples/contrail/ledger.jsonl` is a JSON object with `at`, `gpu` `cpu`, `kind` `take`, `mode`, `model` `stand-in`, `seconds`, `seed`, `shot` and `tape`. A take's `shot` is its title, such as `key home` or `booked(CT 306, 2026-12-13) -> home "Done"`. `examples/contrail/tape` holds no `ledger.jsonl`. Run `.claude/skills/verify/scripts/vt-verify run "$RUN" render-ledger examples/contrail -- dailies`. `.exit` is `0` and `.stdout` is one line starting `wrote tape/dailies.html with {"takes": 480, "gpu_seconds": ` that also lists `pods`, `pod_hours` and `usd`.
- **Dailies.** `grep -c '<section class="shot"' examples/contrail/tape/dailies.html` and `grep -c 'badge kept' examples/contrail/tape/dailies.html` both print `160`. `grep -o '<span class="note">[^<]*' examples/contrail/tape/dailies.html | head -1` prints `<span class="note">58 keys checked by stand-in, all passing`. `grep -o 'Seams: [^<]*' examples/contrail/tape/dailies.html | wc -l` prints `102`, and the first is `Seams: leaves home by 0.004, enters search by 0.004.` `grep -c '<video data-src=' examples/contrail/tape/dailies.html` prints `480`. After `render-cached`, `grep -o '<p class="summary">[^<]*' examples/contrail/tape/dailies.html` is `<p class="summary">160 shots, 0 rendered this run, 160 from cache. Ledger: ` followed by the GPU seconds, the pod hours, the dollars and the tape's size, such as `79.6 GPU seconds, 0.0 pod hours, $0.00. Tape: 9.3 MB.` Run `.claude/skills/verify/scripts/vt-verify screenshot "$RUN" render-dailies examples/contrail/tape/dailies.html 5200` and read `$RUN/render-dailies.light.png` and `$RUN/render-dailies.dark.png`. Each shows a page headed `Contrail dailies` and the summary line. Under it is a card headed `Keys` with key cards five to a row, `home`, `search`, `trip(CT 100, 2026-12-18)`, `my_trips` and `profile` first, each with its key image, a `stand-in` badge, its checks, and a note `The last frame of take N, rendered in N s, all 3 takes in N s on cpu.` In a key's checks a `hotspot "..."` is `found at` a box, and a `text "..."` shows what was `read` and its CER. The dark capture has a dark background and light text. The shot cards are below the 58 key cards, too far down for one capture, so read them on the cafe's page in the next journey.
- **Cafe.** Run `S="${TMPDIR:-/tmp}"/videotape-verify-cafe; rm -rf "$S"; cp -R tests/fixtures/cafe "$S"; rm -rf "$S/tape" "$S/ledger.jsonl" "$S/__pycache__"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-cafe "$S" -- render`. `.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:
  ```
  1. key menu  rendered 3 takes, kept take 1
  2. key order(Espresso)  rendered 3 takes, kept take 2
  3. key order(Latte)  rendered 3 takes, kept take 3
  4. key thanks(Espresso)  rendered 3 takes, kept take 3
  5. key thanks(Latte)  rendered 3 takes, kept take 1
  6. menu -> order(Espresso) "Espresso, $3"  rendered 3 takes, kept take 1
  7. menu -> order(Latte) "Latte, $5"  rendered 3 takes, kept take 1
  8. order(Espresso) -> thanks(Espresso) "Order"  rendered 3 takes, kept take 2
  9. order(Latte) -> thanks(Latte) "Order"  rendered 3 takes, kept take 2
  10. thanks(Espresso) -> menu "Done"  rendered 3 takes, kept take 1
  11. thanks(Latte) -> menu "Done"  rendered 3 takes, kept take 1
  rendered 11 of 11 shots -> tape
  ```
  Run `.claude/skills/verify/scripts/vt-verify screenshot "$RUN" render-cafe-dailies "$S/tape/dailies.html" 7400` and read both captures. After the Keys card come eleven shot cards headed like `2. key order(Espresso) (text-to-video)` and `10. thanks(Espresso) -> menu "Done" (first-and-last-frame)`, each with three takes. One take per card has a coloured frame and a `kept` badge, and every take shows a seconds badge. Each take lists its checks with a tick or cross. Take 1 of `order(Espresso)` fails `text "$3"` with `read "$x", CER 0.500`, and take 1 of `order(Latte)` fails `hotspot "Order"` with `not found`. On a move take `start` and `end` show a difference each, in red when over 0.05. A key card ends with the key image it gave its state. A move card ends with `Seams: leaves <state> by N, enters <state> by N.` and the render time line.
- **Edit one line.** Needs the tape from `render-cafe`. Run `perl -pi -e 's/vt.Heading\("Corner Cafe"\)/vt.Heading("The Corner Cafe")/' "$S/cafe.py"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-cascade "$S" -- render`. `.exit` is `0` and `.stdout` is exactly:
  ```
  1. key menu  rendered 3 takes, kept take 2
  2. key order(Espresso)  cached, kept take 2
  3. key order(Latte)  cached, kept take 3
  4. key thanks(Espresso)  cached, kept take 3
  5. key thanks(Latte)  cached, kept take 1
  6. menu -> order(Espresso) "Espresso, $3"  rendered 3 takes, kept take 1
  7. menu -> order(Latte) "Latte, $5"  rendered 3 takes, kept take 1
  8. order(Espresso) -> thanks(Espresso) "Order"  cached, kept take 2
  9. order(Latte) -> thanks(Latte) "Order"  cached, kept take 2
  10. thanks(Espresso) -> menu "Done"  rendered 3 takes, kept take 1
  11. thanks(Latte) -> menu "Done"  rendered 3 takes, kept take 1
  rendered 5 of 11 shots -> tape
  ```
  Only the menu key and the four moves that start or end on it render. `$RUN/render-cascade.project/cafe.py` shows the edited line.
- **Out.** Run `(cd "$S/tape" && find . -type f | sort | xargs shasum) > "$RUN/render-out.before"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-out "$S" -- render --out tape-b`. `.exit` is `0`, `.stderr` is empty, and the last `.stdout` line is `rendered 11 of 11 shots -> tape-b`. `"$S/tape-b"` holds `tape.json`, `keys/`, `moves/`, `takes/`, `dailies.json` and `dailies.html`. Running the same `find` again and piping it to `diff "$RUN/render-out.before" -` prints nothing. `grep -c '"tape": "tape-b"' "$S/ledger.jsonl"` prints `33` and `grep -c '"tape": "tape"' "$S/ledger.jsonl"` prints `48`, the first render's 33 takes and the edit's 15. `grep -o '"takes": [0-9][0-9]*' "$S/tape-b/dailies.json"` prints `"takes": 33`, that tape's own takes.
- **One take per shot.** Run `T="${TMPDIR:-/tmp}"/videotape-verify-takes; rm -rf "$T"; cp -R tests/fixtures/cafe "$T"; rm -rf "$T/tape" "$T/ledger.jsonl" "$T/__pycache__"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" render-takes "$T" -- render --takes 1`. Every shot line ends `rendered 1 take, kept take 1` and the last `.stdout` line is `rendered 11 of 11 shots -> tape`. `.exit` is `1`, because with one take there is no better take to keep and the stand-in's seed-1 takes carry flaws for some prompts. `.stderr` is exactly these six lines:
  ```
  fail: 2. key order(Espresso)  kept take 1 fails text "$3": read "$x", CER 0.500
  fail: 3. key order(Latte)  kept take 1 fails hotspot "Order": not found
  fail: 3. key order(Latte)  kept take 1 fails text "Order": read nothing, CER 1.000
  fail: 4. key thanks(Espresso)  kept take 1 fails text "Thanks": read nothing, CER 1.000
  fail: 8. order(Espresso) -> thanks(Espresso) "Order"  kept take 1 fails start: difference 0.277
  fail: 9. order(Latte) -> thanks(Latte) "Order"  kept take 1 fails start: difference 0.276
  ```
  Then run the same with `--takes 0` as `render-takes-zero`. `.exit` is `2` and `.stderr` ends with `videotape render: error: argument --takes: must be at least 1, got 0`.
- **Hotspots.** On a stand-in tape with three takes every action is found, so this journey is proven by `uv run pytest tests/test_render.py -k do_not_find`, which renders two states with a stand-in that leaves one button out of every take and asserts that the button has no hotspot, that both moves are still under `moves`, and that `render` printed a `fail:` line for the hotspot and exited 1. On a Wan tape, compare the `fail: N. key <state>  kept take S fails hotspot "<label>": not found` lines on stderr with that state's `hotspots` in `tape.json`.
- **Unknown model.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" render-model "$S" -- render --model sora`. `.exit` is `2` and `.stderr` ends with `videotape render: error: argument --model: invalid choice: 'sora' (choose from stand-in, wan2.2-5b, wan3.0)`.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` lines. Also cite the `shasum` diff for `render-cached`, the `.project/cafe.py` copy for `render-cascade`, the `find` diff and the ledger counts for `render-out`, and both screenshots for `render-dailies` and `render-cafe-dailies`.

## Gotchas

- A key take's cache key is the shot's mode, the prompt, the model name, the seed and, for a model that has them, its generation settings. A move take's cache key also holds the two key images it is pinned to, which is what makes a changed key re-render only its moves. The cache is not keyed on the stand-in's code. After changing how the stand-in draws or encodes, delete `tape/takes/` (or the whole `tape/`) before rendering, or old takes come back from cache.
- `--takes` changes which seeds exist, not the cache key, so `--takes 1` on a tape rendered with three takes keeps only seed 1 per shot. When that changes a kept key, the moves that start or end on it re-render.
- `ledger.jsonl` is append-only and lives in the project, not in the tape. A render appends a line per take it films; a cached run appends nothing. Deleting a stand-in tape leaves its lines behind, and a new render of that tape adds to them, so its totals then count both.
- Kept take numbers come from the stand-in's flaws, which are derived from a hash of the prompt and seed. A prompt change, such as a new line in a scene, changes them. Re-run the journey and update the expected lines rather than treating that as a regression. Seed 3 is always clean, so an exit of `1` with `fail:` lines on stderr from a three-take render is a regression.
- `render-first` needs no `tape/`. If one exists, every line says `cached` and the summary says `rendered 0 of 160 shots`.
- A state's key and clips are named by its name in lower case with every run of other characters turned into a hyphen, so `results(SEA, 2026-12-12)` has `keys/results-sea-2026-12-12.png`. A move is named by its state and the words its action is found by.
- The stand-in draws each line as a box in rows of 33 pixels, 15 rows to a frame. A state with more rows stops the render with `error: the stand-in has no room to draw "<line>"`.
- The summary prints the tape path relative to the working directory, which is the project, so it is `tape` or `tape-b`.
- In a tall capture every take is near the window at once, and a take that has not decoded yet shows black or its first frame. Read the checks and badges, not the pictures. In a browser only the takes near the window load.
- `ls` on this machine is aliased to a tool that prefixes icons. Use `command ls` when you assert on file names.
