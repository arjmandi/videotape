# Stories

A story is one look of an app. It is `stories/<name>.toml` in the project, named by its file, and it never touches the code. It holds a `version`, a `look`, a direction for each scene under `[scenes]`, an appearance for each element type under `[elements]`, and a camera move for each element type under `[moves]`, with `default` for the rest. The screenplay keeps the words, and a story never repeats them. A key's prompt is `Static shot.`, the look, its scene's direction, each element in reading order as its type's appearance and then its words quoted exactly, and `Sharp, legible lettering.` A move's prompt names the element that was pressed, by its words, and then the story's move for that element's type. `videotape shots --story <name>` prints every prompt, one clause to a line, with the clause's source beside it: `engine`, `story look`, `story scenes.<scene>`, `story elements.<Type>`, `story moves.<Type>`, `story moves.default`, or `screenplay <scene>, <Type>`. A render in a story writes `tapes/<name>/`, and its `tape.json` carries a `made` block: a label such as `contrail 0.1.0 + terminal 1.0.0`, the app's name and version, a hash of its code and one of `data/`, the story's name, version and hash, the model and its settings, a hash of the engine's code, and an id that hashes all of these. `videotape diff <tape> <tape>` reads two such tapes and says whether they are of the same app and the same story.

## Sub-features

- `stories-shots-state` prints the key of `results(SEA, 2026-12-12)` in `posters` and the four moves that leave it, each clause beside its source.
- `stories-shots-all` prints all 160 shots of Contrail in a story, 58 keys and then 102 moves.
- `stories-words` shows that the two stories quote the same words in the same order.
- `stories-moves` gives a move its element type's move in `terminal`, and `default` in `posters`, which has only that one.
- `stories-missing` names the stories the project has when the one asked for is not among them, names the closest states for a state the app does not have, and rejects `shots` and `render` without `--story`.
- `stories-made` writes the `made` block and the label into `tape.json`.
- `stories-diff` says `same app` and `another story` for Contrail's two tapes, with 58 states and 102 moves shared.
- `stories-cascade` re-renders one scene's keys and the moves that touch them after that scene's direction changes, and nothing else.
- `stories-rerender` counts on Contrail what a change to a direction, an appearance, the look or one fare renders again, proven by `uv run pytest tests/test_rerender.py`.

## How to get to it (user POV)

- In `examples/contrail`, run `uv run videotape shots --story posters --state "results(SEA, 2026-12-12)"`.
- Edit a line of `stories/terminal.toml`, or copy it to a new file under `stories/`, and run `uv run videotape plan --story <name>`, then `uv run videotape render --story <name>`.
- After rendering both stories, run `uv run videotape diff tapes/terminal tapes/posters`.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- For `stories-made` and `stories-diff`, `examples/contrail/tapes/terminal/tape.json` and `examples/contrail/tapes/posters/tape.json` exist. If not, drive `render-first` from [render.md](./render.md) for each story.
- For `stories-cascade`, the scratch cafe `$S` from `render-cafe` in [render.md](./render.md) holds its rendered tape.

- **One state.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" stories-shots-state examples/contrail -- shots --story posters --state "results(SEA, 2026-12-12)"`. `.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:
  ```
  key results(SEA, 2026-12-12)
    engine                         Static shot.
    story look                     A long sunlit wall in a 1960s airline ticket office, hung with screen-printed travel posters. Flat shapes, a few bold colors (teal, coral, mustard, and cream), paper grain, and bold geometric sans-serif letters. The camera faces the wall straight on.
    story scenes.results           A poster of a printed timetable under a city skyline.
    story elements.Heading         Big bold cream letters across the top of the poster,
    screenplay results, Heading    reading "San Francisco to Seattle".
    story elements.DateStrip       A printed row of day squares, with the chosen day in coral,
    screenplay results, DateStrip  reading "Fri 11" "$99", "Sat 12" "$89", and "Sun 13" "$109", with "Sat 12" chosen.
    story elements.List            A printed timetable, one line per row,
    screenplay results, List       reading "8:15 AM to 10:25 AM", "2h 10m, Nonstop", and "$89"; and "5:40 PM to 7:50 PM", "2h 10m, Nonstop", and "$119".
    engine                         Sharp, legible lettering.

  results(SEA, 2026-12-12) -> results(SEA, 2026-12-11) "Friday, December 11, $99"
    screenplay results, DateStrip  The day "Fri 11" is pressed.
    story moves.default            The camera slides along the wall to the next poster and settles straight on.

  results(SEA, 2026-12-12) -> results(SEA, 2026-12-13) "Sunday, December 13, $109"
    screenplay results, DateStrip  The day "Sun 13" is pressed.
    story moves.default            The camera slides along the wall to the next poster and settles straight on.

  results(SEA, 2026-12-12) -> flight(CT 300, 2026-12-12) "8:15 AM to 10:25 AM, 2h 10m, Nonstop, $89"
    screenplay results, List       The row "8:15 AM to 10:25 AM" is pressed.
    story moves.default            The camera slides along the wall to the next poster and settles straight on.

  results(SEA, 2026-12-12) -> flight(CT 306, 2026-12-12) "5:40 PM to 7:50 PM, 2h 10m, Nonstop, $119"
    screenplay results, List       The row "5:40 PM to 7:50 PM" is pressed.
    story moves.default            The camera slides along the wall to the next poster and settles straight on.
  ```
  The key's clauses, joined by single spaces, are the prompt the model is sent.
- **Every shot.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" stories-shots-all examples/contrail -- shots --story terminal`. `.exit` is `0`, `.stdout` has 1221 lines, and `grep -c '^[^ ]' "$RUN/stories-shots-all.stdout"` prints `160`, one title per shot. The first title is `key home()`, and its clauses end `reading "Home", "Trips", and "Profile", with "Home" chosen.` and `Sharp, legible lettering.` The 59th title, `grep -n '^[^ ]' "$RUN/stories-shots-all.stdout" | sed -n 59p`, is line 815, `home() -> search() "Where to?"`, and the two lines under it are `  screenplay home, SearchBar      The search bar "Where to?" is pressed.` and `  story moves.SearchBar           The slot lights up. The camera steps closer to the departure board.` The source column is as wide as the longest source the command prints, so it is narrower with `--state`.
- **Same words.** Run the same with `--story posters` as `stories-shots-all-posters`. `diff <(grep -o '"[^"]*"' "$RUN/stories-shots-all.stdout") <(grep -o '"[^"]*"' "$RUN/stories-shots-all-posters.stdout")` prints nothing and exits 0.
- **Moves.** `grep -o '^  story moves\.[A-Za-z]*' "$RUN/stories-shots-all.stdout" | sort | uniq -c` prints `40   story moves.Button`, `21   story moves.List`, `8   story moves.SearchBar`, `6   story moves.Tabs` and `27   story moves.default`, which are the 9 days of the date pickers and the 18 of the date strips. The same on `stories-shots-all-posters.stdout` prints one line, `102   story moves.default`.
- **Missing.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" stories-no-story examples/contrail -- shots --story poster`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error VT309 stories: no story "poster"` over `fix: name one of the stories there, posters and terminal`. `plan --story poster` and `render --story poster` print the same, and `command ls examples/contrail/tapes` shows no `poster`. With `-- shots --story posters --state "results(SEA, 2026-12-21)"`, `.stderr` is `error: the app has no state "results(SEA, 2026-12-21)"; the closest are results(SEA, 2026-12-11), results(SEA, 2026-12-12), results(SEA, 2026-12-13)`. With `-- shots` alone, `.exit` is `2` and `.stderr` ends with `videotape shots: error: the following arguments are required: --story`, and `-- render` alone ends the same way for `videotape render`.
- **Made.** Run `.venv/bin/python -c 'import json; m = json.load(open("examples/contrail/tapes/terminal/tape.json"))["made"]; print(list(m)); print(m["label"]); print(m["app"]["name"], m["app"]["version"], m["story"], m["model"]); print(all(len(h) == 64 for h in (m["id"], m["app"]["code"], m["app"]["data"], m["engine"])))'`. It prints `['label', 'id', 'app', 'story', 'model', 'engine']`, then `contrail 0.1.0 + terminal 1.0.0`, then `contrail 0.1.0 {'name': 'terminal', 'version': '1.0.0', 'hash': '0b012621d2d6da91c4ab4fff5ce5c2ede46c642ed001570e7bb6299466fb8811'} {'name': 'stand-in', 'settings': {'text-to-video': {}, 'first-and-last-frame': {}}}`, then `True`. `shasum -a 256 examples/contrail/stories/terminal.toml` prints the same hash. The posters tape's label is `contrail 0.1.0 + posters 1.0.0`.
- **Diff.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" stories-diff -C examples/contrail -- uv run videotape diff tapes/terminal tapes/posters`. `.exit` is `0`, `.stderr` is empty, and `.stdout` is these six lines, with each tape's own 64-character id in place of `<id>`:
  ```
  tapes/terminal  contrail 0.1.0 + terminal 1.0.0  <id>
  tapes/posters   contrail 0.1.0 + posters 1.0.0   <id>
  same app
  another story
  58 states shared, of 58 and 58
  102 moves shared, of 102 and 102
  ```
  The two ids differ, and each is the `id` of that tape's `made` block. With `tapes/terminal tapes/terminal`, both lines carry one id and the third and fourth lines are `same app` and `same story`. With `tapes/terminal tapes/neon`, `.exit` is `1` and `.stderr` is `error: no tape.json in tapes/neon; render the screenplay first`.
- **Edit one direction.** Needs the scratch cafe `$S` after `render-cascade` in [render.md](./render.md). Run `perl -pi -e 's/order = "One panel of the board, up close."/order = "One panel of the board, up close, by candlelight."/' "$S/stories/chalk.toml"`, then `.claude/skills/verify/scripts/vt-verify run "$RUN" stories-cascade "$S" -- render --story chalk`. `.exit` is `0`. The shot lines come in the order the shots finish, so sort them: `grep '^[0-9]*\. ' "$RUN/stories-cascade.stdout" | sort -n | sed -E 's/, [0-9.]+ s$//'` prints:
  ```
  1. key menu()  kept take 2, passed, cached, $0.00
  2. key order(Espresso)  kept take 3, passed, 3 takes filmed, $0.00
  3. key order(Latte)  kept take 1, passed, 1 take filmed, $0.00
  4. key thanks(Espresso)  kept take 2, passed, cached, $0.00
  5. key thanks(Latte)  kept take 1, passed, cached, $0.00
  6. menu() -> order(Espresso) "Espresso, $3"  kept take 3, passed, 3 takes filmed, $0.00
  7. menu() -> order(Latte) "Latte, $5"  kept take 1, passed, 1 take filmed, $0.00
  8. order(Espresso) -> thanks(Espresso) "Order"  kept take 2, passed, 2 takes filmed, $0.00
  9. order(Latte) -> thanks(Latte) "Order"  kept take 2, passed, 2 takes filmed, $0.00
  10. thanks(Espresso) -> menu() "Done"  kept take 1, passed, cached, $0.00
  11. thanks(Latte) -> menu() "Done"  kept take 1, passed, cached, $0.00
  ```
  The two keys of the order scene film again, and so do the four moves that start or land on them, though no move's prompt changed. The last line starts `11 shots, 12 takes filmed, $0.00, `. `$RUN/stories-cascade.project/chalk.toml` shows the edited line.
- **What renders again.** Run `uv run pytest tests/test_rerender.py -v`. All 8 tests pass. It took 2 minutes 38 seconds on an M3 Max. The module renders Contrail once in `terminal` with one take per shot, makes each change in a copy of that render, and renders again. The results scene's direction films its 9 keys and the 45 moves that touch them. The DatePicker's appearance films the 3 keys that show one and 12 moves. The look films all 58 keys and 102 moves. One fare in `data/flights.json` films the 5 keys that show it and 17 moves.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted `.stdout` or `.stderr` lines. Also cite the empty `diff` for `stories-words`, the `shasum` line for `stories-made`, and the `.project/chalk.toml` copy for `stories-cascade`.

## Gotchas

- A story's hash is of its file's bytes, so a comment or a blank line changes it, and `diff` then says `another story` though every prompt is the same.
- `same app` compares the hash of the app's code and the hash of `data/`. The code is every `.py` file of the package that holds the screenplay, or the one module when there is no package. `vt.table` and `vt.one` load only files under `data/` (a path outside it is `VT205`), so the data hash covers every record the app loads.
- The `made` block is written with `tape.json` at the end of every render. Its engine hash is of the videotape code that wrote it, and takes that came from the cache may have been drawn by earlier code. After a change to videotape itself, a cached render changes `tape.json` and nothing else.
- A file's hash covers its path from the project and its bytes. A rename changes it. The order the files are read in does not.
- The ids differ between checkouts whenever videotape's own code differs, so never assert an id from this file. Assert the label and the story's hash.
- `shots` prints nothing a model has drawn. It needs no ffmpeg and no model, and runs in well under a second on Contrail.
- `shots` and `render` check the story against the project's model and print its warnings to stderr, as `plan --story <name>` does, before their own output.
- A line that ends with a period is quoted with it, so a clause can end `fare.".`, with the line's own period inside the quotes and the clause's after them.
- A chosen option or tab is quoted a second time, as in `with "Sat 12" chosen`. The stand-in draws that line once.
- The stand-in draws only a prompt's quoted lines, and marks every key with a row of 64 faint cells along its bottom edge, each a little lighter or darker by one bit of the whole prompt's hash. That is how a change to a look, a direction or an appearance changes a stand-in key, and through the key the moves pinned to it.
