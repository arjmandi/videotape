import base64
import json
import subprocess
import urllib.request
from pathlib import Path

import pytest

from conftest import FIXTURES, copy_of, planned, told, words
from videotape import ledger, wan3
from videotape.fal import Fal, FalError, Receipt
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.standin import StandInEye

KEY = "fal-test-key-0123456789abcdef"
SHOTS = {shot.title: words(shot, told(FIXTURES / "cafe")) for shot in planned(FIXTURES / "cafe").shots}
SETTINGS = {"resolution": "720p", "aspect_ratio": "16:9", "duration": 5, "audio": False, "enable_prompt_expansion": False}


def recorded(mode: str) -> dict:
    return json.loads((FIXTURES / f"wan3.0-{mode}.json").read_text())


def png(path: Path, colour: str) -> Path:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:size=64x36", "-frames:v", "1",
                    "-y", str(path)], check=True)
    return path


def clip(path: Path, colour: str) -> bytes:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:size=1280x720:rate=24:duration=0.5",
                    "-pix_fmt", "yuv420p", "-y", str(path)], check=True)
    return path.read_bytes()


def unpacked(uri: str) -> bytes:
    prefix = "data:image/png;base64,"
    assert uri.startswith(prefix)
    return base64.b64decode(uri[len(prefix):])


def test_a_key_is_text_to_video_from_its_own_prompt_at_720p_without_sound_or_prompt_expansion():
    order = SHOTS["key order(Latte)"]
    built = wan3.request(Mode.TEXT_TO_VIDEO, order, 1)
    assert built == wan3.Wan3Request("alibaba/wan-3.0/text-to-video", {"prompt": order, **SETTINGS, "seed": 1})


def test_the_prompt_limit_is_the_20000_characters_fals_schema_gives_both_endpoints():
    limit = MODELS["wan3.0"].prompt_limit
    assert (limit.model, limit.most, limit.count("four")) == ("wan3.0", 20_000, 4)


def test_a_move_is_image_to_video_from_the_key_it_starts_on_to_the_key_it_lands_on(tmp_path):
    pick = SHOTS['menu() -> order(Latte) "Latte, $5"']
    menu, order = png(tmp_path / "menu.png", "red"), png(tmp_path / "order.png", "blue")
    built = wan3.request(Mode.FIRST_AND_LAST_FRAME, pick, 2, menu, order)
    assert built.endpoint == "alibaba/wan-3.0/image-to-video"
    images = {name: built.arguments[name] for name in ("start_image_url", "end_image_url")}
    assert {name: value for name, value in built.arguments.items() if name not in images} == {
        "prompt": pick, **SETTINGS, "seed": 2}
    assert unpacked(images["start_image_url"]) == menu.read_bytes()
    assert unpacked(images["end_image_url"]) == order.read_bytes()


def test_settings_cover_every_argument_a_shot_does_not_supply(tmp_path):
    images = png(tmp_path / "a.png", "red"), png(tmp_path / "b.png", "blue")
    for mode, built in ((Mode.TEXT_TO_VIDEO, wan3.request(Mode.TEXT_TO_VIDEO, "a prompt", 7)),
                        (Mode.FIRST_AND_LAST_FRAME, wan3.request(Mode.FIRST_AND_LAST_FRAME, "a prompt", 7, *images))):
        from_shot = {"prompt", "seed", "start_image_url", "end_image_url"}
        assert wan3.Wan3.settings(mode) == {"endpoint": built.endpoint,
                                            **{k: v for k, v in built.arguments.items() if k not in from_shot}}


def test_a_recorded_response_reads_into_a_video_and_a_receipt_without_the_network():
    for mode, request_id, video in (
            ("text-to-video", "01a1c5fb-027e-7b70-857e-d4305eafbbdb",
             "https://v3b.fal.media/files/b/0ab1eb6e/GNvrhPb7RelDLEjjuL7xY_UcjPFGG8.mp4"),
            ("image-to-video", "01a1c61c-45f6-76e1-9089-e4151dcebb51",
             "https://v3b.fal.media/files/b/0ab1ec52/ovFng3HiN7lAS57AK3Vmg_5d55sEuG.mp4")):
        response = recorded(mode)
        url, receipt = wan3.bill(response)
        assert url == video
        assert receipt == Receipt(request_id, 5.0, 0.5, response)


def test_a_response_without_a_video_is_an_error():
    response = recorded("text-to-video")
    with pytest.raises(FalError, match="request 01a1c5fb-027e-7b70-857e-d4305eafbbdb answered without a video"):
        wan3.bill({**response, "result": {"detail": "the safety checker flagged the output"}})


class Hosted:
    """fal's queue for a whole render: each submit gets its own request id and a solid 1280x720 clip of its own colour."""

    def __init__(self, scratch: Path):
        self.scratch = scratch
        self.answers: dict[str, bytes] = {}
        self.posts: list[tuple[str, dict]] = []
        self.served: set[bytes] = set()
        self.seen: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request) -> bytes:
        self.seen.append(request)
        if request.get_method() != "POST":
            return self.answers[request.full_url]
        mode = request.full_url.rsplit("/", 1)[1]
        number = len(self.posts)
        self.posts.append((mode, json.loads(request.data)))
        response = recorded(mode)
        queue = f"https://queue.fal.run/alibaba/wan-3.0/requests/request-{number}"
        video = f"https://v3b.fal.media/files/test/request-{number}.mp4"
        self.answers[f"{queue}/status"] = json.dumps(response["status"]).encode()
        self.answers[queue] = json.dumps({**response["result"], "video": {**response["result"]["video"], "url": video}}).encode()
        self.answers[video] = clip(self.scratch / f"{number}.mp4", f"0x{(number * 0x1F3D5B) % 0xFFFFFF:06x}")
        self.served.add(self.answers[video])
        return json.dumps({**response["submitted"], "request_id": f"request-{number}", "status_url": f"{queue}/status",
                           "response_url": queue}).encode()


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    """The cafe, with wan3.0 answered by a queue that is not the network. Its solid clips show the stand-in's eye nothing."""
    directory = copy_of("cafe", tmp_path)
    (tmp_path / "clips").mkdir()
    fal = Hosted(tmp_path / "clips")
    monkeypatch.setitem(MODELS, "wan3.0", Listing(lambda: wan3.Wan3(Fal(KEY, send=fal, sleep=lambda _: None)),
                                                  lambda tape: StandInEye()))
    return directory, fal


RENDER = ("render", "--story", "chalk", "--model", "wan3.0", "--takes", "1", "--out", "tape-wan3")


def test_wan3_renders_every_pixel_of_its_tape_and_pins_each_move_to_its_own_keys(hosted, cli, capsys):
    directory, fal = hosted
    out = directory / "tape-wan3"
    assert cli(directory, *RENDER) == 1
    stdout, stderr = capsys.readouterr()
    assert stdout.splitlines()[0] == "wan3.0: 11 calls, $5.50 at $0.10/s"
    assert 'fail: 1. key menu()  kept take 1 fails hotspot "Espresso, $3": not found' in stderr.splitlines()
    assert stdout.splitlines()[-1] == "rendered 11 of 11 shots -> tape-wan3"
    assert [mode for mode, _ in fal.posts] == ["text-to-video"] * 5 + ["image-to-video"] * 6
    plan = planned(directory)
    assert [arguments["prompt"] for _, arguments in fal.posts] == [words(shot, told(directory)) for shot in plan.shots]
    images = {key.state: out / key.image for key in plan.keys}
    for move, (_, arguments) in zip(plan.moves, fal.posts[5:]):
        assert unpacked(arguments["start_image_url"]) == images[move.start].read_bytes()
        assert unpacked(arguments["end_image_url"]) == images[move.land].read_bytes()
    assert len({image.read_bytes() for image in images.values()}) == 5
    assert {take.read_bytes() for take in (out / "takes").glob("*.mp4")} <= fal.served
    data = json.loads((out / "tape.json").read_text())
    assert (data["size"], data["fps"]) == ({"width": 1280, "height": 720}, 24)
    lines = ledger.of(directory, out).lines()
    assert [(line["tape"], line["model"], line["shot"], line["mode"], line["seed"], line["request_id"], line["duration"],
             line["usd"]) for line in lines] == [("tape-wan3", "wan3.0", shot.title, shot.mode.value, 1, f"request-{number}",
                                                  5.0, 0.5) for number, shot in enumerate(plan.shots)]
    assert all(line["seconds"] > 0 and line["gpu"] == "fal" for line in lines)
    assert ledger.of(directory, out).totals()["usd"] == 5.5
    assert not (directory / "tapes").exists()
    written = "".join(path.read_text(errors="replace") for path in directory.rglob("*")
                      if path.suffix in (".json", ".jsonl", ".html"))
    assert KEY not in written + stdout + stderr
    record = json.loads((out / "dailies.json").read_text())
    sidecar = json.loads((out / record["keys"][0]["takes"][0]["clip"]).with_suffix(".json").read_text())
    assert (sidecar["request_id"], sidecar["duration"], sidecar["usd"]) == ("request-0", 5.0, 0.5)
    assert sidecar["response"]["submitted"]["request_id"] == "request-0"
    assert sidecar["response"]["result"]["video"]["url"] == "https://v3b.fal.media/files/test/request-0.mp4"


def test_a_cached_wan3_render_calls_fal_for_nothing_and_says_no_price(hosted, cli, capsys):
    directory, fal = hosted
    cli(directory, *RENDER)
    book = ledger.of(directory, directory / "tape-wan3")
    lines, posts = book.lines(), len(fal.seen)
    capsys.readouterr()
    cli(directory, *RENDER)
    assert len(fal.seen) == posts
    assert book.lines() == lines
    assert not capsys.readouterr().out.startswith("wan3.0:")


@pytest.mark.parametrize("old, new, calls, line", [
    ('vt.Heading("Corner Cafe")', 'vt.Heading("The Corner Cafe")', 5, "wan3.0: 5 calls, $2.50 at $0.10/s"),
    ("coming up.", "on its way.", 6, "wan3.0: 6 calls, $3.00 at $0.10/s"),
])
def test_the_price_line_counts_only_the_calls_an_edit_needs(hosted, cli, capsys, old, new, calls, line):
    directory, fal = hosted
    cli(directory, *RENDER)
    screenplay = directory / "cafe.py"
    assert screenplay.read_text().count(old) == 1
    screenplay.write_text(screenplay.read_text().replace(old, new))
    posts = len(fal.posts)
    capsys.readouterr()
    cli(directory, *RENDER)
    assert capsys.readouterr().out.splitlines()[0] == line
    assert len(fal.posts) - posts == calls


def test_a_change_to_the_request_settings_renders_again(hosted, cli, monkeypatch):
    directory, fal = hosted
    cli(directory, *RENDER)
    monkeypatch.setitem(wan3.SETTINGS, "resolution", "1080p")
    cli(directory, *RENDER)
    assert len(fal.posts) == 22
    assert {arguments["resolution"] for _, arguments in fal.posts[11:]} == {"1080p"}


def test_wan3_without_fal_key_says_so_and_sends_nothing(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    monkeypatch.delenv("FAL_KEY", raising=False)
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: sent.append(args))
    assert cli(directory, "render", "--story", "chalk", "--model", "wan3.0", "--out", "tape-wan3") == 1
    assert capsys.readouterr() == ("", "error: wan3.0 needs FAL_KEY in the environment\n")
    assert sent == []
    assert sorted(path.name for path in directory.iterdir()) == ["cafe.py", "data", "pyproject.toml", "stories"]


def test_a_key_a_header_cannot_carry_is_refused_without_printing_it(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    monkeypatch.setenv("FAL_KEY", f"{KEY[:8]}\n{KEY[8:]}")
    assert cli(directory, "render", "--story", "chalk", "--model", "wan3.0", "--out", "tape-wan3") == 1
    out, err = capsys.readouterr()
    assert (out, err) == ("", "error: FAL_KEY holds a character an HTTP header cannot carry, such as a line break\n")


class Answer:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False

    def read(self) -> bytes:
        return self.body


@pytest.mark.parametrize("exported", [KEY, f"  {KEY}\n"])
def test_the_key_from_the_environment_goes_only_into_the_submits_authorization_header(monkeypatch, exported):
    monkeypatch.setenv("FAL_KEY", exported)
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout: sent.append(request) or Answer(b'{"detail": "no request today"}'))
    with pytest.raises(FalError, match="answered without a request") as error:
        wan3.from_environment().text_to_video("a prompt", 1, Path("unused.mp4"))
    assert [(request.full_url, request.get_header("Authorization")) for request in sent] == [
        ("https://queue.fal.run/alibaba/wan-3.0/text-to-video", f"Key {KEY}")]
    assert KEY not in str(error.value)
