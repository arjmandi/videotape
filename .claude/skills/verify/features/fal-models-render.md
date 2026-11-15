# MiniMax H3 and Gemini Omni Flash 1.2 renders

`videotape render --story <name> --model minimax-h3 --takes N --out <tape> --cap-usd <cap>`, or `--model gemini-omni-flash-1.2`, renders the app's shots in that story with MiniMax H3 or Gemini Omni Flash 1.2 on fal into another tape of the project. Both film through the adapter wan3.0 films through, `videotape/hosted.py`, where one `FalModel` each holds what differs. The cap, the estimate line, the request recorded beside each take and the resume, `FAL_KEY` and its handling, the ledger, the sidecars, Qwen3-VL-8B's checks and the two calls at once work as [wan3-render.md](./wan3-render.md) says. This page holds what differs.

| | minimax-h3 | gemini-omni-flash-1.2 |
|---|---|---|
| Key | `minimax/h3/text-to-video` | `google/gemini-omni-flash/v1.2/text-to-video` |
| Move | `minimax/h3/image-to-video`, the first frame in `image_url` and the last in `end_image_url` | `google/gemini-omni-flash/v1.2/image-to-video`, the same two fields |
| Request | `resolution` `768P`, `aspect_ratio` `16:9` on a key only, `duration` 5, `prompt_expansion_mode` `disabled`, `seed` | `resolution` `720p`, `aspect_ratio` `16:9`, `duration` 5, no seed |
| Size | 1344x768 | 720p; fal states no pixel size |
| A five-second call | $0.30, at $0.06/s | $0.4395, at $0.0819/s plus $0.03 for the prompt |
| Prompt limit | 7,000 characters | 20,000 characters |
| Sound | no field | always on |

No paid run has been made with either model. The missing-key errors, the estimates and the tests below were driven. The paid journeys are recipes whose expected lines come from the code and from fal's schemas, so correct them on the first paid run.

## Sub-features

- `fal-no-key` rejects `--model minimax-h3` without `FAL_KEY` with `error: minimax-h3 needs FAL_KEY in the environment or the project's .env`, exit 1, before any network call and before writing anything. `gemini-omni-flash-1.2` says the same with its own name.
- `fal-estimate` prints the plan's estimate with no key: `videotape plan --story <name> --model minimax-h3`.
- `fal-requests` builds each model's key and move requests, bills an answer with no duration, writes the ledger line, stops at the cap, refuses a missing key and checks `FAL_KEY` in doctor, all proven by `uv run pytest tests/test_hosted.py`.
- `fal-size` keeps a 1344x768 tape at its size through its keys, moves, seams, crops, `tape.json` and dailies, and through publish's HEVC clips, proven by `uv run pytest tests/test_hosted.py tests/test_publish.py -k 1344`.
- `fal-paid` is the paid run into `<project>/tape-h3` or `<project>/tape-gemini`. Costs money, and waits for the user's cap.

## Driving it with vt-verify

Preconditions are [wan3-render.md](./wan3-render.md)'s, with the same rules for `FAL_KEY` and the cap.

- **No key.** Run `env -u FAL_KEY https_proxy=http://127.0.0.1:9 .claude/skills/verify/scripts/vt-verify run "$RUN" fal-no-key examples/contrail -- render --story terminal --model minimax-h3 --takes 1 --out tape-h3 --cap-usd 60`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is exactly `error: minimax-h3 needs FAL_KEY in the environment or the project's .env`. `command ls examples/contrail` shows no `tape-h3`.
- **Estimate.** Run `env -u FAL_KEY .claude/skills/verify/scripts/vt-verify run "$RUN" fal-plan examples/contrail -- plan --story terminal --model minimax-h3`. `.exit` is `0`, `.stderr` is empty, and the last two lines are `0 errors, 0 warnings` and `minimax-h3: 160 shots, 160 to 640 calls, $48.00 to $192.00 at $0.06/s`. With `--model gemini-omni-flash-1.2` the last line is `gemini-omni-flash-1.2: 160 shots, 160 to 640 calls, $70.32 to $281.28 at $0.0819/s plus $0.03 a call for the prompt`.
- **Requests, price and cap.** Run `uv run pytest tests/test_hosted.py -v`. Every test passes, each once per model: `test_a_key_and_a_move_send_fal_the_models_own_fields`, `test_an_answer_without_a_duration_is_billed_for_the_five_seconds_the_request_asked_for`, `test_a_render_films_every_shot_on_fal_and_writes_each_calls_price_in_the_ledger`, which reads the estimate line `minimax-h3: 11 shots, 11 calls, $3.30 at $0.06/s, cap $20.00, $0.00 spent` and sees two calls at once, `test_a_render_stops_at_the_cap_before_the_call_that_would_pass_it`, `test_a_model_on_fal_without_fal_key_says_so_and_sends_nothing`, `test_doctor_checks_fal_key_for_a_project_on_the_model` and `test_plan_estimates_the_model_and_warns_of_a_prompt_past_its_limit`, and then `test_a_1344x768_tape_keeps_its_size_through_its_keys_its_seams_and_its_dailies`.
- **Size.** Run `uv run pytest tests/test_publish.py -k 1344 -v`. `test_a_1344x768_tape_is_published_at_its_own_size` renders the starter at 1344x768 and publishes it, and every HEVC clip in the app is 1344x768.
- **Paid run.** As [wan3-render.md](./wan3-render.md)'s, with `--model minimax-h3 --out tape-h3` or `--model gemini-omni-flash-1.2 --out tape-gemini`, and the cap agreed from this page's estimate. Afterwards `.venv/bin/python -c 'import json; t = json.load(open("examples/contrail/tape-h3/tape.json")); print(t["size"], t["fps"])'` prints the size and rate the clips came back at, `{'width': 1344, 'height': 768}` for minimax-h3 if fal's 768P is what the research says. Record the first answer of each mode in a sidecar's `response`, and replace the fixtures that `tests/fixtures/fal-models.txt` names with them.
- **Proof.** As [wan3-render.md](./wan3-render.md)'s.

## Gotchas

- Neither model's answer carries a duration, so the ledger's `duration` is the five seconds the request asked for, and `usd` is that times the rate, plus $0.03 for gemini-omni-flash-1.2.
- fal bills gemini-omni-flash-1.2's prompt at $1.50 per million tokens, and no answer says how many. The price counts the most a prompt at fal's 20,000-character limit can cost, $0.03 a call, so the estimate, the cap and the ledger never count less than fal bills, and count up to $0.03 a call more. Contrail's longest prompt, 1,121 characters, costs at most $0.0017. fal's page says a move's two images are not billed.
- fal takes no seed for gemini-omni-flash-1.2. A take is still named by its seed, and a render run again reuses the take on disk, so a rerun is free and gives the same tape. A take filmed again, after its clip and its request record are both gone, gets new pixels.
- minimax-h3's prompt limit is the 7,000 characters fal's article on H3 gives, where its schema allows 50,000. `VT307` warns past 7,000.
- A move of minimax-h3 takes its size from the key image it starts on, since its image-to-video has no aspect ratio. In a tape of its own, every key is 1344x768.
- gemini-omni-flash-1.2's clips carry sound, and minimax-h3's may. The dailies play muted and publish encodes without sound, but TapePlayer's `AVPlayer` in `clients/macos/TapePlayer/Projector.swift` is not muted, so `videotape play` on such a tape should play each move's sound. No run has heard it.
- `tests/fixtures/minimax-h3-*.json` and `tests/fixtures/gemini-omni-flash-1.2-*.json` follow fal's schemas, not a paid call, as `tests/fixtures/fal-models.txt` says.
- A minimax-h3 or gemini-omni-flash-1.2 tape cost money. Never delete it, its `takes/`, or its lines in the project's `ledger.jsonl`.
