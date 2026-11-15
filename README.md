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
made contrail: a screenplay of two scenes, a table of data, and the story starter
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
  contrail/screenplay.py  the starter's screenplay: two scenes and a table of steps
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
ok   VT105 Apple silicon, for wan3.0's checks
```

The first `uv run` makes the project's Python environment. `VT104` fails because wan3.0 runs Wan 3.0 on fal, which needs the API key `FAL_KEY`. Leave it for now. The stand-in is a model that needs no API key and no GPU, and costs nothing. It films each key as a plain picture: a box for each line of the state's words. A render with the stand-in tests everything but the pictures.

Render the starter's story with the stand-in:

```sh
uv run videotape render --story starter --model stand-in
```

```text
1. key home()  kept take 1, passed, 1 take filmed, $0.00, 0.3 s
2. key todo()  kept take 3, passed, 3 takes filmed, $0.00, 0.8 s
4. todo() -> home() "Back"  kept take 2, passed, 2 takes filmed, $0.00, 0.4 s
3. home() -> todo() "See the steps"  kept take 3, passed, 3 takes filmed, $0.00, 0.6 s
4 shots, 9 takes filmed, $0.00, 2.8 s, tape 0.2 MB -> tapes/starter
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

`plan` walks every state the app can reach, from the first scene, before anything renders:

```sh
uv run videotape plan
```

```text
Contrail 0.1.0: 2 scenes, 2 states, 2 keys, 2 moves, 4 shots

scene        states   moves out
home              1           1
todo              1           1

0 errors, 0 warnings
wan3.0: 4 shots, 4 to 16 calls, $2.00 to $8.00 at $0.10/s
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
Contrail 0.1.0: 11 scenes, 58 states, 58 keys, 102 moves, 160 shots

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
stand-in: 160 shots, 160 to 640 calls, free
```

The data gives every number that `plan` prints. Three cities have flights, on three days each, so `results` has 9 states. There are 18 flights, so `flight` and `booked` have 18 states each. The estimate is for the stand-in, the project's model since part 2.

A mistake in the screenplay stops the plan with an error code from `VT201` to `VT211` and the file and line it is at. A scene that raises for one state's arguments, an action that leads to a scene instead of a state, and a scene no action reaches are such mistakes. `uv run videotape explain <code>` prints a code's long form, with an example and its fix.

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
search = "Up close at the departure board, where the destinations are listed."
not_found = "The departure board, with a printed notice taped beside it."
no_flights = "An empty gate, its sign lit and its seats empty."
dates = "A wall calendar beside the ticket desk."
results = "The departure board, showing one day's flights."
flight = "The gate desk, with the flight's details on its sign."
booked = "A printed boarding pass on the gate desk."
my_trips = "A lounge wall pinned with boarding passes."
trip = "One boarding pass on a lounge table, seen from above."
profile = "The lounge's wall display, beside a window onto the runway."

[elements]
Heading = "large white letters on a long dark sign"
Text = "smaller white letters on a dark sign"
Button = "a lit amber panel with bold black letters, like a gate sign"
SearchBar = "a wide white slot in the departure board with black letters, its destinations listed below it as lines of the board"
DatePicker = "a wall calendar of square white tiles, each with the day's number large and the fare small beneath it, and days without flights greyed out"
DateStrip = "a row of square white tiles, one per day, with the chosen day lit amber"
List = "a departure board, one line per row, its words in columns"
BarChart = "a backlit wall display with amber bars and white labels"
LineChart = "a backlit wall display with one amber line and white labels"
Tabs = "three dark signs hanging in a row, the current one lit amber"

[moves]
default = "The camera glides through the terminal to the next place and settles."
Button = "The panel lights up as it is pressed. The camera walks forward."
SearchBar = "The slot lights up. The camera steps closer to the departure board."
List = "The row lights up. The camera pushes in toward the gate."
Tabs = "The sign lights up. The camera pans across the concourse."
```

`plan --story` reads the story too. It stops on a direction for a scene the screenplay lacks, and warns about a scene without a direction:

```sh
uv run videotape plan --story terminal
```

```text
Contrail 0.1.0 + terminal 1.0.0: 11 scenes, 58 states, 58 keys, 102 moves, 160 shots
...
0 errors, 0 warnings
stand-in: 160 shots, 160 to 640 calls, free
```

`shots` prints each shot's prompt, one clause to a line, with the clause's source beside it. Print the shots of the first state:

```sh
uv run videotape shots --story terminal --state "home()"
```

```text
key home()
  engine                      Static shot.
  story look                  A quiet international airport terminal at first light. Polished pale terrazzo, tall glass walls onto the runway, brushed steel, warm walnut, and low golden sun. Every sign is a dark panel with crisp white letters in a plain sans-serif face.
  story scenes.home           The main hall, facing the big departure board.
  story elements.Heading      Large white letters on a long dark sign,
  screenplay home, Heading    reading "Good morning, Alex".
  story elements.SearchBar    A wide white slot in the departure board with black letters, its destinations listed below it as lines of the board,
  screenplay home, SearchBar  reading "Where to?".
  story elements.List         A departure board, one line per row, its words in columns,
  screenplay home, List       reading "Your next trip"; and "San Francisco to New York" and "Friday, December 18".
  story elements.Text         Smaller white letters on a dark sign,
  screenplay home, Text       reading "48,250 Contrail Miles".
  story elements.Tabs         Three dark signs hanging in a row, the current one lit amber,
  screenplay home, Tabs       reading "Home", "Trips", and "Profile", with "Home" chosen.
  engine                      Sharp, legible lettering.

home() -> search() "Where to?"
  screenplay home, SearchBar  The search bar "Where to?" is pressed.
  story moves.SearchBar       The slot lights up. The camera steps closer to the departure board.
...
```

A key's prompt is the look, then the scene's direction, then each element, as its appearance from the story and its words from the screenplay. The move's prompt is the press, from the screenplay, and then the move from the story. When a shot comes out wrong, its sources say which line to change.

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
SearchBar = "a printed cream box with dark letters and a small magnifier, its destinations printed below it on cream strips"
DatePicker = "a printed month calendar, each day a square with its number and its fare, and days without flights faded"
DateStrip = "a printed row of day squares, with the chosen day in coral"
List = "a printed timetable, one line per row"
BarChart = "a screen-printed bar chart in teal, with cream labels"
LineChart = "a screen-printed line chart in coral, with cream labels"
Tabs = "three printed tabs along the poster's bottom edge, the current one in coral"

[moves]
default = "The camera slides along the wall to the next poster and settles straight on."
```

The same state in this story has the same words, and looks different:

```sh
uv run videotape shots --story posters --state "home()"
```

```text
key home()
  engine                      Static shot.
  story look                  A long sunlit wall in a 1960s airline ticket office, hung with screen-printed travel posters. Flat shapes, a few bold colors (teal, coral, mustard, and cream), paper grain, and bold geometric sans-serif letters. The camera faces the wall straight on.
  story scenes.home           A poster of a plane over the Golden Gate Bridge.
...
home() -> search() "Where to?"
  screenplay home, SearchBar  The search bar "Where to?" is pressed.
  story moves.default         The camera slides along the wall to the next poster and settles straight on.
...
```

## 6. Render, review, fix, and publish

### Render

A render films every key first, then each move as soon as both of its keys are done, several shots at once. Each shot films one take at a time, with seed 1, then 2, and on. The eye reads each take back, and the take's checks compare what it read with the screenplay: each action's words are found on the key, each line reads back exactly, nothing on the key looks like a control the state lacks, and each move starts and ends on its keys. A shot keeps the first take that passes every check, and stops there. When no take passes by `takes`, it keeps the best one.

The render prints a line for each shot as it finishes, then the totals, then each failing shot with the command to run next. It writes the tape to `tapes/terminal/`, and a line for each take to `ledger.jsonl`. The stand-in passes every shot within four takes, and a real model does not. So the output here comes from `tests/test_guide.py`, whose stand-in films every other shot clean on its first take, and fails two keys on every take:

```sh
uv run videotape render --story terminal
```

```text
1. key home()  kept take 1, passed, 1 take filmed, $0.00, 1.5 s
2. key search()  kept take 1, passed, 1 take filmed, $0.00, 1.8 s
...
34. key flight(CT 104, 2026-12-13)  kept take 1, fails VT502, 4 takes filmed, $0.00, 6.1 s
...
53. key booked(CT 300, 2026-12-11)  kept take 1, fails VT503, 4 takes filmed, $0.00, 6.3 s
...
160 shots, 166 takes filmed, $0.00, 51.7 s, tape 9.8 MB -> tapes/terminal
fail: 34. key flight(CT 104, 2026-12-13)  VT502 Airbus A321neo. Earns 2,586 miles.: read "Airbus A321neo. Exrns 2,586 miles.", CER 0.029
  next: videotape retake "flight(CT 104, 2026-12-13)" --story terminal
fail: 53. key booked(CT 300, 2026-12-11)  VT503 Not in the script: a control reading "Not in the script" at 24,192 315x33, and no action has those words
  next: videotape retake "booked(CT 300, 2026-12-11)" --story terminal
```

A render run again reuses every take on disk and films only what is missing or changed. An edit to the screenplay, the data, or a story films again only the shots whose prompts it changes, and the moves that start or end on a key that changed.

### Review

```sh
uv run videotape dailies --story terminal
```

```text
wrote tapes/terminal/dailies.html with {"takes": 166, "gpu_seconds": 108.0, "pods": 0, "pod_hours": 0.0, "usd": 0.0}
```

`dailies` writes the tape's dailies page and opens it in your browser. Failing shots come first, each with its error code, what the eye read, a crop of the key where the failure is, and the commands that fix it. Below them is every shot with all its takes. `explain` prints a code's long form:

```sh
uv run videotape explain VT502
```

```text
VT502: a word was misread

Every line of a state is read back from its key, and a line reads back exactly or the check fails. The character error rate says how far off it was, and the dailies show the line's box when the eye saw one.

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
accepted VT503 on key booked(CT 300, 2026-12-11): a printed logo, not a control
```

An accept holds for the take you reviewed, which is the shot's kept take. When a later render keeps another take of that shot, the failure counts again, and the dailies show your reason beside it.

The key of `flight(CT 104, 2026-12-13)` misread a word on all four takes. Retake it:

```sh
uv run videotape retake "flight(CT 104, 2026-12-13)" --story terminal
```

```text
retaking key flight(CT 104, 2026-12-13) with seed 5
...
34. key flight(CT 104, 2026-12-13)  kept take 5, passed, 1 take filmed, $0.00, 1.1 s
...
53. key booked(CT 300, 2026-12-11)  kept take 1, fails VT503, cached, $0.00, 0.0 s
...
160 shots, 3 takes filmed, $0.00, 36.2 s, tape 9.8 MB -> tapes/terminal
accepted: 53. key booked(CT 300, 2026-12-11)  VT503 Not in the script: a control reading "Not in the script" at 24,192 315x33, and no action has those words
  reason: a printed logo, not a control
```

A retake films new takes of one shot, with seeds after the highest it has tried, and keeps the best of all its takes. Add `--takes 3` to film three. It then renders the story again, so the moves that start or end on the key film again. To retake a move, name it by its states, as in `"flight(CT 104, 2026-12-13) -> booked(CT 104, 2026-12-13)"`.

Nothing fails now that nobody accepted. Play the tape:

```sh
uv run videotape play --story terminal
```

Search for Seattle, pick a day and a flight, and book it.

### Render with a real model

wan3.0 runs Wan 3.0 on fal, which bills for each call. Its eye, Qwen3-VL-8B, needs Apple silicon or a CUDA GPU. Read the estimate before you render:

```sh
uv run videotape plan --story terminal --model wan3.0
```

```text
Contrail 0.1.0 + terminal 1.0.0: 11 scenes, 58 states, 58 keys, 102 moves, 160 shots
...
wan3.0: 160 shots, 160 to 640 calls, $80.00 to $320.00 at $0.10/s
```

To render with it, copy `.env.example` to `.env` and set `FAL_KEY` there, and set `model = "wan3.0"` in `pyproject.toml`. `.gitignore` keeps `.env` out of git, and no videotape command prints an API key. The render stops before a call that would spend more than the cap, with `VT402`. What the tape has spent is the sum of its lines in `ledger.jsonl`, so a render run again never pays for a take twice. To go on, run the render again with a higher cap, as in `--cap-usd 400`.

### Publish

`publish` turns a tape into a Mac app that plays it:

```sh
uv run videotape publish --story terminal
```

<!-- The output of publish goes here. -->

`publish` refuses a tape that is out of date with its project's files (`VT601`), that has a failing check nobody accepted (`VT602`), or whose label `videotape.lock` holds with another made id (`VT305`). Then it builds TapePlayer and writes `dist/Contrail-terminal.app`, named after the screenplay and the story, with the tape inside it and each move re-encoded as HEVC. Then the tape's eye reads the last frame of each clip in the app again, against the state the clip lands on and that state's key. A check that passed in the tape and fails on that frame is `VT604`. It signs the app ad hoc, not with a Developer ID, zips it to `dist/Contrail-terminal.zip`, and adds the label, the made id, and the file hashes to `videotape.lock`. The app opens on the tape it holds.

## The words Videotape uses

Each word below has one meaning in this guide, and each meaning has one word.

- **accept**. To mark a failing check of a shot's kept take as fine, with a reason. The accept holds while the shot keeps that take. `videotape accept`.
- **action**. What pressing an element does. It leads to the state that the element's `to=` names, and a render films it as a move.
- **API key**. A secret that a model run as a service needs, such as `FAL_KEY` for wan3.0. It comes from the environment or the project's `.env`.
- **appearance**. A story's words for how one type of element looks, under `[elements]`.
- **cap**. The most a render may spend on a model that bills per call. `cap_usd` in `[tool.videotape]` sets it, and `--cap-usd` sets it for one render.
- **check**. One test that a take must pass: each action's words are found on the key (`VT501`), each line reads back exactly (`VT502`), the key shows no control the state lacks (`VT503`), and a move starts and ends on its keys (`VT508`).
- **clause**. One part of a prompt, with its source: the engine, a part of the story, or an element of the screenplay.
- **dailies**. The review of a tape: `dailies.json`, which holds what the render knew of each shot, and `dailies.html`, the page that shows it, failures first. `videotape dailies`.
- **data table**. The records of one record class, loaded from a JSON array in `data/` with `vt.table`.
- **direction**. A story's words for one scene, under `[scenes]`, which say where the camera is and what is there.
- **element**. One thing that a state shows: `Heading`, `Text`, `Button`, `SearchBar`, `DatePicker`, `DateStrip`, `List`, `BarChart`, `LineChart`, or `Tabs`. An `Option` is a part of a search bar or a date picker, and a `Row` is a part of a list.
- **error code**. `VT` and three digits, which name one kind of error. `videotape explain <code>` prints its long form.
- **estimate**. The last line of `videotape plan`: the shots, the calls a render makes if every first take passes and if none passes before the last, and their price.
- **eye**. What reads a take back for its checks: Qwen3-VL-8B for the Wan models, and the stand-in's own reader for the stand-in.
- **hotspot**. Where a person presses an action on a key: the box in which the eye found the action's words.
- **key**. The shot of one state at rest, filmed from its own prompt. The last frame of its kept take is the state's picture in the tape, and the moves to and from the state start and end on that picture.
- **kept take**. The take a shot keeps: the first that passes every check, or the best when none passes.
- **label**. The name of a tape: the app's name and version and the story's name and version, as in `contrail 0.1.0 + terminal 1.0.0`.
- **ledger**. `ledger.jsonl` in the project, with one line for each take filmed and its price.
- **lock**. `videotape.lock` in the project, with the label, the made id, and the file hashes of each tape published. A label is published with one made id only.
- **look**. The sentence or two of a story that every key's prompt starts with.
- **made id**. One hash of everything that made a tape: the app's Python files and data, the story, the model and its settings, and videotape itself. Two tapes with one made id were made from the same things.
- **model**. The video model that films takes: `stand-in`, `wan3.0`, or `wan2.2-5b`.
- **move**. The shot of one action: the press, from the key of the state it leaves to the key of the state it lands on. A story's `[moves]` says what the camera does in it.
- **plan**. Every state the app can reach, walked from the first scene, with the keys and moves to film. `videotape plan`.
- **project**. The folder whose `pyproject.toml` has a `[tool.videotape]` section that names the screenplay.
- **prompt**. The words a model is given for one shot, made of clauses from the story and the screenplay. `videotape shots` prints them.
- **publish**. To turn a tape into a signed Mac app in `dist/` that plays it. `videotape publish`.
- **record**. One value of a record class, a `vt.Record` with typed fields. `key=` names the fields that tell two records apart.
- **render**. To film every shot of the plan in one story into a tape. `videotape render`.
- **retake**. To film new takes of one shot, with seeds after the highest it has tried, and keep the best of all its takes. `videotape retake`.
- **scene**. A function, marked with `@app.scene`, that returns the elements of one screen. Calling it names a state.
- **screenplay**. The app written as scenes: a `vt.Screenplay` and its scenes. It holds every word on the screen and nothing of how the screen looks.
- **seed**. The number a take is filmed with: 1, 2, 3, and on. A render run again reuses the take of each seed whose prompt has not changed.
- **shot**. What a render films for the plan: a key or a move.
- **stand-in**. A model that films each key as a box for each line of the state's words, and reads the boxes back as its eye. It needs no API key and no GPU, and costs nothing.
- **state**. A scene with the arguments of one call, as in `flight(CT 104, 2026-12-13)`.
- **story**. How the app looks, in one file, `stories/<name>.toml`: a version, a look, directions, appearances, and what the camera does in each move. Each story renders into its own tape.
- **take**. One filming of a shot, with one seed.
- **tape**. What a render writes in `tapes/<story>/`: each key's picture, each move's clip, every take, `tape.json`, and the dailies. `tape.json` holds each state's words and hotspots, and the label and made id. TapePlayer plays the tape.
- **TapePlayer**. The Mac app that plays a tape. `videotape play` builds it and opens a tape in it.
