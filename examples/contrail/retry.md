# What to redo with more budget

Both tapes rendered all 150 shots on 2026-11-22 and stopped at the budget with failing shots. Each failure below is
real, seen in its frames, and each is accepted in its tape's record with the reason
"left for budget; the cause and the fix are in retry.md", so the apps could be published. An accept holds only for the
take it was given on: when a shot is filmed again, its failure counts again until someone looks at the new take.

Run `uv run videotape plan --story <story>` for the estimate before raising a cap, and
`uv run videotape dailies --story <story>` to see each accepted shot and its frames.

## Both tapes: variants that keep their base's words (VT502)

A variant is drawn from its base's picture with its own words, and the engine's `RELETTERED` clause says that only
the lettering changes and none of the first picture's words remain. The model still keeps a word, a number or a few
letters of the base when the variant's line is close to it: "CT 500" for "CT 504", "AM" for "PM", the base's miles,
or "Seattlele" where "Seattle" was written over "Honolulu". The last takes kept show smaller slips of the same
kind, a letter dropped or a digit off. Retakes fixed most such variants in posters, at 1 take in
4 to 5, but not these, each tried 8 to 13 times:

| Tape | Variant | Kept take reads |
|---|---|---|
| terminal | `flight(CT 504, 2026-12-13)` | "5 :55 PM", a space in the time; its other takes kept the base's AM or miles |
| terminal | `flight(CT 100, 2026-12-11)` | "2,386 miles" for "2,586", near the base's 2,398 |
| terminal | `flight(CT 306, 2026-12-13)` | "Suday" for "Sunday"; its other takes kept the base's AM or miles |
| posters | `results(HNL, 2026-12-12)` | "$399" for "$299" |
| posters | `flight(CT 504, 2026-12-11)` | "2:20 AM" for "2:20 PM" |
| posters | `flight(CT 100, 2026-12-11)` | "13:40 PM" for "3:40 PM" |
| posters | `flight(CT 100, 2026-12-13)` | "Sunda" for "Sunday", and the base's 2,398 miles for 2,586 |

The fix to try is in the engine: a variant's prompt names each line that changed from its base, the old words and
the new, as in `The sign that read "CT 500 to Honolulu" now reads "CT 504 to Honolulu".` It is not sampled yet.
Sample it first on these variants alone, in a tape of its own (`render --out`), then render: it changes the prompt of
every variant, so it redraws every variant of every scene in both stories and the moves pinned to them, 47 keys and
84 moves a story, roughly $100 a story at the takes this render needed.

## Terminal: the board's words change in place (VT507)

Every Heading, Text and Button in `stories/terminal.toml` is drawn on a dark sign, so the model draws `flight` and
`booked` on the same gate sign as the results board, and a press changes that sign's words in place as the camera
moves, which `VT507` rightly calls a dissolve. These moves failed every take, 7 to 8 each:

- `my_trips() -> trip(CT 100, 2026-12-18)`
- `profile() -> my_trips()`
- `results(HNL, 2026-12-12) -> flight(CT 504, 2026-12-12)`
- `results(JFK, 2026-12-11) -> flight(CT 100, 2026-12-11)`
- `results(JFK, 2026-12-12) -> flight(CT 104, 2026-12-12)`
- `results(JFK, 2026-12-13) -> flight(CT 104, 2026-12-13)`
- `results(SEA, 2026-12-12) -> flight(CT 306, 2026-12-12)`
- `results(SEA, 2026-12-13) -> flight(CT 300, 2026-12-13)`
- `results(SEA, 2026-12-13) -> flight(CT 306, 2026-12-13)`

Two story lines fix the cause:

1. `scenes.booked`: the camera looks down at the printed boarding pass on the gate desk, its words printed on it,
   and the sign above out of view. This redraws the booked keys and every move into and out of booked, about 54
   shots, roughly $50.
2. `moves.List`: the row lights up, and the camera turns from the board, which keeps its words, and walks to the
   gate desk. This redraws the flight base, which is rehearsed from a row's press, and so every flight and booked
   key and move after it, about 90 shots, roughly $80.

Each move left above is pinned, so without those lines a retake redraws nothing else, as in
`uv run videotape retake "profile() -> my_trips()" --story terminal --takes 2`. Retakes passed about 1 take in 6 on
the moves that failed their first four.
