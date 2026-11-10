# Compare

`videotape compare <tapeA> <tapeB>` puts two tapes of one screenplay side by side, so a developer can tell whether a missing button or a move that dissolves comes from the model or from how videotape asks it. It reads each tape's `dailies.json`, `tape.json` and `ledger.jsonl` and writes `compare.html` in the folder the two tapes share, such as `examples/surf_shop/compare.html` for `examples/surf_shop/tape` and `examples/surf_shop/tape-wan3`. Shots match by title. Each shot shows both kept takes looping side by side. A key also shows its key image, how many of its buttons were found, and every button as `found at` a box or `not found` and every line and label as read with its CER. A move also shows its seams, five stills at 0, 25, 50, 75 and 100% of the kept clip, and how much each frame differs from the next on average. Each shot ends with its kept take's render time and what all its takes cost. The top of the page gives each tape's model, size, fps, takes, ledger dollars, take cost, buttons found and lines read exactly. The command prints one line per tape and the path it wrote.

## Sub-features

- `compare-stand-ins` compares two stand-in tapes of the surf shop, prints an `A` line, a `B` line and a `wrote` line, and exits 0.
- `compare-5b` compares a copy of the paid Wan 2.2 5B tape with a stand-in tape. The `A` line reads `wan2.2-5b`, `1280x704 at 24 fps`, `30 takes`, `$3.48` and `buttons found 3 of 5`.
- `compare-page` shows the header with both tapes' facts, then ten shot cards, five keys and then five moves, in light and dark.
- `compare-unfound` shows a button the checks did not find as `not found` in red, with a red `N of M buttons found.` line, and counts it in the header.
- `compare-moves` writes five PNG stills per move per tape into `compare-frames/a/` and `compare-frames/b/` and shows them under each move with its seams and its frame-to-frame difference.
- `compare-cost` prices a take billed per call at its bill, a take on a rented pod at its GPU seconds and the pod's price without setup, and a take on this machine at $0.00.
- `compare-wan3` compares the 5B tape with the Wan 3.0 tape from the paid run in [wan3-render.md](./wan3-render.md).
- `compare-errors` rejects a folder that is not a rendered tape with `error:` and exit 1.

## How to get to it (user POV)

- Render a second tape beside the first with `videotape render examples/surf_shop --model <name> --out examples/surf_shop/tape-<name>`, then run `videotape compare examples/surf_shop/tape examples/surf_shop/tape-<name>` from the repo root and open `examples/surf_shop/compare.html`.
- Each tape's name in the header links to its own `dailies.html`.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `examples/surf_shop/tape-b` holds the stand-in render from `render-out` in [render.md](./render.md).
- For `compare-5b`, `examples/surf_shop/tape` is a copy of the paid 5B tape. In a fresh checkout, copy it from the checkout that rendered it with `cp -R <that checkout>/examples/surf_shop/tape examples/surf_shop/tape`. Never render it again, because it cost $3.48 and it is the yardstick.

- **Two stand-in tapes.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" render-out-one-take -- render examples/surf_shop --model stand-in --takes 1 --out examples/surf_shop/tape-c`, which exits 1 with the seven `fail:` lines of `render-takes`. Then run `.claude/skills/verify/scripts/vt-verify run "$RUN" compare-stand-ins -- compare examples/surf_shop/tape-b examples/surf_shop/tape-c`. `.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:
  ```
  A examples/surf_shop/tape-b  stand-in  1280x704 at 24 fps  30 takes  $0.00  buttons found 5 of 5
  B examples/surf_shop/tape-c  stand-in  1280x704 at 24 fps  10 takes  $0.00  buttons found 5 of 5
  wrote examples/surf_shop/compare.html with 50 stills in examples/surf_shop/compare-frames
  ```
  Screenshot it now with `.claude/skills/verify/scripts/vt-verify screenshot "$RUN" compare-stand-ins examples/surf_shop/compare.html 7000`, because the next compare writes the same file.
- **The 5B against a stand-in.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" compare-5b -- compare examples/surf_shop/tape examples/surf_shop/tape-b`. `.exit` is `0` and `.stdout` is exactly:
  ```
  A examples/surf_shop/tape  wan2.2-5b  1280x704 at 24 fps  30 takes  $3.48  buttons found 3 of 5
  B examples/surf_shop/tape-b  stand-in  1280x704 at 24 fps  30 takes  $0.00  buttons found 5 of 5
  wrote examples/surf_shop/compare.html with 50 stills in examples/surf_shop/compare-frames
  ```
  It takes about 3 seconds. `grep -c '<section class="shot"' examples/surf_shop/compare.html` prints `10`, and `command ls examples/surf_shop/compare-frames/a | wc -l` and the same for `b` print `25`.
- **Page.** Run `.claude/skills/verify/scripts/vt-verify screenshot "$RUN" compare-5b examples/surf_shop/compare.html 7000` and read `$RUN/compare-5b.light.png` and `$RUN/compare-5b.dark.png`. The page is headed `Brushstroke Surf Co. compare`. Under it are two cards, `A. tape` and `B. tape-b`. The A card lists `wan2.2-5b, checked by qwen3-vl-8b`, `1280x704 at 24 fps`, `30 takes filmed in 2727.7 s, 1 pod for 0.873 h with setup`, `$3.48 in the ledger; the takes cost $3.02, GPU time at the pod's $3.99/h, setup excluded` and `3 of 5 buttons found, 8 of 15 lines and labels read exactly`. Then come ten shot cards headed like `1. key welcome (text-to-video)` and `6. welcome -> entrance "Enter shop" (first-and-last-frame)`, each with an A side and a B side. Each side has the tape's name, a model badge and a `kept take N` badge, plus `fails checks` in red when its checks fail. A key side shows the looping kept take labelled `kept take` beside the image labelled `key, its last frame`, then its checklist. A move side shows the looping kept take over a strip of five stills labelled `0%` to `100%`. The dark capture has a dark background and light text.
- **Unfound buttons.** In `compare-5b`, `2. key entrance` has `1 of 3 buttons found.` in red on the A side, and `button "I have an account"` and `button "Browse as guest"` each read `not found` in red. `grep -o 'not found</span>' examples/surf_shop/compare.html | wc -l` prints `2`. The B side reads `3 of 3 buttons found.` Keys without buttons, `login` and `gallery`, read `No buttons to find.`
- **Moves.** In `compare-5b`, `grep -o 'Seams: [^<]*' examples/surf_shop/compare.html` prints ten lines, A then B for each move, starting `Seams: leaves welcome by 0.004, enters entrance by 0.033.` and `Seams: leaves welcome by 0.004, enters entrance by 0.004.` `grep -o 'Each frame differs from the next by [^<]*'` prints ten lines. The 5B's run from 0.0072 to 0.0488 and the stand-in's from 0.0005 to 0.0022. The 5B's `welcome -> entrance` stills at 25, 50 and 75% show the entrance lettering laid over the shop front, which is the dissolve.
- **Cost.** Every shot side ends with a line like `Kept take rendered in 89.4 s. 3 takes in 415.2 s for $0.46, GPU time at the pod's $3.99/h, setup excluded.` on a 5B side and `Kept take rendered in 0.2 s. 3 takes in 0.6 s for $0.00, rendered on this machine.` on a stand-in side. `grep -o 'Kept take rendered in' examples/surf_shop/compare.html | wc -l` prints `20`. A side whose takes were billed per call ends `as billed per call.`, such as `for $1.51` for three takes of 5.04 s each.
- **Wan 3.0.** After the paid run in [wan3-render.md](./wan3-render.md), run `.claude/skills/verify/scripts/vt-verify run "$RUN" compare-wan3 -- compare examples/surf_shop/tape examples/surf_shop/tape-wan3` and screenshot it as `compare-wan3` with a height of `7000`. The B line reads `wan3.0` and the size the clips came back at, such as `1280x720 at 24 fps`, and `30 takes  $15.12` when every clip was 5.04 s. Read which buttons each tape found and how each move's stills travel or dissolve, and report both, shot by shot.
- **Errors.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" compare-errors -- compare examples/surf_shop/tape examples/surf_shop/tape-none`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is exactly `error: no tape.json in examples/surf_shop/tape-none; render a screenplay into it first`.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` or `.stderr` lines, both screenshots for `compare-stand-ins` and `compare-5b`, and the `grep` counts.

## Gotchas

- Every compare writes the same `compare.html` and `compare-frames/` in the folder the two tapes share, so screenshot each page before the next compare.
- The tapes, `compare.html` and `compare-frames/` under `examples/` are gitignored. `examples/surf_shop/tape` and `examples/surf_shop/tape-wan3` cost money. Never delete them or their `takes/`.
- A key's checklist is the key's own checks, which `videotape check` can rewrite. A move's seams are its kept take's.
- The header's ledger dollars include a pod's setup. The take cost does not, so the 5B reads `$3.48` and `$3.02`.
- The frame-to-frame difference is on the scale of the seams, from 0 to 1. A move that holds still and then dissolves reads low. Look at the stills to tell a dissolve from a camera move.
- `ls` on this machine is aliased to a tool that prefixes icons. Use `command ls` when you assert on file names.
