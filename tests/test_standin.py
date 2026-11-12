import pytest

import videotape as vt
from conftest import CONTRAIL, planned
from videotape import frames, standin
from videotape.checks import KeyChecks, Reading, readings, score
from videotape.frames import Box
from videotape.plan import Key, Mode, plan
from videotape.standin import Flaw, StandIn, StandInEye


def clean(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.NONE


def contrail_key(name: str) -> Key:
    return next(key for key in planned(CONTRAIL).keys if key.state.name == name)


def repeated() -> Key:
    app = vt.Screenplay("Fares")
    app.scene(lambda: [vt.Text("$89"), vt.Text("$89")]).name = "home"
    return plan(app).keys[0]


def test_the_stand_in_draws_every_contrail_key_so_its_eye_reads_every_line_and_finds_every_action():
    eye = StandInEye()
    for key in planned(CONTRAIL).keys:
        frame, drawn = standin.draw(standin.quoted(key.prompt))
        assert (frame.width, frame.height) == (1280, 704)
        assert eye.read(frame) == list(key.lines), key.state.name
        assert score(frame, key, eye).failures == [], key.state.name
        boxes = {text: box for text, box in ((d.text, d.box) for d in drawn)}
        for action in key.actions:
            assert eye.find(frame, action.words) == boxes[action.words], (key.state.name, action.label)


@pytest.mark.parametrize("state, lines, actions", [("profile", 51, 2), ("search", 7, 7), ("my_trips", 16, 4)])
def test_a_take_of_a_dense_key_still_reads_exactly_after_it_is_encoded(tmp_path, state, lines, actions):
    key = contrail_key(state)
    assert (len(key.lines), len(key.actions)) == (lines, actions)
    model = StandIn(flaw=clean)
    model.text_to_video(key.prompt, 1, tmp_path / "take.mp4")
    frame = frames.last_frame(tmp_path / "take.mp4")
    checks = score(frame, key, StandInEye())
    assert checks.failures == []
    assert [reading.seen for reading in checks.text] == list(key.lines)
    drawn = {d.text: d.box for d in model.drawn[tmp_path / "take.mp4"]}
    for action in key.actions:
        found, truth = checks.hotspots[action.label], drawn[action.words]
        assert max(abs(found.x - truth.x), abs(found.y - truth.y), abs(found.w - truth.w), abs(found.h - truth.h)) <= 2


@pytest.mark.parametrize("flaw", [Flaw.MISSPELL, Flaw.DROP_LINE])
def test_a_flawed_take_fails_its_checks_even_when_the_flaw_is_on_a_line_the_key_shows_twice(tmp_path, flaw):
    key = repeated()
    assert key.lines == ("$89", "$89")
    for seed in (1, 2, 3):
        take = tmp_path / f"{seed}.mp4"
        StandIn(flaw=lambda mode, prompt, seed: flaw).text_to_video(key.prompt, seed, take)
        checks = score(frames.last_frame(take), key, StandInEye())
        assert [reading.cer for reading in checks.text].count(0.0) == 1
        assert [item.name for item in checks.failures] == ['text "$89"']


def test_only_seeds_one_and_two_ever_carry_a_flaw_and_some_do(tmp_path):
    flawed = set()
    for key in planned(CONTRAIL).keys[:4]:
        for seed in (1, 2, 3, 4):
            model = StandIn()
            model.text_to_video(key.prompt, seed, tmp_path / "take.mp4")
            if [d.text for d in model.drawn[tmp_path / "take.mp4"]] != list(key.lines):
                flawed.add(seed)
    assert flawed == {1, 2}


def test_each_line_is_read_from_a_different_line_the_eye_saw():
    assert readings(("$89", "Sat 12", "$89"), ["$89", "Sat 12", "x89"]) == (
        Reading("$89", "$89", 0.0), Reading("Sat 12", "Sat 12", 0.0), Reading("$89", "x89", 1 / 3))
    assert readings(("$89", "Sat 12", "$89"), ["Sat 12", "$89"]) == (
        Reading("$89", "$89", 0.0), Reading("Sat 12", "Sat 12", 0.0), Reading("$89", "", 1.0))
    assert readings(("Book",), ["Trips", "Bonk", "Book now"]) == (Reading("Book", "Bonk", 0.25),)
    assert readings((), ["Trips"]) == ()


def test_a_missing_hotspot_costs_a_take_more_than_any_misread_line_and_the_seed_breaks_ties():
    box = Box(24, 24, 100, 33)
    clean_take = KeyChecks({"Done": box}, (Reading("Thanks", "Thanks", 0.0),))
    misread = KeyChecks({"Done": box}, (Reading("Thanks", "", 1.0),))
    unfound = KeyChecks({"Done": None}, (Reading("Thanks", "Thanks", 0.0),))
    assert clean_take.rank(3) < misread.rank(1) < unfound.rank(1)
    assert clean_take.rank(2) < clean_take.rank(3)
    assert [item.name for item in unfound.failures] == ['hotspot "Done"']
    assert [(item.name, item.result) for item in misread.failures] == [('text "Thanks"', "read nothing, CER 1.000")]


def test_the_stand_in_says_which_line_it_has_no_room_or_no_letters_for(tmp_path):
    with pytest.raises(standin.StandInError, match='no room to draw "' + "x" * 80):
        standin.draw([["x" * 80]])
    with pytest.raises(standin.StandInError, match=r'no room to draw "row \d+"'):
        standin.draw([[f"row {number}"] for number in range(1, 30)])
    with pytest.raises(standin.StandInError, match="cannot draw 'é'"):
        standin.draw([["Café"]])
