import pytest

import videotape as vt
from conftest import CONTRAIL, a_story, planned, told, words
from videotape import frames, standin
from videotape.checks import KeyChecks, Reading, Spot, find, read, readings, score
from videotape.frames import Box
from videotape.plan import Key, Mode, plan
from videotape.standin import EXTRA, Flaw, StandIn, StandInEye


def seen(*texts: str) -> tuple[Spot, ...]:
    """Spots as an eye reports them, each at its own place."""
    return tuple(Spot(text, Box(0, 40 * number, 100, 33), True) for number, text in enumerate(texts))


def failed(checks: KeyChecks) -> list[tuple[str, str]]:
    return [(item.code, item.about) for item in checks.failures]


def clean(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.NONE


def contrail_key(name: str) -> Key:
    return next(key for key in planned(CONTRAIL).keys if key.state.name == name)


def repeated() -> Key:
    app = vt.Screenplay("Fares")
    app.scene(lambda: [vt.Text("$89"), vt.Text("$89")]).name = "home"
    return plan(app).keys[0]


@pytest.mark.parametrize("name", ["terminal", "posters"])
def test_the_stand_in_draws_every_contrail_key_so_its_eye_reads_every_line_and_finds_every_action(name):
    eye, look = StandInEye(), told(CONTRAIL, name)
    for key in planned(CONTRAIL).keys:
        frame, drawn = standin.draw(standin.quoted(words(key, look)))
        assert (frame.width, frame.height) == (1280, 704)
        assert read(eye.see(frame)) == list(key.lines), key.state.name
        assert score(frame, key, eye).failures == [], key.state.name
        boxes = {text: box for text, box in ((d.text, d.box) for d in drawn)}
        for action in key.actions:
            assert find(eye.see(frame), action.words) == boxes[action.words], (key.state.name, action.label)


@pytest.mark.parametrize("state, lines, actions", [("profile()", 51, 2), ("search()", 7, 7), ("my_trips()", 16, 4)])
def test_a_take_of_a_dense_key_still_reads_exactly_after_it_is_encoded(tmp_path, state, lines, actions):
    key = contrail_key(state)
    assert (len(key.lines), len(key.actions)) == (lines, actions)
    model = StandIn(flaw=clean)
    model.text_to_video(words(key, told(CONTRAIL, "terminal")), 1, tmp_path / "take.mp4")
    frame = frames.last_frame(tmp_path / "take.mp4")
    checks = score(frame, key, StandInEye())
    assert checks.failures == []
    assert [reading.seen for reading in checks.text] == list(key.lines)
    drawn = {d.text: d.box for d in model.drawn[tmp_path / "take.mp4"]}
    for action in key.actions:
        found, truth = checks.hotspots[action.label], drawn[action.words]
        assert max(abs(found.x - truth.x), abs(found.y - truth.y), abs(found.w - truth.w), abs(found.h - truth.h)) <= 2


def test_two_prompts_that_quote_the_same_line_give_two_pictures_and_the_eye_reads_the_line_in_both(tmp_path):
    seen = {}
    for prompt in ('A dark sign reads "Trips".', 'A printed poster reads "Trips".', 'A dark sign reads "Trips".'):
        take = tmp_path / f"{len(seen)}.mp4"
        StandIn(flaw=clean).text_to_video(prompt, 1, take)
        frame = frames.last_frame(take)
        assert read(StandInEye().see(frame)) == ["Trips"]
        assert seen.setdefault(prompt, frame) == frame
    sign, poster = seen.values()
    assert sign.rgb != poster.rgb
    assert frames.difference(sign, poster) < 0.005


@pytest.mark.parametrize("flaw", [Flaw.MISSPELL, Flaw.DROP_LINE])
def test_a_flawed_take_fails_its_checks_even_when_the_flaw_is_on_a_line_the_key_shows_twice(tmp_path, flaw):
    key = repeated()
    assert key.lines == ("$89", "$89")
    for seed in (1, 2, 3):
        take = tmp_path / f"{seed}.mp4"
        StandIn(flaw=lambda mode, prompt, seed: flaw).text_to_video(words(key, a_story()), seed, take)
        checks = score(frames.last_frame(take), key, StandInEye())
        assert [reading.cer for reading in checks.text].count(0.0) == 1
        assert failed(checks) == [("VT502", "$89")]


def test_an_extra_box_is_an_invented_control_which_fails_vt503_with_its_box(tmp_path):
    key = contrail_key("thanks(Latte)") if False else repeated()
    take = tmp_path / "extra.mp4"
    model = StandIn(flaw=lambda mode, prompt, seed: Flaw.EXTRA_BOX)
    model.text_to_video(words(key, a_story()), 1, take)
    checks = score(frames.last_frame(take), key, StandInEye())
    [extra] = [d for d in model.drawn[take] if d.text == EXTRA]
    assert [(spot.text, spot.control) for spot in checks.invented] == [(EXTRA, True)]
    assert failed(checks) == [("VT503", EXTRA)]
    [item] = checks.failures
    assert item.box == checks.invented[0].box
    assert max(abs(item.box.x - extra.box.x), abs(item.box.y - extra.box.y)) <= 2
    assert item.result.startswith(f'a control reading "{EXTRA}" at ')
    clean_checks = KeyChecks({}, checks.text)
    assert clean_checks.rank(3) < checks.rank(1)


def test_only_seeds_one_and_two_ever_carry_a_flaw_and_some_do(tmp_path):
    flawed = set()
    for key in planned(CONTRAIL).keys[:4]:
        for seed in (1, 2, 3, 4):
            model = StandIn()
            model.text_to_video(words(key, told(CONTRAIL, "terminal")), seed, tmp_path / "take.mp4")
            if [d.text for d in model.drawn[tmp_path / "take.mp4"]] != list(key.lines):
                flawed.add(seed)
    assert flawed == {1, 2}


def test_each_line_is_read_from_a_different_spot_the_eye_saw_and_knows_where():
    spots = seen("$89", "Sat 12", "x89")
    assert readings(("$89", "Sat 12", "$89"), spots) == (
        Reading("$89", "$89", 0.0, spots[0].box), Reading("Sat 12", "Sat 12", 0.0, spots[1].box),
        Reading("$89", "x89", 1 / 3, spots[2].box))
    spots = seen("Sat 12", "$89")
    assert readings(("$89", "Sat 12", "$89"), spots) == (
        Reading("$89", "$89", 0.0, spots[1].box), Reading("Sat 12", "Sat 12", 0.0, spots[0].box),
        Reading("$89", "", 1.0, None))
    spots = seen("Trips", "Bonk", "Book now")
    assert readings(("Book",), spots) == (Reading("Book", "Bonk", 0.25, spots[1].box),)
    assert readings((), seen("Trips")) == ()


def test_find_takes_the_closest_spot_within_the_limit_and_a_control_before_a_plain_one():
    spots = seen("Book", "Trips")
    plain = (Spot("Book", Box(0, 0, 50, 20), False), spots[0])
    assert find(spots, "Book") == spots[0].box
    assert find(plain, "Book") == spots[0].box
    assert find(spots, "Boook") == spots[0].box
    assert find(spots, "Bonk") is None
    assert find(spots, "Profile") is None
    assert find((), "Book") is None


def test_a_missing_hotspot_costs_a_take_more_than_any_misread_line_and_the_seed_breaks_ties():
    box = Box(24, 24, 100, 33)
    clean_take = KeyChecks({"Done": box}, (Reading("Thanks", "Thanks", 0.0, box),))
    misread = KeyChecks({"Done": box}, (Reading("Thanks", "", 1.0, None),))
    unfound = KeyChecks({"Done": None}, (Reading("Thanks", "Thanks", 0.0, box),))
    invented = KeyChecks({"Done": box}, (Reading("Thanks", "Thanks", 0.0, box),), (Spot("Cancel", box, True),))
    assert clean_take.rank(3) < misread.rank(1) < invented.rank(1) < unfound.rank(1)
    assert clean_take.rank(2) < clean_take.rank(3)
    assert failed(unfound) == [("VT501", "Done")] and failed(invented) == [("VT503", "Cancel")]
    assert [(item.code, item.about, item.result) for item in misread.failures] == [
        ("VT502", "Thanks", "read nothing, CER 1.000")]
    assert (clean_take.passed, misread.passed, unfound.passed, invented.passed) == (True, False, False, False)


def test_the_stand_in_says_which_line_it_has_no_room_or_no_letters_for(tmp_path):
    with pytest.raises(standin.StandInError, match='no room to draw "' + "x" * 80):
        standin.draw([["x" * 80]])
    with pytest.raises(standin.StandInError, match=r'no room to draw "row \d+"'):
        standin.draw([[f"row {number}"] for number in range(1, 30)])
    with pytest.raises(standin.StandInError, match="cannot draw 'é'"):
        standin.draw([["Café"]])
