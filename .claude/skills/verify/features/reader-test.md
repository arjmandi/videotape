# Reader test

`scripts/reader-test` asks whether a reader can tell what Contrail does from its screenplay alone. The first call sends only `examples/contrail/contrail/screenplay.py` to `claude-opus-5-5` and asks what the app does. The second call checks that answer against each of the nine features in `examples/contrail/README.md`, one yes or no each. It asks whether the answer describes each feature's behavior, in any words, and never asks for a look, because a screenplay can't say how an element looks, such as that a date picker is a month calendar. The script saves both answers in `examples/contrail/reader-test.md`, prints the two calls' tokens and cost, and exits 0 only when every feature is a yes. The key comes from `ANTHROPIC_API_KEY` in the environment and is never printed. Both calls are paid.

The paid run of 2026-11-22 stated 9 of 9 features, and `examples/contrail/reader-test.md` holds it. The run before it, the same day, stated 8 of 9: the answer listed the search's airports and what text that matches none does, but never said that typing a city or a code finds one, which the screenplay never said either, since what a search bar with options does lives in the framework. The screenplay's docstring now says it. The missing-key error and the tests below were driven.

## Sub-features

- `reader-no-key` stops without `ANTHROPIC_API_KEY` with `error: ANTHROPIC_API_KEY is not set`, exit 2, before any network call and before writing anything.
- `reader-requests` builds both requests, reads a response with no network, prices it, writes the report, and exits by the verdicts, all proven by `uv run pytest tests/test_reader_test.py`.
- `reader-paid` is the paid run. Costs money, and waits for the user's cap.

## How to get to it (user POV)

- Export `ANTHROPIC_API_KEY`, then run `scripts/reader-test` from the repo root and read `examples/contrail/reader-test.md`.
- Add `--record <file>` to keep both raw responses in that file.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- For `reader-paid`, the user named a cap in this session and `ANTHROPIC_API_KEY` is exported in the shell that runs the drive. Never run it on your own initiative, and never ask for the key or type it into a command.

- **No key.** Run `env -u ANTHROPIC_API_KEY https_proxy=http://127.0.0.1:9 .claude/skills/verify/scripts/vt-verify exec "$RUN" reader-no-key -- scripts/reader-test`. `.exit` is `2`, `.stdout` is empty, and `.stderr` is exactly `error: ANTHROPIC_API_KEY is not set`. `git diff --quiet -- examples/contrail/reader-test.md` exits 0: the report the paid run of 2026-11-12 left is unchanged.
- **Requests and answers.** Run `uv run pytest tests/test_reader_test.py -v`. All 14 tests pass, among them `test_the_read_sends_only_the_screenplay_to_claude_opus`, `test_the_check_sends_the_answer_and_every_feature_and_must_answer_yes_or_no_to_each`, `test_the_check_asks_for_each_features_behavior_in_any_words_and_never_for_a_look`, `test_nine_yeses_exit_zero_and_both_answers_are_saved_with_the_tokens_and_cost`, `test_one_no_exits_nonzero_and_says_which_feature` and `test_the_key_never_appears_in_an_error`.
- **Paid run.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" reader-paid -- scripts/reader-test --record "$RUN/reader-test.json"`. `.stdout` has a `read` line and a `check` line, each `claude-opus-5-5: N input tokens, N output tokens, $N`, then `total  $N`, then nine lines `<number>. yes  <feature>` or `<number>. no   <feature>`, then `N of 9 features stated -> examples/contrail/reader-test.md`. `.exit` is `0` when all nine are yes and `1` otherwise. `examples/contrail/reader-test.md` holds the answer, the nine verdicts with the reason for each, and the same token and cost lines. The report is tracked, so `git diff examples/contrail/reader-test.md` shows the new run against the last; commit it or restore it with `git checkout`, as the user decides. Leave `tests/fixtures/reader-test.json` as it is. Run `env | grep -c '^ANTHROPIC_API_KEY='` to confirm the key was set, then `grep -rlF -e "$ANTHROPIC_API_KEY" examples/contrail "$RUN"`, which must print nothing and exit 1.
- **Proof.** For `reader-no-key` cite `.cmd`, `.exit` and `.stderr`. For the paid run cite `.exit`, the three cost lines, the nine verdict lines and the empty key grep.

## Gotchas

- `tests/fixtures/reader-test.json` holds two responses written by hand in the shape the Messages API documents. The paid run stated 8 of 9 features, and the tests need nine yeses, so its responses stay out of the fixture. `--record` writes the real ones to the file it names.
- A key that holds a line break or another control character stops the script with `error: ANTHROPIC_API_KEY holds a character an HTTP header cannot carry, such as a line break` and exit 2, and a key of only spaces counts as not set.
- The script prices the calls at $4 for a million input tokens and $20 for a million output tokens, Anthropic's prices for `claude-opus-5-5` as of 2026-10-06. This model always thinks, and its thinking is billed as output tokens, so the output count is larger than the answer.
- The model is pinned, so the request names no fallback model. A refusal, an answer cut off at the token limit, or a check that leaves a feature out stops the script with an `error:` line and exit 2, and no report is written.
- The first request holds only the screenplay's text. It does not hold `copy.py`, `data.py`, the data files or the README, so the reader sees names like `money` and `long_day` without their definitions.
- The key is only ever read from the environment. `vt-verify exec` records its whole argv in `.cmd`, so never pass the key as an argument.
