import json
import shutil
from pathlib import Path

import pytest

from videotape import dailies
from videotape.cli import main
from videotape.render import render
from videotape.standin import Flaw, StandIn, StandInEye

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
SCENES = ["welcome", "entrance", "login", "signup", "gallery"]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    directory = tmp_path_factory.mktemp("rendered") / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape"))
    render(directory, StandIn(flaw=lambda prompt, seed: Flaw.NONE), StandInEye())
    return directory


@pytest.fixture
def tape(rendered, tmp_path):
    shutil.copytree(rendered, tmp_path / "surf_shop")
    return tmp_path / "surf_shop" / "tape"


def test_check_reports_each_scene_and_replaces_the_keys_section(tape, capsys):
    stale = json.loads((tape / "dailies.json").read_text())
    (tape / "dailies.json").write_text(json.dumps({**stale, "keys": {"checks": "stale", "scenes": []}}))
    assert main(["check", str(tape), "--checks", "stand-in"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert [line for line in out if not line.startswith("  ")] == [
        *(f"{name}  keys/{name}.png" for name in SCENES),
        f"checked 5 keys with stand-in, all passing -> {tape / 'dailies.html'}"]
    # The stand-in draws "Enter shop" as a 65 by 13 cell button at scale 4, centred, at the top of its button rows.
    assert out[:5] == [
        "welcome  keys/welcome.png",
        '  button "Enter shop"  found at 510,392 260x52',
        '  text "Brushstroke Surf Co."  read "Brushstroke Surf Co.", CER 0.000',
        '  text "Hand-painted surfboards from California"  read "Hand-painted surfboards from California", CER 0.000',
        '  text "Enter shop"  read "Enter shop", CER 0.000',
    ]
    record = json.loads((tape / "dailies.json").read_text())
    assert record["shots"] == stale["shots"]
    assert record["keys"]["checks"] == "stand-in"
    assert [scene["scene"] for scene in record["keys"]["scenes"]] == SCENES
    # The keys section keeps the seams and render times, which come from the shots, not from the key images.
    assert [seam["move"] for seam in record["keys"]["scenes"][2]["seams"]] == ["signup--sign-up"]
    assert record["keys"]["scenes"][0]["time"]["move"] == "opening"
    assert (tape / "dailies.html").read_text() == dailies.page(record)


def test_check_fails_on_a_key_that_shows_the_wrong_scene(tape, capsys):
    shutil.copyfile(tape / "keys" / "login.png", tape / "keys" / "gallery.png")
    assert main(["check", str(tape)]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == f"checked 5 keys with stand-in, 1 failing -> {tape / 'dailies.html'}"
    assert captured.err.startswith('fail: gallery  text "The gallery": read "')
    assert len(captured.err.splitlines()) == 1
    assert "5 keys checked by stand-in, 1 failing" in (tape / "dailies.html").read_text()


def test_check_needs_a_rendered_tape(tmp_path, capsys):
    shutil.copytree(SURF_SHOP, tmp_path / "surf_shop", ignore=shutil.ignore_patterns("tape"))
    assert main(["check", str(tmp_path / "surf_shop" / "tape")]) == 1
    assert capsys.readouterr().err == (f"error: no tape.json in {tmp_path / 'surf_shop' / 'tape'}; "
                                       "render the screenplay first, then pass its tape directory\n")


def test_check_needs_the_screenplay_next_to_the_tape(tape, tmp_path, capsys):
    moved = shutil.copytree(tape, tmp_path / "elsewhere" / "tape")
    assert main(["check", str(moved)]) == 1
    assert capsys.readouterr().err == f"error: no screenplay.py in {moved.parent}\n"


def test_check_rejects_unknown_checks(tape, capsys):
    with pytest.raises(SystemExit) as exit:
        main(["check", str(tape), "--checks", "tesseract"])
    assert exit.value.code == 2
    assert "invalid choice: 'tesseract'" in capsys.readouterr().err
