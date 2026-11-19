import pytest

import videotape as vt
from conftest import CONTRAIL, a_story, planned, told, words
from videotape import frames, standin
from videotape.checks import Hotspot, KeyChecks, Reading, Seen, Sighting, Spot, find, read, readings, score
from videotape.errors import ModelError
from videotape.frames import Box
from videotape.plan import Key, Mode, plan
from videotape.standin import EXTRA, Flaw, StandIn, StandInEye, StandInJudge, _png


def seen(*texts: str) -> tuple[Spot, ...]:
    """Spots as a reader reports them, each at its own place."""
    return tuple(Spot(text, Box(0, 40 * number, 100, 33), True) for number, text in enumerate(texts))


def by_stand_in(text: str, cer: float, box: Box | None) -> Seen:
    return Seen("stand-in", text, cer, box)


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
        prompt = words(key, look)
        frame, drawn = standin.draw(standin.quoted(prompt), prompt)
        assert (frame.width, frame.height) == (1280, 704)
        seen = eye.see(frame)
        assert read(seen.spots) == list(key.lines), key.state.name
        assert score(key, [seen]).failures == [], key.state.name
        boxes = {text: box for text, box in ((d.text, d.box) for d in drawn)}
        for action in key.actions:
            assert find(seen.spots, action.words) == boxes[action.words], (key.state.name, action.label)


@pytest.mark.parametrize("state, lines, actions", [("profile()", 51, 2), ("search()", 7, 7), ("my_trips()", 16, 4)])
def test_a_take_of_a_dense_key_still_reads_exactly_after_it_is_encoded(tmp_path, state, lines, actions):
    key = contrail_key(state)
    assert (len(key.lines), len(key.actions)) == (lines, actions)
    model = StandIn(flaw=clean)
    model.text_to_video(words(key, told(CONTRAIL, "terminal")), 1, tmp_path / "take.mp4")
    frame = frames.last_frame(tmp_path / "take.mp4")
    checks = score(key, [StandInEye().see(frame)])
    assert checks.failures == []
    assert [reading.seen[0].text for reading in checks.text] == list(key.lines)
    drawn = {d.text: d.box for d in model.drawn[tmp_path / "take.mp4"]}
    for action in key.actions:
        found, truth = checks.hotspots[action.label], drawn[action.words]
        assert max(abs(found.x - truth.x), abs(found.y - truth.y), abs(found.w - truth.w), abs(found.h - truth.h)) <= 2


def test_a_key_drawn_from_a_start_picture_opens_on_it_ends_on_the_prompts_lines_and_may_carry_a_key_flaw(tmp_path):
    base, key = contrail_key("flight(CT 500, 2026-12-11)"), contrail_key("flight(CT 104, 2026-12-12)")
    terminal = told(CONTRAIL, "terminal")
    model = StandIn(flaw=clean)
    assert model.modes == set(Mode)
    model.text_to_video(words(base, terminal), 1, tmp_path / "base.mp4")
    frames.write_png(frames.last_frame(tmp_path / "base.mp4"), tmp_path / "base.png")
    model.first_frame(words(key, terminal), tmp_path / "base.png", 1, tmp_path / "take.mp4")
    assert model.calls[-1] == standin.Call(Mode.FIRST_FRAME, words(key, terminal), 1, tmp_path / "base.png", None,
                                           tmp_path / "take.mp4")
    assert frames.difference(frames.first_frame(tmp_path / "take.mp4"), frames.read_png(tmp_path / "base.png")) < 0.01
    checks = score(key, [StandInEye().see(frames.last_frame(tmp_path / "take.mp4"))])
    assert checks.failures == [] and [reading.seen[0].text for reading in checks.text] == list(key.lines)
    flawed = StandIn(flaw=lambda mode, prompt, seed: Flaw.MISSPELL)
    flawed.first_frame(words(key, terminal), tmp_path / "base.png", 1, tmp_path / "flawed.mp4")
    misread = failed(score(key, [StandInEye().see(frames.last_frame(tmp_path / "flawed.mp4"))]))
    assert len(misread) == 1 and misread[0][0] == "VT502"


def test_two_prompts_that_quote_the_same_line_give_two_pictures_and_the_eye_reads_the_line_in_both(tmp_path):
    seen = {}
    for prompt in ('A dark sign reads "Trips".', 'A printed poster reads "Trips".', 'A dark sign reads "Trips".'):
        take = tmp_path / f"{len(seen)}.mp4"
        StandIn(flaw=clean).text_to_video(prompt, 1, take)
        frame = frames.last_frame(take)
        assert read(StandInEye().see(frame).spots) == ["Trips"]
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
        checks = score(key, [StandInEye().see(frames.last_frame(take))])
        assert [reading.seen[0].cer for reading in checks.text].count(0.0) == 1
        assert failed(checks) == [("VT502", "$89")]


def test_an_extra_box_is_an_invented_control_which_fails_vt503_with_its_box(tmp_path):
    key = contrail_key("thanks(Latte)") if False else repeated()
    take = tmp_path / "extra.mp4"
    model = StandIn(flaw=lambda mode, prompt, seed: Flaw.EXTRA_BOX)
    model.text_to_video(words(key, a_story()), 1, take)
    checks = score(key, [StandInEye().see(frames.last_frame(take))])
    [extra] = [d for d in model.drawn[take] if d.text == EXTRA]
    assert [(seen.reader, seen.spot.text, seen.spot.control) for seen in checks.invented] == [("stand-in", EXTRA, True)]
    assert failed(checks) == [("VT503", EXTRA)]
    [item] = checks.failures
    assert (item.box, item.element) == (checks.invented[0].spot.box, None)
    assert max(abs(item.box.x - extra.box.x), abs(item.box.y - extra.box.y)) <= 2
    assert item.result == f'a control reading "{EXTRA}" at {item.box.x},{item.box.y} {item.box.w}x{item.box.h}, and no ' \
                          "action has those words"
    clean_checks = KeyChecks((), checks.text)
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


def test_each_line_is_read_from_a_different_spot_the_reader_saw_and_knows_where():
    def read(lines, spots):
        return tuple(seen for seen, _ in readings("stand-in", lines, spots))

    spots = seen("$89", "Sat 12", "x89")
    assert read(("$89", "Sat 12", "$89"), spots) == (
        by_stand_in("$89", 0.0, spots[0].box), by_stand_in("Sat 12", 0.0, spots[1].box),
        by_stand_in("x89", 1 / 3, spots[2].box))
    spots = seen("Sat 12", "$89")
    assert read(("$89", "Sat 12", "$89"), spots) == (
        by_stand_in("$89", 0.0, spots[1].box), by_stand_in("Sat 12", 0.0, spots[0].box), by_stand_in("", 1.0, None))
    spots = seen("Trips", "Bonk", "Book now")
    assert read(("Book",), spots) == (by_stand_in("Bonk", 0.25, spots[1].box),)
    assert read((), seen("Trips")) == ()


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
    done = (Hotspot("Done", "Button", (by_stand_in("Done", 0.0, box),)),)
    thanks = (Reading("Thanks", "Heading", (by_stand_in("Thanks", 0.0, box),)),)
    clean_take = KeyChecks(done, thanks)
    misread = KeyChecks(done, (Reading("Thanks", "Heading", (by_stand_in("", 1.0, None),)),))
    unfound = KeyChecks((Hotspot("Done", "Button", (by_stand_in("", 1.0, None),)),), thanks)
    invented = KeyChecks(done, thanks, (Sighting("stand-in", Spot("Cancel", box, True)),))
    assert clean_take.rank(3) < misread.rank(1) < invented.rank(1) < unfound.rank(1)
    assert clean_take.rank(2) < clean_take.rank(3)
    assert failed(unfound) == [("VT501", "Done")] and failed(invented) == [("VT503", "Cancel")]
    assert [(item.code, item.about, item.result, item.element) for item in misread.failures] == [
        ("VT502", "Thanks", "read nothing, CER 1.000", "Heading")]
    assert [(item.result, item.element) for item in unfound.failures] == [("not found", "Button")]
    assert (clean_take.passed, misread.passed, unfound.passed, invented.passed) == (True, False, False, False)
    assert clean_take.hotspots == {"Done": box} and unfound.hotspots == {"Done": None}


def test_a_chosen_line_is_the_one_of_its_own_elements_sentence_and_keeps_its_mark_through_a_flaw():
    prompt = ('Heading, reading "Home". Tabs, reading "Home", "Trips", with "Home" chosen. SearchBar, reading '
              '"Where to?"; "Portland (PDX)"; "Seattle (SEA)", with "Portland (PDX)" chosen. Sharp lettering.')
    assert standin.quoted(prompt) == [["Home"], ["Home", "Trips"], ["Where to?"], ["Portland (PDX)"], ["Seattle (SEA)"]]
    assert standin.chosen(prompt) == {(1, 0), (3, 0)}
    frame, drawn = standin.draw(standin.quoted(prompt), prompt)
    seen = StandInEye().see(frame)
    assert read(seen.spots) == ["Home", "Home", "Trips", "Where to?", "Portland (PDX)", "Seattle (SEA)"]
    assert seen.marked == (drawn[1].box, drawn[4].box)
    rows, (r, i) = standin._spoil(standin.quoted(prompt), Flaw.MISSPELL, bytes([0, 0, 1, 2]))
    assert (r, i) == (1, 0) and rows[1] == ["Hoxe", "Trips"]
    frame, drawn = standin.draw(rows, prompt, standin.chosen(prompt))
    assert StandInEye().see(frame).marked == (drawn[1].box, drawn[4].box)


def test_the_stand_in_says_which_line_it_has_no_room_or_no_letters_for(tmp_path):
    with pytest.raises(ModelError, match='VT406 the model.s call: the stand-in has no room to draw "' + "x" * 80):
        standin.draw([["x" * 80]])
    with pytest.raises(ModelError, match=r'VT406 the model.s call: the stand-in has no room to draw "row \d+"'):
        standin.draw([[f"row {number}"] for number in range(1, 30)])
    with pytest.raises(ModelError, match="VT406 the model.s call: the stand-in cannot draw 'é'"):
        standin.draw([["Café"]])


def test_the_stand_ins_judge_calls_the_middle_of_a_crossfade_overlaid_and_a_wipes_held_or_cut_picture_one(tmp_path):
    start, end = tmp_path / "start.png", tmp_path / "end.png"
    frames.write_png(standin.draw([["Thanks"], ["One Espresso coming up."]])[0], start)
    frames.write_png(standin.draw([["Corner Cafe"], ["Drinks"]])[0], end)
    crossfade, wipe, held, cut = (tmp_path / name for name in ("crossfade.mp4", "wipe.mp4", "held.mp4", "cut.mp4"))
    frames.crossfade(start, end, crossfade)
    frames.wipe(start, end, wipe)
    frames.wipe(start, start, held)
    first, last = frames.read_png(start).rgb, frames.read_png(end).rgb
    frames.write_video([first] * 12 + [last] * 12, cut)
    judge = StandInJudge(tmp_path)
    assert (StandInJudge.name, StandInJudge.key, StandInJudge.paid, StandInJudge.most(1280, 704)) == ("stand-in", None, False, 0.0)
    faded = judge.judge(frames.sampled(crossfade, 8))
    assert faded.judge == "stand-in" and faded.at == (0, 3, 7, 10, 13, 16, 20, 23)
    assert faded.overlaid == (False, False, True, True, False, False, False, False) and not faded.passed
    assert faded.seen[0] == "the first frame" and faded.seen[-1] == "the last frame"
    assert faded.seen[2].startswith("the first frame fading into the last, ") and faded.seen[2].endswith("% of the way")
    assert max(frames.scene_scores(crossfade)) < 0.3
    wiped = judge.judge(frames.sampled(wipe, 8))
    assert wiped.passed and wiped.at == faded.at
    assert "a picture that is neither the first frame nor the last" in wiped.seen
    assert set(wiped.seen) <= {"the first frame", "a picture that is neither the first frame nor the last", "the last frame"}
    assert max(frames.scene_scores(wipe)) < 0.3
    assert frames.difference(frames.first_frame(wipe), frames.read_png(start)) < 0.01
    assert frames.difference(frames.last_frame(wipe), frames.read_png(end)) < 0.01
    still = judge.judge(frames.sampled(held, 8))
    assert still.passed and set(still.seen) == {"the first and last frames, which are alike"}
    hard = judge.judge(frames.sampled(cut, 8))
    assert hard.passed and set(hard.seen) == {"the first frame", "the last frame"}


def test_a_cut_between_two_stand_in_keys_scores_under_the_cut_threshold_since_they_share_a_background(tmp_path):
    first = frames.read_png(_png(standin.draw([["Thanks"], ["One Espresso coming up."]])[0], tmp_path / "s.png")).rgb
    last = frames.read_png(_png(standin.draw([["Corner Cafe"], ["Drinks"]])[0], tmp_path / "e.png")).rgb
    frames.write_video([first] * 12 + [last] * 12, tmp_path / "cut.mp4")
    assert max(frames.scene_scores(tmp_path / "cut.mp4")) < 0.05


def test_a_wipe_travels_and_the_dissolve_and_cut_flaws_fail_their_check_and_keep_the_seams(tmp_path):
    """A clean move wipes from the key it leaves to the key it lands on, so it passes the cut check, the stand-in's
    judge and both seams. The dissolve flaw crossfades instead, which the judge calls overlaid, and the cut flaw jumps
    through the last picture's negative, which scores far over the cut threshold since the two keys alone sit too
    close for a cut between them to score."""
    start, end = tmp_path / "start.png", tmp_path / "end.png"
    frames.write_png(standin.draw([["Thanks"], ["One Espresso coming up."]])[0], start)
    frames.write_png(standin.draw([["Corner Cafe"], ["Drinks"]])[0], end)
    judge, taken = StandInJudge(), {}
    for flaw in (Flaw.NONE, Flaw.DISSOLVE, Flaw.CUT):
        for mode in (Mode.FIRST_AND_LAST_FRAME, Mode.FIRST_FRAME):
            model = StandIn(flaw=lambda mode, prompt, seed: flaw)
            out = tmp_path / f"{flaw.value}-{mode.value}.mp4"
            if mode is Mode.FIRST_AND_LAST_FRAME:
                model.first_last_frame('The button "Done" is pressed.', start, end, 1, out)
            else:
                model.first_frame('Reading "Corner Cafe". Reading "Drinks".', start, 1, out)
            taken[flaw, mode] = (judge.judge(frames.sampled(out, 8)).passed, max(frames.scene_scores(out)) <= 0.3,
                                 frames.difference(frames.first_frame(out), frames.read_png(start)) < 0.01)
    assert taken == {(Flaw.NONE, Mode.FIRST_AND_LAST_FRAME): (True, True, True),
                     (Flaw.NONE, Mode.FIRST_FRAME): (True, True, True),
                     (Flaw.DISSOLVE, Mode.FIRST_AND_LAST_FRAME): (False, True, True),
                     (Flaw.DISSOLVE, Mode.FIRST_FRAME): (False, True, True),
                     (Flaw.CUT, Mode.FIRST_AND_LAST_FRAME): (True, False, True),
                     (Flaw.CUT, Mode.FIRST_FRAME): (True, False, True)}
    pinned = tmp_path / f"{Flaw.CUT.value}-{Mode.FIRST_AND_LAST_FRAME.value}.mp4"
    assert frames.difference(frames.last_frame(pinned), frames.read_png(end)) < 0.01
    with pytest.raises(ValueError, match="DISSOLVE does not apply to this text-to-video take"):
        StandIn(flaw=lambda mode, prompt, seed: Flaw.DISSOLVE).text_to_video('Reading "Drinks".', 1, tmp_path / "no.mp4")
    assert standin.FLAWS[Mode.FIRST_AND_LAST_FRAME] == (Flaw.WRONG_START, Flaw.WRONG_END, Flaw.DISSOLVE, Flaw.CUT)
    assert standin.FLAWS[Mode.FIRST_FRAME] == standin.FLAWS[Mode.TEXT_TO_VIDEO] == (Flaw.MISSPELL, Flaw.DROP_LINE, Flaw.EXTRA_BOX)
