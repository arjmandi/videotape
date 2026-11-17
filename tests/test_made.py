import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from conftest import CONTRAIL, contrail_copy, copy_of, planned, told
from videotape import hosted, ledger, new, project
from videotape.errors import PACKAGE
from videotape.fal import Fal
from videotape.made import made
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.render import render
from videotape.standin import Flaw, StandIn, StandInEye

HASH = re.compile(r"[0-9a-f]{64}")


def block(directory: Path, story: str = "terminal", model=None) -> dict:
    return made(project.find(directory), told(directory, story), model or StandIn())


def test_a_tapes_made_block_names_the_app_the_story_the_model_and_the_engine_and_its_label_reads_them():
    found = block(CONTRAIL)
    assert list(found) == ["label", "id", "app", "story", "model", "engine"]
    assert found["label"] == "contrail 0.1.0 + terminal 1.0.0"
    assert {name: found["app"][name] for name in ("name", "version", "screenplay")} == \
        {"name": "contrail", "version": "0.1.0", "screenplay": "contrail.screenplay:app"}
    assert found["story"] == {"name": "terminal", "version": "1.0.0", "hash": hashlib.sha256(
        (CONTRAIL / "stories" / "terminal.toml").read_bytes()).hexdigest()}
    assert found["model"] == {"name": "stand-in", "settings": {"text-to-video": {}, "first-and-last-frame": {}}}
    assert all(HASH.fullmatch(value) for value in (found["id"], found["app"]["code"], found["app"]["data"], found["engine"]))
    assert block(CONTRAIL, "posters")["label"] == "contrail 0.1.0 + posters 1.0.0"


def test_the_same_everything_has_one_id_wherever_the_project_is(tmp_path):
    assert block(contrail_copy(tmp_path / "contrail")) == block(CONTRAIL)


def test_each_listed_models_class_gives_the_made_block_its_built_model_does_without_a_key(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    found, terminal = project.find(CONTRAIL), told(CONTRAIL, "terminal")
    assert made(found, terminal, MODELS["wan3.0"].kind) == made(found, terminal, hosted.OnFal(hosted.WAN3, Fal("a key")))
    assert made(found, terminal, MODELS["stand-in"].kind) == made(found, terminal, StandIn())
    assert {name: made(found, terminal, listing.kind)["model"]["name"] for name, listing in MODELS.items()} == \
        {name: name for name in MODELS}


class Tuned(StandIn):
    def settings(self, mode: Mode) -> dict:
        return {"steps": 50} if mode is Mode.TEXT_TO_VIDEO else {}


def changed(directory: Path, after: dict) -> set[str]:
    """The parts of the made block that differ from the untouched Contrail's."""
    before = block(CONTRAIL)
    flat = lambda found: {**{f"app.{name}": value for name, value in found["app"].items()}, "story": found["story"],
                          "model": found["model"], "engine": found["engine"], "id": found["id"], "label": found["label"]}
    return {name for name, value in flat(after).items() if value != flat(before)[name]}


def test_the_id_changes_with_the_code_the_data_the_story_and_the_models_settings_each_by_its_own_hash(tmp_path):
    directory = contrail_copy(tmp_path / "contrail")
    copy_py = directory / "contrail" / "copy.py"
    copy_py.write_text(copy_py.read_text() + "\n# a comment\n")
    assert changed(directory, block(directory)) == {"app.code", "id"}
    copy_py.rename(copy_py.with_name("words.py"))
    renamed = block(directory)
    (directory / "contrail" / "words.py").rename(copy_py)
    assert renamed["app"]["code"] != block(directory)["app"]["code"]

    directory = contrail_copy(tmp_path / "data" / "contrail")
    (directory / "data" / ".DS_Store").write_bytes(b"left by a file browser")
    assert changed(directory, block(directory)) == set()
    flights = directory / "data" / "flights.json"
    flights.write_text(flights.read_text().replace('"fare": 89,', '"fare": 91,'))
    assert changed(directory, block(directory)) == {"app.data", "id"}

    directory = contrail_copy(tmp_path / "story" / "contrail")
    story = directory / "stories" / "terminal.toml"
    story.write_text(story.read_text().replace("low golden sun", "a low red sun"))
    assert changed(directory, block(directory)) == {"story", "id"}
    assert changed(CONTRAIL, block(CONTRAIL, "posters")) == {"story", "id", "label"}
    assert changed(CONTRAIL, block(CONTRAIL, model=Tuned())) == {"model", "id"}


def test_the_id_changes_with_the_screenplay_the_project_names_from_one_package(tmp_path):
    directory = contrail_copy(tmp_path / "contrail")
    (directory / "contrail" / "again.py").write_text("from contrail.screenplay import app\n")
    before = block(directory)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('"contrail.screenplay:app"', '"contrail.again:app"'))
    after = block(directory)
    assert {name for name in before if before[name] != after[name]} == {"app", "id"}
    assert {name for name in before["app"] if before["app"][name] != after["app"][name]} == {"screenplay"}


def test_the_engines_hash_is_of_videotapes_own_python_files(tmp_path, monkeypatch):
    before = block(CONTRAIL)
    engine = Path(shutil.copytree(PACKAGE, tmp_path / "videotape", ignore=shutil.ignore_patterns("__pycache__")))
    monkeypatch.setattr("videotape.made.PACKAGE", engine)
    assert block(CONTRAIL) == before
    (engine / "standin.py").write_text((engine / "standin.py").read_text() + "\n# a comment\n")
    after = block(CONTRAIL)
    assert {name for name in before if before[name] != after[name]} == {"engine", "id"}


def clean(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.NONE


@pytest.fixture(scope="module")
def cafe(tmp_path_factory) -> Path:
    directory = copy_of("cafe", tmp_path_factory.mktemp("made"))
    found, chalk, model = project.find(directory), told(directory), StandIn(flaw=clean)
    tape = directory / "tapes" / "chalk"
    render(planned(directory), chalk, model, [StandInEye()], tape, ledger.of(directory, tape), made(found, chalk, model),
           takes=1)
    return directory


def test_tape_json_carries_the_made_block_beside_what_the_player_reads(cafe):
    manifest = json.loads((cafe / "tapes" / "chalk" / "tape.json").read_text())
    assert list(manifest) == ["size", "fps", "opening", "scenes", "moves", "made"]
    assert manifest["made"] == block(cafe, "chalk")
    assert manifest["made"]["label"] == "cafe 0.3.0 + chalk 1.0.0"
    assert manifest["made"]["app"]["code"] == block(cafe, "chalk")["app"]["code"]


def test_the_cli_writes_the_made_block_of_the_model_it_rendered_with(cafe, tmp_path, cli, monkeypatch):
    directory = Path(shutil.copytree(cafe, tmp_path / "cafe", ignore=shutil.ignore_patterns("__pycache__")))
    tuned = Tuned(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: tuned, (StandInEye,), kind=tuned))
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--out", "tape-tuned") == 0
    written = json.loads((directory / "tape-tuned" / "tape.json").read_text())["made"]
    assert written == block(directory, "chalk", tuned)
    assert written["model"]["settings"] == {"text-to-video": {"steps": 50}, "first-and-last-frame": {}}
    assert written["id"] != json.loads((directory / "tapes" / "chalk" / "tape.json").read_text())["made"]["id"]


def test_an_app_without_a_project_name_is_named_by_its_folder(tmp_path):
    directory = tmp_path / "doors"
    (directory / "stories").mkdir(parents=True)
    (directory / "pyproject.toml").write_text('[tool.videotape]\nscreenplay = "doors:app"\n')
    (directory / "doors.py").write_text('import videotape as vt\n\napp = vt.Screenplay("Doors")\n')
    (directory / "stories" / "bare.toml").write_text('version = "2.0.0"\nlook = "A bare hallway."\n')
    found = block(directory, "bare")
    assert (found["label"], found["app"]["name"], found["app"]["version"]) == ("doors + bare 2.0.0", "doors", None)


@pytest.fixture
def two(cafe, tmp_path, cli, monkeypatch, capsys):
    """A copy of the rendered cafe, and a way to render it again after a change, with a stand-in that never flaws."""
    directory = Path(shutil.copytree(cafe, tmp_path / "cafe", ignore=shutil.ignore_patterns("__pycache__")))
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: StandIn(flaw=clean), (StandInEye,), kind=StandIn))

    def render_again(*arguments: str) -> None:
        assert cli(directory, "render", "--takes", "1", *arguments) == 0
        capsys.readouterr()
    return directory, render_again


def diff(cli, capsys, directory: Path, a: str, b: str) -> list[str]:
    assert cli(directory, "diff", a, b) == 0
    out, err = capsys.readouterr()
    assert err == ""
    return out.splitlines()


def test_diff_of_a_tape_with_itself_is_the_same_app_and_story_and_shares_everything(two, cli, capsys):
    directory, _ = two
    made_ = json.loads((directory / "tapes" / "chalk" / "tape.json").read_text())["made"]
    line = f"tapes/chalk  cafe 0.3.0 + chalk 1.0.0  {made_['id']}"
    assert diff(cli, capsys, directory, "tapes/chalk", "tapes/chalk") == [
        line, line, "same app", "same story", "5 states shared, of 5 and 5", "6 moves shared, of 6 and 6"]


def test_diff_of_two_stories_of_one_app_is_the_same_app_and_another_story(two, cli, capsys):
    directory, render_again = two
    chalk = (directory / "stories" / "chalk.toml").read_text()
    (directory / "stories" / "neon.toml").write_text(chalk.replace("A chalkboard behind", "A neon sign above"))
    render_again("--story", "neon")
    chalk_id, neon_id = (json.loads((directory / "tapes" / name / "tape.json").read_text())["made"]["id"]
                         for name in ("chalk", "neon"))
    assert chalk_id != neon_id
    assert diff(cli, capsys, directory, "tapes/chalk", "tapes/neon") == [
        f"tapes/chalk  cafe 0.3.0 + chalk 1.0.0  {chalk_id}",
        f"tapes/neon   cafe 0.3.0 + neon 1.0.0   {neon_id}",
        "same app", "another story", "5 states shared, of 5 and 5", "6 moves shared, of 6 and 6"]


def test_diff_after_the_code_changes_is_another_app_and_counts_the_states_and_moves_both_tapes_have(two, cli, capsys):
    directory, render_again = two
    screenplay = directory / "cafe.py"
    listed = 'for drink in drinks.order_by("name")]'
    assert screenplay.read_text().count(listed) == 1
    screenplay.write_text(screenplay.read_text().replace(listed, 'for drink in drinks.where(price=3)]'))
    render_again("--story", "chalk", "--out", "tape-espresso")
    assert diff(cli, capsys, directory, "tapes/chalk", "tape-espresso")[2:] == [
        "another app", "same story", "3 states shared, of 5 and 3", "3 moves shared, of 6 and 3"]


def test_diff_of_two_screenplays_of_one_package_is_another_app_though_their_code_and_data_are_one(tmp_path, cli,
                                                                                                   capsys):
    folder = new.project("shop", tmp_path)
    package = folder / "shop"
    (package / "other.py").write_text((package / "screenplay.py").read_text().replace("of two scenes", "of two pages"))
    assert cli(folder, "render", "--story", "starter", "--model", "stand-in", "--out", "tape-screenplay") == 0
    pyproject = folder / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('"shop.screenplay:app"', '"shop.other:app"'))
    assert cli(folder, "render", "--story", "starter", "--model", "stand-in", "--out", "tape-other") == 0
    capsys.readouterr()
    apps = [json.loads((folder / tape / "tape.json").read_text())["made"]["app"]
            for tape in ("tape-screenplay", "tape-other")]
    assert [(app["code"], app["data"]) for app in apps[1:]] == [(apps[0]["code"], apps[0]["data"])]
    assert diff(cli, capsys, folder, "tape-screenplay", "tape-other")[2:3] == ["another app"]


def test_diff_says_which_tape_has_no_tape_json_or_does_not_say_what_made_it(two, cli, capsys):
    directory, _ = two
    assert cli(directory, "diff", "tapes/chalk", "tapes/neon") == 1
    assert capsys.readouterr() == ("", "error VT405 tapes/neon: has no tape.json, which a render writes when it "
                                       "finishes\nnext: render the story first, or run a render that stopped again as "
                                       "it ran, which resumes, as in:\nvideotape render --story <story>\n")
    old = directory / "tape-old"
    old.mkdir()
    manifest = json.loads((directory / "tapes" / "chalk" / "tape.json").read_text())
    (old / "tape.json").write_text(json.dumps({name: part for name, part in manifest.items() if name != "made"}))
    assert cli(directory, "diff", "tape-old", "tapes/chalk") == 1
    assert capsys.readouterr() == ("", "error VT405 tape-old/tape.json: does not say what made the tape\n"
                                       "next: render the story again, as in:\nvideotape render --story <story>\n")
