import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

import videotape as vt
from conftest import CONTRAIL, as_explained, copy_of, planned, told, words
from videotape import dailies, frames, ledger, project
from videotape.checks import MAX_DIFFERENCE
from videotape.errors import ModelError, RenderError
from videotape.fal import Price, Receipt
from videotape.ledger import Ledger
from videotape.made import made
from videotape.model import MODELS, Listing
from videotape.plan import Mode, Plan, plan
from videotape.render import render
from videotape.standin import EXTRA, Flaw, StandIn, StandInEye

STATES = ("menu()", "order(Espresso)", "order(Latte)", "thanks(Espresso)", "thanks(Latte)")
KEYS = {"menu()": "menu", "order(Espresso)": "order-espresso", "order(Latte)": "order-latte",
        "thanks(Espresso)": "thanks-espresso", "thanks(Latte)": "thanks-latte"}
MOVES = {"menu--espresso": "order(Espresso)", "menu--latte": "order(Latte)", "order-espresso--order": "thanks(Espresso)",
         "order-latte--order": "thanks(Latte)", "thanks-espresso--done": "menu()", "thanks-latte--done": "menu()"}
TITLES = ["key menu()", "key order(Espresso)", "key order(Latte)", "key thanks(Espresso)", "key thanks(Latte)",
          'menu() -> order(Espresso) "Espresso, $3"', 'menu() -> order(Latte) "Latte, $5"',
          'order(Espresso) -> thanks(Espresso) "Order"', 'order(Latte) -> thanks(Latte) "Order"',
          'thanks(Espresso) -> menu() "Done"', 'thanks(Latte) -> menu() "Done"']
WORDS = {
    "menu()": ["Corner Cafe", "Drinks", "Espresso", "$3", "Latte", "$5"],
    "order(Espresso)": ["Espresso", "$3", "Order"],
    "order(Latte)": ["Latte", "$5", "Order"],
    "thanks(Espresso)": ["Thanks", "One Espresso coming up.", "Done"],
    "thanks(Latte)": ["Thanks", "One Latte coming up.", "Done"],
}
"""Every string the cafe's screenplay puts on screen in each state, in reading order, written out by hand."""
THANKS_LATTE = '"One Latte coming up."'
DONE = 'The button "Done" is pressed.'
LINE = re.compile(r"(\d+)\. (.*)  kept take (\d+), (passed|fails [VT0-9 ]+), (\d+ takes? filmed|cached), \$(\d+\.\d\d), \d+\.\d s")


def flaws(mode: Mode, prompt: str, seed: int) -> Flaw:
    """thanks(Latte) carries a misspelt line at seed 1 and a missing one at seed 2, and both Done moves a wrong start
    at seed 1 and a wrong end at seed 2. Every other shot passes at seed 1."""
    if THANKS_LATTE in prompt:
        return {1: Flaw.MISSPELL, 2: Flaw.DROP_LINE}.get(seed, Flaw.NONE)
    if DONE in prompt:
        return {1: Flaw.WRONG_START, 2: Flaw.WRONG_END}.get(seed, Flaw.NONE)
    return Flaw.NONE


def clean(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.NONE


def stand_in(model: StandIn, **listing) -> Listing:
    return Listing(lambda: model, (StandInEye,), kind=model, **listing)


class Witness(StandIn):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.existed: list[bool] = []

    def first_last_frame(self, prompt, start, end, seed, out):
        self.existed += [start.is_file(), end.is_file()]
        super().first_last_frame(prompt, start, end, seed, out)


TAPE = "tapes/chalk"
RENDER = ("render", "--story", "chalk")


def rendered(directory: Path, model, takes: int = 4, out: str = TAPE, **more):
    chalk = told(directory)
    return render(planned(directory), chalk, model, [StandInEye()], directory / out, ledger.of(directory, directory / out),
                  made(project.find(directory), chalk, model), takes=takes, **more)


def lines(out: str) -> list[tuple[int, str, int, str, str, str]]:
    """The shot lines of a render's output, without their times."""
    found = [LINE.fullmatch(line) for line in out.splitlines()]
    return [(int(m[1]), m[2], int(m[3]), m[4], m[5], m[6]) for m in found if m]


@pytest.fixture(scope="module")
def first(tmp_path_factory):
    directory = copy_of("cafe", tmp_path_factory.mktemp("first"))
    model = Witness(flaw=flaws)
    return directory, model, rendered(directory, model)


def again(first, tmp_path: Path, old: str | None = None, new: str | None = None) -> Path:
    """A copy of the rendered cafe, with one piece of its screenplay rewritten when asked."""
    directory = Path(shutil.copytree(first[0], tmp_path / "cafe", ignore=shutil.ignore_patterns("__pycache__")))
    if old is not None:
        screenplay = directory / "cafe.py"
        source = screenplay.read_text()
        assert source.count(old) == 1
        screenplay.write_text(source.replace(old, new))
    return directory


def tape_files(directory: Path) -> dict[str, bytes]:
    tape = directory / TAPE
    return {path.name: path.read_bytes() for path in [tape / "tape.json", *sorted((tape / "keys").iterdir())]}


def test_every_key_is_filmed_before_any_move_and_a_shot_stops_at_the_first_take_that_passes(first):
    directory, model, result = first
    plan, chalk = planned(directory), told(directory)
    assert [shot.title for shot in plan.shots] == TITLES
    expected = [(shot, seed) for shot in plan.shots
                for seed in (range(1, 4) if THANKS_LATTE in words(shot, chalk) or DONE in words(shot, chalk) else [1])]
    # A move is filmed once both of its keys are, so with one worker the moves come in the order they became ready.
    assert sorted((call.mode.value, call.prompt, call.seed) for call in model.calls) == sorted(
        (shot.mode.value, words(shot, chalk), seed) for shot, seed in expected)
    assert [(call.prompt, call.seed) for call in model.calls[:7]] == [
        (words(shot, chalk), seed) for shot, seed in expected[:7]]
    assert [filmed.rendered for filmed in result.shots] == [1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 3]
    assert model.calls[0].prompt == (
        "Static shot. A chalkboard behind the counter of a small corner cafe, lettered by hand in white chalk. Warm "
        "light from the left, and a strip of pale wood along the bottom edge. The whole board, seen from across the "
        'counter. Large chalk letters across the top of the board, reading "Corner Cafe". Chalk lines, one per row, '
        'with a dotted line from each name to its price, reading "Drinks"; "Espresso" and "$3"; and "Latte" and "$5". '
        "Sharp, legible lettering.")
    assert model.calls[-1].prompt == ('The button "Done" is pressed. The chalk box is rubbed out. The camera pulls '
                                      "back from the board.")
    assert [call.mode for call in model.calls] == [Mode.TEXT_TO_VIDEO] * 7 + [Mode.FIRST_AND_LAST_FRAME] * 10
    keys = directory / TAPE / "keys"
    pinned = {(words(move, chalk), keys / f"{KEYS[move.start.name]}.png", keys / f"{KEYS[move.land.name]}.png")
              for move in plan.moves}
    for call in model.calls:
        if call.mode is Mode.FIRST_AND_LAST_FRAME:
            assert (call.prompt, call.start, call.end) in pinned
        else:
            assert (call.start, call.end) == (None, None)
    assert model.existed == [True] * 20


def test_the_tape_has_one_scene_for_each_state_with_its_words_its_hotspots_and_its_moves(first):
    data = json.loads((first[0] / TAPE / "tape.json").read_text())
    assert data["size"] == {"width": 1280, "height": 704}
    assert data["fps"] == 24
    assert data["opening"] == {"clip": "moves/opening.mp4", "lands": "menu()"}
    assert {name: scene["key"] for name, scene in data["scenes"].items()} == {
        state: f"keys/{name}.png" for state, name in KEYS.items()}
    assert {name: scene["words"] for name, scene in data["scenes"].items()} == WORDS
    assert {name: [(h["label"], h["move"]) for h in scene["hotspots"]] for name, scene in data["scenes"].items()} == {
        "menu()": [("Espresso, $3", "menu--espresso"), ("Latte, $5", "menu--latte")],
        "order(Espresso)": [("Order", "order-espresso--order")],
        "order(Latte)": [("Order", "order-latte--order")],
        "thanks(Espresso)": [("Done", "thanks-espresso--done")],
        "thanks(Latte)": [("Done", "thanks-latte--done")],
    }
    assert all(set(scene) == {"key", "words", "hotspots"} for scene in data["scenes"].values())
    assert data["moves"] == {move: {"clip": f"moves/{move}.mp4", "lands": lands} for move, lands in MOVES.items()}


def test_a_states_words_are_what_its_scene_shows_in_reading_order(tmp_path):
    """Contrail's words, computed by calling each scene and reading its elements, without the plan or the render."""
    directory = Path(shutil.copytree(CONTRAIL, tmp_path / "contrail", ignore=shutil.ignore_patterns(
        ".venv", "tape*", "ledger.jsonl", "__pycache__")))
    terminal, model, tape = told(directory, "terminal"), StandIn(flaw=clean), directory / "tapes" / "terminal"
    render(planned(directory), terminal, model, [StandInEye()], tape, ledger.of(directory, tape),
           made(project.find(directory), terminal, model), takes=1, limit=8)
    data = json.loads((tape / "tape.json").read_text())
    app = project.find(directory).load()
    scenes = {scene.name: scene for scene in app.scenes}
    checked = 0
    for name, scene in data["scenes"].items():
        called = scenes[name.partition("(")[0]]
        state = next(key.state for key in planned(directory).keys if key.state.name == name)
        expected = [line.words for element in called.build(*state.args) for line in element.show(state).lines]
        assert scene["words"] == expected, name
        checked += 1
    assert checked == 58
    assert data["scenes"]["home()"]["words"] == [
        "Good morning, Alex", "Where to?", "Your next trip", "San Francisco to New York", "Friday, December 18",
        "48,250 Contrail Miles", "Home", "Trips", "Profile"]
    search = data["scenes"]["search()"]["search"]
    assert search["bar"] == "Where to?"
    assert [option["label"] for option in search["options"]] == [
        "Boston (BOS)", "Chicago (ORD)", "Honolulu (HNL)", "Los Angeles (LAX)", "New York (JFK)", "Seattle (SEA)"]
    assert {option["move"] for option in search["options"]} <= set(data["moves"])
    assert data["moves"][search["options"][-1]["move"]]["lands"] == "dates(SEA)"
    assert search["no_match"] == {"move": "search--where-to", "lands": "not_found()"}
    assert [name for name, scene in data["scenes"].items() if "search" in scene] == ["search()"]


def test_a_search_bar_without_options_or_without_a_no_match_offers_no_search(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.videotape]\nscreenplay = "bars:app"\nmodel = "stand-in"\n')
    (tmp_path / "bars.py").write_text(
        'import videotape as vt\n\napp = vt.Screenplay("Bars")\n\n\n@app.scene\ndef home():\n'
        '    return [vt.SearchBar("Find", to=plain()), vt.Button("Pick", to=picking())]\n\n\n@app.scene\ndef plain():\n'
        '    return [vt.Heading("Plain")]\n\n\n@app.scene\ndef picking():\n'
        '    return [vt.SearchBar("Pick one", options=[vt.Option("A", to=home()), vt.Option("B", to=home())])]\n')
    (tmp_path / "stories").mkdir()
    (tmp_path / "stories" / "bare.toml").write_text('version = "1.0.0"\nlook = "A bare room."\n')
    chalk, model = told(tmp_path, "bare"), StandIn(flaw=clean)
    render(planned(tmp_path), chalk, model, [StandInEye()], tmp_path / "tapes" / "bare",
           ledger.of(tmp_path, tmp_path / "tapes" / "bare"), made(project.find(tmp_path), chalk, model), takes=1)
    data = json.loads((tmp_path / "tapes" / "bare" / "tape.json").read_text())
    assert [name for name, scene in data["scenes"].items() if "search" in scene] == []
    assert data["scenes"]["picking()"]["words"] == ["Pick one", "A", "B"]


def test_tape_files_are_keys_and_browser_playable_clips(first):
    tape = first[0] / TAPE
    keys = sorted((tape / "keys").iterdir())
    assert [key.name for key in keys] == sorted(f"{name}.png" for name in KEYS.values())
    assert all((frames.read_png(key).width, frames.read_png(key).height) == (1280, 704) for key in keys)
    moves = sorted((tape / "moves").iterdir())
    assert [move.name for move in moves] == sorted(["opening.mp4", *(f"{move}.mp4" for move in MOVES)])
    for move in moves:
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                                "stream=codec_name,pix_fmt,width,height,r_frame_rate", "-of", "csv=p=0", str(move)],
                               capture_output=True, text=True, check=True)
        assert probe.stdout.strip() == "h264,1280,704,yuv420p,24/1"
    assert (tape / "dailies.html").is_file()


class Taller(StandIn):
    """Pads every key take to 1280x720 in the stand-in's background, eight pixels above and below, as a model with another
    frame size would."""

    def text_to_video(self, prompt, seed, out):
        drawn = out.with_name(f"drawn-{out.name}")
        super().text_to_video(prompt, seed, drawn)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(drawn), "-vf", "pad=1280:720:0:8:color=0x2f6f7e", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-r", "24", "-f", "mp4", "-y", str(out)], check=True)
        drawn.unlink()


def test_a_tape_takes_its_size_from_its_clips(first, tmp_path):
    directory = copy_of("cafe", tmp_path)
    rendered(directory, Taller(flaw=clean), takes=1)
    tape = directory / TAPE
    data = json.loads((tape / "tape.json").read_text())
    assert (data["size"], data["fps"]) == ({"width": 1280, "height": 720}, 24)
    assert {(frames.read_png(key).width, frames.read_png(key).height) for key in (tape / "keys").iterdir()} == {(1280, 720)}
    [order] = data["scenes"]["order(Latte)"]["hotspots"]
    [short] = json.loads((first[0] / TAPE / "tape.json").read_text())["scenes"]["order(Latte)"]["hotspots"]
    assert abs(order["box"]["y"] * 720 - (short["box"]["y"] * 704 + 8)) <= 1
    assert abs(order["box"]["h"] * 720 - short["box"]["h"] * 704) <= 1


def test_hotspots_sit_where_the_kept_take_drew_the_words_each_action_is_found_by(first):
    directory, model, result = first
    scenes = json.loads((directory / TAPE / "tape.json").read_text())["scenes"]
    checked = 0
    for filmed in result.keys:
        call = next(c for c in model.calls if c.prompt == words(filmed.shot, told(directory)) and c.seed == filmed.kept.seed)
        drawn = {d.text: d.box for d in model.drawn[call.out]}
        hotspots = scenes[filmed.shot.state.name]["hotspots"]
        assert [hotspot["label"] for hotspot in hotspots] == [action.label for action in filmed.shot.actions]
        for hotspot, action in zip(hotspots, filmed.shot.actions):
            box, truth = hotspot["box"], drawn[action.words]
            assert abs(box["x"] * 1280 - truth.x) <= 2 and abs(box["w"] * 1280 - truth.w) <= 2
            assert abs(box["y"] * 704 - truth.y) <= 2 and abs(box["h"] * 704 - truth.h) <= 2
            checked += 1
    assert checked == 6


def test_each_key_is_its_kept_takes_last_frame_and_the_entrys_kept_take_is_the_opening(first):
    directory, _, result = first
    tape = directory / TAPE
    for filmed in result.keys:
        assert frames.difference(frames.read_png(tape / filmed.shot.image), frames.last_frame(filmed.kept.path)) < 0.001
    assert result.keys[0].shot.state.name == "menu()"
    assert (tape / "moves" / "opening.mp4").read_bytes() == result.keys[0].kept.path.read_bytes()
    for filmed in result.moves:
        assert (tape / filmed.shot.clip).read_bytes() == filmed.kept.path.read_bytes()


def test_a_key_keeps_the_take_whose_checks_pass_over_a_misspelt_one_and_one_with_a_line_missing(first):
    directory, model, result = first
    thanks = next(filmed for filmed in result.keys if filmed.shot.state.name == "thanks(Latte)")
    misspelt_take, dropped_take, clean_take = thanks.takes
    assert thanks.kept is clean_take and clean_take.checks.failures == []
    prompt = words(thanks.shot, told(directory))
    drawn = [[d.text for d in model.drawn[next(c.out for c in model.calls if c.prompt == prompt and c.seed == seed)]]
             for seed in (1, 2)]
    lines_ = ["Thanks", "One Latte coming up.", "Done"]
    [misspelt] = [line for line in lines_ if line not in drawn[0]]
    [dropped] = [line for line in lines_ if line not in drawn[1]]
    assert len(drawn[0]) == 3 and len(drawn[1]) == 2
    assert ("VT502", misspelt) in [(item.code, item.about) for item in misspelt_take.checks.failures]
    assert ("VT502", dropped) in [(item.code, item.about) for item in dropped_take.checks.failures]
    assert clean_take.checks.rank(3) < min(misspelt_take.checks.rank(1), dropped_take.checks.rank(2))


def test_every_films_each_seed_up_to_the_limit_whatever_passed_before_and_keeps_the_best(tmp_path):
    """A screen test films both takes of a key even when the first passes, so it can count how many first takes do."""
    def latte_misspelt_first(mode: Mode, prompt: str, seed: int) -> Flaw:
        return Flaw.MISSPELL if THANKS_LATTE in prompt and seed == 1 else Flaw.NONE

    directory = copy_of("cafe", tmp_path)
    model = StandIn(flaw=latte_misspelt_first)
    result = rendered(directory, model, takes=2, every=True)
    assert [[take.seed for take in filmed.takes] for filmed in result.shots] == [[1, 2]] * 11
    assert sorted((call.prompt, call.seed) for call in model.calls) == sorted(
        (words(filmed.shot, told(directory)), seed) for filmed in result.shots for seed in (1, 2))
    assert {filmed.shot.title: filmed.kept.seed for filmed in result.shots} == {
        title: 2 if title == "key thanks(Latte)" else 1 for title in TITLES}
    record = dailies.read(directory / TAPE)
    assert record["yield"] == {"first_take": 10, "shots": 11} and record["failures"] == []


def test_a_plan_of_keys_alone_films_only_them_and_its_tape_has_their_words_without_hotspots_or_search(tmp_path):
    """A screen test films a few of an app's keys and none of its moves."""
    directory = Path(shutil.copytree(CONTRAIL, tmp_path / "contrail", ignore=shutil.ignore_patterns(
        ".venv", "tape*", "ledger.jsonl", "__pycache__")))
    full = planned(directory)
    keys = Plan(full.title, full.scenes, tuple(key for key in full.keys if key.state.name in ("home()", "search()")),
                (), full.warnings)
    terminal, model, tape = told(directory, "terminal"), StandIn(flaw=clean), directory / "tapes" / "sample"
    result = render(keys, terminal, model, [StandInEye()], tape, ledger.of(directory, tape),
                    made(project.find(directory), terminal, model), takes=1)
    assert [filmed.shot.title for filmed in result.shots] == ["key home()", "key search()"]
    assert [call.mode for call in model.calls] == [Mode.TEXT_TO_VIDEO] * 2
    assert all(filmed.passed for filmed in result.shots)
    data = json.loads((tape / "tape.json").read_text())
    assert {name: scene for name, scene in data["scenes"].items()} == {
        "home()": {"key": "keys/home.png", "words": ["Good morning, Alex", "Where to?", "Your next trip",
                                                     "San Francisco to New York", "Friday, December 18",
                                                     "48,250 Contrail Miles", "Home", "Trips", "Profile"],
                   "hotspots": []},
        "search()": {"key": "keys/search.png", "words": ["Where to?", "Boston (BOS)", "Chicago (ORD)", "Honolulu (HNL)",
                                                         "Los Angeles (LAX)", "New York (JFK)", "Seattle (SEA)"],
                     "hotspots": []},
    }
    assert data["moves"] == {} and dailies.read(tape)["moves"] == []


def test_a_move_keeps_the_take_whose_frames_sit_closest_to_its_keys(first):
    _, _, result = first
    done = next(filmed for filmed in result.moves if filmed.shot.id == "thanks-latte--done")
    wrong_start, wrong_end, clean_take = done.takes
    assert done.kept is clean_take
    assert wrong_start.checks.start > MAX_DIFFERENCE and wrong_start.checks.end <= MAX_DIFFERENCE
    assert [(item.code, item.about) for item in wrong_start.checks.failures] == [("VT508", "start")]
    assert wrong_end.checks.end > MAX_DIFFERENCE and wrong_end.checks.start <= MAX_DIFFERENCE
    assert [(item.code, item.about) for item in wrong_end.checks.failures] == [("VT508", "end")]
    assert clean_take.checks.failures == []
    assert clean_take.checks.rank(3) < wrong_start.checks.rank(1) and clean_take.checks.rank(3) < wrong_end.checks.rank(2)


def test_dailies_page_is_a_view_of_its_record(first):
    directory = first[0]
    tape = directory / TAPE
    record = json.loads((tape / "dailies.json").read_text())
    page = (tape / "dailies.html").read_text()
    assert page == dailies.page(record)
    assert (record["title"], record["checks"], record["story"], record["out"]) == ("Corner Cafe", "stand-in", "chalk", None)
    assert (record["takes"], record["complete"], record["yield"]) == (4, True, {"first_take": 8, "shots": 11})
    assert (record["retakes"], record["corrupt"], record["accepted"], record["failures"]) == ({}, {}, [], [])
    assert [(key["state"], key["key"], key["title"]) for key in record["keys"]] == [
        (state, f"keys/{name}.png", f"key {state}") for state, name in KEYS.items()]
    assert [(item["code"], item["about"], item["passed"]) for item in record["keys"][0]["items"]] == [
        ("VT501", "Espresso, $3", True), ("VT501", "Latte, $5", True), ("VT502", "Corner Cafe", True),
        ("VT502", "Drinks", True), ("VT502", "Espresso", True), ("VT502", "$3", True), ("VT502", "Latte", True),
        ("VT502", "$5", True)]
    assert record["keys"][0]["items"][0]["result"].startswith("found at ")
    assert record["keys"][0]["items"][0]["box"] == {"x": 24, "y": 108, "w": 153, "h": 33}
    assert [move["move"] for move in record["moves"]] == [f"moves/{move}.mp4" for move in MOVES]
    assert '<section class="shot failures"' not in page
    assert '<section class="shot keys" id="keys">' in page
    assert "5 keys checked by stand-in, all passing" in page
    assert "First-take yield 8 of 11." in page
    assert page.count('<section class="shot" id="shot-') == 11
    assert "<h2>1. key menu() (text-to-video)</h2>" in page
    assert "<h2>11. thanks(Latte) -&gt; menu() &quot;Done&quot; (first-and-last-frame)</h2>" in page
    failing = [item for shot in record["keys"] + record["moves"] for take in shot["takes"] for item in take["items"]
               if not item["passed"]]
    assert page.count('<li class="fail">') == len(failing) >= 6
    assert page.count("<video data-src=") == 17 and "<video src=" not in page


def test_dailies_record_has_each_moves_seams_and_the_size_of_what_the_tape_plays(first):
    directory, _, result = first
    tape = directory / TAPE
    record = json.loads((tape / "dailies.json").read_text())
    page = (tape / "dailies.html").read_text()
    for move, filmed in zip(record["moves"], result.moves):
        for take, filmed_take in zip(move["takes"], filmed.takes):
            assert (take["start"], take["end"]) == (filmed_take.checks.start, filmed_take.checks.end)
        kept = filmed.kept.checks
        assert (f"Seams: leaves {filmed.shot.start.name} by {kept.start:.3f}, enters {filmed.shot.land.name} by "
                f"{kept.end:.3f}.") in page
    played = [tape / "tape.json", *(tape / "keys").iterdir(), *(tape / "moves").iterdir()]
    assert record["tape"] == {"bytes": sum(path.stat().st_size for path in played)}
    assert record["tape"]["bytes"] > 100_000
    assert record["ledger"] == ledger.of(directory, tape).totals()
    assert f" Ledger: {record['ledger']['gpu_seconds']} GPU seconds, 0.0 pod hours, $0.00. Tape: " in page
    assert f"Tape: {record['tape']['bytes'] / 1e6:.1f} MB." in page


def pod_line(tape: str, seconds: int, usd: float) -> str:
    return json.dumps({"kind": "pod", "tape": tape, "at": "2026-11-09T12:00:00+00:00", "pod": "abc123",
                       "gpu": "NVIDIA H100 80GB HBM3", "usd_per_hour": 3.99, "started": "2026-11-09T11:00:00+00:00",
                       "stopped": "2026-11-09T12:00:00+00:00", "seconds": seconds, "usd": usd}) + "\n"


def test_dailies_command_rewrites_the_page_with_the_pod_totals_of_its_own_tape_and_opens_it(first, tmp_path, cli, capsys,
                                                                                            monkeypatch):
    directory = again(first, tmp_path)
    with (directory / "ledger.jsonl").open("a") as file:
        file.write(pod_line(TAPE, 1800, 1.995) + pod_line("tape-wan3", 7200, 7.98))
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    assert cli(directory, "dailies", "--story", "chalk") == 0
    record = json.loads((directory / TAPE / "dailies.json").read_text())
    assert (record["ledger"]["takes"], record["ledger"]["pods"]) == (17, 1)
    assert (record["ledger"]["pod_hours"], record["ledger"]["usd"]) == (0.5, 2.0)
    assert ", 0.5 pod hours, $2.00." in (directory / TAPE / "dailies.html").read_text()
    assert capsys.readouterr().out.startswith("wrote tapes/chalk/dailies.html with ")
    assert opened == [(directory / TAPE / "dailies.html").resolve().as_uri()]


def test_second_render_is_cached(first, tmp_path):
    directory = again(first, tmp_path)
    before = tape_files(directory)
    model = StandIn()
    result = rendered(directory, model)
    assert model.calls == []
    assert [filmed.rendered for filmed in result.shots] == [0] * 11
    assert tape_files(directory) == before


def test_a_takes_name_is_the_hash_of_everything_its_pixels_depend_on(first):
    directory, _, result = first
    menu, done = result.keys[0], result.moves[-1]
    recipe = ["text-to-video", words(menu.shot, told(directory)), "stand-in", 1]
    assert menu.takes[0].path.name == f"{hashlib.sha256(json.dumps(recipe).encode()).hexdigest()}.mp4"
    pinned = [hashlib.sha256((directory / TAPE / "keys" / f"{name}.png").read_bytes()).hexdigest()
              for name in ("thanks-latte", "menu")]
    recipe = ["first-and-last-frame", words(done.shot, told(directory)), *pinned, "stand-in", 2]
    assert done.takes[1].path.name == f"{hashlib.sha256(json.dumps(recipe).encode()).hexdigest()}.mp4"


def test_each_filmed_take_records_its_render_time_and_a_line_in_the_projects_ledger_naming_its_tape(first):
    directory, _, result = first
    for filmed in result.shots:
        for take in filmed.takes:
            assert take.seconds > 0 and take.gpu == "cpu"
            assert json.loads(take.path.with_suffix(".json").read_text()) == {"seconds": take.seconds, "gpu": "cpu"}
    lines_ = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]
    assert sorted((line["kind"], line["tape"], line["model"], line["shot"], line["mode"], line["seed"], line["gpu"],
                   line["seconds"]) for line in lines_) == sorted(
        ("take", TAPE, "stand-in", filmed.shot.title, filmed.shot.mode.value, take.seed, "cpu", take.seconds)
        for filmed in result.shots for take in filmed.takes)
    assert all(line["at"].endswith("+00:00") for line in lines_)
    assert ledger.of(directory, directory / TAPE).totals() == {
        "takes": 17, "gpu_seconds": round(sum(line["seconds"] for line in lines_), 1), "pods": 0, "pod_hours": 0.0, "reads": 0, "usd": 0.0}
    assert not (directory / TAPE / "ledger.jsonl").exists()


def test_cached_takes_keep_their_render_time_and_add_no_ledger_lines(first, tmp_path):
    directory = again(first, tmp_path)
    before = (directory / "ledger.jsonl").read_text()
    result = rendered(directory, StandIn())
    assert [[(take.seconds, take.gpu) for take in filmed.takes] for filmed in result.shots] == \
        [[(take.seconds, take.gpu) for take in filmed.takes] for filmed in first[2].shots]
    assert (directory / "ledger.jsonl").read_text() == before


class Billed(StandIn):
    """Bills each call as a hosted model would, 5.04 seconds of video at ten cents a second."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.requests = iter(range(100))

    def text_to_video(self, prompt, seed, out):
        super().text_to_video(prompt, seed, out)
        return self._receipt()

    def first_last_frame(self, prompt, start, end, seed, out):
        super().first_last_frame(prompt, start, end, seed, out)
        return self._receipt()

    def _receipt(self):
        number = next(self.requests)
        return Receipt(f"request-{number}", 5.04, 0.504, {"result": {"request": number}})


def test_a_paid_take_carries_its_price_into_its_sidecar_the_ledger_and_the_dailies(tmp_path):
    directory = copy_of("cafe", tmp_path)
    result = rendered(directory, Billed(flaw=clean), takes=1)
    tape = directory / TAPE
    book = ledger.of(directory, tape)
    lines_ = book.lines()
    assert sorted((line["shot"], line["duration"], line["usd"]) for line in lines_) == sorted(
        (filmed.shot.title, 5.04, 0.504) for filmed in result.shots)
    assert {line["request_id"] for line in lines_} == {f"request-{number}" for number in range(11)}
    menu = result.keys[0].kept
    assert json.loads(menu.path.with_suffix(".json").read_text()) == {
        "seconds": menu.seconds, "gpu": "cpu", "request_id": "request-0", "duration": 5.04, "usd": 0.504,
        "response": {"result": {"request": 0}}}
    assert [filmed.usd for filmed in result.shots] == [0.504] * 11
    record = dailies.read(tape)
    assert [take["usd"] for shot in record["keys"] + record["moves"] for take in shot["takes"]] == [0.504] * 11
    assert record["ledger"]["usd"] == 5.54
    assert ", 0.0 pod hours, $5.54. Tape: " in (tape / "dailies.html").read_text()
    again_ = rendered(directory, StandIn(), takes=1)
    assert book.lines() == lines_
    assert [filmed.kept.usd for filmed in again_.shots] == [0.504] * 11
    assert [filmed.usd for filmed in again_.shots] == [0.0] * 11
    with (directory / "ledger.jsonl").open("a") as file:
        file.write(pod_line(TAPE, 1800, 2.0))
    assert book.totals()["usd"] == 7.54


def test_takes_flag_sets_the_most_takes_a_shot_gets_and_the_projects_model_renders(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER, "--takes", "1") == 0
    assert [call.seed for call in model.calls] == [1] * 11
    out = capsys.readouterr().out
    assert lines(out)[0] == (1, "key menu()", 1, "passed", "1 take filmed", "0.00")
    assert sorted(number for number, *_ in lines(out)) == list(range(1, 12))
    assert out.splitlines()[-1].startswith("11 shots, 11 takes filmed, $0.00, ") and out.endswith(" MB -> tapes/chalk\n")
    with pytest.raises(SystemExit) as exit:
        cli(directory, *RENDER, "--takes", "0")
    assert exit.value.code == 2
    assert "--takes: must be at least 1, got 0" in capsys.readouterr().err


def test_takes_in_the_project_is_the_limit_and_four_is_the_default(tmp_path, cli, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    always_flawed = lambda mode, prompt, seed: Flaw.MISSPELL if mode is Mode.TEXT_TO_VIDEO else Flaw.WRONG_END
    model = StandIn(flaw=always_flawed)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER, "--out", "tape-four") == 1
    assert [call.seed for call in model.calls if call.mode is Mode.TEXT_TO_VIDEO] == [1, 2, 3, 4] * 5
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + "takes = 2\n")
    model.calls.clear()
    assert cli(directory, *RENDER, "--out", "tape-two") == 1
    assert [call.seed for call in model.calls if call.mode is Mode.TEXT_TO_VIDEO] == [1, 2] * 5
    assert dailies.read(directory / "tape-two")["takes"] == 2


def test_model_flag_renders_with_another_model_than_the_projects(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    named, other = StandIn(flaw=clean), StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(named))
    monkeypatch.setitem(MODELS, "wan3.0", stand_in(other))
    assert cli(directory, *RENDER, "--model", "wan3.0", "--takes", "1") == 0
    assert (len(named.calls), len(other.calls)) == (0, 11)


@pytest.mark.parametrize("setting, error", [
    ("", "error VT110 pyproject.toml: [tool.videotape] names no model, and neither does --model\nfix: set it in "
         '[tool.videotape], as in model = "stand-in", or name one for this render, as in videotape render --story '
         "chalk --model stand-in\n"),
    ('model = "sora"\n', 'error VT107 pyproject.toml: [tool.videotape] model is "sora", and videotape has no such '
     "model\nfix: set model to one of gemini-omni-flash-1.2, minimax-h3, stand-in, wan2.2-5b, wan3.0\n"),
])
def test_a_project_without_a_model_it_can_render_with_says_so(tmp_path, cli, capsys, setting, error):
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('model = "stand-in"\n', setting))
    assert cli(directory, *RENDER) == 1
    assert capsys.readouterr() == ("", error)
    assert not (directory / "tapes").exists()


def test_a_render_with_no_model_named_is_vt110_as_explain_says(tmp_path, cli, capsys):
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('model = "stand-in"\n', ""))
    assert cli(directory, *RENDER) == 1
    assert as_explained("VT110").fullmatch(capsys.readouterr().err.rstrip("\n"))


class Tuned(StandIn):
    def __init__(self, knobs: dict, **kwargs):
        super().__init__(**kwargs)
        self.knobs = knobs

    def settings(self, mode):
        return self.knobs


def test_a_models_settings_are_part_of_the_cache_key(first, tmp_path):
    directory = again(first, tmp_path)
    assert len(rendered(directory, StandIn(flaw=clean), takes=1).shots) == 11
    model = Tuned({"steps": 50, "frames": 81}, flaw=clean)
    rendered(directory, model, takes=1)
    assert len(model.calls) == 11
    same = Tuned({"frames": 81, "steps": 50}, flaw=clean)
    rendered(directory, same, takes=1)
    assert same.calls == []
    for knobs in ({"steps": 40, "frames": 81}, {"steps": 50, "frames": 121}, {"steps": 50, "frames": 81, "shift": 5.0}):
        other = Tuned(knobs, flaw=clean)
        rendered(directory, other, takes=1)
        assert len(other.calls) == 11, knobs


def test_editing_one_line_rerenders_its_key_and_only_the_moves_that_touch_it(first, tmp_path, cli, capsys, monkeypatch):
    directory = again(first, tmp_path, 'vt.Heading("Corner Cafe")', 'vt.Heading("The Corner Cafe")')
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER) == 0
    assert len(model.calls) == 5
    assert sorted(lines(capsys.readouterr().out)) == [
        (1, "key menu()", 1, "passed", "1 take filmed", "0.00"),
        (2, "key order(Espresso)", 1, "passed", "cached", "0.00"),
        (3, "key order(Latte)", 1, "passed", "cached", "0.00"),
        (4, "key thanks(Espresso)", 1, "passed", "cached", "0.00"),
        (5, "key thanks(Latte)", 3, "passed", "cached", "0.00"),
        (6, 'menu() -> order(Espresso) "Espresso, $3"', 1, "passed", "1 take filmed", "0.00"),
        (7, 'menu() -> order(Latte) "Latte, $5"', 1, "passed", "1 take filmed", "0.00"),
        (8, 'order(Espresso) -> thanks(Espresso) "Order"', 1, "passed", "cached", "0.00"),
        (9, 'order(Latte) -> thanks(Latte) "Order"', 1, "passed", "cached", "0.00"),
        (10, 'thanks(Espresso) -> menu() "Done"', 1, "passed", "1 take filmed", "0.00"),
        (11, 'thanks(Latte) -> menu() "Done"', 1, "passed", "1 take filmed", "0.00"),
    ]


def test_cli_render_writes_everything_then_fails_on_a_failing_kept_take_and_names_the_retake(tmp_path, cli, capsys,
                                                                                          monkeypatch):
    directory = copy_of("cafe", tmp_path)
    misspelt_keys = lambda mode, prompt, seed: Flaw.MISSPELL if mode is Mode.TEXT_TO_VIDEO else Flaw.NONE
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=misspelt_keys)))
    assert cli(directory, *RENDER, "--takes", "1") == 1
    out, err = capsys.readouterr()
    verdicts = [verdict for _, _, _, verdict, _, _ in sorted(lines(out))]
    assert all(verdict.startswith("fails ") and "VT502" in verdict for verdict in verdicts[:5])
    assert verdicts[5:] == ["passed"] * 6
    failed = [line for line in err.splitlines() if line.startswith("fail: ")]
    assert sorted({line.split("  ")[0] for line in failed}) == sorted(
        f"fail: {number}. key {state}" for number, state in enumerate(STATES, 1))
    assert all(" VT502 " in line or " VT501 " in line for line in failed)
    assert len([line for line in err.splitlines() if line.startswith("  next: videotape retake ")]) == len(failed)
    record = dailies.read(directory / TAPE)
    assert [(f["shot"], f["code"], f["about"]) for f in record["failures"]][0][:2] == ("key menu()", "VT502")
    assert "kept take fails checks" in (directory / TAPE / "dailies.html").read_text()
    assert sorted(json.loads((directory / TAPE / "tape.json").read_text())["moves"]) == sorted(MOVES)


def test_an_action_the_checks_do_not_find_has_no_hotspot_but_its_move_still_renders(tmp_path, cli, capsys, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[tool.videotape]\nscreenplay = "doors:app"\nmodel = "stand-in"\n')
    (tmp_path / "doors.py").write_text(
        'import videotape as vt\n\napp = vt.Screenplay("Doors")\n\n\n@app.scene\ndef hall():\n'
        '    return [vt.Button("Go in", to=room())]\n\n\n@app.scene\ndef room():\n'
        '    return [vt.Button("Go out", to=hall())]\n')
    (tmp_path / "stories").mkdir()
    (tmp_path / "stories" / "bare.toml").write_text('version = "1.0.0"\nlook = "A bare hallway."\n')
    no_hall_button = lambda mode, prompt, seed: Flaw.DROP_LINE if '"Go in"' in prompt and mode is Mode.TEXT_TO_VIDEO else Flaw.NONE
    model = StandIn(flaw=no_hall_button)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(tmp_path, "render", "--story", "bare", "--takes", "2") == 1
    data = json.loads((tmp_path / "tapes" / "bare" / "tape.json").read_text())
    assert data["scenes"]["hall()"]["hotspots"] == []
    assert [hotspot["label"] for hotspot in data["scenes"]["room()"]["hotspots"]] == ["Go out"]
    assert sorted(data["moves"]) == ["hall--go-in", "room--go-out"]
    assert (tmp_path / "tapes" / "bare" / "moves" / "hall--go-in.mp4").is_file()
    assert capsys.readouterr().err.splitlines()[4:] == [
        "fail: 1. key hall()  VT501 Go in: not found",
        '  next: videotape retake "hall()" --story bare',
        "fail: 1. key hall()  VT502 Go in: read nothing, CER 1.000",
        '  next: videotape retake "hall()" --story bare']
    page = (tmp_path / "tapes" / "bare" / "dailies.html").read_text()
    assert '<span class="name">VT501 Go in</span><span class="result">not found' in page
    assert [call.mode for call in model.calls].count(Mode.FIRST_AND_LAST_FRAME) == 2


def test_out_writes_another_tape_whose_ledger_lines_and_totals_are_its_own(first, tmp_path, cli, capsys, monkeypatch):
    directory = again(first, tmp_path)
    before = tape_files(directory)
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER, "--takes", "1", "--out", "tape-b") == 0
    out = directory / "tape-b"
    assert len(model.calls) == 11
    assert capsys.readouterr().out.splitlines()[-1].endswith(" MB -> tape-b")
    assert json.loads((out / "tape.json").read_text())["opening"] == {"clip": "moves/opening.mp4", "lands": "menu()"}
    assert sorted(path.name for path in (out / "keys").iterdir()) == sorted(name for name in before if name.endswith(".png"))
    lines_ = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]
    assert [line["tape"] for line in lines_] == [TAPE] * 17 + ["tape-b"] * 11
    assert [line["seed"] for line in Ledger(directory / "ledger.jsonl", "tape-b").lines()] == [1] * 11
    assert dailies.read(out)["ledger"]["takes"] == 11
    assert (dailies.read(out)["title"], dailies.read(out)["out"]) == ("Corner Cafe", "tape-b")
    assert tape_files(directory) == before


def test_cli_render_rejects_a_model_that_does_not_exist(tmp_path, cli, capsys):
    with pytest.raises(SystemExit) as exit:
        cli(copy_of("cafe", tmp_path), *RENDER, "--model", "sora")
    assert exit.value.code == 2
    assert "invalid choice: 'sora'" in capsys.readouterr().err


class Counting(StandIn):
    """Counts how many calls run at once, and which shots were filmed while the keys were still being filmed."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lock = threading.Lock()
        self.running = 0
        self.most = 0
        self.keys_done = 0
        self.moves_before_every_key: list[str] = []

    def _film(self, mode, prompt, seed, start, end, out):
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
            if mode is Mode.FIRST_AND_LAST_FRAME and self.keys_done < 5:
                self.moves_before_every_key.append(prompt)
        try:
            time.sleep(0.05)
            super()._film(mode, prompt, seed, start, end, out)
        finally:
            with self.lock:
                self.running -= 1
                if mode is Mode.TEXT_TO_VIDEO:
                    self.keys_done += 1


@pytest.mark.parametrize("limit, at_once", [(1, 1), (4, 4)])
def test_shots_that_do_not_depend_on_each_other_film_at_once_up_to_the_models_limit(tmp_path, limit, at_once):
    directory = copy_of("cafe", tmp_path / str(limit))
    model = Counting(flaw=clean)
    result = rendered(directory, model, takes=1, limit=limit)
    assert model.most == at_once
    assert len(model.calls) == 11 and [filmed.shot.title for filmed in result.shots] == TITLES
    if limit == 1:
        assert model.moves_before_every_key == []


def test_a_move_waits_for_both_of_its_keys_while_the_rest_film_at_once(tmp_path):
    directory = copy_of("cafe", tmp_path)
    model = Witness(flaw=clean)
    rendered(directory, model, takes=1, limit=8)
    assert model.existed == [True] * 12
    keys = {call.prompt for call in model.calls if call.mode is Mode.TEXT_TO_VIDEO}
    assert len(keys) == 5


def test_a_parallel_render_matches_a_sequential_one_take_for_take(tmp_path):
    alone, together = copy_of("cafe", tmp_path / "alone"), copy_of("cafe", tmp_path / "together")
    rendered(alone, StandIn(), limit=1)
    rendered(together, StandIn(), limit=8)
    assert tape_files(alone) == tape_files(together)
    kept = lambda directory: [(filmed["title"], next(t["seed"] for t in filmed["takes"] if t["kept"]))
                              for filmed in (*dailies.read(directory / TAPE)["keys"], *dailies.read(directory / TAPE)["moves"])]
    assert kept(alone) == kept(together)
    assert sorted(path.name for path in (alone / TAPE / "takes").iterdir()) == \
        sorted(path.name for path in (together / TAPE / "takes").iterdir())


class Garbled(StandIn):
    """Writes a file that is not a clip for the seeds it is told to, once per take when told to heal."""

    def __init__(self, garble: set[int], heal: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.garble, self.heal = garble, heal
        self.garbled: list[Path] = []

    def _film(self, mode, prompt, seed, start, end, out):
        if seed in self.garble and (not self.heal or out not in self.garbled):
            self.calls.append(None)
            self.garbled.append(out)
            out.write_bytes(b"not a clip")
            return
        super()._film(mode, prompt, seed, start, end, out)


class GarbledBilled(Garbled, Billed):
    pass


def test_a_corrupt_take_is_vt403_its_seed_is_skipped_from_then_on_and_the_shot_goes_on(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    model = Garbled({1}, flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER) == 0
    out, err = capsys.readouterr()
    reported = [line for line in err.splitlines() if line.startswith("error VT403")]
    assert re.fullmatch(r"error VT403 key menu\(\) take 1: tapes/chalk/takes/[0-9a-f]{64}\.mp4 did not decode to one frame: .+",
                        reported[0])
    assert err.count("error VT403 ") == 11 and err.count("next: nothing; seed 1 is skipped from now on") == 11
    assert as_explained("VT403").search(err)
    assert [seed for _, _, seed, *_ in lines(out)] == [2] * 11
    record = dailies.read(directory / TAPE)
    assert record["corrupt"] == {title: [1] for title in TITLES}
    assert record["keys"][0]["corrupt"] == [1]
    assert "Corrupt and skipped: seed 1." in (directory / TAPE / "dailies.html").read_text()
    model.calls.clear()
    assert cli(directory, *RENDER) == 0
    assert model.calls == [] and "VT403" not in capsys.readouterr().err
    assert dailies.read(directory / TAPE)["corrupt"] == record["corrupt"]


def test_a_corrupt_take_from_a_model_with_nothing_to_download_again_is_vt403_and_not_filmed_again(tmp_path):
    directory = copy_of("cafe", tmp_path)
    # Filmed again, each garbled take would heal. It is not: its seed is skipped and paid for once, like every other.
    model = GarbledBilled({1}, heal=True, flaw=clean)
    result = rendered(directory, model, takes=2)
    assert [filmed.kept.seed for filmed in result.shots] == [2] * 11
    assert [error.code for filmed in result.shots for error in filmed.reported] == ["VT403"] * 11
    assert dailies.read(directory / TAPE)["corrupt"]["key menu()"] == [1]
    book = ledger.of(directory, directory / TAPE)
    assert [line["seed"] for line in book.lines()].count(1) == 11 and len(book.lines()) == 22
    assert next(model.requests) == 22


def test_every_take_corrupt_stops_the_render_with_vt403(tmp_path):
    directory = copy_of("cafe", tmp_path)
    with pytest.raises(RenderError) as error:
        rendered(directory, Garbled({1, 2}, flaw=clean), takes=2)
    assert (error.value.code, error.value.place, error.value.message) == (
        "VT403", "key menu()", "every take of the shot is corrupt")
    assert error.value.next.endswith('videotape retake "menu()" --story chalk')


class Refusing(StandIn):
    """Refuses the takes of its seeds for their content, as fal's content checker does, on every prompt or on those
    that hold on, and fails seeds in failing with VT401."""

    def __init__(self, seeds: set[int], on: str = "", failing: frozenset[int] = frozenset(), **kwargs):
        super().__init__(**kwargs)
        self.refused, self.on, self.failing, self.asked = seeds, on, failing, list[tuple[str, int]]()

    def _film(self, mode, prompt, seed, start, end, out):
        self.asked.append((prompt, seed))
        if self.on in prompt and seed in self.refused:
            raise ModelError(f"request r-{seed} was refused for its content: HTTP 422 content_policy_violation, "
                             "model_moderated", "VT409", "nothing; a render skips the take's seed from now on")
        if self.on in prompt and seed in self.failing:
            raise ModelError(f"request r-{seed} failed with HTTP 500")
        super()._film(mode, prompt, seed, start, end, out)


class BilledRefusing(Refusing, Billed):
    pass


def test_a_refused_take_is_vt409_its_seed_is_skipped_from_then_on_and_the_shot_goes_on(tmp_path, cli, capsys,
                                                                                        monkeypatch):
    directory = copy_of("cafe", tmp_path)
    model = Refusing({1}, flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER) == 0
    out, err = capsys.readouterr()
    assert err.splitlines()[:2] == [
        "error VT409 key menu() take 1: request r-1 was refused for its content: HTTP 422 content_policy_violation, "
        "model_moderated", "next: nothing; seed 1 is skipped from now on"]
    assert err.count("error VT409 ") == 11 and "VT401" not in err
    assert [seed for _, _, seed, *_ in lines(out)] == [2] * 11
    record = dailies.read(directory / TAPE)
    assert [shot["refused"] for shot in (*record["keys"], *record["moves"])] == [[1]] * 11 and record["corrupt"] == {}
    assert len(list((directory / TAPE / "takes").glob("*.refused.json"))) == 11
    assert "Refused for its content and skipped: seed 1." in (directory / TAPE / "dailies.html").read_text()
    model.asked.clear()
    assert cli(directory, *RENDER) == 0
    assert model.asked == [] and "VT409" not in capsys.readouterr().err
    assert [shot["refused"] for shot in (*record["keys"], *record["moves"])] == [
        shot["refused"] for shot in (*dailies.read(directory / TAPE)["keys"], *dailies.read(directory / TAPE)["moves"])]


def test_a_refusal_is_kept_when_its_shot_then_stops_on_another_error_and_is_not_asked_for_again(tmp_path):
    directory = copy_of("cafe", tmp_path)
    with pytest.raises(RenderError) as error:
        rendered(directory, Refusing({1}, on=THANKS_LATTE, failing=frozenset({2}), flaw=clean), takes=2)
    assert (error.value.code, error.value.place) == ("VT401", "key thanks(Latte) take 2")
    model = Refusing(set(), flaw=clean)
    rendered(directory, model, takes=2)
    assert (1, 1) not in [(THANKS_LATTE in prompt, seed) for prompt, seed in model.asked]
    [latte] = [shot for shot in dailies.read(directory / TAPE)["keys"] if shot["title"] == "key thanks(Latte)"]
    assert latte["refused"] == [1] and [take["seed"] for take in latte["takes"]] == [2]


def test_a_refused_call_goes_in_the_ledger_once_at_its_listed_price_so_the_cap_counts_it(tmp_path):
    directory = copy_of("cafe", tmp_path)
    price = Price(0.1, 5)
    rendered(directory, BilledRefusing({1}, on=THANKS_LATTE, flaw=clean), takes=2, price=price, cap=20)
    book = ledger.of(directory, directory / TAPE)
    refused = [line for line in book.lines() if line.get("refused")]
    assert [(line["shot"], line["seed"], line["usd"]) for line in refused] == [("key thanks(Latte)", 1, 0.5)]
    spent = book.totals()["usd"]
    rendered(directory, BilledRefusing(set(), flaw=clean), takes=2, price=price, cap=20)
    assert [line for line in ledger.of(directory, directory / TAPE).lines() if line.get("refused")] == refused
    assert ledger.of(directory, directory / TAPE).totals()["usd"] == spent


def test_every_take_of_a_shot_refused_films_the_other_shots_then_stops_with_vt409(tmp_path):
    directory = copy_of("cafe", tmp_path)
    with pytest.raises(RenderError) as error:
        rendered(directory, Refusing({1, 2}, on=THANKS_LATTE, flaw=clean), takes=2)
    assert (error.value.code, error.value.place, error.value.message) == (
        "VT409", "key thanks(Latte)", "every take of the shot was refused for its content")
    assert error.value.next.endswith('videotape retake "thanks(Latte)" --story chalk')
    record = dailies.read(directory / TAPE)
    assert record["unfilmed"] == {"key thanks(Latte)": [1, 2]} and record["complete"] is False
    assert [shot["title"] for shot in record["keys"]] == [title for title in TITLES if title.startswith("key ")
                                                          and title != "key thanks(Latte)"]


def test_a_shot_with_a_corrupt_seed_and_a_refused_one_stops_with_vt403(tmp_path):
    directory = copy_of("cafe", tmp_path)
    tape = directory / TAPE
    rendered(directory, StandIn(flaw=clean), takes=1)
    record = dailies.read(tape)
    dailies.write(tape, {**record, "corrupt": {"key thanks(Latte)": [1]}}, ledger.of(directory, tape).totals())
    with pytest.raises(RenderError) as error:
        rendered(directory, Refusing({2}, on=THANKS_LATTE, flaw=clean), takes=2)
    assert (error.value.code, error.value.place, error.value.message) == (
        "VT403", "key thanks(Latte)", "every take of the shot is corrupt")


class Failing(StandIn):
    def __init__(self, on: str, **kwargs):
        super().__init__(**kwargs)
        self.on = on

    def _film(self, mode, prompt, seed, start, end, out):
        if self.on in prompt:
            raise ModelError(f"the stand-in refused seed {seed}; request r-{seed}")
        super()._film(mode, prompt, seed, start, end, out)


def test_a_failed_model_call_is_vt401_with_the_providers_message_and_nothing_is_lost(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(Failing(THANKS_LATTE, flaw=clean)))
    assert cli(directory, *RENDER, "--takes", "1") == 1
    out, err = capsys.readouterr()
    assert err.splitlines()[0] == "error VT401 key thanks(Latte) take 1: the stand-in refused seed 1; request r-1"
    assert err.splitlines()[1] == "next: run the render again, which resumes; a request that was submitted is polled, not submitted again:"
    assert err.splitlines()[2] == "videotape render --story chalk --takes 1"
    assert not (directory / TAPE / "tape.json").exists()
    assert dailies.read(directory / TAPE)["complete"] is False
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=clean)))
    assert cli(directory, *RENDER, "--takes", "1") == 0
    assert [status for *_, status, _ in lines(capsys.readouterr().out)].count("cached") == 4
    assert (directory / TAPE / "tape.json").exists() and dailies.read(directory / TAPE)["complete"] is True


class Crashing(StandIn):
    """Raises what no render error covers on one shot, as a bug or a dropped connection would."""

    def __init__(self, on: str, **kwargs):
        super().__init__(**kwargs)
        self.on = on

    def _film(self, mode, prompt, seed, start, end, out):
        if self.on in prompt:
            raise RuntimeError("the stand-in fell over")
        super()._film(mode, prompt, seed, start, end, out)


def test_an_error_no_render_error_covers_stops_the_render_and_settles_the_take_in_flight(tmp_path):
    directory = copy_of("cafe", tmp_path)
    model = Crashing('"Corner Cafe"', flaw=clean)
    with pytest.raises(RuntimeError, match="the stand-in fell over"):
        rendered(directory, model, takes=1, limit=1)
    # The one worker may have begun the next key before the stop reached it. The other keys and the moves never start.
    assert len(model.calls) <= 1
    assert [line["shot"] for line in ledger.of(directory, directory / TAPE).lines()] == ["key order(Espresso)"] * len(model.calls)
    assert not (directory / TAPE / "tape.json").exists()


def test_an_interrupt_stops_the_render_before_the_queued_shots_start(tmp_path):
    directory = copy_of("cafe", tmp_path)
    model = StandIn(flaw=clean)

    def interrupted(filmed):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        rendered(directory, model, takes=1, limit=1, report=interrupted)
    assert 1 <= len(model.calls) <= 2
    assert len(ledger.of(directory, directory / TAPE).lines()) == len(model.calls)


def test_a_state_with_more_lines_than_the_stand_in_has_room_for_is_vt406_and_stops_the_render(tmp_path, cli, capsys,
                                                                                               monkeypatch):
    directory = copy_of("cafe", tmp_path)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=clean)))
    (directory / "data" / "drinks.json").write_text(json.dumps([{"name": f"Drink {n}", "price": n} for n in range(1, 21)]))
    assert cli(directory, *RENDER, "--takes", "1") == 1
    assert as_explained("VT406").search(capsys.readouterr().err)
    assert not (directory / TAPE / "tape.json").exists() and dailies.read(directory / TAPE)["complete"] is False


def test_a_missing_ffmpeg_is_vt404(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=clean)))
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cli(directory, *RENDER, "--takes", "1") == 1
    err = capsys.readouterr().err.splitlines()
    assert err[0].startswith("error VT404 key ") and err[0].endswith(": ffmpeg is not on PATH")
    assert err[1] == "next: install ffmpeg, as in brew install ffmpeg, and run the render again"
    assert as_explained("VT404").fullmatch("\n".join(err))


def test_the_stand_ins_extra_box_fails_vt503_on_the_kept_take_when_it_is_the_only_take(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    extra = lambda mode, prompt, seed: Flaw.EXTRA_BOX if '"Order"' in prompt and mode is Mode.TEXT_TO_VIDEO else Flaw.NONE
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=extra)))
    assert cli(directory, *RENDER, "--takes", "1") == 1
    err = capsys.readouterr().err.splitlines()
    assert err[0] == (f'fail: 2. key order(Espresso)  VT503 {EXTRA}: a control reading "{EXTRA}" at 24,150 315x33, and no '
                      "action has those words")
    assert err[1] == '  next: videotape retake "order(Espresso)" --story chalk'
    record = dailies.read(directory / TAPE)
    assert [(f["shot"], f["code"]) for f in record["failures"]] == [("key order(Espresso)", "VT503"),
                                                                     ("key order(Latte)", "VT503")]
    [first_failure, _] = record["failures"]
    assert first_failure["next"] == {
        "retake": 'videotape retake "order(Espresso)" --story chalk',
        "story": "stories/chalk.toml line 11, scenes.order",
        "screenplay": "cafe.py line 24",
        "accept": 'videotape accept "order(Espresso)" VT503 --story chalk --reason "..."'}
    assert first_failure["crop"] == "dailies/1.png"
    crop = frames.read_png(directory / TAPE / "dailies/1.png")
    assert (crop.width, crop.height) == (315 + 48, 33 + 48)
    assert data_ok(directory / TAPE)


def test_the_dailies_folder_holds_only_the_crops_of_the_failures_the_record_names(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    folder = directory / TAPE / "dailies"
    latte_always_misspelt = lambda mode, prompt, seed: (
        Flaw.MISSPELL if THANKS_LATTE in prompt else Flaw.WRONG_START if DONE in prompt and seed == 1 else Flaw.NONE)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=latte_always_misspelt)))
    crops = lambda: sorted(failure["crop"] for failure in dailies.read(directory / TAPE)["failures"])
    files = lambda: sorted(path.relative_to(directory / TAPE).as_posix() for path in folder.iterdir())
    assert cli(directory, *RENDER, "--takes", "1") == 1
    assert files() == crops() == ["dailies/1.png", "dailies/2.png", "dailies/3.png", "dailies/4.png"]
    assert cli(directory, *RENDER, "--takes", "2") == 1
    assert files() == crops() == ["dailies/1.png"]
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=clean)))
    assert cli(directory, "retake", "thanks(Latte)", "--story", "chalk") == 0
    assert files() == crops() == []


def data_ok(tape: Path) -> bool:
    return json.loads((tape / "tape.json").read_text())["opening"]["lands"] == "menu()"
