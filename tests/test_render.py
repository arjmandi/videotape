import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videotape import dailies, frames
from videotape.checks import MAX_DIFFERENCE
from videotape.cli import main
from videotape.loader import load
from videotape.model import MODELS
from videotape.render import render
from videotape.shots import Mode, plan
from videotape.standin import Flaw, StandIn, StandInEye

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
CREATE_ACCOUNT = 'The button labelled "Create an account" is pressed.'
SIGN_UP = 'The button labelled "Sign up" is pressed.'


def flaws(prompt: str, seed: int) -> Flaw:
    if CREATE_ACCOUNT in prompt:
        return {1: Flaw.MISSPELL, 2: Flaw.DROP_BUTTON}.get(seed, Flaw.NONE)
    if SIGN_UP in prompt:
        return {1: Flaw.WRONG_START, 2: Flaw.WRONG_END}.get(seed, Flaw.NONE)
    return Flaw.NONE


class Witness(StandIn):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.existed: list[bool] = []

    def image_to_video(self, prompt, start, seed, out):
        self.existed.append(start.is_file())
        super().image_to_video(prompt, start, seed, out)

    def first_last_frame(self, prompt, start, end, seed, out):
        self.existed += [start.is_file(), end.is_file()]
        super().first_last_frame(prompt, start, end, seed, out)


@pytest.fixture(scope="module")
def first(tmp_path_factory):
    directory = tmp_path_factory.mktemp("first") / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape"))
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


def test_model_is_called_three_times_per_shot_in_plan_order(first):
    directory, model, _ = first
    keys = directory / "tape" / "keys"
    expected = [(shot, seed) for shot in plan(load(directory)) for seed in (1, 2, 3)]
    assert [(call.mode, call.prompt, call.seed) for call in model.calls] == [
        (shot.mode, shot.prompt, seed) for shot, seed in expected]
    for call, (shot, _) in zip(model.calls, expected):
        assert call.start == (keys / f"{shot.start}.png" if shot.start else None)
        assert call.end == (keys / f"{shot.land}.png" if shot.mode is Mode.FIRST_AND_LAST_FRAME else None)
    assert model.existed == [True] * 18


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
    assert len(moves) == 6
    for move in moves:
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                                "stream=codec_name,pix_fmt,width,height,r_frame_rate", "-of", "csv=p=0", str(move)],
                               capture_output=True, text=True, check=True)
        assert probe.stdout.strip() == "h264,1280,704,yuv420p,24/1"
    assert (tape / "dailies.html").is_file()


def test_hotspots_sit_where_the_kept_take_drew_its_buttons(first):
    directory, model, result = first
    scenes = json.loads((directory / "tape" / "tape.json").read_text())["scenes"]
    checked = 0
    for filmed in result.shots:
        if filmed.key is None:
            continue
        call = next(c for c in model.calls if c.prompt == filmed.shot.prompt and c.seed == filmed.kept.seed)
        drawn = {d.text: d.box for d in model.drawn[call.out] if d.button}
        hotspots = scenes[filmed.shot.land]["hotspots"]
        assert [hotspot["label"] for hotspot in hotspots] == list(drawn)
        for hotspot in hotspots:
            box, truth = hotspot["box"], drawn[hotspot["label"]]
            assert abs(box["x"] * 1280 - truth.x) <= 2 and abs(box["w"] * 1280 - truth.w) <= 2
            assert abs(box["y"] * 704 - truth.y) <= 2 and abs(box["h"] * 704 - truth.h) <= 2
            checked += 1
    assert checked == 5


def test_each_key_is_its_kept_takes_last_frame(first):
    directory, _, result = first
    tape = directory / "tape"
    keyed = [filmed for filmed in result.shots if filmed.key]
    assert [filmed.key for filmed in keyed] == [tape / "keys" / f"{filmed.shot.land}.png" for filmed in keyed]
    for filmed in keyed:
        assert frames.difference(frames.read_png(filmed.key), frames.last_frame(filmed.kept.path)) < 0.001
    for filmed in result.shots:
        assert (tape / "moves" / f"{filmed.shot.move}.mp4").read_bytes() == filmed.kept.path.read_bytes()


def test_best_take_is_kept(first):
    _, model, result = first
    signup = next(filmed for filmed in result.shots if CREATE_ACCOUNT in filmed.shot.prompt)
    misspelt_call = next(c for c in model.calls if c.prompt == signup.shot.prompt and c.seed == 1)
    drawn = {d.text for d in model.drawn[misspelt_call.out]}
    [misspelt] = [text for text in ("Create your account", "Email", "Password", "Sign up") if text not in drawn]
    misspelt_take, dropped_take, clean_take = signup.takes
    assert signup.kept is clean_take
    assert misspelt_take.checks.text[misspelt].cer > 0
    assert f'text "{misspelt}"' in [item.name for item in misspelt_take.checks.failures]
    assert dropped_take.checks.buttons == {"Sign up": None}
    assert clean_take.checks.failures == []

    login = next(filmed for filmed in result.shots if SIGN_UP in filmed.shot.prompt)
    wrong_start, wrong_end, clean = login.takes
    assert login.kept is clean
    assert wrong_start.checks.start > MAX_DIFFERENCE
    assert [item.name for item in wrong_start.checks.failures] == ["start"]
    assert wrong_end.checks.end > MAX_DIFFERENCE
    assert [item.name for item in wrong_end.checks.failures] == ["end"]
    assert clean.checks.failures == []


def test_dailies_page_is_a_view_of_its_record_with_a_keys_section(first):
    tape = first[0] / "tape"
    record = json.loads((tape / "dailies.json").read_text())
    assert (tape / "dailies.html").read_text() == dailies.page(record)
    assert record["keys"]["checks"] == "stand-in"
    scenes = record["keys"]["scenes"]
    assert [(scene["scene"], scene["key"]) for scene in scenes] == [
        (name, f"keys/{name}.png") for name in ("welcome", "entrance", "login", "signup", "gallery")]
    assert [(item["name"], item["passed"]) for item in scenes[0]["items"]] == [
        ('button "Enter shop"', True), ('text "Brushstroke Surf Co."', True),
        ('text "Hand-painted surfboards from California"', True), ('text "Enter shop"', True)]
    assert scenes[0]["items"][0]["result"].startswith("found at ")
    assert scenes[0]["items"][1]["result"] == 'read "Brushstroke Surf Co.", CER 0.000'
    page = (tape / "dailies.html").read_text()
    assert '<section class="shot keys" id="keys">' in page
    assert "5 keys checked by stand-in, all passing" in page


def test_second_render_is_cached(first, tmp_path):
    directory = copy_of(first, tmp_path)
    before = tape_files(directory)
    model = StandIn()
    result = render(directory, model, StandInEye())
    assert model.calls == []
    assert [filmed.rendered for filmed in result.shots] == [0] * 6
    assert tape_files(directory) == before


@pytest.mark.parametrize("old, new, rerendered", [
    ('"Create your account"', '"Open your account"', ["Create an account", "Sign up"]),
    ('"Log in"', '"Sign in"', ["I have an account", "Sign up"]),
])
def test_editing_a_line_rerenders_only_its_shots_and_their_dependents(first, tmp_path, old, new, rerendered):
    directory = copy_of(first, tmp_path, old, new)
    model = StandIn()
    result = render(directory, model, StandInEye())
    assert len(model.calls) == 6
    assert [filmed.shot.label for filmed in result.shots if filmed.rendered] == rerendered
    assert all(filmed.rendered in (0, 3) for filmed in result.shots)


def test_cli_render_prints_each_shot(first, tmp_path, capsys, monkeypatch):
    directory = copy_of(first, tmp_path, '"The gallery"', '"The board room"')
    monkeypatch.setitem(MODELS, "stand-in", lambda: StandIn(flaw=lambda prompt, seed: Flaw.NONE))
    assert main(["render", str(directory), "--model", "stand-in", "--checks", "stand-in"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "1. opening -> welcome  cached, kept take 1",
        '2. welcome -> entrance "Enter shop"  cached, kept take 1',
        '3. entrance -> login "I have an account"  cached, kept take 1',
        '4. entrance -> signup "Create an account"  cached, kept take 3',
        '5. entrance -> gallery "Browse as guest"  rendered 3 takes, kept take 1',
        '6. signup -> login "Sign up"  cached, kept take 3',
        f"rendered 1 of 6 shots -> {directory / 'tape'}",
    ]


def test_cli_render_writes_everything_then_fails_on_a_failing_kept_take(first, tmp_path, capsys, monkeypatch):
    directory = copy_of(first, tmp_path, '"The gallery"', '"The board room"')
    monkeypatch.setitem(MODELS, "stand-in", lambda: StandIn(flaw=lambda prompt, seed: Flaw.MISSPELL))
    assert main(["render", str(directory), "--model", "stand-in"]) == 1
    err = capsys.readouterr().err
    assert err.startswith('fail: 5. entrance -> gallery "Browse as guest"  kept take 1 fails text "The board room": read "')
    assert "kept take fails checks" in (directory / "tape" / "dailies.html").read_text()
    assert "entrance--browse-as-guest" in json.loads((directory / "tape" / "tape.json").read_text())["moves"]


@pytest.mark.parametrize("flag", ["--model", "--checks"])
def test_cli_render_rejects_an_unknown_model_or_checks(tmp_path, capsys, flag):
    arguments = {"--model": "stand-in", "--checks": "stand-in", flag: "sora"}
    with pytest.raises(SystemExit) as exit:
        main(["render", str(tmp_path), *(word for pair in arguments.items() for word in pair)])
    assert exit.value.code == 2
    assert "invalid choice: 'sora'" in capsys.readouterr().err
