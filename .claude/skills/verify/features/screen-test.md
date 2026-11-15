# Screen test

`uv run scripts/screen-test examples/contrail --models wan3.0,minimax-h3,gemini-omni-flash-1.2 --stories terminal,posters --cap-usd 60`, run from the repo root, picks the model that draws Contrail best. It films the keys of the eight states in `SAMPLER`, which together show all ten element types, on each model in each story: two takes of each key, both filmed even when the first passes, and no move. Each model's takes in each story go into a tape of their own, `tapes/screen-test/<model>/<story>/` in the project, and the eye of each model, Qwen3-VL-8B and Claude, reads every take. Before any call it prints the estimate, and it stops before any call when the estimate passes the cap or an API key is missing. One cap holds for the whole screen test, and every call and read goes into the project's `ledger.jsonl`. It writes `tapes/screen-test/report.html` and prints the pick, and it never edits `pyproject.toml`. Run again, it films no take on disk and reads no picture whose read is cached, so the report is rebuilt for free.

No paid run has been made. The estimate, the three refusals and the tests below were driven. The paid journeys are recipes whose expected lines come from the code, so correct them on the first paid run.

## Sub-features

- `screen-estimate` prints a line per model, its calls at its price on fal and its reads by Claude at the most a read of its picture size costs, then the total against the cap. `--estimate` stops there with exit 0 and needs no API key.
- `screen-over-cap` stops with `VT402` before the first call when the estimate passes `--cap-usd`, and names the cap the run needs.
- `screen-no-cap` stops with `VT402` before the first call when no `--cap-usd` is given.
- `screen-no-key` stops with `VT104` before any call when `FAL_KEY` is missing, and when `ANTHROPIC_API_KEY` is missing. Without the qwen extra it stops with `VT105` first.
- `screen-sampler` stops with `VT212` when the plan lacks a state that `SAMPLER` names.
- `screen-tests` is `uv run pytest tests/test_screen_test.py`, which runs the whole screen test on stand-ins with fal's names and prices: both takes of every key, the ledger, the rerun, one cap across the tapes, the report, the marks and the pick.
- `screen-every` is the render option the screen test films with, proven by `uv run pytest tests/test_render.py -k "every_films or keys_alone"`.
- `screen-paid` is the paid run. Costs money, and waits for the user's cap.
- `screen-rerun` runs the same command again after the paid run, and films and reads nothing.
- `screen-report` is what `report.html` must show.
- `screen-marks` is the calibration: a person ticks each element of wan3.0's terminal takes that is drawn right, downloads `marks.json`, and runs again with `--marks marks.json`.

## How to get to it (user POV)

- From the repo root, read the estimate first: `uv run scripts/screen-test examples/contrail --models wan3.0,minimax-h3,gemini-omni-flash-1.2 --stories terminal,posters --estimate`.
- Approve a cap at least the estimate's total, then run the same command with `--cap-usd <cap>` in place of `--estimate`.
- Open `examples/contrail/tapes/screen-test/report.html` from disk. It needs no server.
- Under Calibration, tick each element drawn right on each of wan3.0's 16 terminal takes, press Download marks.json, and run the same command again with `--marks <path to marks.json>`.
- Set the pick by hand: `model = "<pick>"` in `[tool.videotape]` of `examples/contrail/pyproject.toml`.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `$RUN` is set. The commands below hold commas, so pass them whole; in zsh, write them out rather than through an unquoted variable, which zsh does not split.
- For `screen-paid`, `screen-rerun` and `screen-marks`: the user approved a cap in this session, at least the estimate's total; `FAL_KEY` and `ANTHROPIC_API_KEY` are exported in the shell that runs the drive; and `.claude/skills/verify/scripts/vt-verify launch qwen` has printed `ready:`, on a Mac with Apple silicon or a machine with a CUDA GPU, with the 17.5 GB of Qwen3-VL-8B's weights cached or room to download them. Never run a paid journey on your own initiative, and never ask for a key or type it into a command.

- **Estimate.** Run `env -u FAL_KEY -u ANTHROPIC_API_KEY .claude/skills/verify/scripts/vt-verify exec "$RUN" screen-estimate -- uv run scripts/screen-test examples/contrail --models wan3.0,minimax-h3,gemini-omni-flash-1.2 --stories terminal,posters --cap-usd 60 --estimate`. `.exit` is `0`, `.stderr` holds nothing of the script's, and `.stdout` is exactly:

  ```
  screen test of contrail 0.1.0: 8 keys, 2 takes each, in terminal and posters, on wan3.0, minimax-h3 and gemini-omni-flash-1.2
  wan3.0: 32 calls, $16.00 at $0.10/s, and 32 reads by claude-opus-5-5 of 1280x720 pictures, at most $5.50; at most $21.50 in all
  minimax-h3: 32 calls, $9.60 at $0.06/s, and 32 reads by claude-opus-5-5 of 1344x768 pictures, at most $5.52; at most $15.12 in all
  gemini-omni-flash-1.2: 32 calls, $14.06 at $0.0819/s plus $0.03 a call for the prompt, and 32 reads by claude-opus-5-5 of 1280x720 pictures, at most $5.50; at most $19.56 in all
  the screen test: 96 takes, at most $56.18, under the cap of $60.00
  ```

- **Over the cap.** Run the same with `--cap-usd 50` in place of `--cap-usd 60 --estimate`, and `https_proxy=http://127.0.0.1:9` after `env`, as `screen-over-cap`. `.exit` is `1`, `.stdout` is the estimate with its last line ending `past the cap of $50.00`, and `.stderr` ends with `error VT402 before the first call: the screen test may cost $56.18, which passes the cap of $50.00`, `next: run it with a cap of at least $56.18, as in:` and the command with `--cap-usd 56.18`. `command ls examples/contrail` shows no `tapes`.
- **No cap.** Run it with no `--cap-usd`, as `screen-no-cap`. `.exit` is `1`, and `.stderr` ends with `error VT402 before the first call: wan3.0, minimax-h3, gemini-omni-flash-1.2 and claude-opus-5-5 bill per call, and no cap is set` and a `next:` that names `--cap-usd 56.18`.
- **No key.** Run it with `--cap-usd 60` and `FAL_KEY` unset, as `screen-no-key`. `.exit` is `1`, `.stdout` is the estimate, and `.stderr` ends with `error VT104 .env: wan3.0 needs FAL_KEY, and it is not in the environment or .env` and `fix: copy .env.example to .env and set FAL_KEY there, or export it`. With `FAL_KEY` set and the qwen extra installed but no `ANTHROPIC_API_KEY`, it is Claude's `VT104` instead; without the qwen extra it is `VT105` for qwen3-vl-8b. No `tapes/screen-test` folder appears.
- **Tests.** Run `uv run pytest tests/test_screen_test.py -v`. All 25 pass, among them `test_it_films_both_takes_of_each_sampled_key_on_each_model_in_each_story_and_books_every_call`, `test_run_again_it_films_nothing_reads_nothing_and_writes_the_same_report`, `test_one_cap_holds_for_the_whole_screen_test_and_counts_what_its_other_tapes_spent`, `test_the_report_tallies_each_element_type_on_each_model_in_each_story_by_check`, `test_the_calibration_lists_each_element_of_wan3s_terminal_takes_with_a_checkbox_and_downloads_them`, `test_marks_that_agree_with_the_checks_less_than_90_percent_withhold_the_pick` and `test_the_pick_has_the_most_element_types_at_the_bar_then_the_fewest_invented_controls_then_the_lowest_cost`. No test reaches the network. Then run `uv run pytest tests/test_render.py -k "every_films or keys_alone" -v`; both pass.
- **Paid run.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" screen-paid -- uv run scripts/screen-test examples/contrail --models wan3.0,minimax-h3,gemini-omni-flash-1.2 --stories terminal,posters --cap-usd <cap>`. `.stdout` starts with the estimate. Then, for each model and story in that order, a line `<model> in <story>: 8 keys, 2 takes each, read by qwen3-vl-8b and claude-opus-5-5 -> examples/contrail/tapes/screen-test/<model>/<story>`, and eight lines `<n>. key <state>  kept take <seed>, passed|fails <codes>, 2 takes filmed, $<usd>, <s> s`, in the order they finish. Then `wrote examples/contrail/tapes/screen-test/report.html`, a `pick: <model>, with N of 10 element types at the bar of 90% in every story, ...` line that says the checks are not yet held to a person's marks, and `to render with it, set model = "<model>" in [tool.videotape] in examples/contrail/pyproject.toml`. `.exit` is `0`. `grep -c '"tape": "tapes/screen-test/' examples/contrail/ledger.jsonl` counts 96 `take` lines and up to 96 `read` lines, and their `usd` sums to no more than the cap. `git diff --quiet -- examples/contrail/pyproject.toml` exits 0. Run `grep -rlF -e "$FAL_KEY" -e "$ANTHROPIC_API_KEY" examples/contrail "$RUN"`, which must print nothing and exit 1.
- **Rerun.** Run the paid command again as `screen-rerun`. Every key line says `cached, $0.00, 0.0 s`, `wc -l examples/contrail/ledger.jsonl` is what it was, and `report.html` is byte for byte what the paid run wrote.
- **Report.** Open `examples/contrail/tapes/screen-test/report.html` in a browser from disk, in light and in dark mode, and take a screenshot of each. It must show, top to bottom: the pick with why, the bar in words, and each element type that misses its bar on every model with its best tally; a table of the ten element types against each model and story, each cell the elements that pass every check that judges them with a count for each of VT501 found, VT502 read exactly by every reader, VT509 drawn marked and VT504 chart values in range; a table of the controls each key's takes invent (VT503) with the first-take yield, the time and the cost of each model and story; Calibration, with wan3.0's 16 terminal takes, a checkbox for each element and the Download marks.json button; every take with its picture, its failing checks, a fold that opens its passing checks, its time and its cost, the three models side by side for each key in each story, both takes of each; and the sources for the choice of models, each with its date.
- **Marks.** Tick the boxes, press Download marks.json, and run the paid command again with `--marks <path>` as `screen-marks`. It films and reads nothing. `.stdout` ends with `the checks agree with a person's marks on N of M elements, P%` and then either the pick and the line that names where to set it, or `no pick: below 90%, the checks must be fixed before the pick`. The report lists the agreement per element type and each disagreement, and keeps the ticks.
- **Proof.** For the refusals and the estimate, cite `.cmd`, `.exit`, `.stdout` and `.stderr`. For the paid run, cite `.exit`, the estimate, the pick line, the ledger counts and sum, the empty key grep, and the two screenshots of the report.

## Gotchas

- The tapes under `tapes/screen-test/` cost money. Never delete them, their `takes/` or `looks/`, or their lines in the project's `ledger.jsonl`, or a rerun pays again.
- A screen-test tape holds keys and no move, so its `tape.json` has no hotspots and no search. Never play or publish it.
- The cap is the whole screen test's. Each tape renders under what the cap leaves after the other tapes' lines in the ledger, from this run and any run before, so a rerun with the same cap after a whole run spends nothing and fits.
- The estimate prices Claude's reads at `SIZES` in the script: 1280x720 for wan3.0, from the prototype run, 1344x768 for minimax-h3, and 1280x720 for gemini-omni-flash-1.2, which fal states no size for. The cap reserves each read at its picture's own size.
- In the tests, a stand-in's two takes of a key are one picture when neither carries a flaw, so Claude reads the second from the tape's cache and the tests count fewer reads than takes. A real model's two takes differ.
- gemini-omni-flash-1.2 takes no seed on fal. A mark is of a take by its clip, and the report writes a take's picture again when the take is filmed again.
- A check names the element type it judges, not which element of that type, so the report places each check on an element by what it is about, as the script's `judged` says. VT503 judges the whole key and no element.
- The report keeps a person's ticks in the browser's storage; `marks.json` is what the script reads. A bad `marks.json` is an argument error, exit 2, as a bad flag of videotape's is.
- The report never names an absolute path, so a copy of the project rebuilds the same page.
