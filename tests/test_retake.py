"""retake films new takes of one shot and keeps the best of all of them, and accept records a failure a person is fine
with. Both live in the tape's record, which a later render carries over."""

import json
from pathlib import Path

import pytest

from conftest import copy_of
from videotape import dailies
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.standin import EXTRA, Flaw, StandIn, StandInEye

RENDER = ("render", "--story", "chalk")
ORDER_LATTE = 'reading "Latte"'
THANKS_ESPRESSO = '"One Espresso coming up."'


def misspelt_until_five(mode: Mode, prompt: str, seed: int) -> Flaw:
    """order(Latte)'s key is misspelt on every seed below 5."""
    return Flaw.MISSPELL if ORDER_LATTE in prompt and mode is Mode.TEXT_TO_VIDEO and seed < 5 else Flaw.NONE


def extra_on_thanks_espresso(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.EXTRA_BOX if THANKS_ESPRESSO in prompt and mode is Mode.TEXT_TO_VIDEO else Flaw.NONE


def stand_in(monkeypatch, flaw) -> StandIn:
    model = StandIn(flaw=flaw)
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: model, lambda tape: StandInEye(), limit=8))
    return model


def kept(tape: Path) -> dict[str, int]:
    record = dailies.read(tape)
    return {shot["title"]: next(take["seed"] for take in shot["takes"] if take["kept"])
            for shot in (*record["keys"], *record["moves"])}


def test_retake_films_seeds_after_the_highest_tried_keeps_the_best_and_redraws_the_moves_pinned_to_a_changed_key(
        tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    model = stand_in(monkeypatch, misspelt_until_five)
    assert cli(directory, *RENDER) == 1
    err = capsys.readouterr().err
    assert "fail: 3. key order(Latte)  VT502 " in err and 'next: videotape retake "order(Latte)" --story chalk' in err
    assert [call.seed for call in model.calls if ORDER_LATTE in call.prompt] == [1, 2, 3, 4]
    before = kept(tape)
    assert before["key order(Latte)"] in (1, 2, 3, 4)
    pinned = (tape / "keys" / "order-latte.png").read_bytes()
    model.calls.clear()

    assert cli(directory, "retake", "order(Latte)", "--story", "chalk") == 0
    out, err = capsys.readouterr()
    assert out.splitlines()[0] == "retaking key order(Latte) with seed 5"
    assert err == ""
    assert [(call.mode, call.seed) for call in model.calls] == [
        (Mode.TEXT_TO_VIDEO, 5), (Mode.FIRST_AND_LAST_FRAME, 1), (Mode.FIRST_AND_LAST_FRAME, 1)]
    assert {call.prompt.split('"')[1] for call in model.calls[1:]} == {"Latte", "Order"}
    after = kept(tape)
    assert after["key order(Latte)"] == 5
    assert {title for title in after if after[title] != before[title]} <= {
        "key order(Latte)", 'menu() -> order(Latte) "Latte, $5"', 'order(Latte) -> thanks(Latte) "Order"'}
    assert (tape / "keys" / "order-latte.png").read_bytes() != pinned
    record = dailies.read(tape)
    assert (record["retakes"], record["failures"], record["takes"]) == ({"key order(Latte)": [5]}, [], 4)
    assert [take["seed"] for take in record["keys"][2]["takes"]] == [1, 2, 3, 4, 5]
    assert "3. key order(Latte)  kept take 5, passed, 1 take filmed" in out
    model.calls.clear()

    assert cli(directory, *RENDER) == 0
    assert model.calls == [] and kept(tape) == after
    assert "3. key order(Latte)  kept take 5, passed, cached" in capsys.readouterr().out

    assert cli(directory, "retake", "order(Latte)", "--story", "chalk", "--takes", "2") == 0
    assert capsys.readouterr().out.splitlines()[0] == "retaking key order(Latte) with seeds 6, 7"
    assert [call.seed for call in model.calls] == [6, 7]
    assert kept(tape)["key order(Latte)"] == 5
    assert dailies.read(tape)["retakes"] == {"key order(Latte)": [5, 6, 7]}


def test_retake_of_a_move_films_its_next_seeds_and_a_wrong_name_names_the_closest(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    model = stand_in(monkeypatch, lambda mode, prompt, seed: Flaw.NONE)
    assert cli(directory, *RENDER) == 0
    model.calls.clear()
    capsys.readouterr()
    assert cli(directory, "retake", "thanks(Latte) -> menu()", "--story", "chalk") == 0
    assert capsys.readouterr().out.splitlines()[0] == 'retaking thanks(Latte) -> menu() "Done" with seed 5'
    assert [(call.mode, call.seed) for call in model.calls] == [(Mode.FIRST_AND_LAST_FRAME, 5)]
    assert cli(directory, "retake", "thanks(Late) -> menu()", "--story", "chalk") == 1
    assert capsys.readouterr().err == ('error: the app has no state or move "thanks(Late) -> menu()"; the closest are '
                                       'thanks(Latte) -> menu(), thanks(Latte) -> menu() "Done", thanks(Espresso) -> menu()\n')
    assert cli(directory, "retake", "order(Latte)", "--story", "chalk", "--out", "tape-none") == 1
    assert capsys.readouterr().err == "error: no dailies.json in tape-none; render the story first\n"


def test_a_move_name_shared_by_two_moves_is_ambiguous_until_given_its_label(tmp_path, cli, capsys, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[tool.videotape]\nscreenplay = "doors:app"\nmodel = "stand-in"\n')
    (tmp_path / "doors.py").write_text(
        'import videotape as vt\n\napp = vt.Screenplay("Doors")\n\n\n@app.scene\ndef hall():\n'
        '    return [vt.Button("Front door", to=room()), vt.Button("Side door", to=room())]\n\n\n@app.scene\ndef room():\n'
        '    return [vt.Heading("Room")]\n')
    (tmp_path / "stories").mkdir()
    (tmp_path / "stories" / "bare.toml").write_text('version = "1.0.0"\nlook = "A bare hallway."\n'
                                                     '[scenes]\nhall = "A hall."\nroom = "A room."\n')
    model = stand_in(monkeypatch, lambda mode, prompt, seed: Flaw.NONE)
    assert cli(tmp_path, "render", "--story", "bare") == 0
    assert cli(tmp_path, "retake", "hall() -> room()", "--story", "bare") == 1
    assert capsys.readouterr().err == ('error: "hall() -> room()" names 2 moves; name one by its full title: '
                                       'hall() -> room() "Front door"; hall() -> room() "Side door"\n')
    model.calls.clear()
    assert cli(tmp_path, "retake", 'hall() -> room() "Side door"', "--story", "bare") == 0
    assert [(call.mode, call.seed, call.prompt.split('"')[1]) for call in model.calls] == [
        (Mode.FIRST_AND_LAST_FRAME, 5, "Side door")]


def test_accept_records_a_failing_check_with_its_reason_and_render_then_passes_and_lists_it(tmp_path, cli, capsys,
                                                                                            monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    stand_in(monkeypatch, extra_on_thanks_espresso)
    assert cli(directory, *RENDER) == 1
    err = capsys.readouterr().err
    assert f"fail: 4. key thanks(Espresso)  VT503 {EXTRA}: " in err
    reason = "a printed logo, not a control"
    assert cli(directory, "accept", "thanks(Espresso)", "VT503", "--story", "chalk", "--reason", reason) == 0
    assert capsys.readouterr().out == f"accepted VT503 on key thanks(Espresso): {reason}\n"
    record = dailies.read(tape)
    [accepted] = record["accepted"]
    assert (accepted["shot"], accepted["code"], accepted["reason"]) == ("key thanks(Espresso)", "VT503", reason)
    assert accepted["at"].endswith("+00:00")
    [failure] = record["failures"]
    assert failure["accepted"] == {"reason": reason, "at": accepted["at"]}
    page = (tape / "dailies.html").read_text()
    assert '<span class="badge accepted">accepted</span>' in page and f"<p class=\"reason\">Accepted: {reason}</p>" in page
    assert "1 failing, 0 to act on, 1 accepted" in page

    assert cli(directory, *RENDER) == 0
    out, err = capsys.readouterr()
    assert "4. key thanks(Espresso)  kept take 1, fails VT503, cached" in out
    assert err.splitlines() == [
        f'accepted: 4. key thanks(Espresso)  VT503 {EXTRA}: a control reading "{EXTRA}" at 24,150 315x33, and no action '
        "has those words", f"  reason: {reason}"]
    assert dailies.read(tape)["accepted"] == [accepted]


def test_accept_of_a_check_that_is_not_failing_says_so_and_records_nothing(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    stand_in(monkeypatch, extra_on_thanks_espresso)
    assert cli(directory, *RENDER) == 1
    capsys.readouterr()
    assert cli(directory, "accept", "order(Latte)", "VT503", "--story", "chalk", "--reason", "fine") == 1
    assert capsys.readouterr().out == "key order(Latte) does not fail VT503; it passes, so nothing is recorded\n"
    assert cli(directory, "accept", "thanks(Espresso)", "VT501", "--story", "chalk", "--reason", "fine") == 1
    assert capsys.readouterr().out == "key thanks(Espresso) does not fail VT501; it fails VT503, so nothing is recorded\n"
    assert dailies.read(tape)["accepted"] == []
    with pytest.raises(SystemExit):
        cli(directory, "accept", "thanks(Espresso)", "VT301", "--story", "chalk", "--reason", "fine")
    assert "invalid choice: 'VT301'" in capsys.readouterr().err


def test_an_accept_survives_a_render_that_films_the_shot_again(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    stand_in(monkeypatch, extra_on_thanks_espresso)
    cli(directory, *RENDER)
    cli(directory, "accept", "thanks(Espresso)", "VT503", "--story", "chalk", "--reason", "a logo")
    story = directory / "stories" / "chalk.toml"
    story.write_text(story.read_text().replace("A paper cup on the counter", "A paper cup on the table"))
    capsys.readouterr()
    assert cli(directory, *RENDER) == 0
    assert "4. key thanks(Espresso)  kept take 1, fails VT503, 4 takes filmed" in capsys.readouterr().out
    record = dailies.read(tape)
    assert [a["reason"] for a in record["accepted"]] == ["a logo"]
    assert json.dumps(record["failures"][0]["accepted"]["reason"]) == '"a logo"'
