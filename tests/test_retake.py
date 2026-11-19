"""retake films new takes of one shot and keeps the best of all of them, and accept records a failure a person is fine
with. Both live in the tape's record, which a later render carries over."""

import json
from pathlib import Path

import pytest

from conftest import as_explained, copy_of
from videotape import dailies, ledger
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.standin import EXTRA, Flaw, StandIn, StandInEye, StandInJudge

RENDER = ("render", "--story", "chalk")
ORDER_LATTE = 'reading "Latte"'
ORDER_LATTE_KEY, THANKS_LATTE_KEY = "key order(Latte) from order(Espresso)", "key thanks(Latte) from thanks(Espresso)"
THANKS_ESPRESSO_KEY = "key thanks(Espresso) rehearsed from order(Espresso)"
THANKS_ESPRESSO = '"One Espresso coming up."'
THANKS_LATTE = '"One Latte coming up."'


def misspelt_until_five(mode: Mode, prompt: str, seed: int) -> Flaw:
    """order(Latte)'s key is misspelt on every seed below 5."""
    return Flaw.MISSPELL if ORDER_LATTE in prompt and mode is not Mode.FIRST_AND_LAST_FRAME and seed < 5 else Flaw.NONE


def misspelt_thanks_latte(mode: Mode, prompt: str, seed: int) -> Flaw:
    """thanks(Latte)'s key is misspelt on every seed: its Done button on seed 1, so the button is not found, and its
    heading on seed 2, which the shot then keeps."""
    return Flaw.MISSPELL if THANKS_LATTE in prompt and mode is not Mode.FIRST_AND_LAST_FRAME else Flaw.NONE


def extra_on_thanks_espresso(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.EXTRA_BOX if THANKS_ESPRESSO in prompt and mode is not Mode.FIRST_AND_LAST_FRAME else Flaw.NONE


def stand_in(monkeypatch, flaw) -> StandIn:
    model = StandIn(flaw=flaw)
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: model, (StandInEye,), limit=8, kind=model, judge=StandInJudge))
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
    assert f"fail: 3. {ORDER_LATTE_KEY}  VT502 " in err and 'next: videotape retake "order(Latte)" --story chalk' in err
    assert [call.seed for call in model.calls if ORDER_LATTE in call.prompt] == [1, 2, 3, 4]
    before = kept(tape)
    assert before[ORDER_LATTE_KEY] in (1, 2, 3, 4)
    pinned = (tape / "keys" / "order-latte.png").read_bytes()
    model.calls.clear()

    assert cli(directory, "retake", "order(Latte)", "--story", "chalk") == 0
    out, err = capsys.readouterr()
    assert out.splitlines()[0] == f"retaking {ORDER_LATTE_KEY} with seed 5"
    assert err == ""
    assert [(call.mode, call.seed) for call in model.calls] == [
        (Mode.FIRST_FRAME, 5), (Mode.FIRST_AND_LAST_FRAME, 1), (Mode.FIRST_AND_LAST_FRAME, 1)]
    assert {call.prompt.split('"')[1] for call in model.calls[1:]} == {"Latte", "Order"}
    after = kept(tape)
    assert after[ORDER_LATTE_KEY] == 5
    assert {title for title in after if after[title] != before[title]} <= {
        ORDER_LATTE_KEY, 'menu() -> order(Latte) "Latte, $5"', 'order(Latte) -> thanks(Latte) "Order"'}
    assert (tape / "keys" / "order-latte.png").read_bytes() != pinned
    record = dailies.read(tape)
    assert (record["retakes"], record["failures"], record["takes"]) == ({ORDER_LATTE_KEY: [5]}, [], 4)
    assert [take["seed"] for take in record["keys"][2]["takes"]] == [1, 2, 3, 4, 5]
    assert f"3. {ORDER_LATTE_KEY}  kept take 5, passed, 1 take filmed" in out
    model.calls.clear()

    assert cli(directory, *RENDER) == 0
    assert model.calls == [] and kept(tape) == after
    assert f"3. {ORDER_LATTE_KEY}  kept take 5, passed, cached" in capsys.readouterr().out

    assert cli(directory, "retake", "order(Latte)", "--story", "chalk", "--takes", "2") == 0
    assert capsys.readouterr().out.splitlines()[0] == f"retaking {ORDER_LATTE_KEY} with seeds 6, 7"
    assert [call.seed for call in model.calls] == [6, 7]
    assert kept(tape)[ORDER_LATTE_KEY] == 5
    assert dailies.read(tape)["retakes"] == {ORDER_LATTE_KEY: [5, 6, 7]}


def test_retake_films_with_the_model_that_made_the_tape_and_not_the_projects(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('model = "stand-in"', 'model = "wan3.0"'))
    monkeypatch.delenv("FAL_KEY", raising=False)
    model = stand_in(monkeypatch, misspelt_until_five)
    assert cli(directory, *RENDER, "--model", "stand-in") == 1
    assert '  next: videotape retake "order(Latte)" --story chalk\n' in capsys.readouterr().err
    model.calls.clear()

    assert cli(directory, "retake", "order(Latte)", "--story", "chalk") == 0
    out, err = capsys.readouterr()
    assert (out.splitlines()[0], err) == (f"retaking {ORDER_LATTE_KEY} with seed 5", "")
    assert [(call.mode, call.seed) for call in model.calls][0] == (Mode.FIRST_FRAME, 5)
    assert {line["model"] for line in ledger.of(directory, directory / "tapes" / "chalk").lines()} == {"stand-in"}
    with pytest.raises(SystemExit) as refused:
        cli(directory, "retake", "order(Latte)", "--story", "chalk", "--model", "stand-in")
    assert refused.value.code == 2 and "unrecognized arguments: --model stand-in" in capsys.readouterr().err


def test_retake_of_a_tape_no_render_finished_names_no_model_and_films_nothing(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    model = stand_in(monkeypatch, misspelt_until_five)
    assert cli(directory, *RENDER) == 1
    (tape / "tape.json").unlink()
    capsys.readouterr()
    model.calls.clear()
    assert cli(directory, "retake", "order(Latte)", "--story", "chalk") == 1
    assert as_explained("VT405").fullmatch(capsys.readouterr().err.rstrip("\n"))
    assert model.calls == [] and dailies.read(tape)["retakes"] == {}


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
    assert capsys.readouterr().err == ('error VT212 "thanks(Late) -> menu()": the app has no state or move of this name\n'
                                       'fix: name one of the closest: thanks(Latte) -> menu(), thanks(Latte) -> menu() '
                                       '"Done", thanks(Espresso) -> menu()\n')
    assert cli(directory, "retake", "thanks(Late)", "--story", "chalk") == 1
    assert as_explained("VT212").fullmatch(capsys.readouterr().err.rstrip("\n"))
    assert cli(directory, "retake", "order(Latte)", "--story", "chalk", "--out", "tape-none") == 1
    assert capsys.readouterr().err == ("error VT405 tape-none: has no dailies.json, which every render writes\n"
                                       "next: render the story first, as in:\n"
                                       "videotape render --story chalk --out tape-none\n")


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
    assert capsys.readouterr().err == ('error VT212 "hall() -> room()": names 2 moves\nfix: name one by its full '
                                       'title: hall() -> room() "Front door"; hall() -> room() "Side door"\n')
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
    assert f"fail: 4. {THANKS_ESPRESSO_KEY}  VT503 {EXTRA}: " in err
    reason = "a printed logo, not a control"
    assert cli(directory, "accept", "thanks(Espresso)", "VT503", "--story", "chalk", "--reason", reason) == 0
    assert capsys.readouterr().out == f"accepted VT503 on {THANKS_ESPRESSO_KEY}: {reason}\n"
    record = dailies.read(tape)
    [accepted] = record["accepted"]
    assert (accepted["shot"], accepted["code"], accepted["reason"]) == (THANKS_ESPRESSO_KEY, "VT503", reason)
    assert accepted["at"].endswith("+00:00")
    [failure] = record["failures"]
    assert accepted["seed"] == failure["take"] == 1
    assert (failure["accepted"], failure["accepted_before"]) == ({"reason": reason, "at": accepted["at"]}, None)
    page = (tape / "dailies.html").read_text()
    assert '<span class="badge accepted">accepted</span>' in page and f"<p class=\"reason\">Accepted: {reason}</p>" in page
    assert "1 failing, 0 to act on, 1 accepted" in page

    assert cli(directory, *RENDER) == 0
    out, err = capsys.readouterr()
    assert f"4. {THANKS_ESPRESSO_KEY}  kept take 1, fails VT503, cached" in out
    assert err.splitlines() == [
        f'accepted: 4. {THANKS_ESPRESSO_KEY}  VT503 {EXTRA}: a control reading "{EXTRA}" at 24,150 315x33, and no action '
        "has those words", f"  reason: {reason}"]
    assert dailies.read(tape)["accepted"] == [accepted]


def test_accept_of_a_check_that_is_not_failing_says_so_and_records_nothing(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    stand_in(monkeypatch, extra_on_thanks_espresso)
    assert cli(directory, *RENDER) == 1
    capsys.readouterr()
    assert cli(directory, "accept", "order(Latte)", "VT503", "--story", "chalk", "--reason", "fine") == 1
    out, err = capsys.readouterr()
    assert out == "" and as_explained("VT408").fullmatch(err.rstrip("\n"))
    assert err == (f"error VT408 {ORDER_LATTE_KEY}: does not fail VT503; it passes, so nothing is written down\n"
                   "next: nothing; its kept take passes every check\n")
    assert cli(directory, "accept", "thanks(Espresso)", "VT501", "--story", "chalk", "--reason", "fine") == 1
    assert capsys.readouterr() == (
        "", f"error VT408 {THANKS_ESPRESSO_KEY}: does not fail VT501; it fails VT503, so nothing is written down\n"
            'next: accept the check it fails: videotape accept "thanks(Espresso)" VT503 --story chalk --reason "..."\n')
    assert dailies.read(tape)["accepted"] == []
    with pytest.raises(SystemExit):
        cli(directory, "accept", "thanks(Espresso)", "VT301", "--story", "chalk", "--reason", "fine")
    assert "invalid choice: 'VT301'" in capsys.readouterr().err


def test_an_accept_fails_again_when_a_story_edit_films_its_take_again(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    stand_in(monkeypatch, extra_on_thanks_espresso)
    cli(directory, *RENDER)
    cli(directory, "accept", "thanks(Espresso)", "VT503", "--story", "chalk", "--reason", "a logo")
    [accepted] = dailies.read(tape)["accepted"]
    story = directory / "stories" / "chalk.toml"
    story.write_text(story.read_text().replace("A paper cup on the counter", "A paper cup on the table"))
    capsys.readouterr()
    assert cli(directory, *RENDER) == 1
    out, err = capsys.readouterr()
    assert f"4. {THANKS_ESPRESSO_KEY}  kept take 1, fails VT503, 4 takes filmed" in out
    assert f"fail: 4. {THANKS_ESPRESSO_KEY}  VT503" in err and "accepted:" not in err
    record = dailies.read(tape)
    [failure] = record["failures"]
    assert failure["take"] == 1 and failure["clip"] != accepted["clip"]
    assert (failure["accepted"], failure["accepted_before"]) == (None, {"reason": "a logo", "at": accepted["at"],
                                                                       "seed": 1})
    assert ('<p class="again">Accepted on take 1: a logo; the take was filmed again, so look again</p>'
            in (tape / "dailies.html").read_text())


def test_an_accept_holds_for_its_take_and_a_retake_that_keeps_another_fails_again_beside_the_earlier_reason(
        tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    stand_in(monkeypatch, misspelt_thanks_latte)
    assert cli(directory, *RENDER, "--takes", "1") == 1
    reason = "the heading reads well enough"
    assert cli(directory, "accept", "thanks(Latte)", "VT502", "--story", "chalk", "--reason", reason) == 0
    [accepted] = dailies.read(tape)["accepted"]
    assert accepted["seed"] == 1
    capsys.readouterr()

    assert cli(directory, "retake", "thanks(Latte)", "--story", "chalk") == 1
    out, err = capsys.readouterr()
    assert f"5. {THANKS_LATTE_KEY}  kept take 2, fails VT502, 1 take filmed" in out
    assert err.splitlines() == [f'fail: 5. {THANKS_LATTE_KEY}  VT502 Thanks: read "xhanks", CER 0.167',
                                '  next: videotape retake "thanks(Latte)" --story chalk']
    record = dailies.read(tape)
    [failure] = record["failures"]
    assert (failure["take"], failure["accepted"]) == (2, None)
    assert failure["accepted_before"] == {"reason": reason, "at": accepted["at"], "seed": 1}
    assert record["accepted"] == [accepted]
    page = (tape / "dailies.html").read_text()
    assert f'<p class="again">Accepted on take 1: {reason}; this is take 2, so look again</p>' in page
    assert "1 failing, 1 to act on, 0 accepted" in page and "badge accepted" not in page

    again = "the new heading reads well enough too"
    assert cli(directory, "accept", "thanks(Latte)", "VT502", "--story", "chalk", "--reason", again) == 0
    assert [accept["seed"] for accept in dailies.read(tape)["accepted"]] == [2]
    capsys.readouterr()
    assert cli(directory, *RENDER, "--takes", "1") == 0
    out, err = capsys.readouterr()
    assert f"5. {THANKS_LATTE_KEY}  kept take 2, fails VT502, cached" in out
    assert err.splitlines() == [f'accepted: 5. {THANKS_LATTE_KEY}  VT502 Thanks: read "xhanks", CER 0.167',
                                f"  reason: {again}"]
    [failure] = dailies.read(tape)["failures"]
    assert (failure["accepted"]["reason"], failure["accepted_before"]) == (again, None)


def test_an_accept_that_names_no_take_holds_for_none(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    tape = directory / "tapes" / "chalk"
    stand_in(monkeypatch, extra_on_thanks_espresso)
    cli(directory, *RENDER)
    cli(directory, "accept", "thanks(Espresso)", "VT503", "--story", "chalk", "--reason", "a logo")
    record = dailies.read(tape)
    for field in ("seed", "clip"):
        del record["accepted"][0][field]
    (tape / "dailies.json").write_text(json.dumps(record))
    capsys.readouterr()
    assert cli(directory, *RENDER) == 1
    assert capsys.readouterr().err.startswith(f"fail: 4. {THANKS_ESPRESSO_KEY}  VT503 ")
    [failure] = dailies.read(tape)["failures"]
    assert failure["accepted"] is None and failure["accepted_before"]["seed"] is None
    assert "Accepted on an earlier render: a logo; this is take 1, so look again" in (tape / "dailies.html").read_text()
