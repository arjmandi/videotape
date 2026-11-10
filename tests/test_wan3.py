import base64
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest

from videotape import ledger, wan3
from videotape.cli import main
from videotape.fal import Fal, FalError, Receipt
from videotape.loader import load
from videotape.model import MODELS
from videotape.shots import Mode, plan

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
FIXTURES = Path(__file__).parent / "fixtures"
KEY = "fal-test-key-0123456789abcdef"
SHOTS = {shot.title: shot for shot in plan(load(SURF_SHOP))}
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
    entrance = SHOTS["key entrance"]
    built = wan3.request(entrance.mode, entrance.prompt, 1)
    assert built == wan3.Wan3Request("alibaba/wan-3.0/text-to-video", {"prompt": entrance.prompt, **SETTINGS, "seed": 1})


def test_a_move_is_image_to_video_from_the_key_it_starts_on_to_the_key_it_lands_on(tmp_path):
    enter = SHOTS['welcome -> entrance "Enter shop"']
    welcome, entrance = png(tmp_path / "welcome.png", "red"), png(tmp_path / "entrance.png", "blue")
    built = wan3.request(enter.mode, enter.prompt, 2, welcome, entrance)
    assert built.endpoint == "alibaba/wan-3.0/image-to-video"
    images = {name: built.arguments[name] for name in ("start_image_url", "end_image_url")}
    assert {name: value for name, value in built.arguments.items() if name not in images} == {
        "prompt": enter.prompt, **SETTINGS, "seed": 2}
    assert unpacked(images["start_image_url"]) == welcome.read_bytes()
    assert unpacked(images["end_image_url"]) == entrance.read_bytes()


def test_settings_cover_every_argument_a_shot_does_not_supply(tmp_path):
    images = png(tmp_path / "a.png", "red"), png(tmp_path / "b.png", "blue")
    for mode, built in ((Mode.TEXT_TO_VIDEO, wan3.request(Mode.TEXT_TO_VIDEO, "a prompt", 7)),
                        (Mode.FIRST_AND_LAST_FRAME, wan3.request(Mode.FIRST_AND_LAST_FRAME, "a prompt", 7, *images))):
        from_shot = {"prompt", "seed", "start_image_url", "end_image_url"}
        assert wan3.Wan3.settings(mode) == {"endpoint": built.endpoint,
                                            **{k: v for k, v in built.arguments.items() if k not in from_shot}}


def test_a_recorded_response_reads_into_a_video_and_a_receipt_without_the_network():
    for mode, request_id, file_name in (("text-to-video", "2c1f7a3e-5d0b-4e9a-9c61-8f3b2d7e4a10", "q7Hk2LmN9pRs.mp4"),
                                        ("image-to-video", "9e4b6d21-0f3a-4c7e-b5d8-1a2c3e4f5a6b", "Xv3Bn8Qw1ZtY.mp4")):
        response = recorded(mode)
        url, receipt = wan3.bill(response)
        assert url == f"https://v3b.fal.media/files/b/0aa4eab2/{file_name}"
        assert receipt == Receipt(request_id, 5.04, 0.504, response)


def test_a_response_without_a_video_is_an_error():
    response = recorded("text-to-video")
    with pytest.raises(FalError, match="request 2c1f7a3e-5d0b-4e9a-9c61-8f3b2d7e4a10 answered without a video"):
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
    directory = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    (tmp_path / "clips").mkdir()
    fal = Hosted(tmp_path / "clips")
    monkeypatch.setitem(MODELS, "wan3.0", lambda: wan3.Wan3(Fal(KEY, send=fal, sleep=lambda _: None)))
    return directory, fal


def test_wan3_renders_every_pixel_of_its_tape_and_pins_each_move_to_its_own_keys(hosted, capsys):
    directory, fal = hosted
    out = directory / "tape-wan3"
    assert main(["render", str(directory), "--model", "wan3.0", "--takes", "1", "--out", str(out)]) == 1
    stdout, stderr = capsys.readouterr()
    assert stdout.splitlines()[0] == "wan3.0: 10 calls, $5.00 at $0.10/s"
    assert 'fail: 1. key welcome  kept take 1 fails button "Enter shop": not found' in stderr.splitlines()
    assert stdout.splitlines()[-1] == f"rendered 10 of 10 shots -> {out}"
    assert [mode for mode, _ in fal.posts] == ["text-to-video"] * 5 + ["image-to-video"] * 5
    shots = plan(load(directory))
    assert [arguments["prompt"] for _, arguments in fal.posts] == [shot.prompt for shot in shots]
    for shot, (_, arguments) in zip(shots[5:], fal.posts[5:]):
        assert unpacked(arguments["start_image_url"]) == (out / "keys" / f"{shot.start}.png").read_bytes()
        assert unpacked(arguments["end_image_url"]) == (out / "keys" / f"{shot.land}.png").read_bytes()
    assert len({(out / "keys" / f"{scene}.png").read_bytes() for scene in load(directory).scenes}) == 5
    assert {take.read_bytes() for take in (out / "takes").glob("*.mp4")} <= fal.served
    data = json.loads((out / "tape.json").read_text())
    assert (data["size"], data["fps"]) == ({"width": 1280, "height": 720}, 24)
    lines = ledger.read(out)
    assert [(line["model"], line["shot"], line["mode"], line["seed"], line["request_id"], line["duration"], line["usd"])
            for line in lines] == [("wan3.0", shot.title, shot.mode.value, 1, f"request-{number}", 5.04, 0.504)
                                   for number, shot in enumerate(shots)]
    assert all(line["seconds"] > 0 and line["gpu"] == "fal" for line in lines)
    assert ledger.totals(lines)["usd"] == 5.04
    assert not (directory / "tape").exists()
    written = "".join(path.read_text(errors="replace") for path in out.rglob("*") if path.suffix in (".json", ".jsonl", ".html"))
    assert KEY not in written + stdout + stderr
    record = json.loads((out / "dailies.json").read_text())
    sidecar = json.loads((out / record["keys"][0]["takes"][0]["clip"]).with_suffix(".json").read_text())
    assert (sidecar["request_id"], sidecar["duration"], sidecar["usd"]) == ("request-0", 5.04, 0.504)
    assert sidecar["response"]["submitted"]["request_id"] == "request-0"
    assert sidecar["response"]["result"]["video"]["url"] == "https://v3b.fal.media/files/test/request-0.mp4"


def test_a_cached_wan3_render_calls_fal_for_nothing_and_says_no_price(hosted, capsys):
    directory, fal = hosted
    out = directory / "tape-wan3"
    main(["render", str(directory), "--model", "wan3.0", "--takes", "1", "--out", str(out)])
    lines, posts = ledger.read(out), len(fal.seen)
    capsys.readouterr()
    main(["render", str(directory), "--model", "wan3.0", "--takes", "1", "--out", str(out)])
    assert len(fal.seen) == posts
    assert ledger.read(out) == lines
    assert not capsys.readouterr().out.startswith("wan3.0:")


@pytest.mark.parametrize("old, new, calls, line", [
    ("The camera walks through the open door.", "The camera strolls in.", 1, "wan3.0: 1 call, $0.50 at $0.10/s"),
    ('"Create your account"', '"Open your account"', 3, "wan3.0: 3 calls, $1.50 at $0.10/s"),
])
def test_the_price_line_counts_only_the_calls_an_edit_needs(hosted, capsys, old, new, calls, line):
    directory, fal = hosted
    out = directory / "tape-wan3"
    main(["render", str(directory), "--model", "wan3.0", "--takes", "1", "--out", str(out)])
    screenplay = directory / "screenplay.py"
    screenplay.write_text(screenplay.read_text().replace(old, new))
    posts = len(fal.posts)
    capsys.readouterr()
    main(["render", str(directory), "--model", "wan3.0", "--takes", "1", "--out", str(out)])
    assert capsys.readouterr().out.splitlines()[0] == line
    assert len(fal.posts) - posts == calls


def test_a_change_to_the_request_settings_renders_again(hosted, monkeypatch):
    directory, fal = hosted
    out = directory / "tape-wan3"
    main(["render", str(directory), "--model", "wan3.0", "--takes", "1", "--out", str(out)])
    monkeypatch.setitem(wan3.SETTINGS, "resolution", "1080p")
    main(["render", str(directory), "--model", "wan3.0", "--takes", "1", "--out", str(out)])
    assert len(fal.posts) == 20
    assert {arguments["resolution"] for _, arguments in fal.posts[10:]} == {"1080p"}


def test_wan3_without_fal_key_says_so_and_sends_nothing(tmp_path, capsys, monkeypatch):
    directory = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    monkeypatch.delenv("FAL_KEY", raising=False)
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: sent.append(args))
    assert main(["render", str(directory), "--model", "wan3.0", "--out", str(directory / "tape-wan3")]) == 1
    assert capsys.readouterr() == ("", "error: wan3.0 needs FAL_KEY in the environment\n")
    assert sent == []
    assert sorted(path.name for path in directory.iterdir()) == ["screenplay.py"]


def test_a_key_a_header_cannot_carry_is_refused_without_printing_it(tmp_path, capsys, monkeypatch):
    directory = tmp_path / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape*", "compare*"))
    monkeypatch.setenv("FAL_KEY", f"{KEY[:8]}\n{KEY[8:]}")
    assert main(["render", str(directory), "--model", "wan3.0", "--out", str(directory / "tape-wan3")]) == 1
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
