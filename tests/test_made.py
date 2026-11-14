import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from conftest import CONTRAIL, copy_of, planned, told
from videotape import ledger, project
from videotape.errors import PACKAGE
from videotape.made import made
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.render import render
from videotape.standin import Flaw, StandIn, StandInEye

HASH = re.compile(r"[0-9a-f]{64}")


def contrail(to: Path) -> Path:
    return Path(shutil.copytree(CONTRAIL, to / "contrail", ignore=shutil.ignore_patterns(
        ".venv", "tape*", "ledger.jsonl", "__pycache__")))


def block(directory: Path, story: str = "terminal", model=None) -> dict:
    return made(project.find(directory), told(directory, story), model or StandIn())


def test_a_tapes_made_block_names_the_app_the_story_the_model_and_the_engine_and_its_label_reads_them():
    found = block(CONTRAIL)
    assert list(found) == ["label", "id", "app", "story", "model", "engine"]
    assert found["label"] == "contrail 0.1.0 + terminal 1.0.0"
    assert {name: found["app"][name] for name in ("name", "version")} == {"name": "contrail", "version": "0.1.0"}
    assert found["story"] == {"name": "terminal", "version": "1.0.0", "hash": hashlib.sha256(
        (CONTRAIL / "stories" / "terminal.toml").read_bytes()).hexdigest()}
    assert found["model"] == {"name": "stand-in", "settings": {"text-to-video": {}, "first-and-last-frame": {}}}
    assert all(HASH.fullmatch(value) for value in (found["id"], found["app"]["code"], found["app"]["data"], found["engine"]))
    assert block(CONTRAIL, "posters")["label"] == "contrail 0.1.0 + posters 1.0.0"


def test_the_same_everything_has_one_id_wherever_the_project_is(tmp_path):
    assert block(contrail(tmp_path)) == block(CONTRAIL)


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
    directory = contrail(tmp_path)
    copy_py = directory / "contrail" / "copy.py"
    copy_py.write_text(copy_py.read_text() + "\n# a comment\n")
    assert changed(directory, block(directory)) == {"app.code", "id"}
    copy_py.rename(copy_py.with_name("words.py"))
    renamed = block(directory)
    (directory / "contrail" / "words.py").rename(copy_py)
    assert renamed["app"]["code"] != block(directory)["app"]["code"]

    directory = contrail(tmp_path / "data")
    (directory / "data" / ".DS_Store").write_bytes(b"left by a file browser")
    assert changed(directory, block(directory)) == set()
    flights = directory / "data" / "flights.json"
    flights.write_text(flights.read_text().replace('"fare": 89,', '"fare": 91,'))
    assert changed(directory, block(directory)) == {"app.data", "id"}

    directory = contrail(tmp_path / "story")
    story = directory / "stories" / "terminal.toml"
    story.write_text(story.read_text().replace("low golden sun", "a low red sun"))
    assert changed(directory, block(directory)) == {"story", "id"}
    assert changed(CONTRAIL, block(CONTRAIL, "posters")) == {"story", "id", "label"}
    assert changed(CONTRAIL, block(CONTRAIL, model=Tuned())) == {"model", "id"}


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
    render(planned(directory), chalk, model, StandInEye(), tape, ledger.of(directory, tape), made(found, chalk, model),
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
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: tuned, lambda tape: StandInEye()))
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
