# GPU render

`videotape render <dir> --model wan2.2-5b --checks qwen3-vl-8b --takes 3` makes Wan 2.2 draw every pixel of the tape, which needs one H100-class CUDA GPU. `scripts/runpod-render <dir> --takes 3 --cap-usd <n>` rents that GPU on Runpod, copies the repo and any cached `tape/` there, renders, copies `tape/` back, deletes the pod, and appends a pod line to `<dir>/tape/ledger.jsonl`. `--dry-run` prints the whole plan and creates nothing. On a Mac, `--model wan2.2-5b` stops with an `error:` line before writing anything. The dailies page shows, per key, the seams the player cuts across, the render time, and the ledger totals in GPU seconds, pod hours and dollars.

## Sub-features

- `gpu-dry-run` prints the plan for the surf shop and for the cafe fixture without a key or a pod: GPU, price, cap, self-destruct deadline, image, disk, env names, create body, start command, setup and render commands. Exit 0, last line `dry run: nothing was created.`
- `gpu-no-key` refuses a real run without `RUNPOD_API_KEY` with `error:` and exit 2, and refuses a directory without `screenplay.py`.
- `gpu-local` rejects `--model wan2.2-5b` on this Mac with `error: wan2.2-5b needs a CUDA GPU with about 80 GB, and this machine has Apple silicon (MPS) only; rent one with scripts/runpod-render`, exit 1, and writes no `tape/`. Without the wan extra it says `error: wan2.2-5b needs the wan extra; install it with uv sync --extra wan` instead.
- `gpu-smoke` is the first paid run: the cafe fixture with one take per shot, which exercises text-to-video, two image-to-video moves, and one first-and-last-frame move. Costs money.
- `gpu-full` is the paid surf shop run with three takes per shot, after which TapePlayer plays the tape with every journey from [player.md](./player.md). Costs money.
- `gpu-ledger` records one `take` line per filmed take and one `pod` line per pod session in `<dir>/tape/ledger.jsonl`, and `videotape dailies <dir>` rewrites the page with the totals.

## How to get to it (user POV)

- Run `scripts/runpod-render examples/surf_shop --takes 3 --cap-usd 20 --dry-run` from the repo root to read the plan.
- Export `RUNPOD_API_KEY`, then run the same command without `--dry-run`. Watch the pod id it prints, then the setup and render logs. When it ends, open `examples/surf_shop/tape/dailies.html` and `open clients/macos/build/TapePlayer.app --args examples/surf_shop/tape`.
- Run `videotape render examples/surf_shop --model wan2.2-5b` on the Mac to see why it needs the pod.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `.claude/skills/verify/scripts/vt-verify launch wan` has printed `ready:` for `gpu-local`. A plain `launch` uninstalls the wan extra again.
- For `gpu-smoke` and `gpu-full`: the user named the cap in this session, `RUNPOD_API_KEY` is exported in the shell that runs the drive, and nothing else of the user's is running on Runpod. Never run them on your own initiative. Each creates one pod that bills from creation to deletion.

- **Dry run.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" gpu-dry-run -- scripts/runpod-render examples/surf_shop --takes 3 --cap-usd 20 --dry-run`. `.exit` is `0`, `.stderr` is empty, and `.stdout` starts with `screenplay    examples/surf_shop, 3 takes per shot`, has a `gpu` line with `NVIDIA H100 80GB HBM3, secure cloud, $3.99/h (assumed, catalog read of 2026-11-09; set RUNPOD_API_KEY for the live price)`, a `cap` line with `$20.00 buys 5.01 h; the pod self-destructs after 17445 s`, a `pod` line with `host CUDA >= 13.0, 160 GB container disk, port 22/tcp`, a `render` line ending `--model wan2.2-5b --checks qwen3-vl-8b --takes 3`, and ends with `dry run: nothing was created.` Run it again as `gpu-dry-run-cafe` with `.claude/skills/verify/fixtures/cafe --takes 1 --cap-usd 5`. The `cap` line reads `$5.00 buys 1.25 h; the pod self-destructs after 3911 s` and the `render` line ends `--takes 1`. The first dry run also prints `made an SSH key for pods at .runpod/id_ed25519` once.
- **No key.** Run `env -u RUNPOD_API_KEY .claude/skills/verify/scripts/vt-verify exec "$RUN" gpu-no-key -- scripts/runpod-render examples/surf_shop --cap-usd 20`. `.exit` is `2` and `.stderr` is `error: RUNPOD_API_KEY is not set; export it, or pass --dry-run to see the plan`. With `examples/nowhere --cap-usd 20 --dry-run` instead, `.exit` is `2` and `.stderr` starts `error: no screenplay.py in examples/nowhere`.
- **Local.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" gpu-local -- render examples/surf_shop --model wan2.2-5b`. `.exit` is `1`, `.stderr` is `error: wan2.2-5b needs a CUDA GPU with about 80 GB, and this machine has Apple silicon (MPS) only; rent one with scripts/runpod-render`, and `.stdout` is empty. `command ls examples/surf_shop/tape` shows no new files, or `No such file` when no tape existed.
- **Smoke (paid).** Run `time .claude/skills/verify/scripts/vt-verify exec "$RUN" gpu-smoke -- scripts/runpod-render .claude/skills/verify/fixtures/cafe --takes 1 --cap-usd 5`. `.stdout` shows the plan, then `pod <id> created at <time>`, the pod status lines until `RUNNING`, the setup log through `df -h /workspace`, the four shot lines of `videotape render` each ending `rendered 1 take, kept take 1`, `render exited 0` (or `1` with `fail:` lines on stderr when a kept take fails its checks, which is a model result, not a script failure), `copied .claude/skills/verify/fixtures/cafe/tape back`, and `pod <id> deleted, confirmed gone; <seconds> s, $<cost> at $<price>/h`. Then `grep -c '"kind": "take"' .claude/skills/verify/fixtures/cafe/tape/ledger.jsonl` prints `4` and `grep -c '"kind": "pod"'` prints `1`. Run `.claude/skills/verify/scripts/vt-verify run "$RUN" gpu-smoke-check -- check .claude/skills/verify/fixtures/cafe/tape --checks qwen3-vl-8b` on the Mac, which reads the three keys. Screenshot `.claude/skills/verify/fixtures/cafe/tape/dailies.html` as `gpu-smoke-dailies` and read the seam lines under each key.
- **Full (paid).** Same as the smoke with `examples/surf_shop --takes 3 --cap-usd 20`. Six shot lines end `rendered 3 takes, kept take N`. Then build TapePlayer with `vt-verify player-build "$RUN"` and ask the user to drive the journeys in [player.md](./player.md) on `examples/surf_shop/tape`.
- **Ledger.** After any render, `tail -n 1 <dir>/tape/ledger.jsonl` is a JSON object with `kind`, `at` and, for a take, `model`, `shot`, `mode`, `seed`, `seconds` and `gpu`, or, for a pod, `pod`, `gpu`, `usd_per_hour`, `started`, `stopped`, `seconds` and `usd`. Run `.claude/skills/verify/scripts/vt-verify run "$RUN" gpu-ledger -- dailies <dir>`. `.exit` is `0` and `.stdout` is one line starting `wrote <dir>/tape/dailies.html with {"takes": ` that lists `gpu_seconds`, `pods`, `pod_hours` and `usd`. `grep -o 'Ledger: [^<]*' <dir>/tape/dailies.html` prints the same totals, such as `Ledger: 3.4 GPU seconds, 0.0 pod hours, $0.00.`
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` or `.stderr` lines. For a paid run also cite the pod id, the `deleted, confirmed gone` line, the ledger line counts, the check output and the dailies screenshot.

## Gotchas

- A paid run starts billing when `pod <id> created` prints and stops when the pod is deleted. The script deletes the pod in its `finally` and confirms with a read. If it prints `NOT CONFIRMED DELETED`, open the Runpod console now.
- The pod arms a timer at boot that terminates it at the self-destruct deadline even if this Mac dies. Killing the script early still deletes the pod through its `finally`; a hard kill of the Mac does not, and then the pod runs until the deadline, which the cap paid for.
- A keyless dry run assumes $3.99/h, the secure-cloud list price read on 2026-11-09. With `RUNPOD_API_KEY` set, a dry run reads the live price and stock and still creates nothing. `error: no NVIDIA H100 80GB HBM3 with CUDA >= 13.0 in the secure cloud right now` means the catalog shows no stock; `--gpu "NVIDIA H200"` is the next option, at $5.29/h.
- The host CUDA floor is 13.0 because `uv.lock` pins torch 2.15.0, whose Linux wheels bundle the CUDA 13 runtime. The image's own CUDA version does not matter; the venv brings its own.
- The script copies `<dir>/tape` to the pod before rendering, so cached takes render again only when a prompt, key or setting changed. Delete `<dir>/tape/takes` to force a full re-render; that costs money.
- The tape comes back in the failure path too, so a run that dies after some takes keeps them, and a rerun resumes from the cache.
- Each take's seconds include loading that checkpoint's pipelines the first time a mode runs, so the first text-to-video take and the first first-and-last-frame take read long.
- Time and cost are guesses until a run has measured them: the cafe smoke run about 25 to 40 minutes and $2 to $3, the full surf shop about 50 to 70 minutes and $3.50 to $5, at $3.99/h. Caps of $5 and $20 leave room.
- `MAX_DIFFERENCE` of 0.05 for seams was set on stand-in clips. Read the seam differences in the Keys section of the smoke run's dailies before trusting it on real model frames.
- `ls` on this machine is aliased to a tool that prefixes icons. Use `command ls` when you assert on file names.
