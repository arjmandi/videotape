import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import copy_of, planned, told, words
from videotape import dailies, frames, ledger, project
from videotape.checks import MAX_DIFFERENCE
from videotape.fal import Receipt
from videotape.ledger import Ledger
from videotape.made import made
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.render import render, uncached
from videotape.standin import Flaw, StandIn, StandInEye

STATES = ("menu()", "order(Espresso)", "order(Latte)", "thanks(Espresso)", "thanks(Latte)")
KEYS = {"menu()": "menu", "order(Espresso)": "order-espresso", "order(Latte)": "order-latte",
        "thanks(Espresso)": "thanks-espresso", "thanks(Latte)": "thanks-latte"}
MOVES = {"menu--espresso": "order(Espresso)", "menu--latte": "order(Latte)", "order-espresso--order": "thanks(Espresso)",
         "order-latte--order": "thanks(Latte)", "thanks-espresso--done": "menu()", "thanks-latte--done": "menu()"}
TITLES = ["key menu()", "key order(Espresso)", "key order(Latte)", "key thanks(Espresso)", "key thanks(Latte)",
          'menu() -> order(Espresso) "Espresso, $3"', 'menu() -> order(Latte) "Latte, $5"',
          'order(Espresso) -> thanks(Espresso) "Order"', 'order(Latte) -> thanks(Latte) "Order"',
          'thanks(Espresso) -> menu() "Done"', 'thanks(Latte) -> menu() "Done"']
THANKS_LATTE = '"One Latte coming up."'
DONE = 'The button "Done" is pressed.'


def flaws(mode: Mode, prompt: str, seed: int) -> Flaw:
    if THANKS_LATTE in prompt:
        return {1: Flaw.MISSPELL, 2: Flaw.DROP_LINE}.get(seed, Flaw.NONE)
    if DONE in prompt:
        return {1: Flaw.WRONG_START, 2: Flaw.WRONG_END}.get(seed, Flaw.NONE)
    return Flaw.NONE


def clean(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.NONE


def stand_in(model: StandIn) -> Listing:
    return Listing(lambda: model, lambda tape: StandInEye())


class Witness(StandIn):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.existed: list[bool] = []

    def first_last_frame(self, prompt, start, end, seed, out):
        self.existed += [start.is_file(), end.is_file()]
        super().first_last_frame(prompt, start, end, seed, out)


TAPE = "tapes/chalk"
RENDER = ("render", "--story", "chalk")


def rendered(directory: Path, model, takes: int = 3, out: str = TAPE):
    chalk = told(directory)
    return render(planned(directory), chalk, model, StandInEye(), directory / out, ledger.of(directory, directory / out),
                  made(project.find(directory), chalk, model), takes=takes)


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


def test_every_key_is_filmed_before_any_move_with_three_takes_each(first):
    directory, model, _ = first
    plan, chalk = planned(directory), told(directory)
    expected = [(shot, seed) for shot in plan.shots for seed in (1, 2, 3)]
    assert [shot.title for shot in plan.shots] == TITLES
    assert [(call.mode, call.prompt, call.seed) for call in model.calls] == [
        (shot.mode, words(shot, chalk), seed) for shot, seed in expected]
    assert model.calls[0].prompt == (
        "Static shot. A chalkboard behind the counter of a small corner cafe, lettered by hand in white chalk. Warm "
        "light from the left, and a strip of pale wood along the bottom edge. The whole board, seen from across the "
        'counter. Large chalk letters across the top of the board, reading "Corner Cafe". Chalk lines, one per row, '
        'with a dotted line from each name to its price, reading "Drinks"; "Espresso" and "$3"; and "Latte" and "$5". '
        "Sharp, legible lettering.")
    assert model.calls[-1].prompt == ('The button "Done" is pressed. The chalk box is rubbed out. The camera pulls '
                                      "back from the board.")
    assert [call.mode for call in model.calls] == [Mode.TEXT_TO_VIDEO] * 15 + [Mode.FIRST_AND_LAST_FRAME] * 18
    keys = directory / TAPE / "keys"
    for call, (shot, _) in zip(model.calls, expected):
        if shot.mode is Mode.FIRST_AND_LAST_FRAME:
            assert (call.start, call.end) == (keys / f"{KEYS[shot.start.name]}.png", keys / f"{KEYS[shot.land.name]}.png")
        else:
            assert (call.start, call.end) == (None, None)
    assert model.existed == [True] * 36


def test_the_tape_has_one_scene_for_each_state_with_its_hotspots_and_moves(first):
    data = json.loads((first[0] / TAPE / "tape.json").read_text())
    assert data["size"] == {"width": 1280, "height": 704}
    assert data["fps"] == 24
    assert data["opening"] == {"clip": "moves/opening.mp4", "lands": "menu()"}
    assert {name: scene["key"] for name, scene in data["scenes"].items()} == {
        state: f"keys/{name}.png" for state, name in KEYS.items()}
    assert {name: [(h["label"], h["move"]) for h in scene["hotspots"]] for name, scene in data["scenes"].items()} == {
        "menu()": [("Espresso, $3", "menu--espresso"), ("Latte, $5", "menu--latte")],
        "order(Espresso)": [("Order", "order-espresso--order")],
        "order(Latte)": [("Order", "order-latte--order")],
        "thanks(Espresso)": [("Done", "thanks-espresso--done")],
        "thanks(Latte)": [("Done", "thanks-latte--done")],
    }
    assert data["moves"] == {move: {"clip": f"moves/{move}.mp4", "lands": lands} for move, lands in MOVES.items()}


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
        call = next(c for c in model.calls if c.prompt == filmed.prompt and c.seed == filmed.kept.seed)
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
    _, model, result = first
    thanks = next(filmed for filmed in result.keys if filmed.shot.state.name == "thanks(Latte)")
    misspelt_take, dropped_take, clean_take = thanks.takes
    assert thanks.kept is clean_take and clean_take.checks.failures == []
    drawn = [[d.text for d in model.drawn[next(c.out for c in model.calls if c.prompt == thanks.prompt and c.seed == seed)]]
             for seed in (1, 2)]
    lines = ["Thanks", "One Latte coming up.", "Done"]
    [misspelt] = [line for line in lines if line not in drawn[0]]
    [dropped] = [line for line in lines if line not in drawn[1]]
    assert len(drawn[0]) == 3 and len(drawn[1]) == 2
    assert ("VT502", misspelt) in [(item.code, item.about) for item in misspelt_take.checks.failures]
    assert ("VT502", dropped) in [(item.code, item.about) for item in dropped_take.checks.failures]
    assert clean_take.checks.rank(3) < min(misspelt_take.checks.rank(1), dropped_take.checks.rank(2))


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
    assert (record["title"], record["checks"]) == ("Corner Cafe", "stand-in")
    assert [(key["state"], key["key"], key["title"]) for key in record["keys"]] == [
        (state, f"keys/{name}.png", f"key {state}") for state, name in KEYS.items()]
    assert [(item["code"], item["about"], item["passed"]) for item in record["keys"][0]["items"]] == [
        ("VT501", "Espresso, $3", True), ("VT501", "Latte, $5", True), ("VT502", "Corner Cafe", True),
        ("VT502", "Drinks", True), ("VT502", "Espresso", True), ("VT502", "$3", True), ("VT502", "Latte", True),
        ("VT502", "$5", True)]
    assert record["keys"][0]["items"][0]["result"].startswith("found at ")
    assert [move["move"] for move in record["moves"]] == [f"moves/{move}.mp4" for move in MOVES]
    assert '<section class="shot keys" id="keys">' in page
    assert "5 keys checked by stand-in, all passing" in page
    assert page.count('<section class="shot" id="shot-') == 11
    assert "<h2>1. key menu() (text-to-video)</h2>" in page
    assert "<h2>11. thanks(Latte) -&gt; menu() &quot;Done&quot; (first-and-last-frame)</h2>" in page
    failing = [item for shot in record["keys"] + record["moves"] for take in shot["takes"] for item in take["items"]
               if not item["passed"]]
    assert page.count('<li class="fail">') == len(failing) >= 6
    assert page.count("<video data-src=") == 33 and "<video src=" not in page


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
    assert f". Ledger: {record['ledger']['gpu_seconds']} GPU seconds, 0.0 pod hours, $0.00. Tape: " in page
    assert f"Tape: {record['tape']['bytes'] / 1e6:.1f} MB." in page


def pod_line(tape: str, seconds: int, usd: float) -> str:
    return json.dumps({"kind": "pod", "tape": tape, "at": "2026-11-09T12:00:00+00:00", "pod": "abc123",
                       "gpu": "NVIDIA H100 80GB HBM3", "usd_per_hour": 3.99, "started": "2026-11-09T11:00:00+00:00",
                       "stopped": "2026-11-09T12:00:00+00:00", "seconds": seconds, "usd": usd}) + "\n"


def test_dailies_command_rewrites_the_page_with_the_pod_totals_of_its_own_tape(first, tmp_path, cli, capsys):
    directory = again(first, tmp_path)
    with (directory / "ledger.jsonl").open("a") as file:
        file.write(pod_line(TAPE, 1800, 1.995) + pod_line("tape-wan3", 7200, 7.98))
    assert cli(directory, "dailies", "--story", "chalk") == 0
    record = json.loads((directory / TAPE / "dailies.json").read_text())
    assert (record["ledger"]["takes"], record["ledger"]["pods"]) == (33, 1)
    assert (record["ledger"]["pod_hours"], record["ledger"]["usd"]) == (0.5, 2.0)
    assert ", 0.5 pod hours, $2.00." in (directory / TAPE / "dailies.html").read_text()
    assert capsys.readouterr().out.startswith("wrote tapes/chalk/dailies.html with ")


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
    menu, enter = result.keys[0], result.moves[0]
    recipe = ["text-to-video", menu.prompt, "stand-in", 1]
    assert menu.takes[0].path.name == f"{hashlib.sha256(json.dumps(recipe).encode()).hexdigest()}.mp4"
    pinned = [hashlib.sha256((directory / TAPE / "keys" / f"{name}.png").read_bytes()).hexdigest()
              for name in ("menu", "order-espresso")]
    recipe = ["first-and-last-frame", enter.prompt, *pinned, "stand-in", 2]
    assert enter.takes[1].path.name == f"{hashlib.sha256(json.dumps(recipe).encode()).hexdigest()}.mp4"


def test_each_filmed_take_records_its_render_time_and_a_line_in_the_projects_ledger_naming_its_tape(first):
    directory, _, result = first
    for filmed in result.shots:
        for take in filmed.takes:
            assert take.seconds > 0 and take.gpu == "cpu"
            assert json.loads(take.path.with_suffix(".json").read_text()) == {"seconds": take.seconds, "gpu": "cpu"}
    lines = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]
    assert [(line["kind"], line["tape"], line["model"], line["shot"], line["mode"], line["seed"], line["gpu"])
            for line in lines] == [("take", TAPE, "stand-in", filmed.shot.title, filmed.shot.mode.value, take.seed, "cpu")
                                   for filmed in result.shots for take in filmed.takes]
    assert [line["seconds"] for line in lines] == [take.seconds for filmed in result.shots for take in filmed.takes]
    assert all(line["at"].endswith("+00:00") for line in lines)
    assert ledger.of(directory, directory / TAPE).totals() == {
        "takes": 33, "gpu_seconds": round(sum(line["seconds"] for line in lines), 1), "pods": 0, "pod_hours": 0.0, "usd": 0.0}
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
    lines = book.lines()
    assert [(line["shot"], line["request_id"], line["duration"], line["usd"]) for line in lines] == [
        (filmed.shot.title, f"request-{number}", 5.04, 0.504) for number, filmed in enumerate(result.shots)]
    menu = result.keys[0].kept
    assert json.loads(menu.path.with_suffix(".json").read_text()) == {
        "seconds": menu.seconds, "gpu": "cpu", "request_id": "request-0", "duration": 5.04, "usd": 0.504,
        "response": {"result": {"request": 0}}}
    record = dailies.read(tape)
    assert [take["usd"] for shot in record["keys"] + record["moves"] for take in shot["takes"]] == [0.504] * 11
    assert record["ledger"]["usd"] == 5.54
    assert ", 0.0 pod hours, $5.54. Tape: " in (tape / "dailies.html").read_text()
    again_ = rendered(directory, StandIn(), takes=1)
    assert book.lines() == lines
    assert [filmed.kept.usd for filmed in again_.shots] == [0.504] * 11
    with (directory / "ledger.jsonl").open("a") as file:
        file.write(pod_line(TAPE, 1800, 2.0))
    assert book.totals()["usd"] == 7.54


def test_takes_flag_sets_the_takes_per_shot_and_the_projects_model_renders(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER, "--takes", "1") == 0
    assert [call.seed for call in model.calls] == [1] * 11
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "1. key menu()  rendered 1 take, kept take 1"
    assert out[-1] == "rendered 11 of 11 shots -> tapes/chalk"
    with pytest.raises(SystemExit) as exit:
        cli(directory, *RENDER, "--takes", "0")
    assert exit.value.code == 2
    assert "--takes: must be at least 1, got 0" in capsys.readouterr().err


def test_model_flag_renders_with_another_model_than_the_projects(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    named, other = StandIn(flaw=clean), StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(named))
    monkeypatch.setitem(MODELS, "wan3.0", stand_in(other))
    assert cli(directory, *RENDER, "--model", "wan3.0", "--takes", "1") == 0
    assert (len(named.calls), len(other.calls)) == (0, 11)


@pytest.mark.parametrize("setting, error", [
    ("", "error: no model to render with; pass --model, or set model in [tool.videotape]\n"),
    ('model = "sora"\n', 'error: [tool.videotape] sets model = "sora", and the models are stand-in, wan2.2-5b, wan3.0\n'),
])
def test_a_project_without_a_model_it_can_render_with_says_so(tmp_path, cli, capsys, setting, error):
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('model = "stand-in"\n', setting))
    assert cli(directory, *RENDER) == 1
    assert capsys.readouterr() == ("", error)
    assert not (directory / "tapes").exists()


class Tuned(StandIn):
    def __init__(self, knobs: dict, **kwargs):
        super().__init__(**kwargs)
        self.knobs = knobs

    def settings(self, mode):
        return self.knobs


def test_a_models_settings_are_part_of_the_cache_key(first, tmp_path):
    directory = again(first, tmp_path)
    plan, chalk, tape = planned(directory), told(directory), directory / TAPE
    assert uncached(plan, chalk, StandIn(), 1, tape) == 0
    model = Tuned({"steps": 50, "frames": 81}, flaw=clean)
    assert uncached(plan, chalk, model, 1, tape) == 11
    rendered(directory, model, takes=1)
    assert len(model.calls) == 11
    assert uncached(plan, chalk, Tuned({"frames": 81, "steps": 50}), 1, tape) == 0
    for knobs in ({"steps": 40, "frames": 81}, {"steps": 50, "frames": 121}, {"steps": 50, "frames": 81, "shift": 5.0}):
        assert uncached(plan, chalk, Tuned(knobs), 1, tape) == 11, knobs


def test_editing_one_line_rerenders_its_key_and_only_the_moves_that_touch_it(first, tmp_path, cli, capsys, monkeypatch):
    directory = again(first, tmp_path, 'vt.Heading("Corner Cafe")', 'vt.Heading("The Corner Cafe")')
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER, "--takes", "3") == 0
    assert len(model.calls) == 15
    assert capsys.readouterr().out.splitlines() == [
        "1. key menu()  rendered 3 takes, kept take 1",
        "2. key order(Espresso)  cached, kept take 1",
        "3. key order(Latte)  cached, kept take 1",
        "4. key thanks(Espresso)  cached, kept take 1",
        "5. key thanks(Latte)  cached, kept take 3",
        '6. menu() -> order(Espresso) "Espresso, $3"  rendered 3 takes, kept take 1',
        '7. menu() -> order(Latte) "Latte, $5"  rendered 3 takes, kept take 1',
        '8. order(Espresso) -> thanks(Espresso) "Order"  cached, kept take 1',
        '9. order(Latte) -> thanks(Latte) "Order"  cached, kept take 1',
        '10. thanks(Espresso) -> menu() "Done"  rendered 3 takes, kept take 1',
        '11. thanks(Latte) -> menu() "Done"  rendered 3 takes, kept take 1',
        "rendered 5 of 11 shots -> tapes/chalk",
    ]


def test_cli_render_writes_everything_then_fails_on_a_failing_kept_take(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    misspelt_keys = lambda mode, prompt, seed: Flaw.MISSPELL if mode is Mode.TEXT_TO_VIDEO else Flaw.NONE
    monkeypatch.setitem(MODELS, "stand-in", stand_in(StandIn(flaw=misspelt_keys)))
    assert cli(directory, *RENDER, "--takes", "1") == 1
    err = capsys.readouterr().err.splitlines()
    assert [line.split("  kept take 1 fails ")[0] for line in err if " fails text " in line] == [
        f"fail: {number}. key {state}" for number, state in enumerate(STATES, 1)]
    assert all(" fails text " in line or " fails hotspot " in line for line in err)
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
    assert capsys.readouterr().err.splitlines() == [
        'fail: 1. key hall()  kept take 1 fails hotspot "Go in": not found',
        'fail: 1. key hall()  kept take 1 fails text "Go in": read nothing, CER 1.000']
    assert ('hotspot &quot;Go in&quot;</span><span class="result">not found'
            in (tmp_path / "tapes" / "bare" / "dailies.html").read_text())
    assert [call.mode for call in model.calls].count(Mode.FIRST_AND_LAST_FRAME) == 4


def test_out_writes_another_tape_whose_ledger_lines_and_totals_are_its_own(first, tmp_path, cli, capsys, monkeypatch):
    directory = again(first, tmp_path)
    before = tape_files(directory)
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", stand_in(model))
    assert cli(directory, *RENDER, "--takes", "1", "--out", "tape-b") == 0
    out = directory / "tape-b"
    assert len(model.calls) == 11
    assert capsys.readouterr().out.splitlines()[-1] == "rendered 11 of 11 shots -> tape-b"
    assert json.loads((out / "tape.json").read_text())["opening"] == {"clip": "moves/opening.mp4", "lands": "menu()"}
    assert sorted(path.name for path in (out / "keys").iterdir()) == sorted(name for name in before if name.endswith(".png"))
    lines = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]
    assert [line["tape"] for line in lines] == [TAPE] * 33 + ["tape-b"] * 11
    assert [line["seed"] for line in Ledger(directory / "ledger.jsonl", "tape-b").lines()] == [1] * 11
    assert dailies.read(out)["ledger"]["takes"] == 11
    assert dailies.read(out)["title"] == "Corner Cafe"
    assert tape_files(directory) == before


def test_cli_render_rejects_a_model_that_does_not_exist(tmp_path, cli, capsys):
    with pytest.raises(SystemExit) as exit:
        cli(copy_of("cafe", tmp_path), *RENDER, "--model", "sora")
    assert exit.value.code == 2
    assert "invalid choice: 'sora'" in capsys.readouterr().err
