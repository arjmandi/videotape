import re
from datetime import date

import pytest

import videotape as vt
from conftest import CONTRAIL, planned
from videotape.plan import Mode, plan


class Airport(vt.Record, key="code"):
    code: str
    city: str


class Flight(vt.Record, key=("number", "day")):
    number: str
    day: date
    fare: int


SEA = Airport("SEA", "Seattle")
CT300 = Flight("CT 300", date(2026, 12, 12), 89)


def one_scene(*elements: vt.Element) -> vt.Screenplay:
    app = vt.Screenplay("Demo")
    app.scene(lambda: list(elements)).name = "home"
    return app


def a_state(name: str = "there") -> vt.State:
    """A state of a scene that shows nothing, for an action to lead to."""
    scene = vt.Scene(lambda: [])
    scene.name = name
    return scene()


def home_key(*elements: vt.Element):
    return plan(one_scene(*elements)).keys[0]


def test_calling_a_scene_names_a_state_and_does_not_build_it():
    app = vt.Screenplay("Demo")
    built = []

    @app.scene
    def results(place: Airport, day: date):
        built.append((place, day))
        return [vt.Heading(place.city)]

    state = results(SEA, date(2026, 12, 12))
    assert built == []
    assert (state.scene, state.args) == (results, (SEA, date(2026, 12, 12)))
    assert state == results(day=date(2026, 12, 12), place=SEA)
    assert state != results(SEA, date(2026, 12, 13))
    assert len({state, results(SEA, date(2026, 12, 12))}) == 1


def test_a_state_is_named_by_its_scene_and_its_arguments():
    app = vt.Screenplay("Demo")

    @app.scene
    def home():
        return []

    @app.scene
    def results(place: Airport, day: date):
        return []

    @app.scene
    def flight(f: Flight):
        return []

    @app.scene
    def seat(row: int, letter: str = "A"):
        return []

    assert home().name == "home()"
    assert results(SEA, date(2026, 12, 12)).name == "results(SEA, 2026-12-12)"
    assert flight(CT300).name == "flight(CT 300, 2026-12-12)"
    assert seat(14).name == "seat(14, A)"


def test_the_walk_is_breadth_first_from_the_first_scene():
    app = vt.Screenplay("House")

    @app.scene
    def hall():
        return [vt.Button("Left door", to=room("left")), vt.Button("Right door", to=room("right"))]

    @app.scene
    def room(side: str):
        return [vt.Heading(side), vt.Button("Open", to=inside(side)), vt.Button("Back", to=hall())]

    @app.scene
    def inside(side: str):
        return [vt.Text(f"Inside the {side} room")]

    planned = plan(app)
    assert planned.scenes == ("hall", "room", "inside")
    assert [key.state.name for key in planned.keys] == ["hall()", "room(left)", "room(right)", "inside(left)", "inside(right)"]
    assert [(move.start.name, move.label, move.land.name) for move in planned.moves] == [
        ("hall()", "Left door", "room(left)"), ("hall()", "Right door", "room(right)"),
        ("room(left)", "Open", "inside(left)"), ("room(left)", "Back", "hall()"),
        ("room(right)", "Open", "inside(right)"), ("room(right)", "Back", "hall()")]
    assert [key.mode for key in planned.keys] == [Mode.TEXT_TO_VIDEO] * 5
    assert [move.mode for move in planned.moves] == [Mode.FIRST_AND_LAST_FRAME] * 6
    assert planned.shots == (*planned.keys, *planned.moves)


def test_each_elements_words_are_its_lines_in_reading_order():
    there = a_state()
    days = {date(2026, 12, 12): vt.Option("$89", there), date(2026, 12, 11): vt.Option("$99", there)}
    assert home_key(vt.Heading("Trips"), vt.Text("Pick a day."), vt.Button("Book", there)).lines == (
        "Trips", "Pick a day.", "Book")
    assert home_key(vt.SearchBar("Where to?", options=[vt.Option("Boston (BOS)", there)])).lines == (
        "Where to?", "Boston (BOS)")
    assert home_key(vt.DatePicker(days)).lines == ("December 2026", "11", "$99", "12", "$89")
    assert home_key(vt.DateStrip(days)).lines == ("Fri 11", "$99", "Sat 12", "$89")
    assert home_key(vt.List([vt.Row("8:15 AM", "Nonstop", "$89"), vt.Row("5:40 PM")], title="Flights")).lines == (
        "Flights", "8:15 AM", "Nonstop", "$89", "5:40 PM")
    assert home_key(vt.List([vt.Row("Seattle", value="$89")])).lines == ("Seattle", "$89")
    assert home_key(vt.BarChart("Flights per month", {"Jan": 1, "Feb": 0})).lines == (
        "Flights per month", "Jan", "1", "Feb", "0")
    assert home_key(vt.LineChart("Miles flown", {"Jan": 679, "Feb": 15055})).lines == (
        "Miles flown", "Jan", "679", "Feb", "15,055")
    assert home_key(vt.Tabs({"Home": there, "Trips": there})).lines == ("Home", "Trips")


def test_an_action_is_found_by_its_words_and_pressed_by_its_hotspots_label():
    there = a_state()
    days = {date(2026, 12, 12): vt.Option("$89", there)}

    def actions(*elements: vt.Element) -> list[tuple[str, str, str]]:
        return [(action.label, action.words, action.to.name) for action in home_key(*elements).actions]

    assert actions(vt.Button("Book for $89", there)) == [("Book for $89", "Book for $89", "there()")]
    assert actions(vt.SearchBar("Where to?", to=there)) == [("Where to?", "Where to?", "there()")]
    assert actions(vt.SearchBar("Where to?", options=[vt.Option("Boston (BOS)", there)], no_match=a_state("lost"))) == [
        ("Where to?", "Where to?", "lost()"), ("Boston (BOS)", "Boston (BOS)", "there()")]
    assert actions(vt.DatePicker(days)) == [("Saturday, December 12, $89", "12", "there()")]
    assert actions(vt.DateStrip(days)) == [("Saturday, December 12, $89", "Sat 12", "there()")]
    assert actions(vt.List([vt.Row("8:15 AM to 10:25 AM", "2h 10m, Nonstop", "$89", to=there)])) == [
        ("8:15 AM to 10:25 AM, 2h 10m, Nonstop, $89", "8:15 AM to 10:25 AM", "there()")]
    assert actions(vt.Tabs({"Trips": there})) == [("Trips", "Trips", "there()")]


def test_what_leads_nowhere_is_no_action():
    there = a_state()
    assert home_key(vt.Heading("Trips"), vt.Text("Soon"), vt.SearchBar("Where to?"), vt.List([vt.Row("Seattle")]),
                    vt.SearchBar("From?", options=[vt.Option("Boston", there)]),
                    vt.BarChart("Flights", {"Jan": 1})).actions == (
        home_key(vt.SearchBar("From?", options=[vt.Option("Boston", there)])).actions)


def test_an_action_that_leads_to_the_state_it_is_on_is_none_and_its_option_or_tab_is_the_chosen_one():
    app = vt.Screenplay("Demo")

    @app.scene
    def home():
        return [vt.Tabs({"Home": home(), "Trips": trips()}), vt.Button("Refresh", to=home()),
                vt.DateStrip({date(2026, 12, 11): vt.Option("$99", to=home()), date(2026, 12, 12): vt.Option("$89", to=trips())})]

    @app.scene
    def trips():
        return [vt.Tabs({"Home": home(), "Trips": trips()})]

    on_home, on_trips = plan(app).keys
    assert [action.label for action in on_home.actions] == ["Trips", "Saturday, December 12, $89"]
    assert on_home.lines == ("Home", "Trips", "Refresh", "Fri 11", "$99", "Sat 12", "$89")
    assert chosen(on_home) == ["Home", "Fri 11"]
    assert [action.label for action in on_trips.actions] == ["Home"]
    assert chosen(on_trips) == ["Trips"]


def chosen(key) -> list[str]:
    return [line.words for element in key.shown for line in element.lines if line.chosen]


def test_a_key_holds_each_element_by_its_type_with_its_lines_in_rows_and_nothing_of_how_it_looks():
    there = a_state()
    key = home_key(vt.Heading("San Francisco to Seattle"),
                   vt.DateStrip({date(2026, 12, 11): vt.Option("$99", there), date(2026, 12, 12): vt.Option("$89", there)}),
                   vt.List([vt.Row("8:15 AM", "Nonstop", "$89"), vt.Row("5:40 PM")], title="Flights"),
                   vt.List([]))
    assert [(element.type, [[[line.words for line in cell] for cell in row] for row in element.rows])
            for element in key.shown] == [
        ("Heading", [[["San Francisco to Seattle"]]]),
        ("DateStrip", [[["Fri 11", "$99"], ["Sat 12", "$89"]]]),
        ("List", [[["Flights"]], [["8:15 AM"], ["Nonstop"], ["$89"]], [["5:40 PM"]]]),
        ("List", []),
    ]
    assert not hasattr(key, "prompt")


def test_a_move_holds_its_action_and_the_type_of_the_element_that_holds_it():
    there = a_state()
    moves = plan(one_scene(vt.Button("Book for $89", there), vt.Tabs({"Trips": a_state("trips")}),
                           vt.DatePicker({date(2026, 12, 12): vt.Option("$89", a_state("day"))}),
                           vt.DateStrip({date(2026, 12, 13): vt.Option("$109", a_state("other"))}),
                           vt.List([vt.Row("8:15 AM", value="$89", to=a_state("flight"))]),
                           vt.SearchBar("Where to?", options=[vt.Option("Seattle (SEA)", a_state("dates"))],
                                        no_match=a_state("lost")))).moves
    assert [(move.action.kind, move.action.words, move.element, move.land.name) for move in moves] == [
        ("button", "Book for $89", "Button", "there()"), ("tab", "Trips", "Tabs", "trips()"),
        ("day", "12", "DatePicker", "day()"), ("day", "Sun 13", "DateStrip", "other()"),
        ("row", "8:15 AM", "List", "flight()"), ("search bar", "Where to?", "SearchBar", "lost()"),
        ("option", "Seattle (SEA)", "SearchBar", "dates()")]
    assert [move.title for move in moves][:2] == ['home() -> there() "Book for $89"', 'home() -> trips() "Trips"']
    assert [move.label for move in moves][2:4] == ["Saturday, December 12, $89", "Sunday, December 13, $109"]


def test_every_key_and_move_of_contrail_has_its_own_file_safe_name():
    plan_ = planned(CONTRAIL)
    names = [key.image for key in plan_.keys] + [move.clip for move in plan_.moves]
    assert len({name.lower() for name in names}) == len(names) == 160
    assert all(re.fullmatch(r"(keys|moves)/[a-z0-9-]+\.(png|mp4)", name) for name in names)
    assert plan_.keys[0].image == "keys/home.png"
    assert "moves/opening.mp4" not in names


def test_two_names_that_would_share_a_file_are_told_apart():
    app = vt.Screenplay("Demo")

    @app.scene
    def home():
        return [vt.Button("Go.", to=room("a b")), vt.Button("Go!", to=room("a-b"))]

    @app.scene
    def room(name: str):
        return []

    planned = plan(app)
    assert [key.image for key in planned.keys] == ["keys/home.png", "keys/room-a-b.png", "keys/room-a-b-2.png"]
    assert [move.clip for move in planned.moves] == ["moves/home--go.mp4", "moves/home--go-2.mp4"]


@pytest.mark.parametrize("line, wrong, fix", [
    ("We open every single day of the week at seven in the morning sharp.", "has 14 words",
     "shorten it to 12 words or fewer"),
    ("Café Lumière", "has the characters è é",
     "write it with plain ASCII letters, digits, spaces, and . , ' ? ! $ % ( ) : -"),
    ('The "best" coffee', 'has the character "',
     "write it with plain ASCII letters, digits, spaces, and . , ' ? ! $ % ( ) : -"),
])
def test_a_line_that_is_hard_to_letter_is_a_vt211_warning_and_the_plan_goes_on(line, wrong, fix):
    planned = plan(one_scene(vt.Heading(line), vt.Text(line), vt.Text("Twelve words: it's $5 (50% off)! So? Yes, yes - indeed, 100%.")))
    assert len(planned.keys) == 1
    [warning] = planned.warnings
    assert (warning.code, warning.place, warning.fix) == ("VT211", "home()", fix)
    assert warning.message == f'the line "{line}" {wrong}'
