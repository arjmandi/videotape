import ast
import builtins
import importlib
import re
import shutil
from pathlib import Path

import pytest

from conftest import FIXTURES, copy_of, videotape
from videotape.errors import CODES, PACKAGE, RenderError, ScreenplayError, step

PLAIN = "plain ASCII letters, digits, spaces, and . , ' ? ! $ % ( ) : -"


def division_by_zero(guests: int = 0) -> str:
    """What this Python says when the vt203 fixture's scene divides by no guests. Python 3.14 reworded it."""
    with pytest.raises(ZeroDivisionError) as raised:
        120 // guests
    return str(raised.value)


ERRORS = {
    "VT201": ("app.py:3", "the screenplay has no scenes",
              "add a scene with @app.scene; the first one is where the app opens"),
    "VT202": ("app.py:8", 'the to= of Button "Open" is the scene detail itself, not a state, in state home()',
              "call the scene to name a state, as in detail()"),
    "VT203": ("app.py:13", f"the scene raised ZeroDivisionError: {division_by_zero()}, in state split(0)",
              "make the scene build for these arguments, or keep this state out of every to="),
    "VT204": ("app.py:11", "no action reaches the scene help",
              "lead to it from a scene that is reached, as in to=help(), or delete it"),
    "VT205": ("app.py:9", "no data file at data/drinks.json",
              'create it, or correct the path; "data/drinks.json" is relative to the folder of pyproject.toml'),
    "VT206": ("data/drinks.json:3", 'record 2 field "price" is "six", not a whole number', "write a whole number"),
    "VT207": ("app.py:15", 'Drink has no field "cost", in state home()', "name one of its fields: name, price"),
    "VT208": ("app.py:15", "get(name='Mocha') matched no Drink from data/drinks.json, in state home()",
              "ask for a record the data holds, or count the matches with where(...).count()"),
    "VT209": ("home()", 'two actions have the spoken name "Open"', "give each action words of its own"),
    "VT210": ("count(5)", "the plan reached more than 5 states",
              "let a scene's arguments come from the data, which ends, or raise max_states in [tool.videotape]"),
    "VT213": ("app.py:9", "Drink.price is <class 'float'>, and a record's field is a str, an int, a date or a time",
              "make price one of those, as in price: int"),
    "VT301": ("stories/neon.toml", "the story has no look",
              'write look = "...", the look of the whole app in a sentence or two, above the first [heading]'),
    "VT302": ("stories/neon.toml:6", "the story directs the scene detial, and the screenplay has no scene of that name",
              "write detail, the closest of the screenplay's scenes"),
    "VT303": ("stories/neon.toml:10",
              "the story gives an appearance to the element type Buton, which the screenplay does not use",
              "write Button, the closest of the screenplay's element types"),
    "VT306": ("stories/neon.toml:2", "the story is not TOML: Invalid value",
              'write each line as name = "words", under [scenes], [elements] or [moves], or above all three'),
    "VT308": ("stories/neon.toml:5", "home under [scenes] quotes '\u201cOpen\u201d.'",
              "remove the quotes; the screenplay owns every word on screen, so describe how they are drawn"),
    "VT309": ("stories", 'no story "neon"', "name one of the stories there, glow"),
}
WARNINGS = {
    "VT211": [("home()", 'the line "Café Lumière" has the characters è é', f"write it with {PLAIN}"),
              ("home()", 'the line "We open every single day of the week at seven in the morning sharp." has 14 words',
               "shorten it to 12 words or fewer")],
    "VT304": [("stories/neon.toml", "the scene detail has no direction, so its keys get only the look",
               'add detail = "..." under [scenes]')],
    "VT307": [("key home()", "the prompt is about 778 tokens long, and wan2.2-5b allows no more than 512",
               "shorten the look, the scene's direction or the appearances in stories/neon.toml, or show fewer lines "
               "in this state")],
}
SUMMARIES = {"VT211": "Cafe 0.1.0: 1 scene, 1 state, 1 key of which 0 rehearsed, 0 moves, 1 shot",
             "VT304": "Shop 0.1.0 + neon 1.0.0: 2 scenes, 2 states, 2 keys of which 1 rehearsed, 1 move, 2 shots",
             "VT307": "Shop 0.1.0 + neon 1.0.0: 1 scene, 1 state, 1 key of which 0 rehearsed, 0 moves, 1 shot"}
ESTIMATES = {"VT307": ["wan2.2-5b: 1 shot, 1 to 4 calls, free, and 1 to 4 reads by claude-opus-5-5, at most $0.17 to $0.69"]}
"""The plan ends with the estimate for the project's model, and only the vt307 fixture names one."""


def in_its_story(code: str) -> tuple[str, ...]:
    """A VT3xx fixture is a project with a story of its own, named neon, which the command has to name."""
    return ("--story", "neon") if code >= "VT300" else ()


PLANNED = sorted(code for code in CODES if "VT200" <= code < "VT400" and code not in ("VT212", "VT305", "VT310"))
"""The codes a plan can raise from a screenplay or a story, each with a fixture. The project's codes and doctor's are
covered by their own tests, the render's and the checks' codes need a model and are covered by the render tests,
VT305, a label published already, is publish's and covered by its tests, VT212, a shot's name no shot has, is
retake's, accept's and shots' and covered by theirs, and VT310, --model without --story, is covered below."""


def test_a_fixture_triggers_every_code_the_plan_can_raise():
    assert sorted(path.name.upper() for path in (FIXTURES / "errors").iterdir()) == PLANNED
    assert sorted([*ERRORS, *WARNINGS]) == PLANNED


@pytest.mark.parametrize("code", sorted(ERRORS))
def test_an_error_prints_its_code_its_place_and_its_fix_and_plans_nothing(code):
    place, message, fix = ERRORS[code]
    result = videotape(FIXTURES / "errors" / code.lower(), "plan", *in_its_story(code))
    assert (result.stdout, result.returncode) == ("", 1)
    assert result.stderr == f"error {code} {place}: {message}\nfix: {fix}\n"


@pytest.mark.parametrize("code", sorted(ERRORS))
def test_render_stops_on_the_same_error_before_it_draws_anything(code):
    directory = FIXTURES / "errors" / code.lower()
    result = videotape(directory, "render", "--story", "neon", "--model", "stand-in")
    assert (result.stdout, result.returncode) == ("", 1)
    assert result.stderr.startswith(f"error {code} {ERRORS[code][0]}: ")
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


@pytest.mark.parametrize("code", sorted(code for code in ERRORS if code >= "VT300"))
def test_shots_stops_on_a_storys_error_before_it_prints_a_prompt(code):
    result = videotape(FIXTURES / "errors" / code.lower(), "shots", "--story", "neon")
    assert (result.stdout, result.returncode) == ("", 1)
    assert result.stderr.startswith(f"error {code} {ERRORS[code][0]}: ")


@pytest.mark.parametrize("code", sorted(WARNINGS))
def test_a_warning_prints_its_code_its_place_and_its_fix_and_the_plan_goes_on(code):
    result = videotape(FIXTURES / "errors" / code.lower(), "plan", *in_its_story(code))
    assert result.returncode == 0
    assert result.stderr == "".join(f"warning {code} {place}: {message}\nfix: {fix}\n"
                                    for place, message, fix in WARNINGS[code])
    assert result.stdout.splitlines()[0] == SUMMARIES[code]
    count = len(WARNINGS[code])
    estimate = ESTIMATES.get(code, [])
    assert result.stdout.splitlines()[-1 - len(estimate):] == [
        f"0 errors, {count} warning{'' if count == 1 else 's'}", *estimate]


def test_a_key_of_a_scene_without_a_direction_gets_only_the_look_before_its_elements():
    result = videotape(FIXTURES / "errors" / "vt304", "shots", "--story", "neon", "--state", "detail()")
    [(place, message, fix)] = WARNINGS["VT304"]
    assert (result.stderr, result.returncode) == (f"warning VT304 {place}: {message}\nfix: {fix}\n", 0)
    assert result.stdout.splitlines()[:5] == [
        "key detail() rehearsed from home()", '  screenplay home, Button     The button "Open" is pressed.',
        "  engine                      It ends held still on the next screen.",
        "  story look                  A narrow shop on a rainy street at night.",
        '  screenplay detail, Heading  Reading "Detail".']


def test_the_stand_in_reads_any_length_of_prompt_so_the_same_story_has_no_vt307_with_it():
    result = videotape(FIXTURES / "errors" / "vt307", "plan", "--story", "neon", "--model", "stand-in")
    assert (result.stderr, result.returncode) == ("", 0)
    assert result.stdout.splitlines()[-2:] == ["0 errors, 0 warnings", "stand-in: 1 shot, 1 to 4 calls, free"]
    over = videotape(FIXTURES / "errors" / "vt307", "plan", "--story", "neon", "--model", "wan3.0")
    assert (over.stderr, over.stdout.splitlines()[-2:]) == (
        "", ["0 errors, 0 warnings", "wan3.0: 1 shot, 1 to 4 calls, $0.50 to $2.00 at $0.10/s, and 1 to 4 reads by claude-opus-5-5, at most $0.17 to $0.69"])


def test_a_plan_with_a_variant_stops_on_a_model_that_films_no_key_from_a_picture_as_its_render_would():
    result = videotape(FIXTURES / "cafe", "plan", "--story", "chalk", "--model", "wan2.2-5b")
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == ("error VT111 wan2.2-5b: films no key from another key's picture, and 4 keys of the plan are "
                             "drawn from one, a base's or the picture of the state a rehearsed base is reached from\n"
                             "fix: render with a model on fal, whose image-to-video takes one picture, as in --model "
                             "gemini-omni-flash-1.2, or with the stand-in\n")
    drawn = videotape(FIXTURES / "cafe", "plan", "--story", "chalk", "--model", "gemini-omni-flash-1.2")
    assert (drawn.returncode, drawn.stderr) == (0, "")


def test_explain_has_a_long_form_an_example_and_a_fix_for_every_code_the_framework_can_raise():
    package = Path(__file__).parent.parent / "videotape"
    raised = {code for path in package.glob("*.py") if path.name != "errors.py"
              for code in re.findall(r"VT\d{3}", path.read_text())}
    assert raised == set(CODES)
    for code, entry in CODES.items():
        result = videotape(package.parent, "explain", code)
        assert result.returncode == 0, code
        title, long, example, fix = result.stdout.rstrip("\n").split("\n\n", 3)
        assert title == f"{code}: {entry.title}"
        assert len(long.split()) > 15
        assert example.startswith("Example:\n    ") and len(example.splitlines()) > 1
        what = "Next" if "VT400" <= code < "VT600" else "Fix"
        assert f"\n\n{what}:\n    " in f"\n\n{fix}" and len(fix.splitlines()) > 1


def test_explain_rejects_a_code_that_does_not_exist(tmp_path):
    result = videotape(tmp_path, "explain", "VT999")
    assert result.returncode == 2
    assert "invalid choice: 'VT999'" in result.stderr


MODELS = "gemini-omni-flash-1.2, minimax-h3, stand-in, wan2.2-5b, wan3.0"


@pytest.mark.parametrize("pyproject, error", [
    (None, "VT106 pyproject.toml: no pyproject.toml here or in any folder above\n"
           "fix: run videotape in an app's project, or start one with videotape new <name>"),
    ('[project]\nname = "app"\n', "VT106 pyproject.toml: has no [tool.videotape] section\nfix: add one that names the "
     'screenplay, its module and the name of its vt.Screenplay: [tool.videotape] screenplay = "shop.screenplay:app"'),
    ("[tool.videotape\n", "VT107 pyproject.toml: is not TOML: Expected ']' at the end of a table declaration "
     "(at line 1, column 16)\nfix: write it as TOML, at the line the error names"),
    ('[tool.videotape]\nscreenplay = "app"\n', "VT107 pyproject.toml: [tool.videotape] screenplay is 'app', not "
     '"module:app"\nfix: set it to the module and the name of its vt.Screenplay, as in '
     'screenplay = "shop.screenplay:app"'),
    ('[tool.videotape]\nscreenplay = "shop:app"\n', 'VT107 pyproject.toml: [tool.videotape] screenplay is "shop:app", '
     "and the project has no module shop\nfix: name the module that holds the screenplay, from the project's folder, "
     "as in shop.screenplay for shop/screenplay.py"),
    ('[tool.videotape]\nscreenplay = "app:shop"\n', 'VT107 pyproject.toml: [tool.videotape] screenplay is "app:shop", '
     'and shop in app is missing\nfix: name the vt.Screenplay that app makes, as in shop = vt.Screenplay("Shop")'),
    ('[tool.videotape]\nscreenplay = "app:Path"\n', 'VT107 pyproject.toml: [tool.videotape] screenplay is "app:Path", '
     'and Path in app is not a vt.Screenplay\nfix: name the vt.Screenplay that app makes, as in '
     'Path = vt.Screenplay("Shop")'),
    ('[tool.videotape]\nscreenplay = "app:app"\nmodel = 3\n', "VT107 pyproject.toml: [tool.videotape] model is 3, "
     f"not a model's name\nfix: set model to one of {MODELS}"),
    ('[tool.videotape]\nscreenplay = "app:app"\nmodel = "wan3"\n', 'VT107 pyproject.toml: [tool.videotape] model is '
     f'"wan3", and videotape has no such model\nfix: set model to one of {MODELS}'),
    ('[tool.videotape]\nscreenplay = "app:app"\nmax_states = 0\n', "VT107 pyproject.toml: [tool.videotape] max_states "
     "is 0, not a whole number of states\nfix: set it to a whole number of at least 1, as in max_states = 500"),
    ('[tool.videotape]\nscreenplay = "app:app"\ntakes = 2.5\n', "VT107 pyproject.toml: [tool.videotape] takes is 2.5, "
     "not a whole number of takes\nfix: set it to a whole number of at least 1, as in takes = 4"),
    ('[tool.videotape]\nscreenplay = "app:app"\ncap_usd = "20"\n', "VT107 pyproject.toml: [tool.videotape] cap_usd is "
     "'20', not a number of dollars\nfix: set it to the most a render may spend, in dollars, as in cap_usd = 20"),
])
def test_a_project_that_is_not_one_or_sets_a_wrong_value_says_what_to_set(tmp_path, pyproject, error):
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject)
    (tmp_path / "app.py").write_text('from pathlib import Path\n\nimport videotape as vt\n\napp = vt.Screenplay("Shop")\n')
    result = videotape(tmp_path, "plan")
    assert (result.stdout, result.stderr, result.returncode) == ("", f"error {error}\n", 1)


UNCODED = {
    ("cli", "ArgumentTypeError"): "argparse prints a value it rejects in its usage line and exits 2, as it does for "
                                  "every argument it rejects",
    ("errors", "KeyError"): "a code without an entry in CODES is a fault in videotape, which this file's tests catch",
    ("data", "ValueError"): "_record catches it and raises VT206 for the field",
    ("plan", "TypeError"): "a scene that returns something other than an element raises it, and the plan reports VT203",
    ("screenplay", "TypeError"): "a scene's code calls it wrongly, and the plan reports VT203 for the scene",
    ("screenplay", "ValueError"): "a scene's code calls it wrongly, and the plan reports VT203 for the scene",
    ("standin", "ValueError"): "a flaw that does not fit a take is a fault in the test that gives the stand-in it",
}
"""The exceptions videotape makes without a code, each with what reports it instead."""


def _exception(node: ast.expr, module: object) -> type[BaseException] | None:
    """The exception class a call's function names, from the module's names or Python's, or None."""
    if isinstance(node, ast.Name):
        found = getattr(module, node.id, getattr(builtins, node.id, None))
    elif isinstance(node, ast.Attribute) and (owner := _exception_owner(node.value, module)) is not None:
        found = getattr(owner, node.attr, None)
    else:
        return None
    return found if isinstance(found, type) and issubclass(found, BaseException) else None


def _exception_owner(node: ast.expr, module: object) -> object | None:
    if isinstance(node, ast.Name):
        return getattr(module, node.id, None)
    if isinstance(node, ast.Attribute) and (owner := _exception_owner(node.value, module)) is not None:
        return getattr(owner, node.attr, None)
    return None


def test_every_error_videotape_makes_carries_a_code_a_place_and_a_fix():
    uncoded = []
    for path in sorted(PACKAGE.glob("*.py")):
        module = importlib.import_module(f"videotape.{path.stem}")
        tree = ast.parse(path.read_text())
        caught = {name.id for handler in ast.walk(tree) if isinstance(handler, ast.ExceptHandler) and handler.type
                  for name in ast.walk(handler.type) if isinstance(name, ast.Name)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or (made := _exception(node.func, module)) is None:
                continue
            private = made.__name__.startswith("_") and made.__name__ in caught
            if not (issubclass(made, (ScreenplayError, RenderError)) or private
                    or (path.stem, made.__name__) in UNCODED):
                uncoded.append(f"{path.name}:{node.lineno} makes a {made.__name__}")
    assert uncoded == []


RENDER, RETAKE = ("render", "--story", "chalk"), ("retake", "menu()", "--story", "chalk")
ACCEPT = ("accept", "menu()", "VT503", "--story", "chalk", "--reason", "a printed logo")
DAILIES, PUBLISH = ("dailies", "--story", "chalk"), ("publish", "--story", "chalk")
DIFF = ("diff", "tapes/chalk", "tapes/chalk")
RENDERS = {DIFF: "videotape render --story <story>"}
"""The render command a next step names, for a command that does not name the story: the rest name the story's own."""


def not_json(text: str) -> str:
    return "{"


def a_line_that_is_not_json(text: str) -> str:
    return '{"kind": "take"\n' + text


def a_model_videotape_lacks(text: str) -> str:
    assert text.count('"name": "stand-in"') == 1
    return text.replace('"name": "stand-in"', '"name": "wan9"')


CORRUPT = [
    ("tapes/chalk/tape.json", not_json, (RETAKE, PUBLISH, DIFF), "VT410", "tapes/chalk/tape.json",
     "run the render again, which writes it afresh from the takes on disk, as in:\n{render}"),
    ("tapes/chalk/tape.json", a_model_videotape_lacks, (RETAKE, PUBLISH), "VT601", "tapes/chalk",
     f"render the story again with a model it has, one of {MODELS}, as in:\n{{render}} --model stand-in"),
    ("tapes/chalk/dailies.json", not_json, (RENDER, RETAKE, ACCEPT, DAILIES, PUBLISH), "VT410",
     "tapes/chalk/dailies.json", "mend it, or put it aside and run the render again, which writes it afresh from the "
     "takes on disk, without the accepts and the retake seeds it held, as in:\n{render}"),
    ("ledger.jsonl", a_line_that_is_not_json, (RENDER, RETAKE, DAILIES), "VT410", "ledger.jsonl:1",
     "delete the line, or mend it; the lines are appended and never rewritten, so the rest stand, and what the line's "
     "call billed no longer counts toward the tape's cap"),
]
"""Each file a command reads from a tape or its project, a way it can be wrong, the commands that read it, and the code,
the place and the next step each of them prints for it. A file videotape reads is one row here."""


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """The cafe, rendered with the stand-in by the installed command, as a developer renders it."""
    directory = copy_of("cafe", tmp_path_factory.mktemp("rendered"))
    result = videotape(directory, *RENDER)
    assert (result.returncode, result.stderr) == (0, ""), result.stderr
    return directory


@pytest.mark.parametrize("file, corrupt, command, code, place, next", [
    pytest.param(file, corrupt, command, code, place, next, id=f"{Path(file).name} {corrupt.__name__} {command[0]}")
    for file, corrupt, commands, code, place, next in CORRUPT for command in commands])
def test_a_corrupt_file_videotape_reads_stops_the_command_with_a_code_a_place_and_a_next_step(
        rendered, tmp_path, file, corrupt, command, code, place, next):
    directory = Path(shutil.copytree(rendered, tmp_path / "cafe", ignore=shutil.ignore_patterns("__pycache__")))
    (directory / file).write_text(corrupt((directory / file).read_text()))
    result = videotape(directory, *command)
    assert (result.stdout, result.returncode) == ("", 1)
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith(f"error {code} {place}: ")
    render = RENDERS.get(command, "videotape render --story chalk")
    assert result.stderr.endswith(f"\n{step(code)}: {next.format(render=render)}\n")
