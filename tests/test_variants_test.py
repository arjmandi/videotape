"""scripts/variants-test draws three scenes of Contrail three ways on the project's model and measures which way keeps
a scene's layout when only its data changes. No test sends a request: the model is a stand-in under
gemini-omni-flash-1.2's name and price, and Claude answers from what the stand-in's eye reads, through a fake network,
as in tests/test_claude.py."""

import contextlib
import dataclasses
import importlib.machinery
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import CONTRAIL, contrail_copy, forget, planned, told, words
from test_claude import KEY as CLAUDE_KEY, Claude
from test_screen_test import Page
from videotape import claude, frames, project
from videotape.claude import ClaudeReader
from videotape.fal import Receipt
from videotape.frames import Box, Frame
from videotape.model import MODELS
from videotape.plan import Mode
from videotape.standin import Flaw, StandIn, StandInEye, draw

ROOT = CONTRAIL.parent.parent
GEMINI = "gemini-omni-flash-1.2"
BASES = {"results": "results(HNL, 2026-12-11)", "flight": "flight(CT 500, 2026-12-11)", "booked": "booked(CT 500, 2026-12-11)"}
"""Each scene's first state in walk order."""
RESULTS = tuple(f"results({place}, 2026-12-{day})" for place in ("HNL", "JFK", "SEA") for day in (11, 12, 13)
                if (place, day) != ("HNL", 11))
FLIGHTS = tuple(f"CT {number}, 2026-12-12" for number in (500, 504, 100, 104, 300, 306))
"""The six flights of 2026-12-12, in walk order."""
MISSPELT = ("results(JFK, 2026-12-12)", Mode.TEXT_TO_VIDEO)
"""The state whose seed-1 take under the seed method misspells a line, so the results scene moves to seed 2."""
DROPPED = ("flight(CT 104, 2026-12-12)", Mode.FIRST_FRAME)
"""The variant whose seed-1 take under from-key drops a line, so it gets a second take."""
BANNERS = {("booked(CT 104, 2026-12-12)", Mode.TEXT_TO_VIDEO), ("results(SEA, 2026-12-12)", Mode.FIRST_FRAME)}
"""The seed-1 takes that come out in another layout: a banner painted outside every box, in a colour the stand-in's
eye does not see as a box, so every text check passes and only the layout differs."""
BANNER, PAINT = Box(640, 480, 560, 200), bytes((220, 111, 20))


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("variants_test", str(ROOT / "scripts" / "variants-test"))
    spec = importlib.util.spec_from_loader("variants_test", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def prompts() -> dict[str, str]:
    """Each state's prompt in the terminal story, by the state's name."""
    terminal = told(CONTRAIL, "terminal")
    return {key.state.name: words(key, terminal) for key in planned(CONTRAIL).keys}


@pytest.fixture(autouse=True)
def keyless(monkeypatch):
    for key in ("FAL_KEY", "ANTHROPIC_API_KEY", "RUNPOD_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def variants(script, directory: Path, *arguments: str) -> tuple[int, str, str]:
    """Run the script in this process on a project, from the repo's root, with Contrail's modules forgotten before and
    after so each copy is imported afresh."""
    out, err = io.StringIO(), io.StringIO()
    forget(project.find(directory))
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = script.main([str(directory), *arguments])
    finally:
        forget(project.find(directory))
    return code, out.getvalue(), err.getvalue()


ESTIMATE = [
    "variants test of contrail 0.1.0 in terminal, on gemini-omni-flash-1.2: 3 scenes, 3 bases and 20 variants: results "
    "8, flight 6, booked 6",
    "seed: 23 to 46 calls; a scene's base and variants at one seed, and the whole scene again at the next seed when any "
    "state fails a check",
    "from-key: 20 to 40 calls; each variant from its base's key picture at seed 1, and again at seed 2 when it fails a "
    "text check",
    "repaint: no call; gemini-omni-flash-1.2 has no mode that repaints only the masked text of a key",
    f"gemini-omni-flash-1.2: 43 to 86 calls, $18.90 to $37.80 at $0.0819/s plus $0.03 a call for the prompt, and 43 to "
    f"86 reads by claude-opus-5-5 of 1280x720 pictures, at most ${43 * claude.estimate(1280, 720):.2f} to "
    f"${86 * claude.estimate(1280, 720):.2f}",
]
LEAST, MOST = (calls * (0.4395 + claude.estimate(1280, 720)) for calls in (43, 86))


def test_the_estimate_counts_each_methods_calls_prices_them_with_the_reads_and_needs_no_api_key(script, tmp_path,
                                                                                                 monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = variants(script, directory, "--story", "terminal", "--estimate")
    assert (code, err) == (0, "")
    assert out.splitlines() == [*ESTIMATE, f"the variants test: 43 to 86 calls and as many reads, at most ${LEAST:.2f} "
                                           f"to ${MOST:.2f}, no cap"]
    assert 26 < LEAST < 27 and 52 < MOST < 53
    code, out, _ = variants(script, directory, "--story", "terminal", "--estimate", "--cap-usd", "40")
    assert code == 0 and out.splitlines()[-1].endswith(f"at most ${LEAST:.2f} to ${MOST:.2f}, under the cap of $40.00 at the least")
    code, out, _ = variants(script, directory, "--story", "terminal", "--estimate", "--model", "stand-in")
    assert code == 0 and out.splitlines()[-2:] == ["stand-in: 43 to 86 calls, free", "the variants test: 43 to 86 calls, free"]
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


def test_each_scenes_base_is_its_first_state_in_walk_order_and_its_variants_are_the_other_results_and_the_flights_of_the_day(
        script):
    scenes = script.selected(planned(CONTRAIL))
    assert [(scene.name, scene.base.state.name) for scene in scenes] == list(BASES.items())
    assert [key.state.name for key in scenes[0].variants] == list(RESULTS)
    assert [key.state.name for key in scenes[1].variants] == [f"flight({flight})" for flight in FLIGHTS]
    assert [key.state.name for key in scenes[2].variants] == [f"booked({flight})" for flight in FLIGHTS]


def test_a_least_past_the_cap_or_no_cap_stops_before_any_call_and_names_the_cap_the_test_needs(script, tmp_path,
                                                                                               monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    needed = f"{__import__('math').ceil(LEAST * 100) / 100:.2f}"
    code, out, err = variants(script, directory, "--story", "terminal", "--cap-usd", "20")
    assert code == 1 and out.splitlines()[-1].endswith("past the cap of $20.00 at the least")
    assert err == (f"error VT402 before the first call: the variants test costs at least ${LEAST:.2f}, which passes the "
                   f"cap of $20.00\nnext: run it with a cap of at least ${needed}, as in:\nuv run scripts/variants-test "
                   f"{directory} --story terminal --cap-usd {needed}\n")
    code, _, err = variants(script, directory, "--story", "terminal")
    assert code == 1 and err == ("error VT402 before the first call: gemini-omni-flash-1.2 and claude-opus-5-5 bill per "
                                 "call, and no cap is set\nnext: set the most the variants test may spend, as in:\n"
                                 f"uv run scripts/variants-test {directory} --story terminal --cap-usd {needed}\n")
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


def test_a_missing_api_key_stops_the_variants_test_before_any_call_as_vt104(script, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = variants(script, directory, "--story", "terminal", "--cap-usd", "40")
    assert (code, err) == (1, "error VT104 .env: gemini-omni-flash-1.2 needs FAL_KEY, and it is not in the environment "
                              "or .env\nfix: copy .env.example to .env and set FAL_KEY there, or export it\n")
    assert out.splitlines()[:5] == ESTIMATE
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


class Gemini(StandIn):
    """A stand-in under gemini-omni-flash-1.2's name and price, which bills each call, carries MISSPELT's and
    DROPPED's flaws at seed 1, and paints a banner on BANNERS' takes at seed 1."""

    device = "fal"

    def __init__(self, prompts: dict[str, str]):
        super().__init__(flaw=self._flaw)
        self.name, self.price = GEMINI, MODELS[GEMINI].price
        self.states = {prompt: state for state, prompt in prompts.items()}

    def _flaw(self, mode: Mode, prompt: str, seed: int) -> Flaw:
        if seed != 1:
            return Flaw.NONE
        return {MISSPELT: Flaw.MISSPELL, DROPPED: Flaw.DROP_LINE}.get((self.states.get(prompt), mode), Flaw.NONE)

    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt:
        super().text_to_video(prompt, seed, out)
        self._paint(Mode.TEXT_TO_VIDEO, prompt, seed, None, out)
        return Receipt(f"{GEMINI}-{uuid.uuid4().hex}", self.price.seconds, self.price.usd, {})

    def first_frame(self, prompt: str, start: Path, seed: int, out: Path) -> Receipt:
        super().first_frame(prompt, start, seed, out)
        self._paint(Mode.FIRST_FRAME, prompt, seed, start, out)
        return Receipt(f"{GEMINI}-{uuid.uuid4().hex}", self.price.seconds, self.price.usd, {})

    def _paint(self, mode: Mode, prompt: str, seed: int, start: Path | None, out: Path) -> None:
        if seed != 1 or (self.states.get(prompt), mode) not in BANNERS:
            return
        last = frames.last_frame(out)
        canvas = bytearray(last.rgb)
        for y in range(BANNER.y, BANNER.y + BANNER.h):
            at = (y * last.width + BANNER.x) * 3
            canvas[at:at + BANNER.w * 3] = PAINT * BANNER.w
        with tempfile.TemporaryDirectory() as scratch:
            first = start or Path(scratch) / "first.png"
            if start is None:
                frames.write_png(draw([], prompt)[0], first)
            frames.write_png(Frame(last.width, last.height, bytes(canvas)), Path(scratch) / "painted.png")
            frames.crossfade(first, Path(scratch) / "painted.png", out)


@dataclass
class Fakes:
    film: Gemini
    claude: Claude


def fake(patch: pytest.MonkeyPatch, prompts: dict[str, str]) -> Fakes:
    film = Gemini(prompts)
    patch.setitem(MODELS, GEMINI, dataclasses.replace(MODELS[GEMINI], model=lambda: film,
                                                      readers=(StandInEye, ClaudeReader)))
    hosted = Claude()
    patch.setattr(claude, "_urlopen", hosted)
    patch.setenv("ANTHROPIC_API_KEY", CLAUDE_KEY)
    return Fakes(film, hosted)


RUN = ("--story", "terminal", "--cap-usd", "40")
TAPES = [f"tapes/variants-test/{method}/{scene}" for method in ("seed", "from-key") for scene in BASES]


@pytest.fixture(scope="module")
def tested(script, prompts, tmp_path_factory):
    """Contrail's variants test on the stand-in named gemini-omni-flash-1.2, run once for the tests that read it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(ROOT)
        fakes = fake(patch, prompts)
        directory = contrail_copy(tmp_path_factory.mktemp("tested") / "contrail")
        return directory, fakes, variants(script, directory, *RUN)


def copied(tested, to: Path) -> Path:
    return Path(shutil.copytree(tested[0], to / "contrail", ignore=shutil.ignore_patterns("__pycache__")))


def ledger_lines(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]


def report(directory: Path) -> tuple[str, Page]:
    text = (directory / "tapes" / "variants-test" / "report.html").read_text()
    return text, Page(text)


def test_it_draws_each_scene_at_one_seed_the_whole_scene_again_when_a_state_fails_and_each_variant_from_its_base_key(
        tested, script):
    directory, fakes, (code, out, err) = tested
    assert (code, err) == (0, "")
    calls = fakes.film.calls
    assert sorted(call.seed for call in calls if call.mode is Mode.TEXT_TO_VIDEO) == [1] * 23 + [2] * 9
    assert sorted(call.seed for call in calls if call.mode is Mode.FIRST_FRAME) == [1] * 20 + [2]
    assert {call.mode for call in calls} == {Mode.TEXT_TO_VIDEO, Mode.FIRST_FRAME}
    for scene, base in BASES.items():
        starts = {call.start for call in calls if call.mode is Mode.FIRST_FRAME
                  and f"{scene}(" in call.prompt.split('"')[1] or call.start == directory / TAPES[3 + list(BASES).index(scene)] / "base.png"}
        picture = directory / "tapes" / "variants-test" / "from-key" / scene / "base.png"
        assert picture in starts
        record = json.loads((directory / "tapes" / "variants-test" / "seed" / scene / "dailies.json").read_text())
        [first] = [take for key in record["keys"] if key["state"] == base for take in key["takes"] if take["seed"] == 1]
        assert frames.read_png(picture) == frames.last_frame(directory / "tapes" / "variants-test" / "seed" / scene / first["clip"])
    lines = ledger_lines(directory)
    assert sorted({line["tape"] for line in lines}) == sorted(TAPES)
    takes = [line for line in lines if line["kind"] == "take"]
    assert len(takes) == 53 and {line["usd"] for line in takes} == {0.4395}
    assert sorted(line["mode"] for line in takes) == ["first-frame"] * 21 + ["text-to-video"] * 32
    assert len(fakes.claude.seen) == sum(line["kind"] == "read" for line in lines) > 0
    assert sum(line["usd"] for line in lines) <= 40
    printed = out.splitlines()
    assert printed[:5] == ESTIMATE
    assert printed[6] == (f"seed, results: 9 states at seed 1, read by stand-in and claude-opus-5-5 -> "
                          f"{directory}/tapes/variants-test/seed/results")
    assert ("seed, results: results(JFK, 2026-12-12) failed at seed 1, so the whole scene is drawn again at seed 2"
            in printed)
    assert (f"from-key, results: 8 variants from results(HNL, 2026-12-11)'s key at seed 1, read by stand-in and "
            f"claude-opus-5-5 -> {directory}/tapes/variants-test/from-key/results") in printed
    assert sum(line.startswith("seed, ") and "drawn again at seed 2" in line for line in printed) == 1
    assert [line for line in printed if line.startswith("from-key, ") and "drawn again" in line] == [
        "from-key, flight: flight(CT 104, 2026-12-12) failed a text check at seed 1, or had the take refused, so drawn "
        "again at seed 2"]
    for scene in BASES:
        record = json.loads((directory / "tapes" / "variants-test" / "from-key" / scene / "dailies.json").read_text())
        assert all(take["items"][-1]["code"] == "VT505" and take["items"][-1]["passed"] for key in record["keys"]
                   for take in key["takes"])
    assert printed[-3:] == [
        f"wrote {directory}/tapes/variants-test/report.html",
        "the layout check: no threshold yet; mark pairs in the report and run again with --marks marks.json",
        "no recommendation: the layout check has no threshold until a person marks pairs",
    ]


def test_run_again_it_films_nothing_reads_nothing_and_writes_the_same_report(tested, script, prompts, tmp_path, monkeypatch):
    directory = copied(tested, tmp_path)
    monkeypatch.chdir(ROOT)
    fakes = fake(monkeypatch, prompts)
    ledger_before = (directory / "ledger.jsonl").read_text()
    report_before = (directory / "tapes" / "variants-test" / "report.html").read_text()
    code, out, err = variants(script, directory, *RUN)
    assert (code, err) == (0, "")
    assert fakes.film.calls == [] and fakes.claude.seen == []
    assert (directory / "ledger.jsonl").read_text() == ledger_before
    assert (directory / "tapes" / "variants-test" / "report.html").read_text() == report_before
    assert sum(", cached, $0.00, 0.0 s" in line for line in out.splitlines()) == 23 + 9 + 20
    assert "drawn again" not in "\n".join(line for line in out.splitlines() if line.startswith("from-key, "))


def test_one_cap_holds_for_the_whole_variants_test_and_counts_what_its_other_tapes_spent(script, prompts, tmp_path,
                                                                                        monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    monkeypatch.chdir(ROOT)
    fake(monkeypatch, prompts)
    earlier = {"kind": "take", "tape": "tapes/variants-test/from-key/booked", "shot": "key booked(CT 104, 2026-12-12) "
               "from booked(CT 500, 2026-12-11)", "seed": 9, "seconds": 1.0, "usd": 30.0, "request_id": "earlier"}
    (directory / "ledger.jsonl").write_text(json.dumps(earlier) + "\n")
    code, out, err = variants(script, directory, *RUN)
    assert code == 1
    assert err.startswith("error VT402 key ") and "the next call would pass the variants test's cap of $40.00, with $" in err
    assert err.endswith("next: run the variants test again with a higher cap, which resumes, as in:\nuv run "
                        f"scripts/variants-test {directory} --story terminal --cap-usd 80.00\n")
    spent = sum(line.get("usd", 0.0) for line in ledger_lines(directory))
    assert 30 + 5 < spent <= 40
    assert not (directory / "tapes" / "variants-test" / "report.html").exists()


def test_the_report_shows_each_methods_keys_side_by_side_with_the_layout_distances_the_checks_and_the_cost(tested):
    directory, _, _ = tested
    text, page = report(directory)
    scenes = [section["data-scene"] for section in page.all("section") if "data-scene" in section]
    assert scenes == list(BASES)
    states = [(state["data-key"], state["data-role"]) for state in page.all("div") if "data-role" in state]
    assert states[:3] == [(BASES["results"], "base"), (RESULTS[0], "variant"), (RESULTS[1], "variant")]
    assert len(states) == 23
    figures = [figure for figure in page.all("figure") if "data-seed" in figure]
    assert len(figures) == 32 + 21
    assert sorted(figure["data-usd"] for figure in figures)[:2] == ["0.44", "0.44"]
    assert all(float(figure["data-usd"]) >= 0.44 for figure in figures)
    distanced = [figure for figure in figures if "data-shading" in figure]
    assert len(distanced) == 28 + 21 and {figure["data-vt505"] for figure in distanced} == {"unjudged"}
    assert all("data-shading" not in figure for figure in figures if figure["data-key"] in BASES.values())
    far = {(figure["data-method"], figure["data-key"], figure["data-seed"]) for figure in distanced
           if float(figure["data-shading"]) > 0.01}
    assert far == {("seed", "booked(CT 104, 2026-12-12)", "1"), ("from-key", "results(SEA, 2026-12-12)", "1")}
    assert all(float(figure["data-shading"]) < 0.005 for figure in distanced
               if (figure["data-method"], figure["data-key"], figure["data-seed"]) not in far)
    assert len(page.all("input", type="radio")) == 2 * len(distanced)
    pictures = {attrs["src"] for attrs in page.all("img")}
    assert all((directory / "tapes" / "variants-test" / picture).is_file() for picture in pictures)
    assert all(not picture.startswith("/") for picture in pictures)
    assert "VT505 layout against the base" in page.text and "no threshold yet" in page.text
    assert "VT502" in page.text and "VT501" in page.text
    passing = {cell["data-method"]: cell["data-passing"] for cell in page.all("td") if "data-passing" in cell}
    assert passing == {"seed": "20 of 20", "from-key": "20 of 20"}
    assert "repaint: gemini-omni-flash-1.2 has no mode that repaints only the masked text of a key" in page.text
    assert "gemini-omni-flash-1.2 takes no seed, so the seed method draws each state on its own" in page.text
    assert "No recommendation yet: the layout check has no threshold until a person marks pairs." in page.text
    [recommendation] = page.all("section", id="recommendation")
    assert "data-recommend" not in recommendation
    assert "color-scheme: light dark" in text and "prefers-color-scheme: dark" in text
    assert "http://" not in text.replace("http://www.w3.org", "") and "<script src" not in text
    assert "google/gemini-omni-flash/v1.2/edit" in text


def test_the_report_counts_what_a_fare_change_and_a_direction_change_draw_again_under_each_method(tested):
    """CT 104 of 2026-12-12 is $179, the lowest fare to New York that day, so its fare is on its own key, on the strip
    of the three results(JFK, ...) keys and on dates(JFK)'s calendar: 5 keys, whose bases change under no method. The
    moves that touch them: dates(JFK)'s 3 days and the search that leads to it, the 4 moves off each results(JFK, ...)
    key, two other days and two rows, and the booking off the flight: 17. The flight scene's direction is in every
    flight key's prompt: 18 keys, each with a booking off it and a row onto it: 36 moves."""
    _, page = report(tested[0])
    counts = {(cell["data-change"], cell["data-method"]): (cell["data-keys"], cell["data-moves"])
              for cell in page.all("td") if "data-change" in cell}
    assert counts == {("fare", method): ("5", "17") for method in ("seed", "from-key", "repaint")} | {
        ("direction", method): ("18", "36") for method in ("seed", "from-key", "repaint")}
    assert "the fare of CT 104 on 2026-12-12, $179 to $181" in page.text
    assert 'the direction of the flight scene, "The gate desk, with the flight\'s details on its sign." to "The gate ' \
           'desk at dusk, with the flight\'s details on its sign."' in page.text


def test_a_change_to_a_base_draws_every_variant_of_its_scene_again_under_from_key_and_only_the_changed_keys_under_seed(
        script, tmp_path):
    """CT 500 of 2026-12-11 is the flight scene's base, and its fare is on the results and dates scenes' bases too,
    results(HNL, 2026-12-11) and dates(HNL), so under from-key every key of those three scenes is drawn again, and
    every move that leaves or lands on one. Under seed only the keys whose own prompt changes are: the flight, the
    three results(HNL, ...) keys, whose strip shows the day's lowest fare, and dates(HNL)."""
    directory = contrail_copy(tmp_path / "contrail")
    before = script.Edition(planned(directory), told(directory, "terminal"))
    file = directory / "data" / "flights.json"
    flights = json.loads(file.read_text())
    [base] = [flight for flight in flights if (flight["number"], flight["day"]) == ("CT 500", "2026-12-11")]
    base["fare"] += 2
    file.write_text(json.dumps(flights, indent=2) + "\n")
    after = script.Edition(planned(directory), told(directory, "terminal"))
    seed, from_key, repaint = (script.rerendered(before, after, method) for method in script.METHODS)
    scenes = {"flight", "results", "dates"}
    keys = {key.id for key in after.plan.keys if key.state.scene.name in scenes}
    moves = {move.id for move in after.plan.moves if {move.start.scene.name, move.land.scene.name} & scenes}
    assert from_key == repaint == (len(keys), len(moves)) == (30, len(moves))
    assert seed[0] == 5 and seed[1] < from_key[1]


def marks_of(directory: Path, same) -> dict:
    """A mark for each variant take in the report, the same layout as its base as same(method, state, seed) says."""
    _, page = report(directory)
    radios = [radio for radio in page.all("input", type="radio") if radio["value"] == "same"]
    return {"test": "variants-test", "model": GEMINI, "story": "terminal", "marks": [
        {"method": radio["data-method"], "state": radio["data-state"], "seed": int(radio["data-seed"]),
         "clip": radio["data-clip"], "same": same(radio["data-method"], radio["data-state"], int(radio["data-seed"]))}
        for radio in radios]}


def test_marks_set_the_threshold_that_parts_them_the_layout_check_judges_by_it_and_the_recommendation_follows(
        tested, script, prompts, tmp_path, monkeypatch):
    directory = copied(tested, tmp_path)
    monkeypatch.chdir(ROOT)
    fakes = fake(monkeypatch, prompts)
    far = {("seed", "booked(CT 104, 2026-12-12)", 1), ("from-key", "results(SEA, 2026-12-12)", 1)}
    marks = marks_of(directory, lambda method, state, seed: (method, state, seed) not in far)
    assert len(marks["marks"]) == 49
    (tmp_path / "marks.json").write_text(json.dumps(marks))
    code, out, err = variants(script, directory, *RUN, "--marks", str(tmp_path / "marks.json"))
    assert (code, err) == (0, "") and fakes.film.calls == [] and fakes.claude.seen == []
    lines = out.splitlines()
    assert lines[-2].startswith("the layout check: shading at 0.0") and lines[-2].endswith(
        ", agreeing with a person's marks on 49 of 49 pairs, 100.0%")
    assert lines[-1].startswith("recommend: from-key, 19 of 20 variants pass the layout check and every text check, $")
    assert lines[-1].endswith(" a passing variant, 23 keys and 53 moves drawn again by the two changes; seed 19 of 20")
    text, page = report(directory)
    [recommendation] = page.all("section", id="recommendation")
    assert recommendation["data-recommend"] == "from-key"
    assert "The recommendation is from-key. from-key: 19 of 20 variants pass the layout check and every text check" \
           in page.text
    verdicts = {(f["data-method"], f["data-key"], int(f["data-seed"])): f["data-vt505"]
                for f in page.all("figure") if "data-vt505" in f}
    assert {pair for pair, verdict in verdicts.items() if verdict == "failed"} == far
    assert set(verdicts.values()) == {"passed", "failed"}
    assert "over the threshold of 0.0" in page.text and "VT505 layout against the base" in page.text
    checked = {(radio["data-method"], radio["data-state"], radio["value"]) for radio in page.all("input", type="radio")
               if "checked" in radio}
    assert ("seed", "booked(CT 104, 2026-12-12)", "different") in checked
    assert ("seed", "booked(CT 100, 2026-12-12)", "same") in checked
    passing = {cell["data-method"]: cell["data-passing"] for cell in page.all("td") if "data-passing" in cell}
    assert passing == {"seed": "19 of 20", "from-key": "19 of 20"}


def test_marks_the_distances_cannot_part_leave_the_threshold_below_agreement_and_withhold_the_recommendation(
        tested, script, prompts, tmp_path, monkeypatch):
    directory = copied(tested, tmp_path)
    monkeypatch.chdir(ROOT)
    fake(monkeypatch, prompts)
    marks = marks_of(directory, lambda method, state, seed: not (method == "seed" and state in RESULTS[:5]))
    (tmp_path / "marks.json").write_text(json.dumps(marks))
    code, out, err = variants(script, directory, *RUN, "--marks", str(tmp_path / "marks.json"))
    assert (code, err) == (0, "")
    _, page = report(directory)
    farthest = max(float(f["data-shading"]) for f in page.all("figure") if "data-shading" in f)
    assert out.splitlines()[-2:] == [
        f"the layout check: shading at {farthest:.4f}, agreeing with a person's marks on 39 of 49 pairs, 79.6%, below 90%",
        "no recommendation: the marks hold the layout check's threshold below 90%",
    ]
    [recommendation] = page.all("section", id="recommendation")
    assert "data-recommend" not in recommendation
    assert f"No recommendation: the layout check's best threshold, shading at {farthest:.4f}, agreeing with a " \
           "person's marks on 39 of 49 pairs, 79.6%, is below 90%." in page.text
    assert "Where the check disagrees with the marks" in page.text
    assert {f["data-vt505"] for f in page.all("figure") if "data-vt505" in f} == {"unjudged"}


@pytest.mark.parametrize("marks, said", [
    ("not json", "is not JSON"),
    (json.dumps({"test": "screen-test", "marks": []}), "holds no marks of a variants test"),
    (json.dumps({"test": "variants-test", "model": GEMINI, "story": "terminal", "marks": [{"state": "home()"}]}),
     "holds an entry that is not a mark"),
    (json.dumps({"test": "variants-test", "model": GEMINI, "story": "posters", "marks": []}),
     "holds marks of the posters story, and this variants test draws terminal"),
])
def test_a_marks_file_that_is_not_the_reports_says_so_and_films_nothing(script, tmp_path, capsys, marks, said):
    (tmp_path / "marks.json").write_text(marks)
    with pytest.raises(SystemExit) as stopped:
        script.main([str(tmp_path), *RUN, "--marks", str(tmp_path / "marks.json")])
    err = capsys.readouterr().err
    assert stopped.value.code == 2 and f"argument --marks: {tmp_path / 'marks.json'} {said}" in err


def test_the_recommendation_has_the_most_variants_passing_then_the_lowest_cost_a_passing_variant_then_the_fewest_redraws(
        script):
    standing, tally = script.Standing, script.Tally
    most = standing("most", tally(18, 20), usd=20.0, keys=30, moves=60)
    fewer = standing("fewer", tally(12, 20), usd=1.0, keys=1, moves=2)
    assert script.recommend([fewer, most]) is most
    cheap = standing("cheap", tally(18, 20), usd=9.0, keys=40, moves=80)
    assert script.recommend([most, cheap, fewer]) is cheap
    steady = standing("steady", tally(18, 20), usd=9.0, keys=30, moves=60)
    assert script.recommend([most, cheap, steady]) is steady
