import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videotape import dailies, frames, ledger
from videotape.checks import MAX_DIFFERENCE
from videotape.cli import main
from videotape.fal import Receipt
from videotape.loader import load
from videotape.model import MODELS
from videotape.render import render
from videotape.shots import Mode, plan
from videotape.standin import Flaw, StandIn, StandInEye

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
SIGNUP_KEY = 'The text reads "Create your account"'
SIGN_UP_MOVE = 'The button labelled "Sign up" is pressed.'


def flaws(mode: Mode, prompt: str, seed: int) -> Flaw:
    if SIGNUP_KEY in prompt:
        return {1: Flaw.MISSPELL, 2: Flaw.DROP_BUTTON}.get(seed, Flaw.NONE)
    if SIGN_UP_MOVE in prompt:
        return {1: Flaw.WRONG_START, 2: Flaw.WRONG_END}.get(seed, Flaw.NONE)
    return Flaw.NONE


def clean(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.NONE


class Witness(StandIn):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.existed: list[bool] = []

    def first_last_frame(self, prompt, start, end, seed, out):
        self.existed += [start.is_file(), end.is_file()]
        super().first_last_frame(prompt, start, end, seed, out)


@pytest.fixture(scope="module")
def first(tmp_path_factory):
    directory = tmp_path_factory.mktemp("first") / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    model = Witness(flaw=flaws)
    return directory, model, render(directory, model, StandInEye())


def copy_of(first, tmp_path: Path, old: str | None = None, new: str | None = None) -> Path:
    directory = tmp_path / "surf_shop"
    shutil.copytree(first[0], directory)
    if old is not None:
        screenplay = directory / "screenplay.py"
        source = screenplay.read_text()
        assert source.count(old) == 1
        screenplay.write_text(source.replace(old, new))
    return directory


def tape_files(directory: Path) -> dict[str, bytes]:
    tape = directory / "tape"
    return {path.name: path.read_bytes() for path in [tape / "tape.json", *sorted((tape / "keys").iterdir())]}


def test_every_key_is_filmed_before_any_move_with_three_takes_each(first):
    directory, model, _ = first
    keys = directory / "tape" / "keys"
    expected = [(shot, seed) for shot in plan(load(directory)) for seed in (1, 2, 3)]
    assert [(call.mode, call.prompt, call.seed) for call in model.calls] == [
        (shot.mode, shot.prompt, seed) for shot, seed in expected]
    assert [call.mode for call in model.calls] == [Mode.TEXT_TO_VIDEO] * 15 + [Mode.FIRST_AND_LAST_FRAME] * 15
    for call, (shot, _) in zip(model.calls, expected):
        if shot.mode is Mode.FIRST_AND_LAST_FRAME:
            assert (call.start, call.end) == (keys / f"{shot.start}.png", keys / f"{shot.land}.png")
        else:
            assert (call.start, call.end) == (None, None)
    assert model.existed == [True] * 30


def test_tape_lists_scenes_hotspots_and_moves(first):
    tape = first[0] / "tape"
    data = json.loads((tape / "tape.json").read_text())
    assert data["size"] == {"width": 1280, "height": 704}
    assert data["fps"] == 24
    assert data["opening"] == {"clip": "moves/opening.mp4", "lands": "welcome"}
    assert {name: scene["key"] for name, scene in data["scenes"].items()} == {
        name: f"keys/{name}.png" for name in ("welcome", "entrance", "login", "signup", "gallery")}
    assert {name: [(h["label"], h["move"]) for h in scene["hotspots"]] for name, scene in data["scenes"].items()} == {
        "welcome": [("Enter shop", "welcome--enter-shop")],
        "entrance": [("I have an account", "entrance--i-have-an-account"),
                     ("Create an account", "entrance--create-an-account"),
                     ("Browse as guest", "entrance--browse-as-guest")],
        "login": [],
        "signup": [("Sign up", "signup--sign-up")],
        "gallery": [],
    }
    assert data["moves"] == {
        move: {"clip": f"moves/{move}.mp4", "lands": lands} for move, lands in [
            ("welcome--enter-shop", "entrance"), ("entrance--i-have-an-account", "login"),
            ("entrance--create-an-account", "signup"), ("entrance--browse-as-guest", "gallery"),
            ("signup--sign-up", "login")]}


def test_tape_files_are_keys_and_browser_playable_clips(first):
    tape = first[0] / "tape"
    keys = sorted((tape / "keys").iterdir())
    assert [key.name for key in keys] == ["entrance.png", "gallery.png", "login.png", "signup.png", "welcome.png"]
    assert all((frames.read_png(key).width, frames.read_png(key).height) == (1280, 704) for key in keys)
    moves = sorted((tape / "moves").iterdir())
    assert [move.name for move in moves] == ["entrance--browse-as-guest.mp4", "entrance--create-an-account.mp4",
                                             "entrance--i-have-an-account.mp4", "opening.mp4", "signup--sign-up.mp4",
                                             "welcome--enter-shop.mp4"]
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
    directory = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    render(directory, Taller(flaw=clean), StandInEye(), takes=1)
    tape = directory / "tape"
    data = json.loads((tape / "tape.json").read_text())
    assert (data["size"], data["fps"]) == ({"width": 1280, "height": 720}, 24)
    assert {(frames.read_png(key).width, frames.read_png(key).height) for key in (tape / "keys").iterdir()} == {(1280, 720)}
    [enter] = data["scenes"]["welcome"]["hotspots"]
    [short] = json.loads((first[0] / "tape" / "tape.json").read_text())["scenes"]["welcome"]["hotspots"]
    assert abs(enter["box"]["y"] * 720 - (short["box"]["y"] * 704 + 8)) <= 1
    assert abs(enter["box"]["h"] * 720 - short["box"]["h"] * 704) <= 1


def test_hotspots_sit_where_the_kept_take_drew_its_buttons(first):
    directory, model, result = first
    scenes = json.loads((directory / "tape" / "tape.json").read_text())["scenes"]
    checked = 0
    for filmed in result.keys:
        call = next(c for c in model.calls if c.prompt == filmed.shot.prompt and c.seed == filmed.kept.seed)
        drawn = {d.text: d.box for d in model.drawn[call.out] if d.button}
        hotspots = scenes[filmed.shot.scene]["hotspots"]
        assert [hotspot["label"] for hotspot in hotspots] == list(drawn)
        for hotspot in hotspots:
            box, truth = hotspot["box"], drawn[hotspot["label"]]
            assert abs(box["x"] * 1280 - truth.x) <= 2 and abs(box["w"] * 1280 - truth.w) <= 2
            assert abs(box["y"] * 704 - truth.y) <= 2 and abs(box["h"] * 704 - truth.h) <= 2
            checked += 1
    assert checked == 5


def test_each_key_is_its_kept_takes_last_frame_and_welcomes_clip_is_the_opening(first):
    directory, _, result = first
    tape = directory / "tape"
    for filmed in result.keys:
        key = tape / "keys" / f"{filmed.shot.scene}.png"
        assert frames.difference(frames.read_png(key), frames.last_frame(filmed.kept.path)) < 0.001
    assert (tape / "moves" / "opening.mp4").read_bytes() == result.keys[0].kept.path.read_bytes()
    for filmed in result.moves:
        assert (tape / "moves" / f"{filmed.shot.move}.mp4").read_bytes() == filmed.kept.path.read_bytes()


def test_a_key_keeps_the_take_with_the_most_buttons_then_the_least_character_error(first):
    _, model, result = first
    signup = next(filmed for filmed in result.keys if filmed.shot.scene == "signup")
    misspelt_call = next(c for c in model.calls if c.prompt == signup.shot.prompt and c.seed == 1)
    drawn = {d.text for d in model.drawn[misspelt_call.out]}
    [misspelt] = [text for text in ("Create your account", "Email", "Password", "Sign up") if text not in drawn]
    misspelt_take, dropped_take, clean_take = signup.takes
    assert signup.kept is clean_take
    assert misspelt_take.checks.text[misspelt].cer > 0
    assert [item.name for item in misspelt_take.checks.failures] == [f'text "{misspelt}"']
    assert dropped_take.checks.buttons == {"Sign up": None}
    assert [item.name for item in dropped_take.checks.failures] == ['button "Sign up"', 'text "Sign up"']
    assert clean_take.checks.failures == []
    # A missing button costs more than a misspelt line, whatever the seeds.
    assert clean_take.checks.rank(3) < misspelt_take.checks.rank(1) < dropped_take.checks.rank(2)


def test_a_move_keeps_the_take_whose_frames_sit_closest_to_its_keys(first):
    _, _, result = first
    sign_up = next(filmed for filmed in result.moves if filmed.shot.move == "signup--sign-up")
    wrong_start, wrong_end, clean = sign_up.takes
    assert sign_up.kept is clean
    assert wrong_start.checks.start > MAX_DIFFERENCE and wrong_start.checks.end <= MAX_DIFFERENCE
    assert [item.name for item in wrong_start.checks.failures] == ["start"]
    assert wrong_end.checks.end > MAX_DIFFERENCE and wrong_end.checks.start <= MAX_DIFFERENCE
    assert [item.name for item in wrong_end.checks.failures] == ["end"]
    assert clean.checks.failures == []
    assert clean.checks.rank(3) < wrong_start.checks.rank(1) and clean.checks.rank(3) < wrong_end.checks.rank(2)


def test_dailies_page_is_a_view_of_its_record(first):
    directory, _, result = first
    tape = directory / "tape"
    record = json.loads((tape / "dailies.json").read_text())
    page = (tape / "dailies.html").read_text()
    assert page == dailies.page(record)
    assert record["checks"] == "stand-in"
    assert [(key["scene"], key["key"], key["title"]) for key in record["keys"]] == [
        (name, f"keys/{name}.png", f"key {name}") for name in ("welcome", "entrance", "login", "signup", "gallery")]
    assert [(item["name"], item["passed"]) for item in record["keys"][0]["items"]] == [
        ('button "Enter shop"', True), ('text "Brushstroke Surf Co."', True),
        ('text "Hand-painted surfboards from California"', True), ('text "Enter shop"', True)]
    assert record["keys"][0]["items"][0]["result"].startswith("found at ")
    assert [move["move"] for move in record["moves"]] == [filmed.shot.move for filmed in result.moves]
    assert '<section class="shot keys" id="keys">' in page
    assert "5 keys checked by stand-in, all passing" in page
    assert page.count('<section class="shot" id="shot-') == 10
    assert "<h2>1. key welcome (text-to-video)</h2>" in page
    assert "<h2>10. signup -&gt; login &quot;Sign up&quot; (first-and-last-frame)</h2>" in page
    # The signup key's dropped take says so, in the open.
    assert 'button &quot;Sign up&quot;</span><span class="result">not found' in page


def test_dailies_record_has_each_moves_seams_and_the_tapes_size(first):
    directory, _, result = first
    tape = directory / "tape"
    record = json.loads((tape / "dailies.json").read_text())
    page = (tape / "dailies.html").read_text()
    for move, filmed in zip(record["moves"], result.moves):
        for take, filmed_take in zip(move["takes"], filmed.takes):
            assert (take["start"], take["end"]) == (filmed_take.checks.start, filmed_take.checks.end)
        kept = filmed.kept.checks
        assert f"Seams: leaves {filmed.shot.start} by {kept.start:.3f}, enters {filmed.shot.land} by {kept.end:.3f}." in page
    played = [tape / "tape.json", *(tape / "keys").iterdir(), *(tape / "moves").iterdir()]
    assert record["tape"] == {"bytes": sum(path.stat().st_size for path in played)}
    assert record["tape"]["bytes"] > 100_000
    assert record["ledger"] == ledger.totals(ledger.read(tape))
    assert f". Ledger: {record['ledger']['gpu_seconds']} GPU seconds, 0.0 pod hours, $0.00. Tape: " in page
    assert f"Tape: {record['tape']['bytes'] / 1e6:.1f} MB." in page


def test_dailies_command_rewrites_the_page_with_the_ledgers_pod_totals(first, tmp_path, capsys):
    directory = copy_of(first, tmp_path)
    tape = directory / "tape"
    ledger.append(tape, {"kind": "pod", "at": "2026-11-09T12:00:00+00:00", "pod": "abc123", "gpu": "NVIDIA H100 80GB HBM3",
                         "usd_per_hour": 3.99, "started": "2026-11-09T11:00:00+00:00", "stopped": "2026-11-09T12:00:00+00:00",
                         "seconds": 1800, "usd": 1.995})
    assert main(["dailies", str(directory)]) == 0
    record = json.loads((tape / "dailies.json").read_text())
    assert record["ledger"]["pods"] == 1 and record["ledger"]["pod_hours"] == 0.5 and record["ledger"]["usd"] == 2.0
    assert ", 0.5 pod hours, $2.00." in (tape / "dailies.html").read_text()
    assert capsys.readouterr().out.startswith(f"wrote {tape / 'dailies.html'} with ")


def test_second_render_is_cached(first, tmp_path):
    directory = copy_of(first, tmp_path)
    before = tape_files(directory)
    model = StandIn()
    result = render(directory, model, StandInEye())
    assert model.calls == []
    assert [filmed.rendered for filmed in result.shots] == [0] * 10
    assert tape_files(directory) == before


def test_take_cache_keys_are_stable_so_paid_takes_survive_a_code_change(first):
    # sha256 of the JSON list [mode, prompt, model name, seed] for the welcome key's first take. A move's list carries
    # the sha256 of each key image it is pinned to between the prompt and the model name.
    welcome = first[2].keys[0]
    assert welcome.takes[0].path.name == "cca4cc7de81bf1ca22ecc0491a35f28ef1ef74433db37a7bf02c52896f7a906d.mp4"


class Tuned(StandIn):
    def __init__(self, knobs: dict, **kwargs):
        super().__init__(**kwargs)
        self.knobs = knobs

    def settings(self, mode):
        return self.knobs


def test_each_filmed_take_records_its_render_time_and_a_ledger_line(first):
    directory, _, result = first
    tape = directory / "tape"
    for filmed in result.shots:
        for take in filmed.takes:
            assert take.seconds > 0 and take.gpu == "cpu"
            assert json.loads(take.path.with_suffix(".json").read_text()) == {"seconds": take.seconds, "gpu": "cpu"}
    lines = ledger.read(tape)
    assert [(line["kind"], line["model"], line["shot"], line["mode"], line["seed"], line["gpu"]) for line in lines] == [
        ("take", "stand-in", filmed.shot.title, filmed.shot.mode.value, take.seed, "cpu")
        for filmed in result.shots for take in filmed.takes]
    assert [line["seconds"] for line in lines] == [take.seconds for filmed in result.shots for take in filmed.takes]
    assert all(line["at"].endswith("+00:00") for line in lines)
    assert ledger.totals(lines) == {"takes": 30, "gpu_seconds": round(sum(line["seconds"] for line in lines), 1),
                                    "pods": 0, "pod_hours": 0.0, "usd": 0.0}


def test_cached_takes_keep_their_render_time_and_add_no_ledger_lines(first, tmp_path):
    directory = copy_of(first, tmp_path)
    before = ledger.read(directory / "tape")
    result = render(directory, StandIn(), StandInEye())
    assert [[(take.seconds, take.gpu) for take in filmed.takes] for filmed in result.shots] == \
        [[(take.seconds, take.gpu) for take in filmed.takes] for filmed in first[2].shots]
    assert ledger.read(directory / "tape") == before


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
    directory = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    result = render(directory, Billed(flaw=clean), StandInEye(), takes=1)
    tape = directory / "tape"
    lines = ledger.read(tape)
    assert [(line["shot"], line["request_id"], line["duration"], line["usd"]) for line in lines] == [
        (filmed.shot.title, f"request-{number}", 5.04, 0.504) for number, filmed in enumerate(result.shots)]
    welcome = result.keys[0].kept
    assert json.loads(welcome.path.with_suffix(".json").read_text()) == {
        "seconds": welcome.seconds, "gpu": "cpu", "request_id": "request-0", "duration": 5.04, "usd": 0.504,
        "response": {"result": {"request": 0}}}
    record = dailies.read(tape)
    assert [take["usd"] for shot in record["keys"] + record["moves"] for take in shot["takes"]] == [0.504] * 10
    assert record["ledger"]["usd"] == 5.04
    assert ", 0.0 pod hours, $5.04. Tape: " in (tape / "dailies.html").read_text()
    again = render(directory, StandIn(), StandInEye(), takes=1)
    assert ledger.read(tape) == lines
    assert [filmed.kept.usd for filmed in again.shots] == [0.504] * 10
    ledger.append(tape, {"kind": "pod", "at": "2026-11-09T12:00:00+00:00", "pod": "abc123", "gpu": "NVIDIA H100 80GB HBM3",
                         "usd_per_hour": 4.0, "started": "2026-11-09T11:30:00+00:00", "stopped": "2026-11-09T12:00:00+00:00",
                         "seconds": 1800, "usd": 2.0})
    assert ledger.totals(ledger.read(tape))["usd"] == 7.04


def test_takes_flag_sets_the_takes_per_shot(tmp_path, capsys, monkeypatch):
    directory = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", lambda: model)
    assert main(["render", str(directory), "--model", "stand-in", "--takes", "1"]) == 0
    assert [call.seed for call in model.calls] == [1] * 10
    assert capsys.readouterr().out.splitlines()[0] == "1. key welcome  rendered 1 take, kept take 1"
    with pytest.raises(SystemExit) as exit:
        main(["render", str(directory), "--model", "stand-in", "--takes", "0"])
    assert exit.value.code == 2
    assert "--takes: must be at least 1, got 0" in capsys.readouterr().err


def test_a_models_settings_are_part_of_the_cache_key(first, tmp_path):
    directory = copy_of(first, tmp_path)
    model = Tuned({"steps": 50, "frames": 81})
    render(directory, model, StandInEye())
    assert len(model.calls) == 30
    same = Tuned({"frames": 81, "steps": 50})
    render(directory, same, StandInEye())
    assert same.calls == []
    for knobs in ({"steps": 40, "frames": 81}, {"steps": 50, "frames": 121}, {"steps": 50, "frames": 81, "shift": 5.0}):
        changed = Tuned(knobs)
        render(directory, changed, StandInEye())
        assert len(changed.calls) == 30, knobs


def test_editing_signups_line_rerenders_its_key_and_only_the_moves_that_touch_it(first, tmp_path):
    directory = copy_of(first, tmp_path, '"Create your account"', '"Open your account"')
    model = StandIn()
    result = render(directory, model, StandInEye())
    assert len(model.calls) == 9
    assert [filmed.shot.title for filmed in result.shots if filmed.rendered] == [
        "key signup", 'entrance -> signup "Create an account"', 'signup -> login "Sign up"']
    assert all(filmed.rendered in (0, 3) for filmed in result.shots)


def test_editing_a_move_rerenders_only_that_move(first, tmp_path):
    directory = copy_of(first, tmp_path, "The camera walks through the open door.", "The camera strolls in.")
    model = StandIn()
    result = render(directory, model, StandInEye())
    assert len(model.calls) == 3
    assert [filmed.shot.title for filmed in result.shots if filmed.rendered] == ['welcome -> entrance "Enter shop"']


def test_cli_render_prints_each_shot(first, tmp_path, capsys, monkeypatch):
    directory = copy_of(first, tmp_path, '"The gallery"', '"The board room"')
    monkeypatch.setitem(MODELS, "stand-in", lambda: StandIn(flaw=clean))
    assert main(["render", str(directory), "--model", "stand-in", "--checks", "stand-in"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "1. key welcome  cached, kept take 1",
        "2. key entrance  cached, kept take 1",
        "3. key login  cached, kept take 1",
        "4. key signup  cached, kept take 3",
        "5. key gallery  rendered 3 takes, kept take 1",
        '6. welcome -> entrance "Enter shop"  cached, kept take 1',
        '7. entrance -> login "I have an account"  cached, kept take 1',
        '8. entrance -> signup "Create an account"  cached, kept take 1',
        '9. entrance -> gallery "Browse as guest"  rendered 3 takes, kept take 1',
        '10. signup -> login "Sign up"  cached, kept take 3',
        f"rendered 2 of 10 shots -> {directory / 'tape'}",
    ]


def test_cli_render_writes_everything_then_fails_on_a_failing_kept_take(first, tmp_path, capsys, monkeypatch):
    directory = copy_of(first, tmp_path, '"The gallery"', '"The board room"')
    misspelt_keys = lambda mode, prompt, seed: Flaw.MISSPELL if mode is Mode.TEXT_TO_VIDEO else Flaw.NONE
    monkeypatch.setitem(MODELS, "stand-in", lambda: StandIn(flaw=misspelt_keys))
    assert main(["render", str(directory), "--model", "stand-in"]) == 1
    err = capsys.readouterr().err
    assert err.startswith('fail: 5. key gallery  kept take 1 fails text "The board room": read "')
    assert "kept take fails checks" in (directory / "tape" / "dailies.html").read_text()
    assert "entrance--browse-as-guest" in json.loads((directory / "tape" / "tape.json").read_text())["moves"]


def test_a_button_the_checks_do_not_find_has_no_hotspot_but_its_move_still_renders(tmp_path, capsys, monkeypatch):
    directory = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    drop = lambda mode, prompt, seed: Flaw.DROP_BUTTON if "bold black letters" in prompt else Flaw.NONE
    model = StandIn(flaw=drop)
    monkeypatch.setitem(MODELS, "stand-in", lambda: model)
    assert main(["render", str(directory), "--model", "stand-in"]) == 1
    data = json.loads((directory / "tape" / "tape.json").read_text())
    record = json.loads((directory / "tape" / "dailies.json").read_text())
    err = capsys.readouterr().err.splitlines()
    unfound = 0
    for key in record["keys"]:
        kept = next(take for take in key["takes"] if take["kept"])
        found = [item["name"][8:-1] for item in kept["items"] if item["name"].startswith("button") and item["passed"]]
        missing = [item["name"][8:-1] for item in kept["items"] if item["name"].startswith("button") and not item["passed"]]
        assert [hotspot["label"] for hotspot in data["scenes"][key["scene"]]["hotspots"]] == found
        for label in missing:
            assert f'fail: {record["keys"].index(key) + 1}. key {key["scene"]}  kept take {kept["seed"]} fails button "{label}": not found' in err
            assert f'button &quot;{label}&quot;</span><span class="result">not found' in (directory / "tape" / "dailies.html").read_text()
        unfound += len(missing)
    assert unfound == 3
    assert sorted(data["moves"]) == ["entrance--browse-as-guest", "entrance--create-an-account", "entrance--i-have-an-account",
                                     "signup--sign-up", "welcome--enter-shop"]
    assert [call.mode for call in model.calls].count(Mode.FIRST_AND_LAST_FRAME) == 15


def test_out_writes_the_tape_beside_the_screenplays_own(first, tmp_path, capsys, monkeypatch):
    directory = copy_of(first, tmp_path)
    before = tape_files(directory)
    out = directory / "tape-b"
    model = StandIn(flaw=clean)
    monkeypatch.setitem(MODELS, "stand-in", lambda: model)
    assert main(["render", str(directory), "--model", "stand-in", "--takes", "1", "--out", str(out)]) == 0
    assert len(model.calls) == 10
    assert capsys.readouterr().out.splitlines()[-1] == f"rendered 10 of 10 shots -> {out}"
    assert json.loads((out / "tape.json").read_text())["opening"] == {"clip": "moves/opening.mp4", "lands": "welcome"}
    assert sorted(path.name for path in (out / "keys").iterdir()) == sorted(name for name in before if name.endswith(".png"))
    assert [line["seed"] for line in ledger.read(out)] == [1] * 10
    assert dailies.read(out)["title"] == "Brushstroke Surf Co."
    assert tape_files(directory) == before


@pytest.mark.parametrize("flag", ["--model", "--checks"])
def test_cli_render_rejects_an_unknown_model_or_checks(tmp_path, capsys, flag):
    arguments = {"--model": "stand-in", "--checks": "stand-in", flag: "sora"}
    with pytest.raises(SystemExit) as exit:
        main(["render", str(tmp_path), *(word for pair in arguments.items() for word in pair)])
    assert exit.value.code == 2
    assert "invalid choice: 'sora'" in capsys.readouterr().err
