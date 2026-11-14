import hashlib
import re
from datetime import date

import pytest

import videotape as vt
from conftest import CONTRAIL, FIXTURES, a_story, planned, told, videotape, words
from videotape import story
from videotape.plan import Key, plan
from videotape.project import ProjectError

RESULTS = "results(SEA, 2026-12-12)"
POSTERS_RESULTS = (
    "Static shot. A long sunlit wall in a 1960s airline ticket office, hung with screen-printed travel posters. Flat "
    "shapes, a few bold colors (teal, coral, mustard, and cream), paper grain, and bold geometric sans-serif letters. "
    "The camera faces the wall straight on. A poster of a printed timetable under a city skyline. Big bold cream "
    'letters across the top of the poster, reading "San Francisco to Seattle". A printed row of day squares, with the '
    'chosen day in coral, reading "Fri 11" "$99", "Sat 12" "$89", and "Sun 13" "$109", with "Sat 12" chosen. A printed '
    'timetable, one line per row, reading "8:15 AM to 10:25 AM", "2h 10m, Nonstop", and "$89"; and "5:40 PM to 7:50 '
    'PM", "2h 10m, Nonstop", and "$119". Sharp, legible lettering.')
TYPES = ["BarChart", "Button", "DatePicker", "DateStrip", "Heading", "LineChart", "List", "SearchBar", "Tabs", "Text"]


def a_state(name: str = "there") -> vt.State:
    scene = vt.Scene(lambda: [])
    scene.name = name
    return scene()


def home_key(*elements: vt.Element) -> Key:
    app = vt.Screenplay("Demo")
    app.scene(lambda: list(elements)).name = "home"
    return plan(app).keys[0]


def contrail_key(name: str) -> Key:
    return next(key for key in planned(CONTRAIL).keys if key.state.name == name)


def test_a_story_is_a_file_named_by_its_file_with_a_version_a_look_and_three_tables():
    terminal = told(CONTRAIL, "terminal")
    file = CONTRAIL / "stories" / "terminal.toml"
    assert (terminal.name, terminal.version, terminal.path) == ("terminal", "1.0.0", file)
    assert terminal.look == (
        "A quiet international airport terminal at first light. Polished pale terrazzo, tall glass walls onto the "
        "runway, brushed steel, warm walnut, and low golden sun. Every sign is a dark panel with crisp white letters "
        "in a plain sans-serif face.")
    assert tuple(terminal.scenes) == planned(CONTRAIL).scenes
    assert terminal.scenes["results"] == "The departure board, showing one day's flights."
    assert sorted(terminal.elements) == TYPES
    assert terminal.elements["Button"] == "a lit amber panel with bold black letters, like a gate sign"
    assert sorted(terminal.moves) == ["Button", "List", "SearchBar", "Tabs", "default"]
    assert terminal.hash == hashlib.sha256(file.read_bytes()).hexdigest()
    assert told(CONTRAIL, "posters").hash != terminal.hash


def test_a_keys_prompt_is_the_look_its_scenes_direction_each_element_and_the_lettering():
    prompt = story.prompt(contrail_key(RESULTS), told(CONTRAIL, "posters"))
    assert story.text(prompt) == POSTERS_RESULTS
    assert [str(clause.source) for clause in prompt] == [
        "engine", "story look", "story scenes.results", "story elements.Heading", "screenplay results, Heading",
        "story elements.DateStrip", "screenplay results, DateStrip", "story elements.List", "screenplay results, List",
        "engine"]
    assert [clause.text for clause in prompt][3:5] == [
        "Big bold cream letters across the top of the poster,", 'reading "San Francisco to Seattle".']


def test_a_story_never_changes_the_words_a_key_quotes():
    key = contrail_key(RESULTS)
    quoted = [re.findall(r'"[^"]*"', words(key, told(CONTRAIL, name))) for name in ("posters", "terminal")]
    assert quoted[0] == quoted[1]
    assert words(key, told(CONTRAIL, "terminal")).startswith("Static shot. A quiet international airport terminal")


THERE = a_state()
DAYS = {date(2026, 12, 11): vt.Option("$99", THERE), date(2026, 12, 12): vt.Option("$89", THERE)}


@pytest.mark.parametrize("element, reading", [
    (vt.Heading("Trips"), 'Reading "Trips".'),
    (vt.Text("Pick a day."), 'Reading "Pick a day.".'),
    (vt.Button("Book for $89", THERE), 'Reading "Book for $89".'),
    (vt.SearchBar("Where to?", to=THERE), 'Reading "Where to?".'),
    (vt.SearchBar("Where to?", options=[vt.Option("Boston (BOS)", THERE), vt.Option("Seattle (SEA)", THERE)]),
     'Reading "Where to?"; "Boston (BOS)"; and "Seattle (SEA)".'),
    (vt.DatePicker(DAYS), 'Reading "December 2026"; and "11" "$99" and "12" "$89".'),
    (vt.DateStrip(DAYS), 'Reading "Fri 11" "$99" and "Sat 12" "$89".'),
    (vt.List([vt.Row("8:15 AM", "Nonstop", "$89"), vt.Row("5:40 PM")], title="Flights"),
     'Reading "Flights"; "8:15 AM", "Nonstop", and "$89"; and "5:40 PM".'),
    (vt.List([vt.Row("Seattle", value="$89")]), 'Reading "Seattle" and "$89".'),
    (vt.BarChart("Flights per month", {"Jan": 1, "Feb": 0, "Mar": 2}),
     'Reading "Flights per month"; and "Jan" "1", "Feb" "0", and "Mar" "2".'),
    (vt.LineChart("Miles flown", {"Jan": 679, "Feb": 15055}), 'Reading "Miles flown"; and "Jan" "679" and "Feb" "15,055".'),
    (vt.Tabs({"Home": THERE, "Trips": THERE, "Profile": THERE}), 'Reading "Home", "Trips", and "Profile".'),
])
def test_an_element_is_quoted_line_by_line_with_a_label_beside_its_value_and_rows_apart(element, reading):
    key = home_key(element)
    engine, look, element_words, lettering = story.prompt(key, a_story())
    assert (engine.text, look.text, lettering.text) == ("Static shot.", "A plain room.", "Sharp, legible lettering.")
    assert (element_words.text, str(element_words.source)) == (reading, f"screenplay home, {type(element).__name__}")
    assert re.findall(r'"([^"]*)"', reading) == list(key.lines)


def test_an_option_or_tab_that_leads_to_the_state_it_is_on_is_quoted_again_as_the_chosen_one():
    app = vt.Screenplay("Demo")

    @app.scene
    def home():
        return [vt.Tabs({"Home": home(), "Trips": trips()}),
                vt.DatePicker({date(2026, 12, 11): vt.Option("$99", to=home()), date(2026, 12, 12): vt.Option("$89", to=trips())})]

    @app.scene
    def trips():
        return [vt.Tabs({"Home": home(), "Trips": trips()})]

    on_home, on_trips = plan(app).keys
    assert words(on_home, a_story()) == (
        'Static shot. A plain room. Reading "Home" and "Trips", with "Home" chosen. Reading "December 2026"; and '
        '"11" "$99" and "12" "$89", with "11" chosen. Sharp, legible lettering.')
    assert 'Reading "Home" and "Trips", with "Trips" chosen.' in words(on_trips, a_story())


def test_a_type_without_an_appearance_is_only_its_words_and_a_scene_without_a_direction_gets_only_the_look():
    key = home_key(vt.Heading("Trips"), vt.Button("Book", THERE), vt.List([]))
    dressed = a_story(scenes={"home": "A long hall."}, elements={"Button": "a lit amber panel", "List": "a board"})
    assert [(clause.text, str(clause.source)) for clause in story.prompt(key, dressed)] == [
        ("Static shot.", "engine"), ("A plain room.", "story look"), ("A long hall.", "story scenes.home"),
        ('Reading "Trips".', "screenplay home, Heading"), ("A lit amber panel,", "story elements.Button"),
        ('reading "Book".', "screenplay home, Button"), ("A board.", "story elements.List"),
        ("Sharp, legible lettering.", "engine")]
    assert words(key, a_story()) == 'Static shot. A plain room. Reading "Trips". Reading "Book". Sharp, legible lettering.'


def moves_of(*elements: vt.Element):
    app = vt.Screenplay("Demo")
    app.scene(lambda: list(elements)).name = "home"
    return plan(app).moves


def test_a_moves_prompt_names_the_element_that_was_pressed_then_the_storys_move_for_its_type():
    moves = moves_of(vt.Button("Book for $89", THERE), vt.Tabs({"Trips": a_state("trips")}),
                     vt.DatePicker({date(2026, 12, 12): vt.Option("$89", a_state("day"))}),
                     vt.DateStrip({date(2026, 12, 13): vt.Option("$109", a_state("other"))}),
                     vt.List([vt.Row("8:15 AM", value="$89", to=a_state("flight"))]),
                     vt.SearchBar("Where to?", options=[vt.Option("Seattle (SEA)", a_state("dates"))], no_match=a_state("lost")))
    directed = a_story(moves={"default": "The camera glides on.", "List": "The row lights up.", "SearchBar": "The slot lights up."})
    assert [[(clause.text, str(clause.source)) for clause in story.prompt(move, directed)] for move in moves] == [
        [('The button "Book for $89" is pressed.', "screenplay home, Button"), ("The camera glides on.", "story moves.default")],
        [('The tab "Trips" is pressed.', "screenplay home, Tabs"), ("The camera glides on.", "story moves.default")],
        [('The day "12" is pressed.', "screenplay home, DatePicker"), ("The camera glides on.", "story moves.default")],
        [('The day "Sun 13" is pressed.', "screenplay home, DateStrip"), ("The camera glides on.", "story moves.default")],
        [('The row "8:15 AM" is pressed.', "screenplay home, List"), ("The row lights up.", "story moves.List")],
        [('The search bar "Where to?" is pressed.', "screenplay home, SearchBar"), ("The slot lights up.", "story moves.SearchBar")],
        [('The option "Seattle (SEA)" is pressed.', "screenplay home, SearchBar"), ("The slot lights up.", "story moves.SearchBar")],
    ]
    assert [words(move, a_story()) for move in moves][:2] == [
        'The button "Book for $89" is pressed.', 'The tab "Trips" is pressed.']


@pytest.mark.parametrize("name", ["terminal", "posters"])
def test_every_contrail_key_quotes_each_of_its_lines_once_and_in_order_and_the_chosen_one_again(name):
    look = told(CONTRAIL, name)
    plan_ = planned(CONTRAIL)
    for key in plan_.keys:
        prompt = words(key, look)
        said_chosen = r', with "([^"]*)" chosen'
        assert re.findall(r'"([^"]*)"', re.sub(said_chosen, "", prompt)) == list(key.lines), key.state.name
        chosen = [line.words for element in key.shown for line in element.lines if line.chosen]
        assert re.findall(said_chosen, prompt) == chosen, key.state.name
    assert sum('" chosen' in words(key, look) for key in plan_.keys) == 12


def test_contrails_moves_take_their_types_move_in_terminal_and_the_default_in_posters():
    plan_ = planned(CONTRAIL)
    terminal, posters = told(CONTRAIL, "terminal"), told(CONTRAIL, "posters")
    sources = {move.element: str(story.prompt(move, terminal)[1].source) for move in plan_.moves}
    assert sources == {"SearchBar": "story moves.SearchBar", "List": "story moves.List", "Tabs": "story moves.Tabs",
                       "Button": "story moves.Button", "DatePicker": "story moves.default",
                       "DateStrip": "story moves.default"}
    assert {str(story.prompt(move, posters)[1].source) for move in plan_.moves} == {"story moves.default"}
    book = next(move for move in plan_.moves if move.title == 'flight(CT 300, 2026-12-12) -> booked(CT 300, 2026-12-12) "Book for $89"')
    assert words(book, terminal) == ('The button "Book for $89" is pressed. The panel lights up as it is pressed. '
                                     "The camera walks forward.")


SHOTS = ("shots", "--story", "posters", "--state", RESULTS)


def test_shots_prints_each_prompt_under_its_title_one_clause_to_a_line_with_its_source_beside_it():
    result = videotape(CONTRAIL, *SHOTS)
    assert (result.stderr, result.returncode) == ("", 0)
    shots = [block.splitlines() for block in result.stdout.split("\n\n")]
    assert [shot[0] for shot in shots] == [
        f"key {RESULTS}", f'{RESULTS} -> results(SEA, 2026-12-11) "Friday, December 11, $99"',
        f'{RESULTS} -> results(SEA, 2026-12-13) "Sunday, December 13, $109"',
        f'{RESULTS} -> flight(CT 300, 2026-12-12) "8:15 AM to 10:25 AM, 2h 10m, Nonstop, $89"',
        f'{RESULTS} -> flight(CT 306, 2026-12-12) "5:40 PM to 7:50 PM, 2h 10m, Nonstop, $119"']
    key, first_move = shots[0][1:], shots[1][1:]
    assert all(line[:2] == "  " and line[31:33] == "  " and line[33] != " " for line in key + first_move)
    assert [line[2:31].rstrip() for line in key] == [
        "engine", "story look", "story scenes.results", "story elements.Heading", "screenplay results, Heading",
        "story elements.DateStrip", "screenplay results, DateStrip", "story elements.List", "screenplay results, List",
        "engine"]
    assert " ".join(line[33:] for line in key) == POSTERS_RESULTS
    assert first_move == [
        '  screenplay results, DateStrip  The day "Fri 11" is pressed.',
        "  story moves.default            The camera slides along the wall to the next poster and settles straight on."]


def test_shots_without_a_state_prints_every_shot_of_the_plan():
    result = videotape(CONTRAIL, "shots", "--story", "terminal")
    shots = result.stdout.split("\n\n")
    assert (len(shots), result.returncode) == (160, 0)
    assert [shot.splitlines()[0] for shot in shots] == [shot.title for shot in planned(CONTRAIL).shots]


@pytest.mark.parametrize("arguments, code, error", [
    (("shots", "--story", "posters", "--state", "results(SEA, 2026-12-21)"), 1,
     'error: the app has no state "results(SEA, 2026-12-21)"; the closest are results(SEA, 2026-12-11), '
     "results(SEA, 2026-12-12), results(SEA, 2026-12-13)\n"),
    (("shots", "--story", "poster"), 1, 'error: no story "poster" in stories; the stories are posters and terminal\n'),
    (("render", "--story", "poster"), 1, 'error: no story "poster" in stories; the stories are posters and terminal\n'),
    (("plan", "--story", "poster"), 1, 'error: no story "poster" in stories; the stories are posters and terminal\n'),
    (("plan", "--model", "wan3.0"), 1,
     "error: --model checks a story's prompts against that model, so pass --story with it\n"),
])
def test_a_story_or_a_state_the_project_does_not_have_is_named_with_the_ones_it_has(arguments, code, error):
    result = videotape(CONTRAIL, *arguments)
    assert (result.stdout, result.stderr, result.returncode) == ("", error, code)
    assert not (CONTRAIL / "tapes" / "poster").exists()


@pytest.mark.parametrize("command", ["shots", "render"])
def test_shots_and_render_need_a_story(command):
    result = videotape(CONTRAIL, command)
    assert result.returncode == 2
    assert f"videotape {command}: error: the following arguments are required: --story" in result.stderr


def test_a_project_without_stories_says_which_file_to_add():
    result = videotape(FIXTURES / "errors" / "vt211", "shots", "--story", "neon")
    assert (result.stdout, result.stderr, result.returncode) == (
        "", 'error: no story "neon" in stories; add stories/neon.toml\n', 1)


@pytest.mark.parametrize("name", ["terminal", "posters"])
def test_plan_checks_a_contrail_story_and_names_it_after_the_apps_version(name):
    result = videotape(CONTRAIL, "plan", "--story", name)
    assert (result.stderr, result.returncode) == ("", 0)
    assert result.stdout.splitlines()[0] == f"Contrail 0.1.0 + {name} 1.0.0: 11 scenes, 58 states, 58 keys, 102 moves, 160 shots"
    assert result.stdout.splitlines()[-1] == "0 errors, 0 warnings"
    assert result.stdout.splitlines()[1:] == videotape(CONTRAIL, "plan").stdout.splitlines()[1:]


def test_a_table_that_holds_something_other_than_words_is_refused(tmp_path):
    file = tmp_path / "odd.toml"
    file.write_text('version = "1.0.0"\nlook = "A plain room."\n\n[scenes]\nhome = 3\n')
    with pytest.raises(ProjectError, match=r'odd\.toml: \[scenes\] holds something other than words, as in name = "\.\.\."'):
        story.load(file)
    file.write_text('version = 1.0\nlook = "A plain room."\n')
    with pytest.raises(vt.ScreenplayError) as error:
        story.load(file)
    assert (error.value.code, error.value.message) == ("VT301", "the story has the version 1.0, which is not in quotes")
