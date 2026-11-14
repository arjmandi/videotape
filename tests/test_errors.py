import re
from pathlib import Path

import pytest

from conftest import FIXTURES, videotape
from videotape.errors import CODES

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
    "VT205": ("app.py:9", "no data file at drinks.json",
              'create it, or correct the path; "drinks.json" is relative to the folder of pyproject.toml'),
    "VT206": ("drinks.json:3", 'record 2 field "price" is "six", not a whole number', "write a whole number"),
    "VT207": ("app.py:15", 'Drink has no field "cost", in state home()', "name one of its fields: name, price"),
    "VT208": ("app.py:15", "get(name='Mocha') matched no Drink from drinks.json, in state home()",
              "ask for a row the data holds, or count the matches with where(...).count()"),
    "VT209": ("home()", 'two actions have the label "Open"', "give each action its own label"),
    "VT210": ("count(5)", "the plan reached more than 5 states",
              "take a scene's arguments from the data, which ends, or raise max_states in [tool.videotape]"),
}
WARNINGS = {
    "VT211": [("home()", 'the line "Café Lumière" has the characters è é', f"write it with {PLAIN}"),
              ("home()", 'the line "We open every single day of the week at seven in the morning sharp." has 14 words',
               "shorten it to 12 words or fewer")],
}


def test_a_fixture_triggers_every_code():
    assert sorted(path.name.upper() for path in (FIXTURES / "errors").iterdir()) == sorted(CODES)
    assert sorted([*ERRORS, *WARNINGS]) == sorted(CODES)


@pytest.mark.parametrize("code", sorted(ERRORS))
def test_an_error_prints_its_code_its_place_and_its_fix_and_plans_nothing(code):
    place, message, fix = ERRORS[code]
    result = videotape(FIXTURES / "errors" / code.lower(), "plan")
    assert (result.stdout, result.returncode) == ("", 1)
    assert result.stderr == f"error {code} {place}: {message}\nfix: {fix}\n"


@pytest.mark.parametrize("code", sorted(ERRORS))
def test_render_stops_on_the_same_error_before_it_draws_anything(code):
    directory = FIXTURES / "errors" / code.lower()
    result = videotape(directory, "render", "--model", "stand-in")
    assert (result.stdout, result.returncode) == ("", 1)
    assert result.stderr.startswith(f"error {code} {ERRORS[code][0]}: ")
    assert not (directory / "tape").exists() and not (directory / "ledger.jsonl").exists()


def test_a_warning_prints_its_code_its_place_and_its_fix_and_the_plan_goes_on():
    result = videotape(FIXTURES / "errors" / "vt211", "plan")
    assert result.returncode == 0
    assert result.stderr == "".join(f"warning VT211 {place}: {message}\nfix: {fix}\n"
                                    for place, message, fix in WARNINGS["VT211"])
    assert result.stdout.splitlines()[0] == "Cafe 0.1.0: 1 scene, 1 state, 1 key, 0 moves, 1 shot"
    assert result.stdout.splitlines()[-1] == "0 errors, 2 warnings"


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
        assert "\n\nFix:\n    " in f"\n\n{fix}" and len(fix.splitlines()) > 1


def test_explain_rejects_a_code_that_does_not_exist(tmp_path):
    result = videotape(tmp_path, "explain", "VT999")
    assert result.returncode == 2
    assert "invalid choice: 'VT999'" in result.stderr


@pytest.mark.parametrize("pyproject, error", [
    (None, "error: no pyproject.toml here or in any folder above; run videotape in an app's project\n"),
    ('[project]\nname = "app"\n',
     'error: pyproject.toml has no [tool.videotape] table; add one with screenplay = "module:app"\n'),
    ('[tool.videotape]\nscreenplay = "app"\n',
     'error: pyproject.toml: [tool.videotape] needs screenplay = "module:app", the module and the name of its '
     "vt.Screenplay, and has 'app'\n"),
    ('[tool.videotape]\nscreenplay = "shop:app"\n',
     'error: [tool.videotape] names the screenplay "shop:app", and the project has no module shop\n'),
    ('[tool.videotape]\nscreenplay = "app:shop"\n',
     'error: [tool.videotape] names the screenplay "app:shop", and shop in app is missing\n'),
    ('[tool.videotape]\nscreenplay = "app:app"\nmax_states = 0\n',
     "error: pyproject.toml: [tool.videotape] max_states is 0, not a whole number of states\n"),
])
def test_a_project_that_names_no_screenplay_says_what_to_set(tmp_path, pyproject, error):
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject)
    (tmp_path / "app.py").write_text('import videotape as vt\n\napp = vt.Screenplay("Shop")\n')
    result = videotape(tmp_path, "plan")
    assert (result.stdout, result.stderr, result.returncode) == ("", error, 1)
