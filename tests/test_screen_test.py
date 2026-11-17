"""scripts/screen-test films eight keys of Contrail on each model, two takes each in each story, and picks the model
whose takes pass the checks for the most element types. No test sends a request: the models on fal are stand-ins
given fal's names and prices, and Claude answers from what the stand-in's eye reads, through a fake network, as in
tests/test_claude.py."""

import contextlib
import dataclasses
import importlib.machinery
import importlib.util
import io
import json
import math
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import pytest

from conftest import CONTRAIL, contrail_copy, forget
from test_claude import KEY as CLAUDE_KEY, Claude
from videotape import claude, project, qwen
from videotape.claude import ClaudeReader
from videotape.errors import ModelError
from videotape.fal import Price, Receipt
from videotape.model import MODELS
from videotape.plan import FromKey, Key, Mode
from videotape.standin import Flaw, StandIn, StandInEye

ROOT = CONTRAIL.parent.parent
THREE = "wan3.0,minimax-h3,gemini-omni-flash-1.2"
BOTH = "terminal,posters"
SAMPLER_STATES = ("home()", "search()", "dates(JFK)", "results(SEA, 2026-12-12)", "flight(CT 104, 2026-12-13)",
                  "booked(CT 300, 2026-12-11)", "my_trips()", "profile()")


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("screen_test", str(ROOT / "scripts" / "screen-test"))
    spec = importlib.util.spec_from_loader("screen_test", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def keyless(monkeypatch):
    for key in ("FAL_KEY", "ANTHROPIC_API_KEY", "RUNPOD_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def run(script, capsys, monkeypatch):
    """Run the script in this process from the repo's root, on a project, with Contrail's modules forgotten before
    and after so each copy is imported afresh."""
    def run(directory: Path, *arguments: str) -> tuple[int, str, str]:
        monkeypatch.chdir(ROOT)
        forget(project.find(directory))
        try:
            code = script.main([str(directory), *arguments])
        finally:
            forget(project.find(directory))
        out, err = capsys.readouterr()
        return code, out, err
    return run


def most() -> float:
    """What the screen test of the three models in both stories costs at most, from fal's price of a five-second call
    of each, $0.50, $0.30 and $0.4395, and the most a read by Claude of each one's picture costs: 32 calls and 32
    reads each."""
    wan, h3 = 32 * claude.estimate(1280, 720), 32 * claude.estimate(1344, 768)
    return 32 * 0.50 + wan + 32 * 0.30 + h3 + 32 * 0.4395 + wan


def test_the_estimate_prices_each_models_calls_and_its_reads_at_the_most_and_needs_no_api_key(run, tmp_path):
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = run(directory, "--models", THREE, "--stories", BOTH, "--estimate")
    assert (code, err) == (0, "")
    wan, h3 = 32 * claude.estimate(1280, 720), 32 * claude.estimate(1344, 768)
    total = most()
    assert out.splitlines() == [
        "screen test of contrail 0.1.0: 8 keys, 2 takes each, in terminal and posters, on wan3.0, minimax-h3 and "
        "gemini-omni-flash-1.2",
        f"wan3.0: 32 calls, $16.00 at $0.10/s, and 32 reads by claude-opus-5-5 of 1280x720 pictures, at most "
        f"${wan:.2f}; at most ${16 + wan:.2f} in all",
        f"minimax-h3: 32 calls, $9.60 at $0.06/s, and 32 reads by claude-opus-5-5 of 1344x768 pictures, at most "
        f"${h3:.2f}; at most ${9.60 + h3:.2f} in all",
        f"gemini-omni-flash-1.2: 32 calls, $14.06 at $0.0819/s plus $0.03 a call for the prompt, and 32 reads by "
        f"claude-opus-5-5 of 1280x720 pictures, at most ${wan:.2f}; at most ${14.064 + wan:.2f} in all",
        f"the screen test: 96 takes, at most ${total:.2f}, no cap",
    ]
    assert 50 < total < 60
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


def test_with_a_cap_the_estimate_says_whether_the_run_fits_under_it(run, tmp_path):
    directory = contrail_copy(tmp_path / "contrail")
    code, out, _ = run(directory, "--models", THREE, "--stories", BOTH, "--estimate", "--cap-usd", "60")
    assert code == 0 and out.splitlines()[-1].endswith(", under the cap of $60.00")
    code, out, _ = run(directory, "--models", "wan3.0", "--stories", "terminal", "--estimate", "--cap-usd", "5")
    assert code == 0 and out.splitlines()[-1] == (
        f"the screen test: 16 takes, at most ${8 + 16 * claude.estimate(1280, 720):.2f}, past the cap of $5.00")


def test_an_estimate_past_the_cap_stops_before_any_call_and_says_the_cap_the_run_needs(run, tmp_path):
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = run(directory, "--models", THREE, "--stories", BOTH, "--cap-usd", "50")
    assert code == 1 and out.splitlines()[-1] == f"the screen test: 96 takes, at most ${most():.2f}, past the cap of $50.00"
    needed = f"{math.ceil(most() * 100) / 100:.2f}"
    assert err == (
        f"error VT402 before the first call: the screen test may cost ${most():.2f}, which passes the cap of $50.00\n"
        f"next: run it with a cap of at least ${needed}, as in:\nuv run scripts/screen-test {directory} --models {THREE} "
        f"--stories {BOTH} --cap-usd {needed}\n")
    assert not (directory / "tapes").exists() and not (directory / "ledger.jsonl").exists()


def test_a_paid_run_without_a_cap_does_not_start(run, tmp_path):
    directory = contrail_copy(tmp_path / "contrail")
    code, _, err = run(directory, "--models", "minimax-h3", "--stories", "terminal")
    assert code == 1 and err.startswith(
        "error VT402 before the first call: minimax-h3 and claude-opus-5-5 bill per call, and no cap is set\nnext: set "
        "the most the screen test may spend, as in:\nuv run scripts/screen-test ")
    assert not (directory / "tapes").exists()


def test_a_missing_api_key_stops_the_screen_test_before_any_call_as_vt104(run, tmp_path, monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = run(directory, "--models", THREE, "--stories", BOTH, "--cap-usd", "60")
    assert (code, err) == (1, "error VT104 .env: wan3.0 needs FAL_KEY, and it is not in the environment or .env\n"
                              "fix: copy .env.example to .env and set FAL_KEY there, or export it\n")
    monkeypatch.setenv("FAL_KEY", "fal-test-key-0123456789abcdef")
    monkeypatch.setattr(qwen, "installed", lambda: True)
    code, out, err = run(directory, "--models", THREE, "--stories", BOTH, "--cap-usd", "60")
    assert (code, err) == (1, "error VT104 .env: claude-opus-5-5, a reader of this model's eye, needs ANTHROPIC_API_KEY,"
                              " and it is not in the environment or .env\nfix: copy .env.example to .env and set "
                              "ANTHROPIC_API_KEY there, or export it\n")
    assert not (directory / "tapes" / "screen-test" / "wan3.0" / "terminal" / "takes").exists()
    assert not (directory / "ledger.jsonl").exists()


def test_the_sampler_holds_every_element_type_of_contrail_and_a_state_the_plan_lacks_is_vt212(run, script, tmp_path,
                                                                                               monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    forget(project.find(directory))
    found = project.find(directory)
    from videotape.plan import plan
    planned = plan(found.load(), found.max_states)
    forget(found)
    sample = script.sampled(planned)
    assert [key.state.name for key in sample.keys] == list(script.SAMPLER) and sample.moves == ()
    # A sampled key is drawn from its own prompt, as the paid run drew it, whatever the plan draws its state from.
    assert all(type(key) is Key and key.mode is Mode.TEXT_TO_VIDEO for key in sample.keys)
    assert sum(isinstance(key, FromKey) for key in planned.keys if key.state.name in script.SAMPLER) == 4
    assert {element.type for key in sample.keys for element in key.shown} == {
        "Heading", "Text", "Button", "SearchBar", "DatePicker", "DateStrip", "List", "BarChart", "LineChart", "Tabs"}
    monkeypatch.setattr(script, "SAMPLER", (*script.SAMPLER[:2], "dates(JFX)"))
    code, out, err = run(directory, "--models", THREE, "--stories", BOTH, "--estimate")
    assert (code, out) == (1, "")
    assert err.startswith('error VT212 "dates(JFX)": the app has no state of this name, and the screen test films its '
                          "key\nfix: name one of the closest in SAMPLER in scripts/screen-test: dates(JFK), ")


class OnFal(StandIn):
    """A stand-in under the name of a model on fal, which bills that model's price for each call."""

    device = "fal"

    def __init__(self, name: str, price: Price, flaw):
        super().__init__(flaw=flaw)
        self.name, self.price = name, price

    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt:
        super().text_to_video(prompt, seed, out)
        return Receipt(f"{self.name}-{uuid.uuid4().hex}", self.price.seconds, self.price.usd, {})


FLAWS = {"wan3.0": lambda mode, prompt, seed: Flaw.NONE, "minimax-h3": None,
         "gemini-omni-flash-1.2": lambda mode, prompt, seed: Flaw.EXTRA_BOX}
"""wan3.0 draws every key clean, minimax-h3 carries the stand-in's own flaws at seeds 1 and 2, and
gemini-omni-flash-1.2 draws one control too many on every key."""


@dataclass
class Fakes:
    films: dict[str, OnFal]
    claude: Claude


def fake(patch: pytest.MonkeyPatch) -> Fakes:
    """fal's three models as stand-ins at their own prices, read by the stand-in's eye and by Claude, who answers
    from what the stand-in's eye reads, through a fake network. Claude reports no chart, so every chart fails VT504."""
    films = {name: OnFal(name, MODELS[name].price, flaw) for name, flaw in FLAWS.items()}
    for name, film in films.items():
        patch.setitem(MODELS, name, dataclasses.replace(MODELS[name], model=lambda film=film: film,
                                                        readers=(StandInEye, ClaudeReader)))
    hosted = Claude()
    patch.setattr(claude, "_urlopen", hosted)
    patch.setenv("ANTHROPIC_API_KEY", CLAUDE_KEY)
    return Fakes(films, hosted)


def screen(script, directory: Path, *arguments: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    forget(project.find(directory))
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = script.main([str(directory), *arguments])
    finally:
        forget(project.find(directory))
    return code, out.getvalue(), err.getvalue()


RUN = ("--models", THREE, "--stories", BOTH, "--cap-usd", "60")
TAPES = [f"tapes/screen-test/{name}/{told}" for name in THREE.split(",") for told in BOTH.split(",")]


@pytest.fixture(scope="module")
def screened(script, tmp_path_factory):
    """Contrail's screen test of the three stand-ins in both stories, run once for the tests that read it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(ROOT)
        fakes = fake(patch)
        directory = contrail_copy(tmp_path_factory.mktemp("screened") / "contrail")
        return directory, fakes, screen(script, directory, *RUN)


def copied(screened, to: Path) -> Path:
    return Path(shutil.copytree(screened[0], to / "contrail"))


def ledger_lines(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]


def test_it_films_both_takes_of_each_sampled_key_on_each_model_in_each_story_and_books_every_call(screened, script):
    directory, fakes, (code, out, err) = screened
    assert (code, err) == (0, "")
    for film in fakes.films.values():
        assert sorted(call.seed for call in film.calls) == [1] * 16 + [2] * 16
        assert {call.mode for call in film.calls} == {Mode.TEXT_TO_VIDEO}
    lines = ledger_lines(directory)
    assert len(fakes.claude.seen) == sum(line["kind"] == "read" for line in lines)
    assert sorted({line["tape"] for line in lines}) == sorted(TAPES)
    prices = {"wan3.0": 0.50, "minimax-h3": 0.30, "gemini-omni-flash-1.2": 0.4395}
    for tape in TAPES:
        takes = [line for line in lines if line["tape"] == tape and line["kind"] == "take"]
        reads = [line for line in lines if line["tape"] == tape and line["kind"] == "read"]
        assert sorted((line["shot"], line["seed"]) for line in takes) == sorted(
            (f"key {state}", seed) for state in script.SAMPLER for seed in (1, 2))
        assert {line["usd"] for line in takes} == {prices[tape.split("/")[2]]}
        assert {line["shot"] for line in reads} == {f"key {state}" for state in script.SAMPLER}
        record = json.loads((directory / tape / "dailies.json").read_text())
        assert [key["state"] for key in record["keys"]] == list(script.SAMPLER) and record["moves"] == []
        assert all([take["seed"] for take in key["takes"]] == [1, 2] for key in record["keys"])
    # A stand-in's two clean takes of a key are one picture, so Claude reads the second from the tape's cache.
    assert len([line for line in lines if line["tape"] == "tapes/screen-test/wan3.0/terminal" and line["kind"] == "read"]) == 8
    assert sum(line["usd"] for line in lines) <= 60
    spent = sum(line["usd"] for line in lines if line["tape"].startswith("tapes/screen-test/wan3.0/"))
    printed = out.splitlines()
    assert printed[5] == ("wan3.0 in terminal: 8 keys, 2 takes each, read by stand-in and claude-opus-5-5 -> "
                          f"{directory}/tapes/screen-test/wan3.0/terminal")
    # Two keys film at once, so they finish in any order.
    assert sorted(line.split("  ")[0] for line in printed[6:14]) == [
        f"{number}. key {state}" for number, state in enumerate(script.SAMPLER, 1)]
    assert all(", 2 takes filmed, $1.03, " in line for line in printed[6:14])
    assert printed[-3:] == [
        f"wrote {directory}/tapes/screen-test/report.html",
        f"pick: wan3.0, with 8 of 10 element types at the bar of 90% in every story, 112 of 120 elements passing every "
        f"check, 93.3%, 0 controls invented and ${spent:.2f} spent; the checks are not yet held to a person's marks, so mark wan3.0's terminal takes in the report and "
        "run again with --marks marks.json",
        f'to render with it, set model = "wan3.0" in [tool.videotape] in {directory}/pyproject.toml',
    ]


def test_run_again_it_films_nothing_reads_nothing_and_writes_the_same_report(screened, script, tmp_path, monkeypatch):
    directory = copied(screened, tmp_path)
    monkeypatch.chdir(ROOT)
    fakes = fake(monkeypatch)
    ledger_before = (directory / "ledger.jsonl").read_text()
    report_before = (directory / "tapes" / "screen-test" / "report.html").read_text()
    code, out, err = screen(script, directory, *RUN)
    assert (code, err) == (0, "")
    assert all(film.calls == [] for film in fakes.films.values()) and fakes.claude.seen == []
    assert (directory / "ledger.jsonl").read_text() == ledger_before
    assert (directory / "tapes" / "screen-test" / "report.html").read_text() == report_before
    assert sum(", cached, $0.00, 0.0 s" in line for line in out.splitlines()) == 48


def test_one_cap_holds_for_the_whole_screen_test_and_counts_what_its_other_tapes_spent(script, tmp_path, monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    monkeypatch.chdir(ROOT)
    fake(monkeypatch)
    earlier = {"kind": "take", "tape": "tapes/screen-test/wan3.0/posters", "shot": "key home()", "seed": 9,
               "seconds": 1.0, "usd": 15.0, "request_id": "earlier"}
    (directory / "ledger.jsonl").write_text(json.dumps(earlier) + "\n")
    code, out, err = screen(script, directory, "--models", "wan3.0", "--stories", BOTH, "--cap-usd", "22")
    assert code == 1
    assert err.startswith("error VT402 key ") and "the next call would pass the screen test's cap of $22.00, with $" in err
    assert err.endswith(f"next: run the screen test again with a higher cap, which resumes, as in:\nuv run "
                        f"scripts/screen-test {directory} --models wan3.0 --stories {BOTH} --cap-usd 44.00\n")
    spent = sum(line.get("usd", 0.0) for line in ledger_lines(directory))
    assert 15 + 5 < spent <= 22
    assert {line["tape"] for line in ledger_lines(directory)} == {"tapes/screen-test/wan3.0/posters",
                                                                  "tapes/screen-test/wan3.0/terminal"}
    assert not (directory / "tapes" / "screen-test" / "report.html").exists()


class Page(HTMLParser):
    """The report's tags with their attributes, and its text, as a person's browser reads it."""

    def __init__(self, text: str):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.words: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        if data.strip():
            self.words.append(" ".join(data.split()))

    def all(self, tag: str, **wanted: str) -> list[dict]:
        return [attrs for name, attrs in self.tags if name == tag and all(attrs.get(k) == v for k, v in wanted.items())]

    @property
    def text(self) -> str:
        return " ".join(self.words)


def report(directory: Path) -> tuple[str, Page]:
    text = (directory / "tapes" / "screen-test" / "report.html").read_text()
    return text, Page(text)


def test_the_report_tallies_each_element_type_on_each_model_in_each_story_by_check(screened):
    text, page = report(screened[0])
    cells = {(cell["data-type"], cell["data-model"], cell["data-story"]): cell["data-tally"]
             for cell in page.all("td") if "data-tally" in cell}
    kinds = ["Heading", "SearchBar", "List", "Text", "Tabs", "DatePicker", "DateStrip", "Button", "BarChart", "LineChart"]
    assert sorted({kind for kind, _, _ in cells}) == sorted(kinds)
    assert {(name, told) for _, name, told in cells} == {(n, t) for n in THREE.split(",") for t in BOTH.split(",")}
    per_take = {"Heading": 7, "SearchBar": 2, "List": 4, "Text": 8, "Tabs": 3, "DatePicker": 1, "DateStrip": 1,
                "Button": 2, "BarChart": 1, "LineChart": 1}
    for kind, count in per_take.items():
        expected = "0" if kind.endswith("Chart") else str(2 * count)
        assert cells[kind, "wan3.0", "terminal"] == f"{expected} of {2 * count}", kind
        assert cells[kind, "gemini-omni-flash-1.2", "posters"] == f"{expected} of {2 * count}", kind
    for code in ("VT501", "VT502", "VT504", "VT509"):
        assert page.all("span", **{"data-code": code}), code
    # Both readers report what is drawn marked, and only Claude reports charts.
    assert "VT504 0 of 2" in page.text and "VT509 12 of 12" in page.text
    assert "An element type meets its bar on a model when, in each story, at least 90% of its elements across " \
           "the model's 16 takes pass every check that judges them." in page.text


def test_the_report_counts_invented_controls_per_key_and_the_first_take_yield_with_each_takes_time_and_cost(screened,
                                                                                                         script):
    directory, _, _ = screened
    _, page = report(directory)
    invented = {(cell["data-key"], cell["data-model"], cell["data-story"]): cell["data-invented"]
                for cell in page.all("td") if "data-invented" in cell}
    for state in script.SAMPLER:
        assert invented[state, "wan3.0", "terminal"] == "0, 0"
        assert invented[state, "gemini-omni-flash-1.2", "posters"] == "2, 2"
    yields = {(cell["data-model"], cell["data-story"]): cell["data-yield"] for cell in page.all("td") if "data-yield" in cell}
    assert yields["wan3.0", "terminal"] == "7 of 8" and yields["gemini-omni-flash-1.2", "terminal"] == "0 of 8"
    figures = page.all("figure", **{"data-model": "wan3.0", "data-story": "terminal"})
    assert len(figures) == 16 and sorted(figure["data-usd"] for figure in figures) == ["0.50"] * 8 + ["0.53"] * 8
    assert all(float(figure["data-seconds"]) > 0 for figure in figures)


def test_the_report_shows_every_take_with_its_picture_and_its_checks_the_models_side_by_side(screened, script):
    directory, _, _ = screened
    text, page = report(directory)
    keys = [section for section in page.all("section") if "data-key" in section]
    assert [(key["data-story"], key["data-key"]) for key in keys] == [
        (told, state) for told in BOTH.split(",") for state in script.SAMPLER]
    figures = page.all("figure")
    taken = [(f["data-story"], f["data-key"], f["data-model"], f["data-seed"]) for f in figures if "data-seed" in f]
    assert taken[:6] == [("terminal", "home()", name, seed) for name in THREE.split(",") for seed in ("1", "2")]
    assert len(taken) == 96
    pictures = {attrs["src"] for attrs in page.all("img")}
    assert len(pictures) == 96
    assert all((directory / "tapes" / "screen-test" / picture).is_file() for picture in pictures)
    assert all(picture.endswith(".png") and not picture.startswith("/") for picture in pictures)
    records = [json.loads((directory / tape / "dailies.json").read_text()) for tape in TAPES]
    items = [item for record in records for key in record["keys"] for take in key["takes"] for item in take["items"]]
    assert text.count('<li class="pass">') == sum(item["passed"] for item in items)
    assert text.count('<li class="fail">') == sum(not item["passed"] for item in items) > 0
    assert "VT503 Not in the script" in page.text
    assert "color-scheme: light dark" in text and "prefers-color-scheme: dark" in text
    assert "http://" not in text.replace("http://www.w3.org", "") and "<script src" not in text


def test_the_report_names_the_pick_why_and_each_element_type_no_model_brings_to_the_bar(screened):
    _, page = report(screened[0])
    [pick] = page.all("section", id="pick")
    assert pick["data-pick"] == "wan3.0"
    assert ("The pick is wan3.0: 8 of 10 element types at the bar in every story, 112 of 120 of its elements pass "
            "every check, 93.3%, 0 controls invented.") in page.text
    # gemini-omni-flash-1.2's extra box is a control both readers see, on each of its 32 takes.
    assert "gemini-omni-flash-1.2 brings 8 to the bar too, and invents 64 controls where wan3.0 invents 0." in page.text
    assert "BarChart misses the bar on every model; its best is 0 of 2 on wan3.0" in page.text
    assert "LineChart misses the bar on every model; its best is 0 of 2 on wan3.0" in page.text
    assert 'set model = "wan3.0" in [tool.videotape]' in page.text


def test_the_report_names_the_sources_for_the_choice_of_models_with_their_dates(screened):
    _, page = report(screened[0])
    for source, date in (("VTR-Bench", "2026-10-01"), ("VidScribe", "2026-09-30"), ("TextVBench", "2026-10-09"),
                         ("Artificial Analysis", "read 2026-11-15"), ("MiniMax H3 vs. MiniMax H3 Max", "2026-09-01"),
                         ("fal's concurrency limits", "read 2026-11-15"), ("fal queue OpenAPI schemas", "read 2026-11-15")):
        assert f"{source}" in page.text and date in page.text, source
    assert "https://arxiv.org/html/2610.01499" in {link["href"] for link in page.all("a")}


def marks_of(directory: Path, script, right) -> dict:
    """A mark for each element of each of wan3.0's terminal takes, drawn right as right(state, kind, place) says."""
    record = json.loads((directory / "tapes" / "screen-test" / "wan3.0" / "terminal" / "dailies.json").read_text())
    forget(project.find(directory))
    found = project.find(directory)
    from videotape.plan import plan
    keys = {key.state.name: key for key in plan(found.load(), found.max_states).keys}
    forget(found)
    return {"model": "wan3.0", "story": "terminal", "marks": [
        {"state": key["state"], "seed": take["seed"], "clip": take["clip"], "element": place, "type": element.type,
         "right": right(key["state"], element.type, place)}
        for key in record["keys"] for take in key["takes"] for place, element in enumerate(keys[key["state"]].shown)]}


def test_the_calibration_lists_each_element_of_wan3s_terminal_takes_with_a_checkbox_and_downloads_them(screened):
    text, page = report(screened[0])
    boxes = page.all("input", type="checkbox")
    assert len(boxes) == 60
    assert {(box["data-state"], box["data-seed"]) for box in boxes} == {
        (state, seed) for state in SAMPLER_STATES for seed in ("1", "2")}
    assert all(box["data-clip"].startswith("takes/") and box["data-place"].isdigit() for box in boxes)
    assert page.all("button", id="download") and 'download = "marks.json"' in text
    assert "drawn right" in page.text


def test_marks_that_agree_with_the_checks_keep_the_pick_and_list_each_disagreement(screened, script, tmp_path,
                                                                                    monkeypatch):
    directory = copied(screened, tmp_path)
    monkeypatch.chdir(ROOT)
    fake(monkeypatch)
    marks = marks_of(directory, script, lambda state, kind, place: not (kind.endswith("Chart") or
                                                                      (state, place) == ("home()", 0)))
    (tmp_path / "marks.json").write_text(json.dumps(marks))
    code, out, err = screen(script, directory, "--models", THREE, "--stories", BOTH, "--marks",
                            str(tmp_path / "marks.json"), "--cap-usd", "60")
    assert (code, err) == (0, "")
    assert out.splitlines()[-3] == "the checks agree with a person's marks on 58 of 60 elements, 96.7%"
    assert out.splitlines()[-2].startswith("pick: wan3.0, with 8 of 10 element types at the bar of 90% in every story")
    _, page = report(directory)
    assert "The checks agree with a person's marks on 58 of 60 elements, 96.7%." in page.text
    assert "Heading 12 of 14, 85.7%" in page.text and "BarChart 2 of 2, 100.0%" in page.text
    assert "home() take 1, Heading \"Good morning, Alex\": marked not drawn right, and every check of it passes" \
           in page.text
    checked = {(box["data-state"], box["data-seed"], box["data-place"]) for box in page.all("input", type="checkbox")
               if "checked" in box}
    assert ("home()", "1", "1") in checked and ("home()", "1", "0") not in checked


def test_marks_that_agree_with_the_checks_less_than_90_percent_withhold_the_pick(screened, script, tmp_path,
                                                                                 monkeypatch):
    directory = copied(screened, tmp_path)
    monkeypatch.chdir(ROOT)
    fake(monkeypatch)
    marks = marks_of(directory, script, lambda state, kind, place: kind not in ("Heading", "BarChart", "LineChart"))
    (tmp_path / "marks.json").write_text(json.dumps(marks))
    code, out, err = screen(script, directory, "--models", THREE, "--stories", BOTH, "--marks",
                            str(tmp_path / "marks.json"), "--cap-usd", "60")
    assert (code, err) == (0, "")
    assert out.splitlines()[-2:] == [
        "the checks agree with a person's marks on 46 of 60 elements, 76.7%",
        "no pick: below 90%, the checks must be fixed before the pick",
    ]
    _, page = report(directory)
    [pick] = page.all("section", id="pick")
    assert "data-pick" not in pick
    assert "The checks agree with a person's marks on 46 of 60 elements, 76.7%, below 90%: fix the checks before " \
           "the pick. The pick is withheld." in page.text
    assert "Heading 0 of 14, 0.0%" in page.text


@pytest.mark.parametrize("marks, said", [
    ("not json", "is not JSON"),
    (json.dumps({"model": "minimax-h3", "story": "terminal", "marks": []}), "holds marks of minimax-h3's terminal takes"),
    (json.dumps({"model": "wan3.0", "story": "terminal", "marks": [{"state": "home()"}]}),
     "holds an entry that is not a mark"),
])
def test_a_marks_file_that_is_not_the_reports_says_so_and_films_nothing(script, tmp_path, capsys, marks, said):
    (tmp_path / "marks.json").write_text(marks)
    with pytest.raises(SystemExit) as stopped:
        script.main([str(tmp_path), *RUN, "--marks", str(tmp_path / "marks.json")])
    err = capsys.readouterr().err
    assert stopped.value.code == 2 and f"argument --marks: {tmp_path / 'marks.json'} {said}" in err
    assert "download it again from the report's Download marks.json button" in err


class RefusingOnFal(OnFal):
    """wan3.0 refusing the takes of its seeds for their content, as fal's content checker does, on every prompt or
    on the one prompt given."""

    def __init__(self, seeds: set[int], prompt: str | None = None):
        super().__init__("wan3.0", MODELS["wan3.0"].price, FLAWS["wan3.0"])
        self.refused, self.prompt = seeds, prompt

    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt:
        if seed in self.refused and self.prompt in (None, prompt):
            raise ModelError(f"request r-{seed} was refused for its content: HTTP 422 content_policy_violation, "
                             "model_moderated", "VT409", "nothing; a render skips the take's seed from now on")
        return super().text_to_video(prompt, seed, out)


def refusing(monkeypatch, film: RefusingOnFal) -> None:
    monkeypatch.chdir(ROOT)
    fake(monkeypatch)
    monkeypatch.setitem(MODELS, "wan3.0", dataclasses.replace(MODELS["wan3.0"], model=lambda: film))


def taken(script, directory: Path) -> list:
    found = project.find(directory)
    keys = script.sampled(script.plan(found.load(), found.max_states)).keys
    return script.gathered(directory, keys, {("wan3.0", "terminal"): directory / "tapes/screen-test/wan3.0/terminal"})


WAN3_TERMINAL = ("--models", "wan3.0", "--stories", "terminal", "--cap-usd", "60")


def test_a_refused_take_shows_as_refused_fails_the_first_take_and_counts_its_elements_not_drawn_right(script, tmp_path,
                                                                                                      monkeypatch):
    refusing(monkeypatch, RefusingOnFal({1}))
    directory = contrail_copy(tmp_path / "contrail")
    code, out, err = screen(script, directory, *WAN3_TERMINAL)
    assert code == 0 and err.count("error VT409 ") == 8, err
    report = (directory / "tapes" / "screen-test" / "report.html").read_text()
    assert report.count('<span class="badge failing">refused VT409</span>') == 8
    assert '<td data-model="wan3.0" data-story="terminal" data-yield="0 of 8">0 of 8</td>' in report
    refused = [take for take in taken(script, directory) if take.refused]
    assert [take.seed for take in refused] == [1] * 8 and not any(take.passed for take in refused)
    assert all(not element.passed for take in refused for element in take.elements)
    assert [take.usd for take in refused] == [MODELS["wan3.0"].price.usd] * 8

    again = screen(script, directory, *WAN3_TERMINAL)
    assert again[0] == 0 and "VT409" not in again[2]
    assert [take.seed for take in taken(script, directory) if take.refused] == [1] * 8
    assert (directory / "tapes" / "screen-test" / "report.html").read_text().count("refused VT409</span>") == 8


def test_a_key_whose_both_takes_are_refused_still_has_its_report_with_both_counted_against_the_model(script, tmp_path,
                                                                                                     monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    found = project.find(directory)
    sample = script.sampled(script.plan(found.load(), found.max_states))
    from videotape import story
    from videotape.story import prompt, text
    first = text(prompt(sample.keys[0], story.named(directory, "terminal")))
    forget(found)
    refusing(monkeypatch, RefusingOnFal({1, 2}, first))
    code, out, err = screen(script, directory, *WAN3_TERMINAL)
    assert code == 0 and (f"error VT409 {sample.keys[0].title}: every take of the shot was refused for its content\n"
                          "next: nothing; the tape's other keys are filmed, and the report counts 2 refused takes against "
                          "wan3.0\n") in err, err
    refused = [take for take in taken(script, directory) if take.refused]
    assert [(take.state, take.seed) for take in refused] == [(sample.keys[0].state.name, 1),
                                                             (sample.keys[0].state.name, 2)]
    assert len([take for take in taken(script, directory) if not take.refused]) == 14
    assert (directory / "tapes" / "screen-test" / "report.html").is_file()


class GarblingOnFal(RefusingOnFal):
    """wan3.0 writing a file that is not a clip for every take of one prompt, with nothing to download again."""

    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt:
        if prompt == self.prompt:
            out.write_bytes(b"not a clip")
            return Receipt(f"wan3.0-{seed}", self.price.seconds, self.price.usd, {})
        return super().text_to_video(prompt, seed, out)


def test_a_key_whose_both_takes_are_corrupt_names_a_next_step_that_films_it_anew_when_followed(script, tmp_path,
                                                                                               monkeypatch):
    directory = contrail_copy(tmp_path / "contrail")
    found = project.find(directory)
    sample = script.sampled(script.plan(found.load(), found.max_states))
    from videotape import story
    from videotape.story import prompt, text
    first = text(prompt(sample.keys[0], story.named(directory, "terminal")))
    forget(found)
    refusing(monkeypatch, GarblingOnFal(set(), first))
    code, out, err = screen(script, directory, *WAN3_TERMINAL)
    assert code == 1 and err.endswith(
        f"error VT403 {sample.keys[0].title}: every take of the shot is corrupt\n"
        "next: the screen test films only seeds 1 and 2, and neither decoded; delete each clip the lines above name, "
        "with the files beside it that share its name, and run the screen test again, which films those seeds anew:\n"
        f"uv run scripts/screen-test {directory} --models wan3.0 --stories terminal --cap-usd 60.00\n"), err
    clips = re.findall(r" take \d: (\S+\.mp4) did not decode", err)
    assert len(clips) == 2
    for clip in clips:
        for beside in Path(clip).parent.glob(f"{Path(clip).stem}.*"):
            beside.unlink()
    refusing(monkeypatch, RefusingOnFal(set()))
    code, out, err = screen(script, directory, *WAN3_TERMINAL)
    assert code == 0 and "VT403" not in err, err


def test_the_pick_has_the_most_types_at_the_bar_then_the_most_elements_passing_then_the_fewest_invented_controls_then_the_lowest_cost(script):
    standing, tally = script.Standing, script.Tally
    most = standing("most", frozenset({"Heading", "Text", "List"}), tally(60, 120), invented=9, usd=30.0)
    fewer = standing("fewer", frozenset({"Heading", "Text"}), tally(110, 120), invented=0, usd=1.0)
    assert script.pick([fewer, most]) is most
    plain = standing("plain", frozenset({"Heading", "Text", "List"}), tally(60, 120), invented=2, usd=30.0)
    assert script.pick([most, plain, fewer]) is plain
    cheap = standing("cheap", frozenset({"Heading", "Text", "List"}), tally(60, 120), invented=2, usd=12.5)
    assert script.pick([most, plain, cheap]) is cheap


def test_while_no_type_meets_the_bar_the_pick_is_the_model_whose_elements_pass_most_whatever_it_invents(script):
    standing, tally = script.Standing, script.Tally
    sparse = standing("sparse", frozenset(), tally(66, 120), invented=17, usd=10.43)
    drawn = standing("drawn", frozenset(), tally(95, 120), invented=82, usd=15.05)
    assert script.pick([sparse, drawn]) is drawn


@pytest.mark.parametrize("passed, of, met", [(9, 10, True), (18, 20, True), (17, 20, False), (0, 0, False)])
def test_an_element_type_meets_its_bar_at_90_percent_of_its_elements(script, passed, of, met):
    assert script.BAR == 0.9 and script.Tally(passed, of).met is met
