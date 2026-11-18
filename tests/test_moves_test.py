"""scripts/moves-test draws twelve moves of Contrail two ways in both stories on the project's model, checks each for a
cut and a dissolve, and recommends a method per story. No test sends a request: the model is a stand-in under
gemini-omni-flash-1.2's name and price, and Claude answers from what the stand-in's eye reads and what the stand-in's
judge sees, through a fake network, as in tests/test_claude.py. The ten labelled clips, under examples/surf_shop and
never in the repo, are judged when they are there: VT506 live, and VT507 from the fixture of Claude's recorded answers,
which the paid run writes with --fixture."""

import base64
import contextlib
import dataclasses
import importlib.machinery
import importlib.util
import io
import json
import shutil
import sys
import threading
import uuid
from pathlib import Path

import pytest

from conftest import CONTRAIL, FIXTURES, contrail_copy, forget, planned, told, words
from test_claude import KEY as CLAUDE_KEY, Claude, message
from test_screen_test import Page
from videotape import claude, frames, project
from videotape.checks import FRAMES, Cut
from videotape.claude import ClaudeJudge, ClaudeReader
from videotape.fal import Receipt
from videotape.model import MODELS
from videotape.plan import FromKey, Key, Mode
from videotape.standin import Flaw, StandIn, StandInEye, StandInJudge
from videotape.story import STATIC, text

ROOT = CONTRAIL.parent.parent
GEMINI = "gemini-omni-flash-1.2"
CLIPS = ROOT / "examples" / "surf_shop"
FIXTURE = FIXTURES / "recorded" / "moves" / "calibration.json"
"""Claude's recorded answers to the ten labelled clips, which the paid run writes with --fixture."""
BASES = {"home()": None, "search()": "home()", "trip(CT 100, 2026-12-18)": "home()", "my_trips()": "home()",
         "profile()": "home()", "no_flights(BOS)": "search()", "dates(HNL)": "search()",
         "results(HNL, 2026-12-11)": "dates(HNL)", "flight(CT 500, 2026-12-11)": "results(HNL, 2026-12-11)",
         "booked(CT 500, 2026-12-11)": "flight(CT 500, 2026-12-11)"}
"""Each base the twelve moves need, and the state it is first reached from, which rehearse draws it from."""
VARIANTS = ("dates(JFK)", "dates(SEA)", "results(JFK, 2026-12-11)", "results(SEA, 2026-12-12)",
            "results(SEA, 2026-12-13)", "flight(CT 300, 2026-12-12)", "booked(CT 300, 2026-12-12)")
REHEARSED_MOVES = (("home()", "search()"), ("home()", "my_trips()"), ("home()", "profile()"),
                   ("search()", "no_flights(BOS)"))
"""The moves under test that rehearse draws as a base's clip."""


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("moves_test", str(ROOT / "scripts" / "moves-test"))
    spec = importlib.util.spec_from_loader("moves_test", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def keyless(monkeypatch):
    for key in ("FAL_KEY", "ANTHROPIC_API_KEY", "RUNPOD_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def moves(script, directory: Path, *arguments: str) -> tuple[int, str, str]:
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


def calibration_line() -> str:
    if CLIPS.is_dir():
        return "calibration: 10 labelled clips under examples/surf_shop, their scene scores free, and 10 judgments"
    return "calibration: no clips folder at examples/surf_shop, so none"


def judgments() -> int:
    return 68 if CLIPS.is_dir() else 58


def judged_usd() -> float:
    moves_usd = 58 * claude.judge_estimate(1280, 720)
    if not CLIPS.is_dir():
        return moves_usd
    return moves_usd + 5 * claude.judge_estimate(1280, 704) + 5 * claude.judge_estimate(1280, 720)


ESTIMATE = [
    "moves test of contrail 0.1.0 in terminal and posters, on gemini-omni-flash-1.2, judged by claude-opus-5-5: 12 moves "
    "across 13 states",
    "pinned, terminal: 29 shots, 17 keys of which 0 rehearsed, 12 pinned moves; 29 to 58 calls, 12 judgments",
    "rehearse, terminal: 25 shots, 17 keys of which 9 rehearsed, 8 pinned moves; 25 to 50 calls, 17 judgments",
    "pinned, posters: 29 shots, 17 keys of which 0 rehearsed, 12 pinned moves; 29 to 58 calls, 12 judgments",
    "rehearse, posters: 25 shots, 17 keys of which 9 rehearsed, 8 pinned moves; 25 to 50 calls, 17 judgments",
]
READ = claude.estimate(1280, 720)
LEAST = 108 * 0.4395 + 68 * READ + judged_usd()
MOST = 216 * 0.4395 + 136 * READ + judged_usd()
BOTH = ("--stories", "terminal,posters")


def price_line() -> str:
    return (f"gemini-omni-flash-1.2: 108 to 216 calls, $47.47 to $94.93 at $0.0819/s plus $0.03 a call for the prompt, "
            f"68 to 136 reads by claude-opus-5-5 of 1280x720 pictures, at most ${68 * READ:.2f} to ${136 * READ:.2f}, "
            f"and {judgments()} judgments of {FRAMES} frames each by claude-opus-5-5, at most ${judged_usd():.2f}")


def test_the_estimate_counts_each_methods_shots_the_reads_and_the_judgments_and_needs_no_api_key(script, tmp_path,
                                                                                              monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = moves(script, directory, *BOTH, "--estimate")
    assert (code, err) == (0, "")
    assert out.splitlines() == [*ESTIMATE, calibration_line(), price_line(),
                                f"the moves test: 108 to 216 calls, at most ${LEAST:.2f} to ${MOST:.2f}, no cap"]
    assert 60 < LEAST < 70 and 120 < MOST < 130
    code, out, _ = moves(script, directory, *BOTH, "--estimate", "--cap-usd", "50")
    assert code == 0 and out.splitlines()[-1].endswith(f"at most ${LEAST:.2f} to ${MOST:.2f}, past the cap of $50.00 at the least")
    code, out, _ = moves(script, directory, *BOTH, "--estimate", "--model", "stand-in")
    assert code == 0 and out.splitlines()[-2:] == ["stand-in: 108 to 216 calls, free", "the moves test: 108 to 216 calls, free"]
    code, out, _ = moves(script, directory, "--stories", "terminal", "--estimate")
    assert code == 0 and out.splitlines()[1:3] == ESTIMATE[1:3] and "54 to 108 calls" in out.splitlines()[-1]
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


def test_the_twelve_moves_are_in_the_plan_and_a_move_the_plan_lacks_stops_the_test(script, monkeypatch):
    full = planned(CONTRAIL)
    chosen = script.selected(full)
    assert [(move.start.name, move.land.name) for move in chosen] == list(script.MOVES)
    monkeypatch.setattr(script, "MOVES", (*script.MOVES, ("home()", "booked(CT 300, 2026-12-12)")))
    with pytest.raises(script.ScreenplayError) as refused:
        script.selected(full)
    assert (refused.value.code, refused.value.place) == ("VT212", '"home() -> booked(CT 300, 2026-12-12)"')
    assert refused.value.message == "the app has no move between states of these names, and the moves test draws one"


def test_pinned_draws_the_bases_the_variants_and_the_moves_as_a_render_does(script):
    full = planned(CONTRAIL)
    drawn = script.cast(script.PINNED, full, script.selected(full))
    assert [key.state.name for key in drawn.keys if type(key) is Key] == list(BASES)
    assert [key.state.name for key in drawn.keys if isinstance(key, FromKey)] == list(VARIANTS)
    assert not script.rehearsals(drawn) and len(drawn.keys) == 17
    assert [(move.start.name, move.land.name) for move in drawn.moves] == list(script.MOVES)
    assert [key.state.name for key in drawn.keys] == [key.state.name for key in full.keys if key in drawn.keys]


def test_rehearse_draws_every_base_but_the_entry_as_the_move_that_first_reaches_it_and_pins_the_later_moves(script):
    full = planned(CONTRAIL)
    drawn = script.cast(script.REHEARSE, full, script.selected(full))
    rehearsed = script.rehearsals(drawn)
    assert {key.state.name: key.start.name for key in rehearsed} == {state: parent for state, parent in BASES.items() if parent}
    assert all((key.move.start, key.move.land) == (key.start, key.state) and key.mode is Mode.FIRST_FRAME for key in rehearsed)
    assert [key.title for key in rehearsed][:2] == ["key search() rehearsed from home()",
                                                     "key trip(CT 100, 2026-12-18) rehearsed from home()"]
    assert [key.state.name for key in drawn.keys if type(key) is Key] == ["home()"]
    assert [key.state.name for key in drawn.keys if type(key) is FromKey] == list(VARIANTS)
    assert len(drawn.keys) == 17 and len(drawn.moves) == 8
    assert [(move.start.name, move.land.name) for move in drawn.moves] == [
        pair for pair in script.MOVES if pair not in REHEARSED_MOVES]


def test_a_rehearsals_prompt_carries_the_moves_clauses_then_the_states_own_without_the_static_shot(script):
    full, terminal = planned(CONTRAIL), told(CONTRAIL, "terminal")
    [search] = [key for key in script.rehearsals(script.cast(script.REHEARSE, full, script.selected(full)))
                if key.state.name == "search()"]
    composed = script.composed(search, terminal)
    move, key = words(search.move, terminal), words(search.from_prompt(), terminal)
    assert text(composed) == f"{move} {script.ARRIVES.text} {key.removeprefix(STATIC.text + ' ')}"
    assert text(composed).startswith('The search bar "Where to?" is pressed. The slot lights up. The camera steps closer to '
                                     "the departure board. It ends held still on the next screen. A quiet international")
    assert "Static shot." not in text(composed) and text(composed).endswith("Sharp, legible lettering.")
    assert [str(clause.source) for clause in composed][:4] == ["screenplay home, SearchBar", "story moves.SearchBar",
                                                                "engine", "story look"]
    assert script.prompts(terminal)(search) == composed and script.prompts(terminal)(full.keys[0])[0] is STATIC


def test_a_least_past_the_cap_or_no_cap_stops_before_any_call_and_names_the_cap_the_test_needs(script, tmp_path,
                                                                                               monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    needed = f"{__import__('math').ceil(LEAST * 100) / 100:.2f}"
    code, out, err = moves(script, directory, *BOTH, "--cap-usd", "50")
    assert code == 1 and out.splitlines()[-1].endswith("past the cap of $50.00 at the least")
    assert err == (f"error VT402 before the first call: the moves test costs at least ${LEAST:.2f}, which passes the "
                   f"cap of $50.00\nnext: run it with a cap of at least ${needed}, as in:\nuv run scripts/moves-test "
                   f"{directory} --stories terminal,posters --cap-usd {needed}\n")
    code, _, err = moves(script, directory, *BOTH)
    assert code == 1 and err == ("error VT402 before the first call: gemini-omni-flash-1.2 and claude-opus-5-5 bill per "
                                 "call, and no cap is set\nnext: set the most the moves test may spend, as in:\n"
                                 f"uv run scripts/moves-test {directory} --stories terminal,posters --cap-usd {needed}\n")
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


def test_a_missing_api_key_stops_the_moves_test_before_any_call_as_vt104(script, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = moves(script, directory, *BOTH, "--cap-usd", "100")
    assert (code, err) == (1, "error VT104 .env: gemini-omni-flash-1.2 needs FAL_KEY, and it is not in the environment "
                              "or .env\nfix: copy .env.example to .env and set FAL_KEY there, or export it\n")
    assert out.splitlines()[:5] == ESTIMATE
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


class Gemini(StandIn):
    """A stand-in under gemini-omni-flash-1.2's name and price, which bills each call and takes a rehearsal's prompt as
    a real model is hoped to: the move's words as direction, so only the state's lines are lettered. The render films
    two shots at once, so it films one at a time to record each call with the prompt it was given."""

    device = "fal"

    def __init__(self, arrives: str):
        super().__init__(flaw=lambda mode, prompt, seed: Flaw.NONE)
        self.name, self.price, self.arrives = GEMINI, MODELS[GEMINI].price, arrives
        self.one_at_a_time = threading.Lock()

    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt:
        with self.one_at_a_time:
            super().text_to_video(prompt, seed, out)
        return self._receipt()

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> Receipt:
        with self.one_at_a_time:
            super().first_last_frame(prompt, start, end, seed, out)
        return self._receipt()

    def first_frame(self, prompt: str, start: Path, seed: int, out: Path) -> Receipt:
        with self.one_at_a_time:
            super().first_frame(prompt.partition(self.arrives)[2] or prompt, start, seed, out)
            self.calls[-1] = dataclasses.replace(self.calls[-1], prompt=prompt)
        return self._receipt()

    def _receipt(self) -> Receipt:
        return Receipt(f"{GEMINI}-{uuid.uuid4().hex}", self.price.seconds, self.price.usd, {})


class Judging(Claude):
    """Claude's fake network, which answers a read from the stand-in's eye and a judgment from the stand-in's judge."""

    def read(self, request):
        body = json.loads(request.data)
        images = [part for part in body["messages"][0]["content"] if part["type"] == "image"]
        if len(images) == 1:
            return super().read(request)
        pictures = [frames.png_frame(base64.b64decode(image["source"]["data"])) for image in images]
        verdict = StandInJudge().judge(list(enumerate(pictures)))
        answer = {"frames": [{"overlaid": overlaid, "seen": seen} for overlaid, seen in zip(verdict.overlaid, verdict.seen)]}
        return {**message(json.dumps(answer)), "id": f"msg_{uuid.uuid4().hex[:24]}"}


@dataclasses.dataclass
class Fakes:
    film: Gemini
    claude: Judging


def fake(patch: pytest.MonkeyPatch, script) -> Fakes:
    film = Gemini(script.ARRIVES.text)
    patch.setitem(MODELS, GEMINI, dataclasses.replace(MODELS[GEMINI], model=lambda: film,
                                                      readers=(StandInEye, ClaudeReader)))
    hosted = Judging()
    patch.setattr(claude, "_urlopen", hosted)
    patch.setenv("ANTHROPIC_API_KEY", CLAUDE_KEY)
    return Fakes(film, hosted)


RUN = (*BOTH, "--cap-usd", "140")
TAPES = [f"tapes/moves-test/{method}/{told}" for method in ("pinned", "rehearse") for told in ("terminal", "posters")]


@pytest.fixture(scope="module")
def tested(script, tmp_path_factory):
    """Contrail's moves test on the stand-in named gemini-omni-flash-1.2, run once for the tests that read it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(ROOT)
        fakes = fake(patch, script)
        directory = contrail_copy(tmp_path_factory.mktemp("tested") / "contrail")
        return directory, fakes, moves(script, directory, *RUN)


def copied(tested, to: Path) -> Path:
    return Path(shutil.copytree(tested[0], to / "contrail", ignore=shutil.ignore_patterns("__pycache__")))


def ledger_lines(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]


def report(directory: Path) -> tuple[str, Page]:
    page = (directory / "tapes" / "moves-test" / "report.html").read_text()
    return page, Page(page)


def test_it_draws_each_story_both_ways_judges_every_move_and_pays_for_each_call_read_and_judgment_under_one_cap(
        tested, script):
    """profile() shows two charts, which the stand-in does not draw and the fake Claude does not read, so its key
    fails VT504 under both methods in both stories and gets its second take."""
    directory, fakes, (code, out, err) = tested
    assert (code, err) == (0, "")
    calls = fakes.film.calls
    assert sorted(call.mode.value for call in calls) == ["first-and-last-frame"] * 40 + ["first-frame"] * 48 + ["text-to-video"] * 24
    retaken = [call for call in calls if call.seed == 2]
    assert sorted(call.mode.value for call in retaken) == ["first-frame"] * 2 + ["text-to-video"] * 2
    assert all("Flights per month in 2026" in call.prompt for call in retaken)
    assert {call.seed for call in calls} == {1, 2}
    rehearsed = [call for call in calls if script.ARRIVES.text in call.prompt]
    assert len(rehearsed) == 20 and all(call.mode is Mode.FIRST_FRAME for call in rehearsed)
    for told in ("terminal", "posters"):
        tape = directory / "tapes" / "moves-test" / "rehearse" / told
        starts = {call.start.name for call in rehearsed if call.start.is_relative_to(tape)}
        assert starts == {"home.png", "search.png", "dates-hnl.png", "results-hnl-2026-12-11.png", "flight-ct-500-2026-12-11.png"}
        assert (tape / "keys" / "search.png").is_file() and not (tape / "moves" / "home--where-to.mp4").exists()
        assert (directory / "tapes" / "moves-test" / "pinned" / told / "moves" / "home--where-to.mp4").is_file()
    lines = ledger_lines(directory)
    tapes = sorted({line["tape"] for line in lines})
    assert tapes == sorted([*TAPES, *(["tapes/moves-test/calibration"] if CLIPS.is_dir() else [])])
    kinds = {kind: [line for line in lines if line["kind"] == kind] for kind in ("take", "read", "judgment")}
    assert len(kinds["take"]) == 112 and {line["usd"] for line in kinds["take"]} == {0.4395}
    # profile()'s second take draws the same picture as its first, so its read is cached and 68 reads are paid.
    assert len(kinds["read"]) == 68 and len(kinds["judgment"]) == judgments()
    assert all(line["model"] == "claude-opus-5-5" and "shot" in line and "seed" in line for line in kinds["judgment"])
    assert sum(line["tape"] == "tapes/moves-test/calibration" for line in kinds["judgment"]) == (10 if CLIPS.is_dir() else 0)
    assert len(fakes.claude.seen) == 68 + judgments()
    assert sum(line["usd"] for line in lines) <= 140
    printed = out.splitlines()
    assert printed[:5] == ESTIMATE and printed[6] == price_line()
    if CLIPS.is_dir():
        assert (f"calibration: 10 labelled clips judged by claude-opus-5-5 -> {directory}/tapes/moves-test/calibration"
                in printed)
        assert any(line.startswith("1. tape/moves/entrance--browse-as-guest.mp4  labelled VT507, VT506 0.167 passed, VT507 ")
                   for line in printed)
    assert (f"pinned, terminal: 17 keys of which 0 rehearsed and 12 pinned moves, up to 2 takes each, read by stand-in and "
            f"claude-opus-5-5 -> {directory}/tapes/moves-test/pinned/terminal") in printed
    assert (f"rehearse, posters: 17 keys of which 9 rehearsed and 8 pinned moves, up to 2 takes each, read by stand-in and "
            f"claude-opus-5-5 -> {directory}/tapes/moves-test/rehearse/posters") in printed
    assert "pinned, terminal: 12 moves judged by claude-opus-5-5" in printed
    assert "rehearse, terminal: 17 moves judged by claude-opus-5-5" in printed
    judged = [line for line in printed if "  VT506 " in line and " overlaid, " in line]
    assert len(judged) == 58 and all(line.endswith(" judged") for line in judged)
    assert sum(" labelled VT50" in line and line.endswith(" judged") for line in printed) == judgments() - 58
    ending = printed[-4:] if CLIPS.is_dir() else printed[-3:]
    assert ending[0] == f"wrote {directory}/tapes/moves-test/report.html"
    if CLIPS.is_dir():
        assert ending[1].startswith("the calibration: VT506 agrees with the labels on 10 of 10 clips, VT507 on ")
    assert printed[-2].startswith("recommend for terminal: rehearse, ") and printed[-1].startswith("recommend for posters: rehearse, ")
    assert all("short of the bar at 0 of 12; 0 of 12 moves travel, 11 of 12 keys pass, $" in line for line in printed[-2:])
    assert sum("key profile()  kept take 1, fails VT504, 2 takes filmed" in line for line in printed) == 2
    assert sum("key profile() rehearsed from home()  kept take 1, fails VT504, 2 takes filmed" in line for line in printed) == 2


def test_run_again_it_films_nothing_reads_nothing_judges_nothing_and_writes_the_same_report(tested, script, tmp_path,
                                                                                            monkeypatch):
    directory = copied(tested, tmp_path)
    monkeypatch.chdir(ROOT)
    fakes = fake(monkeypatch, script)
    ledger_before = (directory / "ledger.jsonl").read_text()
    report_before = (directory / "tapes" / "moves-test" / "report.html").read_text()
    code, out, err = moves(script, directory, *RUN)
    assert (code, err) == (0, "")
    assert fakes.film.calls == [] and fakes.claude.seen == []
    assert (directory / "ledger.jsonl").read_text() == ledger_before
    assert (directory / "tapes" / "moves-test" / "report.html").read_text() == report_before
    assert sum(", cached, $0.00, 0.0 s" in line for line in out.splitlines()) == 108
    assert sum(line.endswith(" overlaid, cached") for line in out.splitlines()) == judgments()


def test_one_cap_holds_for_the_whole_moves_test_and_counts_what_its_other_tapes_spent(script, tmp_path, monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    monkeypatch.chdir(ROOT)
    fake(monkeypatch, script)
    earlier = {"kind": "judgment", "tape": "tapes/moves-test/rehearse/posters", "shot": "key search() rehearsed from "
               "home()", "seed": 9, "seconds": 0.0, "usd": 139.0, "request_id": "earlier"}
    (directory / "ledger.jsonl").write_text(json.dumps(earlier) + "\n")
    code, out, err = moves(script, directory, *RUN)
    assert code == 1
    assert err.startswith("error VT402 ") and "the next call would pass the moves test's cap of $140.00, with $" in err
    assert err.endswith("next: run the moves test again with a higher cap, which resumes, as in:\nuv run "
                        f"scripts/moves-test {directory} --stories terminal,posters --cap-usd 280.00\n")
    spent = sum(line.get("usd", 0.0) for line in ledger_lines(directory))
    assert 139 <= spent <= 140
    assert not (directory / "tapes" / "moves-test" / "report.html").exists()


def test_the_report_shows_each_move_under_each_method_with_its_frames_the_judges_answers_the_checks_and_its_key(tested):
    directory, _, _ = tested
    page, parsed = report(directory)
    stories = [section["data-story"] for section in parsed.all("section") if "data-story" in section]
    assert stories == ["terminal", "posters"]
    figures = [figure for figure in parsed.all("figure") if "data-move" in figure]
    assert len(figures) == 2 * (12 + 12 + 5)
    tested_figures = [figure for figure in figures if figure["data-tested"] == "yes"]
    assert len(tested_figures) == 48 and {figure["data-travels"] for figure in figures} == {"no"}
    failing_keys = [(figure["data-story"], figure["data-method"]) for figure in figures if figure["data-key-passed"] == "no"]
    assert sorted(failing_keys) == sorted((told, method) for told in ("terminal", "posters") for method in ("pinned", "rehearse"))
    assert all(figure["data-move"] == 'home() -> profile() "Profile"' for figure in figures if figure["data-key-passed"] == "no")
    assert sum(figure["data-rehearsed"] == "yes" for figure in tested_figures) == 8
    assert all(float(figure["data-usd"]) >= 0.44 for figure in figures)
    frames_shown = [figure for figure in parsed.all("figure") if "data-frame" in figure]
    assert len(frames_shown) == FRAMES * (len(figures) + (10 if CLIPS.is_dir() else 0))
    assert {figure["data-overlaid"] for figure in frames_shown} == {"yes", "no"}
    pictures = {attrs["src"] for attrs in parsed.all("img")}
    assert all((directory / "tapes" / "moves-test" / picture).is_file() for picture in pictures)
    assert all(not picture.startswith("/") for picture in pictures)
    assert "VT506 frame" in parsed.text and "VT507 frame" in parsed.text and "VT508 start" in parsed.text
    assert "A rehearsal: the key is this clip's last frame, so its end seam is 0 by construction" in parsed.text
    assert "It ends held still on the next screen." in parsed.text
    assert "two pictures overlaid, the first frame fading into the last" in parsed.text
    travel = {(cell["data-story"], cell["data-method"]): cell["data-travel"] for cell in parsed.all("td") if "data-travel" in cell}
    assert travel == {(told, method): "0 of 12" for told in stories for method in ("pinned", "rehearse")}
    picks = [(pick["data-story"], pick["data-recommend"], pick["data-bar"]) for pick in parsed.all("p") if "data-recommend" in pick]
    assert [(told, bar) for told, _, bar in picks] == [("terminal", "short"), ("posters", "short")]
    assert "The recommendation for terminal is " in parsed.text
    if CLIPS.is_dir():
        [calibration] = parsed.all("section", id="calibration")
        assert calibration["data-vt506"] == "10 of 10"
        labelled = {figure["data-clip"]: (figure["data-label"], figure["data-vt506"]) for figure in parsed.all("figure") if "data-label" in figure}
        assert len(labelled) == 10 and all(agrees == "agrees" for _, agrees in labelled.values())
        assert labelled["tape-wan3/moves/signup--sign-up.mp4"][0] == "VT506"
    else:
        assert "No labelled clips" in parsed.text
    assert "color-scheme: light dark" in page and "prefers-color-scheme: dark" in page
    assert "http://" not in page.replace("http://www.w3.org", "") and "<script" not in page
    assert "ffmpeg.org/ffmpeg-filters.html" in page


def test_the_report_counts_what_a_direction_change_draws_again_under_each_method(tested, script):
    """The search scene's direction is in search()'s own prompt alone, since search has no variant: under pinned it
    draws that key again and the moves that leave or land on it. Under rehearse search()'s clip is drawn from home's
    key with its own words, so it is drawn again, and with it every base first reached through it, every variant of
    those, and every move that touches any of them."""
    _, parsed = report(tested[0])
    counts = {(cell["data-story"], cell["data-method"]): (int(cell["data-keys"]), int(cell["data-moves"]))
              for cell in parsed.all("td") if "data-keys" in cell and "data-moves" in cell}
    full = planned(CONTRAIL)
    search = next(key.state for key in full.keys if key.state.name == "search()")
    touching = sum(search in (move.start, move.land) for move in full.moves)
    downstream = {"search", "not_found", "no_flights", "dates", "results", "flight", "booked"}
    keys = sum(key.state.scene.name in downstream for key in full.keys)
    moves_down = sum({move.start.scene.name, move.land.scene.name} & downstream != set() for move in full.moves)
    for told in ("terminal", "posters"):
        assert counts[told, "pinned"] == (1, touching)
        assert counts[told, "rehearse"] == (keys, moves_down) and keys > 40
    assert 'the direction of the search scene, "Up close at the departure board, where the destinations are listed." to ' \
           '"The same place, seen from a step further back."' in parsed.text


def test_the_recommendation_has_the_most_moves_travelling_then_the_most_keys_passing_then_the_lower_cost_then_fewer_redraws(
        script):
    standing, tally = script.Standing, script.Tally
    most = standing("terminal", "most", tally(11, 12), tally(8, 12), 30.0, 50, 90)
    fewer = standing("terminal", "fewer", tally(9, 12), tally(12, 12), 1.0, 1, 2)
    assert script.recommend([fewer, most]) is most and not most.meets_the_bar
    keys = standing("terminal", "keys", tally(11, 12), tally(12, 12), 40.0, 50, 90)
    assert script.recommend([most, keys, fewer]) is keys
    cheap = standing("terminal", "cheap", tally(11, 12), tally(12, 12), 20.0, 60, 90)
    assert script.recommend([keys, cheap]) is cheap
    steady = standing("terminal", "steady", tally(11, 12), tally(12, 12), 20.0, 10, 20)
    assert script.recommend([cheap, steady]) is steady
    assert standing("terminal", "bar", tally(12, 12), tally(12, 12), 50.0, 1, 1).meets_the_bar


# The calibration.

needs_clips = pytest.mark.skipif(not CLIPS.is_dir(), reason=f"the ten labelled clips are not at {CLIPS}")


@needs_clips
def test_the_cut_check_agrees_with_the_labels_on_the_ten_clips(script):
    """Run live: ffmpeg scores every frame of each clip. The three cuts score 0.319 and up, the dissolves 0.187 and
    under, and 0.3 parts them."""
    tops = {}
    for clip, fails in script.LABELS.items():
        cut = Cut(tuple(frames.scene_scores(CLIPS / clip)))
        tops[clip] = cut.top[1]
        assert cut.passed == (fails != "VT506"), f"{clip}: {cut.top}"
    assert max(score for clip, score in tops.items() if script.LABELS[clip] == "VT507") < 0.19
    assert min(score for clip, score in tops.items() if script.LABELS[clip] == "VT506") > 0.31


@needs_clips
@pytest.mark.skipif(not FIXTURE.is_file(), reason=f"no recorded answers at {FIXTURE}; the paid run writes them with "
                                                  "--fixture")
def test_the_dissolve_check_agrees_with_the_labels_on_claudes_recorded_answers(script, tmp_path, monkeypatch):
    """Replays the text of Claude's answers to the ten clips, which the paid run recorded, against frames sampled
    live. The answers hold only for the question they answered: a changed prompt or rule needs a new paid run."""
    recorded = json.loads(FIXTURE.read_text())
    assert recorded["test"] == "moves-test" and recorded["judge"] == "claude-opus-5-5"
    assert recorded["asked"] == claude.asked(), ("the judge's prompt, schema or settings changed since the answers were "
                                                 "recorded; run the paid calibration again with --fixture")
    monkeypatch.setenv("ANTHROPIC_API_KEY", CLAUDE_KEY)
    for clip, fails in script.LABELS.items():
        assert clip in recorded["clips"], f"no recorded answer for {clip}"
        judge = ClaudeJudge(tmp_path / clip, send=Claude(message(recorded["clips"][clip]["reply"])))
        verdict = judge.judge(frames.sampled(CLIPS / clip, FRAMES))
        assert verdict.passed == (fails != "VT507"), f"{clip}: {verdict.overlaid} {verdict.seen}"


@needs_clips
def test_the_fixture_flag_writes_the_judges_recorded_answers_to_the_labelled_clips_text_only(tested, script, tmp_path,
                                                                                            monkeypatch):
    directory = copied(tested, tmp_path)
    monkeypatch.chdir(ROOT)
    fakes = fake(monkeypatch, script)
    code, out, err = moves(script, directory, *RUN, "--fixture", str(tmp_path / "calibration.json"))
    assert (code, err) == (0, "") and fakes.claude.seen == []
    assert f"wrote {tmp_path / 'calibration.json'}: 10 recorded answers" in out.splitlines()
    held = json.loads((tmp_path / "calibration.json").read_text())
    assert (held["test"], held["judge"], held["asked"]) == ("moves-test", "claude-opus-5-5", claude.asked())
    assert sorted(held["clips"]) == sorted(script.LABELS)
    for clip, answer in held["clips"].items():
        assert set(answer) == {"model", "reply", "tokens", "usd"}
        assert len(json.loads(answer["reply"])["frames"]) == FRAMES and "data:" not in answer["reply"]
    code, _, err = moves(script, directory, *BOTH, "--model", "stand-in", "--fixture", str(tmp_path / "none.json"))
    assert code == 1 and err.startswith("error VT110 --fixture: holds claude-opus-5-5's answers, and stand-in's judge is stand-in")
