"""videotape new writes the starter as a project that depends on videotape from where it was installed, and the
starter plans and renders clean with the stand-in."""

import json
from pathlib import Path

import pytest

from conftest import as_explained
from videotape import dailies, new

ROOT = Path(__file__).parent.parent


def test_new_writes_the_starter_and_says_what_to_run_next(tmp_path, cli, capsys):
    assert cli(tmp_path, "new", "corner_shop") == 0
    project = tmp_path / "corner_shop"
    assert sorted(path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file()) == [
        ".env.example", ".gitignore", "corner_shop/__init__.py", "corner_shop/screenplay.py", "data/steps.json",
        "pyproject.toml", "stories/starter.toml"]
    pyproject = (project / "pyproject.toml").read_text()
    assert 'name = "corner_shop"\nversion = "0.1.0"\n' in pyproject
    assert f'dependencies = ["videotape @ {ROOT.as_uri()}"]' in pyproject
    assert pyproject.endswith('[tool.videotape]\nscreenplay = "corner_shop.screenplay:app"\nmodel = "wan3.0"\ntakes = 4\n'
                              "cap_usd = 200\n")
    assert 'app = vt.Screenplay("Corner Shop")' in (project / "corner_shop" / "screenplay.py").read_text()
    assert (project / "stories" / "starter.toml").read_text().startswith("# Corner Shop as a notebook")
    assert (project / ".env.example").read_text() == "FAL_KEY=\nANTHROPIC_API_KEY=\n"
    assert (project / ".gitignore").read_text() == "tapes/\ndist/\n.env\nledger.jsonl\n.DS_Store\n"
    assert capsys.readouterr() == (
        "made corner_shop: a screenplay of two scenes, a data table, and the story starter\nnext:\n"
        "  cd corner_shop\n  uv run videotape doctor\n  uv run videotape render --story starter --model stand-in\n"
        "  uv run videotape play --story starter\n", "")


@pytest.mark.parametrize("direct_url, line", [
    (None, "videotape==0.1.0"),
    ('{"url": "file:///Users/me/videotape", "dir_info": {}}', "videotape @ file:///Users/me/videotape"),
    ('{"url": "https://github.com/arjmandi/videotape.git", "vcs_info": {"vcs": "git", "requested_revision": "main", '
     '"commit_id": "96edfa5d1c0ffee"}}', "videotape @ git+https://github.com/arjmandi/videotape.git@96edfa5d1c0ffee"),
])
def test_the_dependency_is_videotape_from_where_it_was_installed(direct_url, line):
    assert new.dependency(direct_url, "0.1.0") == line


def test_new_writes_into_an_empty_folder_and_refuses_one_that_is_not(tmp_path, cli, capsys):
    (tmp_path / "shop").mkdir()
    assert cli(tmp_path, "new", "shop") == 0
    capsys.readouterr()
    before = sorted(path for path in (tmp_path / "shop").rglob("*"))
    assert cli(tmp_path, "new", "shop") == 1
    out, err = capsys.readouterr()
    assert out == "" and as_explained("VT109").fullmatch(err.rstrip("\n"))
    assert sorted(path for path in (tmp_path / "shop").rglob("*")) == before


@pytest.mark.parametrize("name", ["my-app", "2shop", "class", "_shop", "shop_", "café"])
def test_new_refuses_a_name_that_cannot_name_a_project(tmp_path, cli, capsys, name):
    assert cli(tmp_path, "new", name) == 1
    out, err = capsys.readouterr()
    assert out == "" and err.startswith(f"error VT108 {name}: ")
    assert as_explained("VT108").fullmatch(err.rstrip("\n"))


@pytest.mark.parametrize("name", ["json", "videotape"])
def test_new_refuses_a_name_whose_package_would_hide_a_module_videotape_needs(tmp_path, cli, capsys, name):
    assert cli(tmp_path, "new", name) == 1
    assert capsys.readouterr() == ("", f"error VT108 {name}: would name a package that hides the module {name}, which "
                                       f"videotape needs\nfix: name the project another way, as in videotape new "
                                       f"{name}_app\n")
    assert list(tmp_path.iterdir()) == []


def test_the_starter_plans_without_a_warning_and_renders_clean_with_the_stand_in(tmp_path, cli, capsys):
    cli(tmp_path, "new", "shop")
    project = tmp_path / "shop"
    capsys.readouterr()
    assert cli(project, "plan") == 0
    assert capsys.readouterr().out.splitlines()[0] == "Shop 0.1.0: 2 scenes, 2 states, 2 keys, 2 moves, 4 shots"
    assert cli(project, "plan", "--story", "starter") == 0
    assert capsys.readouterr().out.splitlines()[-2:] == ["0 errors, 0 warnings",
                                                         "wan3.0: 4 shots, 4 to 16 calls, $2.00 to $8.00 at $0.10/s, and 2 to 8 reads by claude-opus-5-5, at most $0.35 to $1.38"]
    assert cli(project, "render", "--story", "starter", "--model", "stand-in") == 0
    out, err = capsys.readouterr()
    assert err == "" and out.splitlines()[-1].startswith("4 shots, ")
    record = dailies.read(project / "tapes" / "starter")
    assert record["failures"] == [] and record["takes"] == 4
    assert json.loads((project / "tapes" / "starter" / "tape.json").read_text())["made"]["label"] == \
        "shop 0.1.0 + starter 1.0.0"
