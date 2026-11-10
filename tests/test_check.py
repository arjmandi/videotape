import json
import shutil
from pathlib import Path

import pytest

from videotape import dailies
from videotape.checks import KeyChecks, MoveChecks, Reading
from videotape.cli import main
from videotape.frames import Box
from videotape.render import render
from videotape.standin import Flaw, StandIn, StandInEye

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
SCENES = ["welcome", "entrance", "login", "signup", "gallery"]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    directory = tmp_path_factory.mktemp("rendered") / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape"))
    render(directory, StandIn(flaw=lambda mode, prompt, seed: Flaw.NONE), StandInEye())
    return directory


@pytest.fixture
def tape(rendered, tmp_path):
    shutil.copytree(rendered, tmp_path / "surf_shop")
    return tmp_path / "surf_shop" / "tape"


def test_a_key_take_ranks_by_buttons_found_then_character_error_then_seed():
    box = Box(0, 0, 10, 10)
    both_clean = KeyChecks({"A": box, "B": box}, {"line": Reading("line", 0.0)})
    both_misspelt = KeyChecks({"A": box, "B": box}, {"line": Reading("lime", 0.25)})
    one_clean = KeyChecks({"A": box, "B": None}, {"line": Reading("line", 0.0)})
    assert both_clean.rank(3) < both_misspelt.rank(1) < one_clean.rank(1)
    assert both_clean.rank(1) < both_clean.rank(2)
    assert [item.name for item in one_clean.failures] == ['button "B"']
    assert [item.name for item in both_misspelt.failures] == ['text "line"']


def test_a_move_take_ranks_by_the_sum_of_its_two_seams_then_seed():
    assert MoveChecks(0.010, 0.020).rank(2) < MoveChecks(0.020, 0.020).rank(1)
    assert MoveChecks(0.010, 0.020).rank(1) < MoveChecks(0.010, 0.020).rank(2)
    assert MoveChecks(0.040, 0.000).rank(1) < MoveChecks(0.000, 0.045).rank(1)
    assert [item.name for item in MoveChecks(0.051, 0.0).failures] == ["start"]
    assert [item.name for item in MoveChecks(0.0, 0.051).failures] == ["end"]
    assert MoveChecks(0.05, 0.05).failures == []


def test_check_reports_each_scene_and_rescores_the_keys(tape, capsys):
    stale = json.loads((tape / "dailies.json").read_text())
    (tape / "dailies.json").write_text(json.dumps({**stale, "checks": "stale",
                                                   "keys": [{**key, "items": []} for key in stale["keys"]]}))
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
    assert record["checks"] == "stand-in"
    assert [key["scene"] for key in record["keys"]] == SCENES
    assert [(item["name"], item["passed"]) for item in record["keys"][0]["items"]] == [
        ('button "Enter shop"', True), ('text "Brushstroke Surf Co."', True),
        ('text "Hand-painted surfboards from California"', True), ('text "Enter shop"', True)]
    # The takes and the moves come from the render and stay as they were.
    assert [key["takes"] for key in record["keys"]] == [key["takes"] for key in stale["keys"]]
    assert record["moves"] == stale["moves"]
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


def test_check_refuses_a_record_from_an_older_render(tape, capsys):
    (tape / "dailies.json").write_text(json.dumps({"title": "T", "shots": [], "keys": {"checks": "stand-in", "scenes": []}}))
    assert main(["check", str(tape)]) == 1
    assert capsys.readouterr().err == f"error: {tape / 'dailies.json'} is from an older render; render the screenplay again to write it\n"


def test_check_needs_the_screenplay_next_to_the_tape(tape, tmp_path, capsys):
    moved = shutil.copytree(tape, tmp_path / "elsewhere" / "tape")
    assert main(["check", str(moved)]) == 1
    assert capsys.readouterr().err == f"error: no screenplay.py in {moved.parent}\n"


def test_check_rejects_unknown_checks(tape, capsys):
    with pytest.raises(SystemExit) as exit:
        main(["check", str(tape), "--checks", "tesseract"])
    assert exit.value.code == 2
    assert "invalid choice: 'tesseract'" in capsys.readouterr().err
