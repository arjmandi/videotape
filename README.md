<img src="assets/icon.svg" width="64" height="64" alt="">

# Videotape

Videotape is a framework for writing an app as a screenplay. You write the app's scenes in Python, its data in JSON, and how it looks in stories. A video model renders the screenplay in a story into a tape: a clip of each state of the app at rest, and a clip of each press that leads from one state to the next. People click through the tape in TapePlayer, a Mac app, as if it were the app.

This guide builds Contrail, an app that books flights, from an empty folder. It has six parts:

1. [Start a project](#1-start-a-project)
2. [What a screenplay holds](#2-what-a-screenplay-holds)
3. [Connect the data](#3-connect-the-data)
4. [Write the screenplay](#4-write-the-screenplay)
5. [Write the stories](#5-write-the-stories)
6. [Render, review, fix, and publish](#6-render-review-fix-and-publish)

It ends with [the words Videotape uses](#the-words-videotape-uses), one meaning each. The finished app is [examples/contrail](examples/contrail). Each file the guide shows whole is that folder's file, byte for byte. `tests/test_guide.py` holds them together, and runs the guide's commands in order.

## Before you start

You need a Mac with these:

- [uv](https://docs.astral.sh/uv/), which installs videotape and runs its commands.
- ffmpeg, which brings ffprobe. Install it with `brew install ffmpeg`.
- Xcode, from the App Store, which builds TapePlayer. The Command Line Tools alone can't build it.

`videotape doctor` reports each of them in part 1.

## 1. Start a project

`videotape new` writes a project to start from. Run it in the folder that will hold the project:

```sh
uvx --from git+https://github.com/arjmandi/videotape-p1p videotape new contrail
```

```text
made contrail: a screenplay of two scenes, a data table, and the story starter
next:
  cd contrail
  uv run videotape doctor
  uv run videotape render --story starter --model stand-in
  uv run videotape play --story starter
```

`--from` says where videotape comes from, and the new project depends on videotape from the same place. The git URL above works for anyone who can clone this repository. To use a checkout of it, name the checkout's folder: `uvx --from ~/src/videotape-p1p videotape new contrail`.

`new` wrote a project of seven files:

```text
contrail/
  pyproject.toml          the app's name and version, its dependency on videotape, and [tool.videotape]
  contrail/__init__.py
  contrail/screenplay.py  the starter's screenplay: two scenes and a data table of steps
  data/steps.json         the starter's three steps
  stories/starter.toml    the starter's story: a notebook on a desk
  .env.example            the names of the API keys, without values
  .gitignore              tapes/, dist/, .env, ledger.jsonl, and .DS_Store
```

A project is the folder whose `pyproject.toml` has a `[tool.videotape]` section. Every videotape command but `new`, `doctor`, `explain`, and `diff` runs in a project, and finds `pyproject.toml` from the working folder upward. `new` wrote this section:

```toml
[tool.videotape]
screenplay = "contrail.screenplay:app"
model = "wan3.0"
takes = 4
cap_usd = 200
```

`screenplay` names the module that holds the screenplay, and the screenplay's name in that module. `model` is the model a render uses, `takes` is the most takes a shot gets, and `cap_usd` is the most a render may spend on a model that bills per call.

Go into the project, and ask `doctor` what this Mac and this project lack:

```sh
cd contrail
uv run videotape doctor
```

```text
ok   VT101 Python 3.12.12, and videotape needs >=3.12
ok   VT102 ffmpeg and ffprobe are on PATH
ok   VT103 Xcode 27.0, at /Applications/Xcode.app/Contents/Developer, for TapePlayer
fail VT104 wan3.0 needs FAL_KEY, and it is not in the environment or .env
  fix: copy .env.example to .env and set FAL_KEY there, or export it
fail VT104 wan3.0's reader claude-opus-5-5 needs ANTHROPIC_API_KEY, and it is not in the environment or .env
  fix: copy .env.example to .env and set ANTHROPIC_API_KEY there, or export it
fail VT105 wan3.0's eye runs Qwen3-VL-8B through videotape's qwen extra, which is not installed here
  fix: in pyproject.toml, put [qwen] right after videotape in dependencies, as in "videotape[qwen] @ file:///Users/me/videotape-p1p" or "videotape[qwen]==0.1.0", then run uv sync
```

The first `uv run` makes the project's Python environment. `VT104` fails because wan3.0 runs Wan 3.0 on fal, which needs the API key `FAL_KEY`, and because Claude, a reader of its eye, needs `ANTHROPIC_API_KEY`. `VT105` fails because its other reader, Qwen3-VL-8B, runs through videotape's `qwen` extra, which the project leaves out so that it installs fast. Leave all three for now. [Render with a real model](#render-with-a-real-model) adds them. The stand-in is a model that needs no API key and no GPU, and costs nothing. It films each key as a plain picture: a box for each line of the state's words. A render with the stand-in tests everything but the pictures.

Render the starter's story with the stand-in:

```sh
uv run videotape render --story starter --model stand-in
```

```text
1. key home()  kept take 1, passed, 1 take filmed, $0.00, 0.2 s
2. key todo() rehearsed from home()  kept take 1, passed, 1 take filmed, $0.00, 0.2 s
3. todo() -> home() "Back"  kept take 2, passed, 2 takes filmed, $0.00, 0.3 s
3 shots, 4 takes filmed, $0.00, 3.0 s, tape 0.2 MB -> tapes/starter
```

Each line is a shot. A shot films takes until one passes its checks, so the key of `todo()` kept its third take. The render wrote a tape to `tapes/starter/`. Play it:

```sh
uv run videotape play --story starter
```

The first `play` builds TapePlayer, which it does once for each version of TapePlayer, and prints how long the build took. Then TapePlayer opens on the starter's first state. Click **See the steps**. The tape plays the clip of that press and rests on the next state.

## 2. What a screenplay holds

Open `contrail/screenplay.py`. The starter's screenplay makes an app and gives it two scenes. The first is `home`:

```python
app = vt.Screenplay("Contrail")


@app.scene
def home():
    return [
        vt.Heading(app.title),
        vt.Text(f"An app of two scenes. {steps.count()} steps make it yours."),
        vt.Button("See the steps", to=todo()),
    ]
```

A screenplay is the app written as scenes. `vt.Screenplay("Contrail")` makes one, and `@app.scene` adds a scene to it. The first scene is where the app opens.

A scene is a function that returns the elements of one screen, from top to bottom. `vt.Heading`, `vt.Text`, and `vt.Button` are elements. Calling a scene names a state, which is the scene with the arguments of that call. `todo()` names the one state of the scene `todo`. Contrail's `flight(f)` names a different state for each flight `f`.

An element with `to=` holds an action. Pressing it leads to the state that `to=` names. The screenplay holds every word on the screen and nothing of how the screen looks. A story says how it looks.

`plan` walks every state the app can reach, from the first scene, before a render films anything:

```sh
uv run videotape plan
```

```text
Contrail 0.1.0: 2 scenes, 2 states, 2 keys of which 1 rehearsed, 2 moves, 3 shots

scene        states   moves out
home              1           1
todo              1           1

0 errors, 0 warnings
wan3.0: 3 shots, 3 to 12 calls, $1.50 to $6.00 at $0.10/s, and 2 to 8 reads by claude-opus-5-5, at most $0.35 to $1.38, and 2 to 8 judgments by claude-opus-5-5, at most $0.24 to $0.98
```

A render films one shot for each state and one for each action. A key is the shot of a state at rest. A move is the shot of an action. It films the press, from the key of the state it leaves to the key of the state it lands on. The last line is the estimate for the project's model. A render makes one call for each shot if every first take passes, and four if none passes before the last.

The rest of this guide turns the starter into Contrail. While you write it, render with the stand-in, so that each render after an edit costs nothing. Make the stand-in the project's model in `pyproject.toml`:

```toml
[tool.videotape]
screenplay = "contrail.screenplay:app"
model = "stand-in"
takes = 4
cap_usd = 200
```

Delete the starter's steps and its story:

```sh
rm data/steps.json stories/starter.toml
```

Until part 4 replaces the starter's screenplay, `plan` stops with `VT205`, because that screenplay still loads `data/steps.json`.

## 3. Connect the data

Contrail books one-way flights from San Francisco for one traveler. Its data is four JSON files in `data/`: the airports, the flights on sale, the traveler's trips, and the traveler. Copy them from [examples/contrail/data](examples/contrail/data) in this repository. Each flight in `data/flights.json` is one object:

```json
{
  "number": "CT 100",
  "origin": "SFO",
  "destination": "JFK",
  "day": "2026-12-11",
  "departs": "07:05",
  "arrives": "15:40",
  "minutes": 335,
  "stops": 0,
  "aircraft": "Airbus A321neo",
  "fare": 219,
  "miles": 2586
}
```

Write `contrail/data.py`, which says what each record holds and loads each file:

```python title=contrail/data.py
"""Contrail's data: the airports, the flights on sale, and the demo traveler's trips."""

from datetime import date, time

import videotape as vt


class Airport(vt.Record, key="code"):
    code: str
    city: str
    name: str


class Flight(vt.Record, key=("number", "day")):
    number: str
    origin: str
    destination: str
    day: date
    departs: time
    arrives: time
    minutes: int
    stops: int
    aircraft: str
    fare: int
    miles: int


class Trip(vt.Record, key=("flight", "day")):
    flight: str
    origin: str
    destination: str
    day: date
    miles: int
    confirmation: str


class Traveler(vt.Record):
    name: str
    first_name: str
    miles: int
    status: str


airports = vt.table(Airport, "data/airports.json")
flights = vt.table(Flight, "data/flights.json")
trips = vt.table(Trip, "data/trips.json")
traveler = vt.one(Traveler, "data/traveler.json")
```

A record class lists the fields of one record and the type of each: `str`, `int`, `date`, or `time`. A date is written as `"2026-12-11"` and a time as `"07:05"`. `key=` names the fields that tell two records apart. No two flights have the same number and day. A record never changes after it loads.

`vt.table` loads a JSON array into a data table of records when the module is imported. `vt.one` loads one record from a JSON object. Each path is relative to the project and is in `data/`. A value that doesn't fit its record class stops the import with `VT206`, which names the file, the line, and the field.

Load the flights:

```sh
uv run python -c "from contrail.data import flights; print(flights.count())"
```

```text
18
```

A data table answers queries: `where`, `order_by`, `limit`, `first`, `get`, `count`, `distinct`, and `min`, and `group_by`, whose groups answer `count` and `sum`. A query returns a new data table and leaves the old one as it was.

## 4. Write the screenplay

Contrail has 11 scenes. Write `contrail/copy.py` first. It says how values read on the screen, such as a fare as `$219`:

```python title=contrail/copy.py
"""How Contrail's values read on screen."""

import hashlib
from datetime import date, time

from contrail.data import Flight


def money(dollars: int) -> str:
    return f"${dollars:,}"


def clock(at: time) -> str:
    return at.strftime("%-I:%M %p")


def times(flight: Flight) -> str:
    return f"{clock(flight.departs)} to {clock(flight.arrives)}"


def duration(flight: Flight) -> str:
    hours, minutes = divmod(flight.minutes, 60)
    return f"{hours}h {minutes:02d}m"


def stops(flight: Flight) -> str:
    return "Nonstop" if flight.stops == 0 else f"{flight.stops} stop"


def long_day(day: date) -> str:
    return day.strftime("%A, %B %-d")


def short_day(day: date) -> str:
    return day.strftime("%b %-d")


def joined(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])}, and {names[-1]}"


def confirmation(flight: Flight) -> str:
    """A demo confirmation code, the same every time for the same flight."""
    return hashlib.sha256(f"{flight.number} {flight.day}".encode()).hexdigest()[:6].upper()
```

Then replace `contrail/screenplay.py` with Contrail's screenplay:

```python title=contrail/screenplay.py
"""Contrail books one-way flights from San Francisco. Each function below is a scene, one screen of
the app, and the first one is where the app opens. Calling a scene, as in results(place, day), names
a state for an action to go to."""

from datetime import date
from itertools import accumulate

import videotape as vt

from contrail.copy import clock, confirmation, duration, joined, long_day, money, short_day, stops, times
from contrail.data import Airport, Flight, Trip, airports, flights, traveler, trips

TODAY = date(2026, 12, 1)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]

app = vt.Screenplay("Contrail")


def city(code: str) -> str:
    return airports.get(code=code).city


def served(place: Airport) -> bool:
    return flights.where(destination=place.code).count() > 0


def upcoming() -> vt.Table[Trip]:
    return trips.where(lambda t: t.day >= TODAY).order_by("day")


def lowest(route: vt.Table[Flight], day: date) -> str:
    return money(route.where(day=day).min("fare"))


def tabs() -> vt.Tabs:
    return vt.Tabs({"Home": home(), "Trips": my_trips(), "Profile": profile()})


@app.scene
def home():
    soonest = upcoming().first()
    next_trip = vt.Row(f"San Francisco to {city(soonest.destination)}", long_day(soonest.day), to=trip(soonest))
    return [
        vt.Heading(f"Good morning, {traveler.first_name}"),
        vt.SearchBar("Where to?", to=search()),
        vt.List([next_trip], title="Your next trip"),
        vt.Text(f"{traveler.miles:,} Contrail Miles"),
        tabs(),
    ]


@app.scene
def search():
    options: list[vt.Option] = []
    for place in airports.where(lambda a: a.code != "SFO").order_by("city"):
        go = dates(place) if served(place) else no_flights(place)
        options.append(vt.Option(f"{place.city} ({place.code})", to=go))
    return [vt.SearchBar("Where to?", options=options, no_match=not_found())]


@app.scene
def not_found():
    return [
        vt.Heading("No airport matches"),
        vt.Text("Try a city or a three-letter airport code."),
        vt.Button("Search again", to=search()),
    ]


@app.scene
def no_flights(place: Airport):
    cities = [a.city for a in airports.where(served).order_by("city")]
    return [
        vt.Heading(f"No flights to {place.city}"),
        vt.Text(f"In December, Contrail flies to {joined(cities)}."),
        vt.Button("Search again", to=search()),
    ]


@app.scene
def dates(place: Airport):
    route = flights.where(destination=place.code)
    return [
        vt.Heading(f"San Francisco to {place.city}"),
        vt.Text("Pick a day. Each shows the lowest one-way fare."),
        vt.DatePicker({day: vt.Option(lowest(route, day), to=results(place, day))
                       for day in route.distinct("day")}),
    ]


@app.scene
def results(place: Airport, day: date):
    route = flights.where(destination=place.code)
    return [
        vt.Heading(f"San Francisco to {place.city}"),
        vt.DateStrip({other: vt.Option(lowest(route, other), to=results(place, other))
                      for other in route.distinct("day")}),
        vt.List([vt.Row(times(f), f"{duration(f)}, {stops(f)}", money(f.fare), to=flight(f))
                 for f in route.where(day=day).order_by("departs")]),
    ]


@app.scene
def flight(f: Flight):
    return [
        vt.Heading(f"{f.number} to {city(f.destination)}"),
        vt.Text(long_day(f.day)),
        vt.Text(f"{times(f)}, {duration(f)}, {stops(f)}"),
        vt.Text(f"{f.aircraft}. Earns {f.miles:,} miles."),
        vt.Button(f"Book for {money(f.fare)}", to=booked(f)),
    ]


@app.scene
def booked(f: Flight):
    return [
        vt.Heading("You're booked"),
        vt.Text(f"{f.number} to {city(f.destination)}, {long_day(f.day)}"),
        vt.Text(f"Departs {clock(f.departs)}. Confirmation {confirmation(f)}."),
        vt.Button("Done", to=home()),
    ]


@app.scene
def my_trips():
    recent = trips.where(lambda t: t.day < TODAY).order_by("day", descending=True).limit(3)
    return [
        vt.Heading("Trips"),
        vt.List([vt.Row(f"San Francisco to {city(t.destination)}", long_day(t.day), to=trip(t))
                 for t in upcoming()], title="Upcoming"),
        vt.List([vt.Row(f"{city(t.origin)} to {city(t.destination)}", short_day(t.day)) for t in recent],
                title="Recent"),
        tabs(),
    ]


@app.scene
def trip(t: Trip):
    return [
        vt.Heading(f"San Francisco to {city(t.destination)}"),
        vt.Text(f"{t.flight}, {long_day(t.day)}"),
        vt.Text(f"Confirmation {t.confirmation}"),
        vt.Text(f"Earns {t.miles:,} miles"),
    ]


@app.scene
def profile():
    by_month = trips.where(lambda t: t.day < TODAY and t.day.year == TODAY.year).group_by(lambda t: t.day.month)
    flown, miles = by_month.count(), by_month.sum("miles")
    running = accumulate(miles.get(month, 0) for month in range(1, 12))
    return [
        vt.Heading(traveler.name),
        vt.Text(f"{traveler.status} member, {traveler.miles:,} miles"),
        vt.BarChart("Flights per month in 2026", {name: flown.get(month, 0)
                                                  for month, name in enumerate(MONTHS, 1)}),
        vt.LineChart("Miles flown in 2026", dict(zip(MONTHS, running))),
        tabs(),
    ]
```

A few things in it are new since the starter:

- `home` is first, so the app opens there. It greets the traveler, shows the next trip, and leads to `search()`, to that trip, and to the other two tabs.
- `search` has a search bar with an option for each airport. An airport with flights leads to `dates(place)`, and one without flights to `no_flights(place)`. A search that matches no airport leads to `not_found()`.
- `results(place, day)` is called with an airport and a day, so each pair names its own state. The plan reaches one for each day with flights to each city.
- `flight(f)` and `booked(f)` are called with a flight record. A state's arguments are values that can be compared, such as records, dates, strings, and numbers.
- `tabs()` is a function, not a scene. It returns the same `vt.Tabs` element for three scenes.

Walk Contrail's states:

```sh
uv run videotape plan
```

```text
Contrail 0.1.0: 11 scenes, 58 states, 58 keys of which 10 rehearsed, 102 moves, 150 shots

scene        states   moves out
home              1           4
search            1           7
not_found         1           1
no_flights        3           3
dates             3           9
results           9          36
flight           18          18
booked           18          18
my_trips          1           4
trip              2           0
profile           1           2

0 errors, 0 warnings
stand-in: 150 shots, 150 to 600 calls, free
```

The data gives every number that `plan` prints. Three cities have flights, on three days each, so `results` has 9 states. There are 18 flights, so `flight` and `booked` have 18 states each. Every scene's base but the entry's is rehearsed, filmed as the move that first reaches it, so those ten moves are no shots of their own, and the 58 keys and 102 moves make 150 shots. The estimate is for the stand-in, the project's model since part 2.

A mistake in the screenplay or its data stops the plan with an error code from `VT201` to `VT211`, or `VT213` for a record field that is not a `str`, an `int`, a `date` or a `time`, and the file and line it is at. A scene that raises for one state's arguments, an action that leads to a scene instead of a state, and a scene no action reaches are such mistakes. `uv run videotape explain <code>` prints a code's long form, with an example and its fix.

The screenplay is typed, so pyright finds a wrong type before a render does. Add pyright to `pyproject.toml`, in its strict mode:

```toml
[dependency-groups]
dev = ["pyright"]

[tool.pyright]
typeCheckingMode = "strict"
```

```sh
uv run pyright contrail
```

```text
0 errors, 0 warnings, 0 informations
```

## 5. Write the stories

A story says how the whole app looks, in a TOML file under `stories/`. One screenplay can have many stories, and each renders into its own tape. A story has these parts:

- `version`, which the tape's label names.
- `look`, the sentence or two that each key's prompt starts with.
- `[scenes]`, a direction for each scene, which says where the camera is and what is there.
- `[elements]`, an appearance for each type of element.
- `[moves]`, what the camera does in a move that presses each type of element. `default` is for the types without their own.

A story never quotes words. The screenplay owns every word on the screen, and a model letters whatever a prompt quotes, so a quote in a story stops the plan with `VT308`. Write Contrail's first story, a quiet airport terminal at first light:

```toml title=stories/terminal.toml
# Contrail as a quiet airport terminal at first light. Each scene is a place in it.
version = "1.0.0"

look = """
A quiet international airport terminal at first light. Polished pale terrazzo, tall glass walls onto
the runway, brushed steel, warm walnut, and low golden sun. Every sign is a dark panel with crisp
white letters in a plain sans-serif face.
"""

[scenes]
home = "The main hall, facing the big departure board."
search = "A self-service kiosk by the tall windows, its screen listing the destinations."
not_found = "A printed notice taped to a steel pillar."
no_flights = "An empty gate, its sign lit and its seats empty."
dates = "A wall calendar beside the ticket desk."
results = "The departure board, showing one day's flights."
flight = "The gate desk, with the flight's details on its sign."
booked = "A printed boarding pass on the gate desk."
my_trips = "A dark panel on the lounge wall, beside pinned boarding passes."
trip = "One boarding pass on a lounge table, seen from above."
profile = "The lounge's wall display, beside a window onto the runway."

[elements]
Heading = "large white letters on a long dark sign"
Text = "smaller white letters on a dark sign"
Button = "a lit amber panel with bold black letters, like a gate sign"
SearchBar = "a wide white slot with black letters, its destinations listed below it as lines"
DatePicker = "a wall calendar page, its month at the top and, below it, only the days with flights, as large square white tiles in a row, each with the day's number large and its fare small beneath, and no arrows"
DateStrip = "a row of square white tiles, one per day, with the chosen day lit amber"
List = "white words in columns on a dark panel, one line per row"
BarChart = "a backlit wall display with amber bars and white labels"
LineChart = "a backlit wall display with one amber line and white labels"
Tabs = "three dark signs hanging in a row, the current one lit amber"

[moves]
default = "The camera turns from the sign, which keeps its words, glides through the terminal to the next place, and settles."
Button = "The panel lights up as it is pressed. The camera walks forward."
List = "The row lights up. The camera pushes in toward the gate."
DateStrip = "The tile lights up. The board's letters flip over, row by row, to that day's flights."
Tabs = "The sign lights up. The camera turns from the board, which keeps its words, and pans across the concourse to the next place."
```

`plan --story` reads the story too. It stops on a direction for a scene the screenplay lacks, and warns about a scene without a direction:

```sh
uv run videotape plan --story terminal
```

```text
Contrail 0.1.0 + terminal 1.0.0: 11 scenes, 58 states, 58 keys of which 10 rehearsed, 102 moves, 150 shots
...
0 errors, 0 warnings
stand-in: 150 shots, 150 to 600 calls, free
```

`shots` prints each shot's prompt, one clause to a line, with the clause's source beside it. Print the shots of the first state:

```sh
uv run videotape shots --story terminal --state "home()"
```

```text
key home()
  engine                          Static shot.
  story look                      A quiet international airport terminal at first light. Polished pale terrazzo, tall glass walls onto the runway, brushed steel, warm walnut, and low golden sun. Every sign is a dark panel with crisp white letters in a plain sans-serif face.
  story scenes.home               The main hall, facing the big departure board.
  story elements.Heading          Large white letters on a long dark sign,
  screenplay home, Heading        reading "Good morning, Alex".
  story elements.SearchBar        A wide white slot with black letters, its destinations listed below it as lines,
  screenplay home, SearchBar      reading "Where to?".
  story elements.List             White words in columns on a dark panel, one line per row,
  screenplay home, List           reading "Your next trip"; and "San Francisco to New York" and "Friday, December 18".
  story elements.Text             Smaller white letters on a dark sign,
  screenplay home, Text           reading "48,250 Contrail Miles".
  story elements.Tabs             Three dark signs hanging in a row, the current one lit amber,
  screenplay home, Tabs           reading "Home", "Trips", and "Profile", with "Home" chosen.
  engine                          Sharp, legible lettering.

key search() rehearsed from home()
  screenplay home, SearchBar      The search bar "Where to?" is pressed.
  story moves.default             The camera turns from the sign, which keeps its words, glides through the terminal to the next place, and settles.
  engine                          It ends held still on the next screen.
...
```

A key's prompt is the look, then the scene's direction, then each element, as its appearance from the story and its words from the screenplay. The move's prompt is the press, from the screenplay, and then what the story says the camera does. A rehearsal's prompt is the move's, then that the clip ends held still on the next screen, then the key's without its static shot, so the search scene's base is drawn as the move that first reaches it from home. When a shot comes out wrong, its sources say which line to change.

Write Contrail's second story, a wall of travel posters:

```toml title=stories/posters.toml
# Contrail as a long wall of screen-printed travel posters in a 1960s airline office.
version = "1.0.0"

look = """
A long sunlit wall in a 1960s airline ticket office, hung with screen-printed travel posters. Flat
shapes, a few bold colors (teal, coral, mustard, and cream), paper grain, and bold geometric
sans-serif letters. The camera faces the wall straight on.
"""

[scenes]
home = "A poster of a plane over the Golden Gate Bridge."
search = "A poster of a map with routes fanning out from San Francisco."
not_found = "A poster of a question mark drawn in clouds."
no_flights = "A poster of an empty runway at dusk."
dates = "A poster of a big printed December calendar."
results = "A poster of a printed timetable under a city skyline."
flight = "A poster of the plane above the clouds."
booked = "A poster of a large ticket, stamped."
my_trips = "A poster of ticket stubs pinned in rows."
trip = "A poster of one large ticket stub."
profile = "A poster of printed charts beside a suitcase."

[elements]
Heading = "big bold cream letters across the top of the poster"
Text = "smaller dark letters printed on the poster"
Button = "a printed coral tab with bold cream letters"
SearchBar = "a printed cream box with dark letters and a small magnifier"
DatePicker = "a printed calendar page, its month at the top and, below it, only the days with flights, as squares in a row, each with its number and its fare under it, and no arrows"
DateStrip = "a printed row of day squares, with the chosen day in coral"
List = "a printed timetable, one line per row"
BarChart = "a screen-printed bar chart in teal, with cream labels"
LineChart = "a screen-printed line chart in coral, with cream labels"
Tabs = "three printed tabs along the poster's bottom edge, the current one in coral"

[moves]
default = "The camera slides from the poster, which stays as it is, along the wall to the next poster and settles straight on."
DateStrip = "The day square is pressed. A hand pins a fresh printed timetable over the old one."
```

The same state in this story has the same words, and looks different:

```sh
uv run videotape shots --story posters --state "home()"
```

```text
key home()
  engine                         Static shot.
  story look                     A long sunlit wall in a 1960s airline ticket office, hung with screen-printed travel posters. Flat shapes, a few bold colors (teal, coral, mustard, and cream), paper grain, and bold geometric sans-serif letters. The camera faces the wall straight on.
  story scenes.home              A poster of a plane over the Golden Gate Bridge.
...
key search() rehearsed from home()
  screenplay home, SearchBar     The search bar "Where to?" is pressed.
  story moves.default            The camera slides along the wall to the next poster and settles straight on.
...
```

## 6. Render, review, fix, and publish

### Render

A render films the entry's key first, from its own prompt. A scene's base is its first state in the plan, and every base but the entry's is rehearsed: filmed as the move that first reaches it in the plan, image to video from the key of the state that move leaves, with the move's words and then the state's, so the clip travels from one screen to the next as a camera would and its last frame is the state's key. Each later state of the scene is a variant, which differs from the base in its data alone, so the model draws it as image to video from the base's picture with the variant's own prompt, as soon as the base is done, and the variant keeps the base's layout. Every other move is pinned, filmed first-and-last-frame between its two keys as soon as both are done. Several shots film at once. Each shot films one take at a time, with seed 1, then 2, and on. The eye reads each take of a key back, and the take's checks compare what it read with the screenplay: each action's words are found on the key, each line reads back exactly, nothing on the key looks like a control the state lacks, each chart's title, labels and values match the data, the chosen day or tab is drawn marked and no other, and a variant's layout stays its base's outside the words. Each take of a move, a rehearsal's or a pinned move's, is checked too: it starts and ends on its keys, no frame jumps far from the one before it, and the judge, shown eight frames across it, sees two pictures overlaid on none of them. The stand-in's eye is its own reader, and its judge its own. A real model's eye is two readers, Qwen3-VL-8B and Claude, and a line reads back exactly from both or the check fails, but for a period one adds to the end of a line that has none while the other reads the line exactly; Claude judges its moves. A shot keeps the first take that passes every check, and stops there. When no take passes by `takes`, it keeps the best one.

The render prints a line for each shot as it finishes, then the totals, then each failing shot with the command to run next. It writes the tape to `tapes/terminal/`, and a line for each take to `ledger.jsonl`. The stand-in passes every shot within four takes, and a real model does not. So the output here comes from `tests/test_guide.py`, whose stand-in films every other shot clean on its first take, and fails two keys on every take:

```sh
uv run videotape render --story terminal
```

```text
1. key home()  kept take 1, passed, 1 take filmed, $0.00, 1.5 s
2. key search() rehearsed from home()  kept take 1, passed, 1 take filmed, $0.00, 0.5 s
...
34. key flight(CT 104, 2026-12-13) from flight(CT 500, 2026-12-11)  kept take 1, fails VT502, 4 takes filmed, $0.00, 6.1 s
...
53. key booked(CT 300, 2026-12-11) from booked(CT 500, 2026-12-11)  kept take 1, fails VT503, 4 takes filmed, $0.00, 6.3 s
...
160 shots, 166 takes filmed, $0.00, 51.7 s, tape 9.8 MB -> tapes/terminal
fail: 34. key flight(CT 104, 2026-12-13) from flight(CT 500, 2026-12-11)  VT502 Airbus A321neo. Earns 2,586 miles.: read "Airbus A321neo. Earns 2,5x6 miles.", CER 0.029
  next: videotape retake "flight(CT 104, 2026-12-13)" --story terminal
fail: 53. key booked(CT 300, 2026-12-11) from booked(CT 500, 2026-12-11)  VT503 Not in the script: a control reading "Not in the script" at 24,192 315x33, and no action has those words
  next: videotape retake "booked(CT 300, 2026-12-11)" --story terminal
```

A render run again reuses every take on disk and films only what is missing or changed. An edit to the screenplay, the data, or a story films again only the shots whose prompts it changes, every key drawn from the picture of a key it films again, down the plan, and the pinned moves that start or end on a key that changed. A rehearsed key starts on the picture of the state it is reached from, so a change to the entry films everything again, and a change to a leaf state films that state's keys and the moves that touch them.

### Review

```sh
uv run videotape dailies --story terminal
```

```text
wrote tapes/terminal/dailies.html with {"takes": 166, "gpu_seconds": 108.0, "pods": 0, "pod_hours": 0.0, "reads": 0, "judgments": 0, "usd": 0.0}
```

`dailies` writes the tape's dailies page and opens it in your browser. Failing shots come first, each with its error code, what each reader read, a crop of the key where the failure is, and the commands that fix it. Below them is every shot with all its takes. When a shot's prompt changed since an earlier render, its card shows each clause added and removed, with the story line, screenplay line or engine rule it came from, and the take the shot kept before, with the checks it failed. `explain` prints a code's long form:

```sh
uv run videotape explain VT502
```

```text
VT502: a line was misread

Every line of a state is read back from its key by each reader of the eye, and a line reads back exactly from every reader or the check fails. A period one reader adds to the end of a line that has none does not fail it while another reader reads the line exactly, since a key that draws the period is read with it by every reader. The character error rate says how far off each reader was, and the dailies show what each reader read and the line's box when a reader saw one. A DatePicker shows a month, and a day without an option shows no words, so an option's words read where the key has no such line fail this check too.

Example:
    vt.Text("Confirmation 7F2K9Q"), read back as "Confirmation 7F2K90"

Next:
    retake the shot, shorten or simplify the line in the screenplay, or accept it with a reason
```

### Fix

A failure has three fixes. Retake the shot, which films new takes of it. Change the screenplay or the story, and render again. Or accept the failure, with the reason it is fine.

On the key of `booked(CT 300, 2026-12-11)`, the eye found a box that reads like a control, and the state has no action with its words. A real model often adds such a box as a sign or a logo. Say the dailies show a printed logo, which nobody would try to press. Accept the failure:

```sh
uv run videotape accept "booked(CT 300, 2026-12-11)" VT503 --story terminal --reason "a printed logo, not a control"
```

```text
accepted VT503 on key booked(CT 300, 2026-12-11) from booked(CT 500, 2026-12-11): a printed logo, not a control
```

An accept holds for the take you reviewed, which is the shot's kept take. When a later render keeps another take of that shot, the failure counts again, and the dailies show your reason beside it.

The key of `flight(CT 104, 2026-12-13)` misread a word on all four takes. Retake it:

```sh
uv run videotape retake "flight(CT 104, 2026-12-13)" --story terminal
```

```text
retaking key flight(CT 104, 2026-12-13) from flight(CT 500, 2026-12-11) with seed 5
...
34. key flight(CT 104, 2026-12-13) from flight(CT 500, 2026-12-11)  kept take 5, passed, 1 take filmed, $0.00, 1.1 s
...
53. key booked(CT 300, 2026-12-11) from booked(CT 500, 2026-12-11)  kept take 1, fails VT503, cached, $0.00, 0.0 s
...
160 shots, 3 takes filmed, $0.00, 36.2 s, tape 9.8 MB -> tapes/terminal
accepted: 53. key booked(CT 300, 2026-12-11) from booked(CT 500, 2026-12-11)  VT503 Not in the script: a control reading "Not in the script" at 24,192 315x33, and no action has those words
  reason: a printed logo, not a control
```

A retake films new takes of one shot, with seeds after the highest it has tried, and keeps the best of all its takes. It films with the model that made the tape, which `tape.json` names, so a retake of a stand-in tape costs nothing whatever model `[tool.videotape]` names. Add `--takes 3` to film three. It then renders the story again, so the pinned moves that start or end on the key film again, and every key drawn from its picture: the variants of the scene when the key is its base, and the rehearsed bases first reached from it. To retake a move, name it by its states, as in `"flight(CT 104, 2026-12-13) -> booked(CT 104, 2026-12-13)"`.

Nothing fails now that nobody accepted. Play the tape:

```sh
uv run videotape play --story terminal
```

Search for Seattle, pick a day and a flight, and book it.

### Render with a real model

Contrail renders with gemini-omni-flash-1.2, which runs Gemini Omni Flash 1.2 on fal at 720p and bills for each call. `scripts/screen-test` filmed eight of Contrail's keys on each model on fal, two takes each in both stories, and picked it: 96 of the 120 elements on its takes passed every check, 80.0%, against 56.7% for wan3.0 and 55.8% for minimax-h3, and none of its keys showed a control the state lacks. Its eye is two readers: Qwen3-VL-8B, which runs here and needs Apple silicon or a CUDA GPU, and Claude, which runs as a service, needs `ANTHROPIC_API_KEY`, and bills for each take of a key it reads, under the same cap. Read the estimate before you render:

```sh
uv run videotape plan --story terminal --model gemini-omni-flash-1.2
```

```text
Contrail 0.1.0 + terminal 1.0.0: 11 scenes, 58 states, 58 keys of which 10 rehearsed, 102 moves, 150 shots
...
gemini-omni-flash-1.2: 150 shots, 150 to 600 calls, $65.92 to $263.70 at $0.0819/s plus $0.03 a call for the prompt, and 58 to 232 reads by claude-opus-5-5, at most $10.01 to $40.04, and 102 to 408 judgments by claude-opus-5-5, at most $12.47 to $49.87
```

fal bills $0.0819 for each second of a clip, and bills the prompt by the token. No answer says what the prompt cost, so the estimate and the cap count the most a prompt can cost, $0.03 a call. A read's estimate charges every output token the reply may take, so a read costs less than its share here, and a reply is cached in the tape, so a render run again pays for no read twice. Claude is the judge of every move too: it sees eight frames across each take of a move and says of each whether it shows two pictures overlaid. A judgment is priced, capped and cached as a read is.

To render with it, first add videotape's `qwen` extra, which runs Qwen3-VL-8B, the reader of the eye that runs here. In `pyproject.toml`, put `[qwen]` right after `videotape` in `dependencies`, and keep the rest of the line. So `"videotape @ git+https://github.com/arjmandi/videotape-p1p@<commit>"` becomes `"videotape[qwen] @ git+https://github.com/arjmandi/videotape-p1p@<commit>"`, and the same goes for a `file://` URL or a version, as in `"videotape[qwen]==0.1.0"`. Then run `uv sync`. Copy `.env.example` to `.env` and set `FAL_KEY` and `ANTHROPIC_API_KEY` there, and set `model = "gemini-omni-flash-1.2"` in `pyproject.toml`. `uv run videotape doctor` now says `ok` for both `VT104` lines and for `VT105`. A render without either API key stops before its first call with doctor's `VT104` and doctor's fix. `.gitignore` keeps `.env` out of git, and no videotape command prints an API key. The render stops before a call that would spend more than the cap, with `VT402`. What the tape has spent is the sum of its lines in `ledger.jsonl`, so a render run again never pays for a take twice. To go on, run the render again with a higher cap, as in `--cap-usd 400`. fal takes no seed for gemini-omni-flash-1.2, so the seed only names a take, and a render run again reuses the take of each seed as it does for any model.

Two more models run on fal, with the same `FAL_KEY`, the same eye and a cap. Name one with `--model`, or set it as `model` in `pyproject.toml`. wan3.0 runs Wan 3.0 at 720p, for $0.10 a second, so $0.50 a call. minimax-h3 runs MiniMax H3 at 1344x768, for $0.06 a second, so $0.30 a call, and allows prompts of up to 7,000 characters. A tape takes the size of its model's clips, and TapePlayer's window takes the tape's shape.

### Publish

`publish` turns a tape into a Mac app that plays it:

```sh
uv run videotape publish --story terminal
```

```text
encoded 103 clips as HEVC; on each one's last frame, where TapePlayer rests, every check its key passed still passes
signed ad hoc, not with a Developer ID, so another Mac's Gatekeeper asks before it opens the app
published dist/Contrail-terminal.app, 8.1 MB, zipped to dist/Contrail-terminal.zip, 7.3 MB
label contrail 0.1.0 + terminal 1.0.0
id 7ab3bc3c8733a665eb87538384f91837a8db27507e1f05d1172f4d478c5a3fb3
videotape.lock holds the label now; commit it
```

`publish` refuses a tape that is out of date with its project's files (`VT601`), that has a failing check nobody accepted (`VT602`), or whose label `videotape.lock` holds with another made id (`VT305`). Then it builds TapePlayer and writes `dist/Contrail-terminal.app`, named after the screenplay and the story, with the tape inside it and each move re-encoded as HEVC. Then the tape's eye reads the last frame of each clip in the app again, against the state the clip lands on and that state's key. A check that passed in the tape and fails on that frame is `VT604`. It signs the app ad hoc, not with a Developer ID, zips it to `dist/Contrail-terminal.zip`, and adds the label, the made id, and the file hashes to `videotape.lock`. The app opens on the tape it holds.

## The words Videotape uses

Each word below has one meaning in this guide, and each meaning has one word.

- **accept**. To mark a failing check of a shot's kept take as fine, with a reason. The accept holds while the shot keeps that take. `videotape accept`.
- **action**. What pressing an element does. It leads to the state that the element's `to=` names, and a render films it as a move.
- **API key**. A secret that a model or a reader run as a service needs, such as `FAL_KEY` for wan3.0, minimax-h3 and gemini-omni-flash-1.2, which run on fal, and `ANTHROPIC_API_KEY` for Claude. It comes from the environment or the project's `.env`.
- **appearance**. A story's words for how one type of element looks, under `[elements]`.
- **base**. The first state of a scene in the plan. The entry's key is filmed from its own prompt, and every other base's as a rehearsal. The keys of the scene's variants are drawn from its picture.
- **cap**. The most a render may spend on a model, a reader or a judge that bills per call. `cap_usd` in `[tool.videotape]` sets it, and `--cap-usd` sets it for one render.
- **check**. One test that a take must pass: each action's words are found on the key (`VT501`), each line reads back exactly from every reader (`VT502`), the key shows no control the state lacks (`VT503`), each chart's title, labels and values match the data (`VT504`), a variant's layout stays its base's outside the words (`VT505`), a move does not cut (`VT506`) or dissolve (`VT507`), a move starts and ends on its keys (`VT508`), and the chosen day or tab is drawn marked and no other (`VT509`).
- **clause**. One part of a prompt, with its source: the engine, a part of the story, or an element of the screenplay.
- **dailies**. The review of a tape: `dailies.json`, which holds what the render knew of each shot, and `dailies.html`, the page that shows it, failures first. `videotape dailies`.
- **data table**. The records of one record class, loaded from a JSON array in `data/` with `vt.table`.
- **direction**. A story's words for one scene, under `[scenes]`, which say where the camera is and what is there.
- **element**. One thing that a state shows: `Heading`, `Text`, `Button`, `SearchBar`, `DatePicker`, `DateStrip`, `List`, `BarChart`, `LineChart`, or `Tabs`. An `Option` is a part of a search bar or a date picker, and a `Row` is a part of a list.
- **error code**. `VT` and three digits, which name one kind of error. `videotape explain <code>` prints its long form.
- **estimate**. The last line of `videotape plan`: the shots, the calls a render makes if every first take passes and if none passes before the last, and their price.
- **eye**. What reads a take back for its checks, made of one or more readers: the stand-in's own reader for the stand-in, and Qwen3-VL-8B with Claude for every other model.
- **hotspot**. Where a person presses an action on a key: the box in which the eye found the action's words.
- **judge**. What sees eight frames across a take of a move and says of each whether it shows two pictures overlaid, for the dissolve check: the stand-in's own judge for the stand-in, and Claude for every other model. A judgment by Claude is paid, reserved under the cap before it is sent, cached in the tape's `looks/`, and written to the ledger.
- **key**. The shot of one state at rest: the entry's filmed from its own prompt, a variant's from its base's picture, and every other base's as a rehearsal. The last frame of its kept take is the state's picture in the tape, and the moves to and from the state start and end on that picture.
- **kept take**. The take a shot keeps: the first that passes every check, or the best when none passes.
- **label**. The name of a tape: the app's name and version and the story's name and version, as in `contrail 0.1.0 + terminal 1.0.0`.
- **ledger**. `ledger.jsonl` in the project, with one line for each take filmed and its price, and one for each paid read and each paid judgment.
- **lock**. `videotape.lock` in the project, with the label, the made id, and the file hashes of each tape published. A label is published with one made id only.
- **look**. The sentence or two of a story that every key's prompt starts with.
- **made id**. One hash of everything that made a tape: the screenplay that `[tool.videotape]` names, the app's Python files and data, the story, the model and its settings, and videotape itself. Two tapes with one made id were made from the same things.
- **model**. The video model that films takes: `stand-in`, `wan3.0`, `minimax-h3`, `gemini-omni-flash-1.2`, or `wan2.2-5b`.
- **move**. One action as the tape plays it: the press, from the key of the state it leaves to the key of the state it lands on. A story's `[moves]` says what the camera does in it. The move that first reaches a base is that base's rehearsal, and every other move is pinned: a shot of its own, filmed first-and-last-frame between the two keys.
- **plan**. Every state the app can reach, walked from the first scene, with the keys and moves to film. `videotape plan`.
- **project**. The folder whose `pyproject.toml` has a `[tool.videotape]` section that names the screenplay.
- **prompt**. The words a model is given for one shot, made of clauses from the story and the screenplay. `videotape shots` prints them.
- **publish**. To turn a tape into a signed Mac app in `dist/` that plays it. `videotape publish`.
- **rehearsal**. The key of a base other than the entry's, filmed as the move that first reaches it in the plan: image to video from the key of the state that move leaves, with the move's words and then the state's, so the clip is the move and its last frame is the key. It is checked as a key and as a move.
- **read**. One reader's report on one picture: every line of text it saw with its box, which look like controls, which are drawn marked, and each chart's title, labels and values. A read by Claude is paid, reserved under the cap before it is sent, cached in the tape's `looks/`, and written to the ledger.
- **reader**. One part of an eye, which reads a picture and reports a read: the stand-in's own, Qwen3-VL-8B, which runs here through the `qwen` extra and reports no marks and no charts, or Claude, which runs as a service and reports both.
- **record**. One value of a record class, a `vt.Record` with typed fields. `key=` names the fields that tell two records apart.
- **render**. To film every shot of the plan in one story into a tape. `videotape render`.
- **retake**. To film new takes of one shot, with seeds after the highest it has tried, and keep the best of all its takes. `videotape retake`.
- **scene**. A function, marked with `@app.scene`, that returns the elements of one screen. Calling it names a state.
- **screenplay**. The app written as scenes: a `vt.Screenplay` and its scenes. It holds every word on the screen and nothing of how the screen looks.
- **seed**. The number a take is filmed with: 1, 2, 3, and on. A render run again reuses the take of each seed whose prompt has not changed. fal is not given the seed of a take of gemini-omni-flash-1.2, so there the seed only names the take.
- **shot**. What a render films for the plan: a key or a pinned move.
- **stand-in**. A model that films each key as a box for each line of the state's words, and reads the boxes back as its eye. It needs no API key and no GPU, and costs nothing.
- **state**. A scene with the arguments of one call, as in `flight(CT 104, 2026-12-13)`.
- **story**. How the app looks, in one file, `stories/<name>.toml`: a version, a look, directions, appearances, and what the camera does in each move. Each story renders into its own tape.
- **take**. One filming of a shot, with one seed.
- **tape**. What a render writes in `tapes/<story>/`: each key's picture, each move's clip, every take, `tape.json`, and the dailies. `tape.json` holds each state's words and hotspots, and the label and made id. TapePlayer plays the tape.
- **TapePlayer**. The Mac app that plays a tape. `videotape play` builds it and opens a tape in it.
- **variant**. A state of a scene after its base, which differs from the base in its data alone. Its key is drawn from the base's picture with its own prompt, so it keeps the base's layout, which the layout check (`VT505`) holds it to.
