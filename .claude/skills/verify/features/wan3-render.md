# Wan 3.0 render

`videotape render examples/surf_shop --model wan3.0 --checks qwen3-vl-8b --takes 3 --out examples/surf_shop/tape-wan3` renders the same ten shots as the 5B from the same prompts, with Wan 3.0 on fal, as a yardstick for the 5B tape. Each key is a call to `alibaba/wan-3.0/text-to-video`. Each move is a call to `alibaba/wan-3.0/image-to-video` whose first and last frames are pinned to the kept Wan 3.0 keys of the scene it leaves and the scene it lands on, so every pixel of the tape is Wan 3.0's. Every call asks for 720p, 16:9, five seconds, no audio and no prompt expansion. fal bills $0.10 a second at 720p, so a call is about $0.50 and the surf shop's thirty calls are about $15. Before its first uncached call the render prints one line with the number of calls and their price. The key comes from `FAL_KEY` in the environment and is never printed. Each call adds a ledger line with its seconds, the duration fal reports and its dollars, and the take's sidecar keeps fal's raw answers. Qwen3-VL-8B scores the keys on this Mac, and TapePlayer plays the tape as it plays any other.

## Sub-features

- `wan3-no-key` rejects `--model wan3.0` without `FAL_KEY` with `error: wan3.0 needs FAL_KEY in the environment`, exit 1, before any network call and before writing anything.
- `wan3-requests` builds each call from the shot alone, reads a recorded answer with no network, prices it, and prints the price line, all proven by `uv run pytest tests/test_wan3.py tests/test_fal.py`.
- `wan3-paid` is the paid run of thirty calls into `examples/surf_shop/tape-wan3`. Costs money, and waits for the user's cap.
- `wan3-cached` reruns the same command. It prints no price line, makes no call, and adds no ledger line.
- `wan3-ledger` records one take line per call with `request_id`, `seconds`, `duration` and `usd`, and the dailies total adds those dollars.
- `wan3-player` plays `examples/surf_shop/tape-wan3` in TapePlayer, whose window takes the tape's own size.
- `wan3-fixture` replaces the hand-written answers in `tests/fixtures/` with real ones from the paid run.

## How to get to it (user POV)

- Export `FAL_KEY`, run `uv sync --extra qwen` once, then run `videotape render examples/surf_shop --model wan3.0 --checks qwen3-vl-8b --takes 3 --out examples/surf_shop/tape-wan3` from the repo root.
- Then run `videotape compare examples/surf_shop/tape examples/surf_shop/tape-wan3` and open `examples/surf_shop/compare.html`, as [compare.md](./compare.md) says.
- Then run `open clients/macos/build/TapePlayer.app --args examples/surf_shop/tape-wan3`.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- For `wan3-paid`, the user named a cap of at least $15.12 in this session, `FAL_KEY` is exported in the shell that runs the drive, and `.claude/skills/verify/scripts/vt-verify launch qwen` has printed `ready:`. Never run it on your own initiative, and never ask for the key or type it into a command.

- **No key.** Run `env -u FAL_KEY https_proxy=http://127.0.0.1:9 .claude/skills/verify/scripts/vt-verify run "$RUN" wan3-no-key -- render examples/surf_shop --model wan3.0 --checks qwen3-vl-8b --takes 3 --out examples/surf_shop/tape-wan3`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is exactly `error: wan3.0 needs FAL_KEY in the environment`. The proxy points at a closed port, so a network call would have failed with another error first. `command ls examples/surf_shop` shows no `tape-wan3`.
- **Requests and answers.** Run `uv run pytest tests/test_wan3.py tests/test_fal.py -v`. Every test passes, among them `test_a_key_is_text_to_video_from_its_own_prompt_at_720p_without_sound_or_prompt_expansion`, `test_a_move_is_image_to_video_from_the_key_it_starts_on_to_the_key_it_lands_on`, `test_a_recorded_response_reads_into_a_video_and_a_receipt_without_the_network`, `test_a_failed_submit_is_never_sent_again`, `test_the_key_never_appears_in_an_error` and `test_wan3_renders_every_pixel_of_its_tape_and_pins_each_move_to_its_own_keys`, which renders the surf shop through a fake fal and checks that each move's two images are the bytes of its own two keys.
- **Paid run.** Before it, record `grep -c '"kind": "take"' examples/surf_shop/tape-wan3/ledger.jsonl`, or `0` when there is no tape yet. Run `time .claude/skills/verify/scripts/vt-verify run "$RUN" wan3-paid -- render examples/surf_shop --model wan3.0 --checks qwen3-vl-8b --takes 3 --out examples/surf_shop/tape-wan3`. The first `.stdout` line is `wan3.0: 30 calls, $15.00 at $0.10/s` on a first run. Nothing else prints until the render ends. Then come ten shot lines, five `key <scene>` lines and then five move lines, each ending `rendered 3 takes, kept take N`, and `rendered 10 of 10 shots -> examples/surf_shop/tape-wan3`. `.exit` is `1` when a kept take fails its checks, with `fail:` lines on `.stderr`, which is a model result, not a script failure. The take count in the ledger rose by 30. Run `env | grep -c '^FAL_KEY='` to confirm the key was set, then `grep -rlF -e "$FAL_KEY" examples/surf_shop/tape-wan3 "$RUN"`, which must print nothing and exit 1.
- **Cached.** Run the same render again as `wan3-cached`. `.stdout` has no `wan3.0:` line, every shot line ends `cached, kept take N` with the same N, the last line is `rendered 0 of 10 shots -> examples/surf_shop/tape-wan3`, and the ledger's take count is unchanged.
- **Ledger.** `tail -n 1 examples/surf_shop/tape-wan3/ledger.jsonl` is a JSON object with `kind` `take`, `model` `wan3.0`, `shot`, `mode`, `seed`, `seconds`, `gpu` `fal`, `request_id`, `duration` and `usd`, where `usd` is `duration` times 0.10. `.venv/bin/python -c 'import json; t = json.load(open("examples/surf_shop/tape-wan3/tape.json")); print(t["size"], t["fps"])'` prints the size the clips came back at, which fal's docs do not state for 720p 16:9. `grep -o 'Ledger: [^<]*' examples/surf_shop/tape-wan3/dailies.html` shows `0.0 pod hours` and the dollars of the thirty calls.
- **Player.** Build with `.claude/skills/verify/scripts/vt-verify player-build "$RUN"`, then ask the user to run `open clients/macos/build/TapePlayer.app --args examples/surf_shop/tape-wan3` and drive the journeys in [player.md](./player.md) whose buttons the checks found. The window takes the tape's shape. A button that was not found has no hotspot, so report that journey as blocked by the model, not by the player.
- **Fixture.** Copy the `response` object of one text-to-video and one image-to-video sidecar in `examples/surf_shop/tape-wan3/takes/` over `tests/fixtures/wan3.0-text-to-video.json` and `tests/fixtures/wan3.0-image-to-video.json`, as `tests/fixtures/wan3.0.txt` says, update the values the tests read from them, and run `uv run pytest tests/test_wan3.py tests/test_fal.py`.
- **Proof.** For `wan3-no-key` cite `.cmd`, `.exit` and `.stderr`. For the paid run cite the price line, the ten shot lines, `.exit`, the `time` output, the ledger counts, the empty key grep, and the compare from [compare.md](./compare.md).

## Gotchas

- The key is only ever read from the environment. `vt-verify run` records the command in `.cmd` and `vt-verify exec` records its whole argv, so never pass the key as an argument to either.
- A submit is sent once and never again, because a second one could pay twice. When a submit or its result fails, the render stops with an `error:` line that names the request when fal gave one. A rerun resumes from the cache and submits only the call that failed, which fal may have billed already.
- The price line counts every take not in the cache. A move counts in full when a key it touches will render again. It assumes five seconds a call, and the ledger then records the duration fal reports.
- The two key images go to fal inline as base64 PNG data URIs of about 1.3 MB each. fal's API page says file inputs accept them, and its storage page discourages them above a few KB. When fal rejects a move's request, suspect its size first.
- fal's safety checker stays on, its default, because turning it off needs account authorization.
- `--checks qwen3-vl-8b` needs the qwen extra. Without it the command stops with an `error:` line before any call. Qwen loads, and on a first run downloads 17.5 GB of weights, after the first key take, so a failed download stops the render after that call was paid for. Run `vt-verify launch qwen` and doctor first, and look for `weights cached` in its `info qwen` line.
- `examples/surf_shop/tape-wan3` is gitignored and exists only in the checkout that rendered it. It cost money, so never delete it or its `takes/`.
- Wan 3.0's takes are only compared with the 5B's, never trained on.
