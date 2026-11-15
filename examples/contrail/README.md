# Contrail

Contrail is a flight booking demo written as a Videotape screenplay. It books one-way flights from San Francisco for one demo traveler.

## Features

1. Home greets the traveler and shows their next trip and their miles. A search bar asks "Where to?".
2. Search finds a destination by typing a city or airport code, or by picking it from a list.
3. A month calendar shows the lowest fare on every day with flights. Other days can't be picked.
4. The day's flights are listed by departure time, with times, duration, stops, and fare. A row of the other days shows their lowest fares, and picking one switches the day.
5. A flight shows its day, times, aircraft, and the miles it earns.
6. One button books it and shows a confirmation code.
7. Trips lists the upcoming trips, which open to their details, and the three most recent trips.
8. Profile shows the traveler's status and miles, a bar chart of flights per month, and a line chart of the miles flown this year.
9. A search that matches no airport says so. A city with no flights says which cities have them.

## Run it

The screenplay says nothing about looks. A story does: one file under `stories/` for each look of the app. Contrail has two, `terminal` and `posters`.

From this folder:

```sh
uv run videotape plan
uv run videotape render --story terminal
uv run videotape play --story terminal
uv run videotape dailies --story terminal
uv run videotape retake "flight(CT 104, 2026-12-13)" --story terminal --takes 2
uv run videotape accept "booked(CT 300, 2026-12-11)" VT503 --story terminal --reason "a printed logo, not a control"
```

`plan` checks the screenplay and ends with what a render will cost: the shots, the calls from one take each up to the limit, and their price. `render` draws a key for every state and a move for every action into `tapes/terminal/`. Each shot films one take at a time and stops at the first that passes its checks, up to `takes` in `pyproject.toml` (4 unless set, or `--takes`), and shots that do not depend on each other film at once. It prints a line per shot as it finishes, the totals, and each failing shot with the command to run next. Run again, it resumes from the takes on disk. A model that bills per call, such as `--model wan3.0`, renders under a cap, `cap_usd` in `pyproject.toml` or `--cap-usd`, and never pays for a take twice.

`play` builds TapePlayer when it needs to and opens the tape in it. `dailies` rewrites `tapes/terminal/dailies.html` and opens it: failures come first, each with its code, its evidence, a crop of where it should be, and its next steps. `retake` films new takes of one shot, with seeds after the highest it has tried, and keeps the best of all of them; a move is named as `"flight(CT 104, 2026-12-13) -> booked(CT 104, 2026-12-13)"`. `accept` records a failure you are fine with, so the dailies show it as accepted and a render passes it.

Also useful:

```sh
uv run pyright contrail
uv run videotape shots --story posters --state "results(SEA, 2026-12-12)"
uv run videotape render --story posters
uv run videotape diff tapes/terminal tapes/posters
uv run videotape explain VT503
```

`shots` prints each prompt with the source of every clause. `diff` says whether two tapes are of the same app and the same story. `explain` prints a code's long form: `VT2xx` for the screenplay and its data, `VT3xx` for a story, `VT4xx` for a render, and `VT5xx` for a check.
