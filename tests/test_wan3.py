import base64
import dataclasses
import io
import json
import re
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import FIXTURES, as_explained, copy_of, planned, told, words
from videotape import dailies, doctor, ledger, project, wan3
from videotape.errors import CODES, ModelError, RenderError
from videotape.fal import Fal, Receipt
from videotape.made import made
from videotape.model import MODELS, Listing
from videotape.plan import Mode
from videotape.render import render
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
    with pytest.raises(ModelError, match="request 01a1c5fb-027e-7b70-857e-d4305eafbbdb answered without video.url"):
        wan3.bill({**response, "result": {"detail": "the safety checker flagged the output"}})


def http(code: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://queue.fal.run/x", code, "error", {}, io.BytesIO(body.encode()))


class Hosted:
    """fal's queue for a whole render: each submit gets its own request id and a solid 1280x720 clip of its own colour.
    A url in broken answers HTTP 400 once, which fal's client does not retry. One request is answered at a time, so
    two workers never number their submits alike."""

    def __init__(self, scratch: Path):
        self.scratch = scratch
        self.answers: dict[str, bytes] = {}
        self.posts: list[tuple[str, dict]] = []
        self.served: set[bytes] = set()
        self.seen: list[urllib.request.Request] = []
        self.broken: set[str] = set()
        self.lock = threading.Lock()

    def __call__(self, request: urllib.request.Request) -> bytes:
        with self.lock:
            return self._answer(request)

    def _answer(self, request: urllib.request.Request) -> bytes:
        self.seen.append(request)
        if request.full_url in self.broken:
            self.broken.remove(request.full_url)
            raise http(400, "a hiccup at the gateway")
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


def test_a_take_is_submitted_once_even_when_the_render_dies_between_submitting_and_downloading(tmp_path):
    fal = Hosted(tmp_path)
    status = "https://queue.fal.run/alibaba/wan-3.0/requests/request-0/status"
    fal.broken.add(status)
    model = wan3.Wan3(Fal(KEY, send=fal, sleep=lambda _: None))
    (tmp_path / "takes").mkdir()
    out = tmp_path / "takes" / "abc123.partial.mp4"
    with pytest.raises(ModelError, match="status of alibaba/wan-3.0/text-to-video request request-0 failed with HTTP 400"):
        model.text_to_video("a prompt", 1, out)
    record = tmp_path / "takes" / "abc123.request.json"
    assert json.loads(record.read_text())["request_id"] == "request-0"
    assert json.loads(record.read_text())["status_url"] == status
    assert KEY not in record.read_text()
    assert not out.exists() and len(fal.posts) == 1
    receipt = model.text_to_video("a prompt", 1, out)
    assert len(fal.posts) == 1
    assert [url for url, in ((r.full_url,) for r in fal.seen)][1:] == [
        status, status, "https://queue.fal.run/alibaba/wan-3.0/requests/request-0",
        "https://v3b.fal.media/files/test/request-0.mp4"]
    assert (receipt.request_id, out.read_bytes()) == ("request-0", fal.answers["https://v3b.fal.media/files/test/request-0.mp4"])
    assert record.exists()


def hosted_by(queue: type[Hosted], tmp_path: Path, monkeypatch) -> tuple[Path, Hosted]:
    """The cafe, with wan3.0 answered by a queue that is not the network. Its solid clips show the stand-in's eye nothing."""
    directory = copy_of("cafe", tmp_path)
    (tmp_path / "clips").mkdir()
    fal = queue(tmp_path / "clips")
    monkeypatch.setitem(MODELS, "wan3.0", Listing(lambda: wan3.Wan3(Fal(KEY, send=fal, sleep=lambda _: None)),
                                                  lambda tape: StandInEye(), price=wan3.PRICE, limit=2,
                                                  kind=wan3.Wan3))
    return directory, fal


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    return hosted_by(Hosted, tmp_path, monkeypatch)


def render_args(takes: int = 1, cap: str = "20") -> tuple[str, ...]:
    return ("render", "--story", "chalk", "--model", "wan3.0", "--takes", str(takes), "--out", "tape-wan3", "--cap-usd", cap)


RENDER = render_args()


def test_wan3_renders_every_pixel_of_its_tape_and_pins_each_move_to_its_own_keys(hosted, cli, capsys):
    directory, fal = hosted
    out = directory / "tape-wan3"
    assert cli(directory, *RENDER) == 1
    stdout, stderr = capsys.readouterr()
    assert stdout.splitlines()[0] == "wan3.0: 11 shots, 11 calls, $5.50 at $0.10/s, cap $20.00, $0.00 spent"
    assert "fail: 1. key menu()  VT501 Espresso, $3: not found" in stderr.splitlines()
    assert '  next: videotape retake "menu()" --story chalk --out tape-wan3' in stderr.splitlines()
    assert stdout.splitlines()[-1].startswith("11 shots, 11 takes filmed, $5.50, ") and stdout.endswith(" MB -> tape-wan3\n")
    assert sorted(mode for mode, _ in fal.posts) == ["image-to-video"] * 6 + ["text-to-video"] * 5
    plan = planned(directory)
    assert sorted(arguments["prompt"] for _, arguments in fal.posts) == sorted(words(shot, told(directory)) for shot in plan.shots)
    images = {key.state: out / key.image for key in plan.keys}
    pinned = {(words(move, told(directory)), images[move.start].read_bytes(), images[move.land].read_bytes())
              for move in plan.moves}
    for mode, arguments in fal.posts:
        if mode == "image-to-video":
            assert (arguments["prompt"], unpacked(arguments["start_image_url"]), unpacked(arguments["end_image_url"])) in pinned
    assert len({image.read_bytes() for image in images.values()}) == 5
    assert {take.read_bytes() for take in (out / "takes").glob("*.mp4")} <= fal.served
    data = json.loads((out / "tape.json").read_text())
    assert (data["size"], data["fps"]) == ({"width": 1280, "height": 720}, 24)
    lines = ledger.of(directory, out).lines()
    assert sorted((line["tape"], line["model"], line["shot"], line["mode"], line["seed"], line["duration"], line["usd"])
                  for line in lines) == sorted(("tape-wan3", "wan3.0", shot.title, shot.mode.value, 1, 5.0, 0.5)
                                               for shot in plan.shots)
    assert {line["request_id"] for line in lines} == {f"request-{number}" for number in range(11)}
    assert all(line["seconds"] > 0 and line["gpu"] == "fal" for line in lines)
    assert ledger.of(directory, out).totals()["usd"] == 5.5
    assert not (directory / "tapes").exists()
    written = "".join(path.read_text(errors="replace") for path in directory.rglob("*")
                      if path.suffix in (".json", ".jsonl", ".html"))
    assert KEY not in written + stdout + stderr
    record = json.loads((out / "dailies.json").read_text())
    sidecar = json.loads((out / record["keys"][0]["takes"][0]["clip"]).with_suffix(".json").read_text())
    number = sidecar["request_id"]
    assert (number in ("request-0", "request-1"), sidecar["duration"], sidecar["usd"]) == (True, 5.0, 0.5)
    assert sidecar["response"]["submitted"]["request_id"] == number
    assert sidecar["response"]["result"]["video"]["url"] == f"https://v3b.fal.media/files/test/{number}.mp4"
    assert sorted(path.name for path in (out / "takes").glob("*.request.json")) == sorted(
        f"{path.stem}.request.json" for path in (out / "takes").glob("*.mp4"))


def test_a_cached_wan3_render_calls_fal_for_nothing(hosted, cli, capsys):
    directory, fal = hosted
    cli(directory, *RENDER)
    book = ledger.of(directory, directory / "tape-wan3")
    lines, posts = book.lines(), len(fal.seen)
    capsys.readouterr()
    cli(directory, *RENDER)
    assert len(fal.seen) == posts
    assert book.lines() == lines


def a_take(directory: Path) -> tuple[Path, dict, str]:
    """One filmed take of a move of the wan3 tape: its clip, its sidecar, and the title of its shot from the ledger.
    A move, since nothing is pinned to a move, so another kept take of it renders nothing else again."""
    sidecars = {clip: json.loads(clip.with_suffix(".json").read_text())
                for clip in sorted((directory / "tape-wan3" / "takes").glob("*.mp4"))}
    shots = {line["request_id"]: line["shot"] for line in ledger.of(directory, directory / "tape-wan3").lines()}
    clip, sidecar = next((clip, sidecar) for clip, sidecar in sidecars.items() if " -> " in shots[sidecar["request_id"]])
    return clip, sidecar, shots[sidecar["request_id"]]


def video_of(sidecar: dict) -> str:
    return f"https://v3b.fal.media/files/test/{sidecar['request_id']}.mp4"


def test_a_corrupt_take_is_downloaded_again_from_its_record_and_counted_once(hosted, cli, capsys):
    directory, fal = hosted
    cli(directory, *RENDER)
    clip, sidecar, shot = a_take(directory)
    clip.write_bytes(b"not a clip")
    capsys.readouterr()
    assert cli(directory, *RENDER) == 1
    assert "VT403" not in capsys.readouterr().err
    assert clip.read_bytes() == fal.answers[video_of(sidecar)]
    book = ledger.of(directory, directory / "tape-wan3")
    assert len(fal.posts) == len(book.lines()) == 11 and book.totals()["usd"] == 5.5


def test_a_take_still_corrupt_after_a_download_is_vt403_and_its_seed_is_skipped(hosted, cli, capsys):
    directory, fal = hosted
    cli(directory, *RENDER)
    clip, sidecar, shot = a_take(directory)
    clip.write_bytes(b"not a clip")
    fal.answers[video_of(sidecar)] = b"still not a clip"
    capsys.readouterr()
    assert cli(directory, *render_args(takes=2)) == 1
    err = capsys.readouterr().err
    assert f"error VT403 {shot} take 1: downloaded again, and still: " in err
    assert "next: nothing; seed 1 is skipped from now on" in err
    assert dailies.read(directory / "tape-wan3")["corrupt"] == {shot: [1]}
    # Every shot fails its checks on these solid clips, so each films seed 2, and the corrupt seed is not filmed again.
    assert len(fal.posts) == len(ledger.of(directory, directory / "tape-wan3").lines()) == 22


def test_a_corrupt_take_whose_record_is_gone_is_vt403_and_never_submitted_again(hosted, cli, capsys):
    directory, fal = hosted
    cli(directory, *RENDER)
    clip, sidecar, shot = a_take(directory)
    clip.write_bytes(b"not a clip")
    wan3.request_record(clip).unlink()
    capsys.readouterr()
    assert cli(directory, *render_args(takes=2)) == 1
    err = capsys.readouterr().err
    assert re.search(rf"error VT403 {re.escape(shot)} take 1: tape-wan3/takes/[0-9a-f]{{64}}\.mp4 did not decode to one frame: ", err)
    assert as_explained("VT403").search(err)
    assert "next: nothing; seed 1 is skipped from now on" in err
    assert dailies.read(directory / "tape-wan3")["corrupt"] == {shot: [1]}
    assert len(fal.posts) == len(ledger.of(directory, directory / "tape-wan3").lines()) == 22


def test_a_take_whose_clip_is_gone_is_downloaded_again_under_any_cap_and_counted_once(hosted, cli, capsys):
    directory, fal = hosted
    cli(directory, *RENDER)
    clip, sidecar, shot = a_take(directory)
    clip.unlink()
    capsys.readouterr()
    # The tape has spent the whole cap. Downloading again costs nothing, so the cap does not stop it.
    assert cli(directory, *render_args(cap="5.50")) == 1
    out, err = capsys.readouterr()
    assert "VT402" not in err
    assert clip.read_bytes() == fal.answers[video_of(sidecar)]
    book = ledger.of(directory, directory / "tape-wan3")
    assert len(fal.posts) == 11 and [line["request_id"] for line in book.lines()].count(sidecar["request_id"]) == 1
    assert (book.totals()["takes"], book.totals()["usd"]) == (11, 5.5)
    assert out.splitlines()[-1].startswith("11 shots, 0 takes filmed, $0.00, ")


def test_a_render_that_died_between_submitting_and_downloading_downloads_on_resume_and_pays_once(hosted, cli, capsys):
    directory, fal = hosted
    fal.broken.add("https://queue.fal.run/alibaba/wan-3.0/requests/request-0/status")
    assert cli(directory, *RENDER) == 1
    err = capsys.readouterr().err
    assert err.startswith("error VT401 ") and "request request-0 failed with HTTP 400" in err
    book = ledger.of(directory, directory / "tape-wan3")
    # Two workers, one of which may begin one more key before the stop reaches it.
    assert "request-0" not in {line["request_id"] for line in book.lines()} and len(fal.posts) <= 3
    assert cli(directory, *RENDER) == 1
    assert "VT401" not in capsys.readouterr().err
    assert len(fal.posts) == 11
    assert sorted(line["request_id"] for line in book.lines()) == sorted(f"request-{n}" for n in range(11))
    assert book.totals()["usd"] == 5.5


class Window(Hosted):
    """Opens the window in which a reservation could leak. Request 0's download waits for go and then fails for good,
    so its call was paid for and is never settled. The third submit waits until a fourth comes, or gives up, so a
    worker that reserves after request 0 fails has the time to submit."""

    def __init__(self, scratch: Path):
        super().__init__(scratch)
        self.go, self.fourth = threading.Event(), threading.Event()
        self.submits = 0

    def __call__(self, request: urllib.request.Request) -> bytes:
        if request.full_url == "https://v3b.fal.media/files/test/request-0.mp4":
            self.go.wait(5)
            raise http(404, "gone")
        if request.get_method() == "POST":
            with self.lock:
                self.submits += 1
                third = self.submits == 3
            if third:
                self.fourth.wait(1.5)
        answer = super().__call__(request)
        if request.get_method() == "POST" and len(self.posts) == 4:
            self.fourth.set()
        return answer


def test_a_call_that_fails_after_its_submit_keeps_its_reservation(tmp_path):
    """Under a cap of $1.50, two keys are submitted at once and a third is reserved. Request 0 then fails after its
    submit. Were its reservation let go, the worker could reserve that money before the main thread stops the
    render, and four submits at $0.50 would pass the cap."""
    directory = copy_of("cafe", tmp_path)
    (tmp_path / "clips").mkdir()
    fal = Window(tmp_path / "clips")
    model = wan3.Wan3(Fal(KEY, send=fal, sleep=lambda _: None))
    reported = []

    def report(filmed):
        reported.append(filmed)
        if len(reported) == 1:
            fal.go.set()
            fal.fourth.wait(1.5)

    chalk, tape = told(directory), directory / "tape-wan3"
    with pytest.raises(RenderError) as error:
        render(planned(directory), chalk, model, StandInEye(), tape, ledger.of(directory, tape),
               made(project.find(directory), chalk, model), takes=1, limit=2, price=wan3.PRICE, cap=1.5, report=report)
    assert error.value.code in ("VT401", "VT402")
    assert 0.5 * len(fal.posts) <= 1.5 and len(fal.posts) == 3
    assert sorted(line["request_id"] for line in ledger.of(directory, tape).lines()) == ["request-1", "request-2"]


class Refusing(Hosted):
    """fal refuses request 0's result for good, as it does when its safety checker flags the output."""

    def _answer(self, request: urllib.request.Request) -> bytes:
        if request.full_url == "https://queue.fal.run/alibaba/wan-3.0/requests/request-0":
            raise http(422, '{"detail": "content policy"}')
        return super()._answer(request)


def test_a_recorded_request_that_fails_for_good_names_its_record_and_deleting_it_submits_a_new_paid_take(
        tmp_path, monkeypatch, cli, capsys):
    directory, fal = hosted_by(Refusing, tmp_path, monkeypatch)
    # Two keys are submitted at once, and whichever posts first is request 0.
    refused = None
    for attempt in range(2):
        assert cli(directory, *RENDER) == 1
        err = capsys.readouterr().err.splitlines()
        failed = re.fullmatch(r"error VT401 (key .+) take 1: result of alibaba/wan-3.0/text-to-video request request-0 "
                              r'failed with HTTP 422: {"detail": "content policy"}', err[0])
        assert failed and refused in (None, failed[1])
        refused = failed[1]
        assert err[1:3] == ["next: run the render again, which resumes; this request is polled, not submitted again:",
                            "videotape render --story chalk --model wan3.0 --takes 1 --out tape-wan3 --cap-usd 20.00"]
        named = re.fullmatch(r"or delete (tape-wan3/takes/[0-9a-f]{64}\.request\.json) first, and the render submits a "
                             r"new, paid take", err[3])
        assert named and json.loads((directory / named[1]).read_text())["request_id"] == "request-0"
        assert [arguments["prompt"] for _, arguments in fal.posts].count(SHOTS[refused]) == 1
    (directory / named[1]).unlink()
    assert cli(directory, *RENDER) == 1
    err = capsys.readouterr().err
    assert "VT401" not in err and (directory / "tape-wan3" / "tape.json").exists()
    assert [arguments["prompt"] for _, arguments in fal.posts].count(SHOTS[refused]) == 2
    assert len(fal.posts) == len(ledger.of(directory, directory / "tape-wan3").lines()) + 1


class Meeting(Hosted):
    """Holds a submit of the shared prompt until a second one arrives, or gives up after a second, so two shots
    that film the same take at once both get to submit it."""

    def __init__(self, scratch: Path):
        super().__init__(scratch)
        self.both = threading.Barrier(2, timeout=1.0)

    def __call__(self, request: urllib.request.Request) -> bytes:
        if request.get_method() == "POST" and b"Coming up." in request.data:
            try:
                self.both.wait()
            except threading.BrokenBarrierError:
                pass
        return super().__call__(request)


def test_two_shots_that_share_a_take_name_film_it_once(tmp_path, monkeypatch, cli, capsys):
    directory, fal = hosted_by(Meeting, tmp_path, monkeypatch)
    # Both thanks states now show the same words, so their keys share a prompt, a take name, and a key image, and
    # so do the two Done moves that leave them.
    screenplay = directory / "cafe.py"
    screenplay.write_text(screenplay.read_text().replace('vt.Text(f"One {drink.name} coming up.")', 'vt.Text("Coming up.")'))
    assert cli(directory, *RENDER) == 1
    posts = [(mode, arguments["prompt"], arguments["seed"], arguments.get("start_image_url"), arguments.get("end_image_url"))
             for mode, arguments in fal.posts]
    assert len(set(posts)) == len(posts) == 9
    assert len(ledger.of(directory, directory / "tape-wan3").lines()) == 9
    record = dailies.read(directory / "tape-wan3")
    thanks = [shot for shot in record["keys"] if shot["title"].startswith("key thanks(")]
    assert len(thanks) == 2 and len({shot["takes"][0]["clip"] for shot in thanks}) == 1
    assert [shot["takes"][0]["cached"] for shot in thanks].count(True) == 1


@pytest.mark.parametrize("old, new, calls", [
    ('vt.Heading("Corner Cafe")', 'vt.Heading("The Corner Cafe")', 5),
    ("coming up.", "on its way.", 6),
])
def test_an_edit_submits_only_the_calls_it_needs(hosted, cli, capsys, old, new, calls):
    directory, fal = hosted
    cli(directory, *RENDER)
    screenplay = directory / "cafe.py"
    assert screenplay.read_text().count(old) == 1
    screenplay.write_text(screenplay.read_text().replace(old, new))
    posts = len(fal.posts)
    capsys.readouterr()
    cli(directory, *RENDER)
    assert capsys.readouterr().out.splitlines()[0] == "wan3.0: 11 shots, 11 calls, $5.50 at $0.10/s, cap $20.00, $5.50 spent"
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
    said = f"error VT104 .env: {CODES['VT104'].example.removeprefix('fail VT104 ')}\nfix: {CODES['VT104'].fix}\n"
    assert capsys.readouterr() == ("", said)
    assert said == f"error VT104 .env: {doctor.key('wan3.0').what}\nfix: {doctor.key('wan3.0').fix}\n"
    assert sent == []
    assert sorted(path.name for path in directory.iterdir()) == ["cafe.py", "data", "pyproject.toml", "stories"]


def test_a_key_in_the_projects_env_file_goes_only_into_the_submits_authorization_header(tmp_path, cli, capsys,
                                                                                       monkeypatch):
    directory = copy_of("cafe", tmp_path)
    (directory / ".env").write_text(f'# from fal.ai/dashboard/keys\nFAL_KEY="{KEY}"\n')
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setitem(MODELS, "wan3.0", dataclasses.replace(MODELS["wan3.0"], eye=lambda tape: StandInEye()))
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout: sent.append(request) or Answer(b'{"detail": "no request today"}'))
    assert cli(directory, "render", "--story", "chalk", "--model", "wan3.0", "--cap-usd", "1", "--out", "tape-wan3") == 1
    assert sent and {request.get_header("Authorization") for request in sent} == {f"Key {KEY}"}
    assert KEY not in "".join(capsys.readouterr())


def test_a_key_a_header_cannot_carry_is_refused_without_printing_it(tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    monkeypatch.setenv("FAL_KEY", f"{KEY[:8]}\n{KEY[8:]}")
    assert cli(directory, "render", "--story", "chalk", "--model", "wan3.0", "--out", "tape-wan3") == 1
    out, err = capsys.readouterr()
    check = doctor.key("wan3.0")
    assert (out, err, check.ok) == ("", f"error VT104 .env: {check.what}\nfix: {check.fix}\n", False)
    assert check.what == "FAL_KEY holds a character an HTTP header cannot carry, such as a line break"


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
    with pytest.raises(ModelError, match="answered without a request") as error:
        wan3.from_environment().text_to_video("a prompt", 1, Path("unused.mp4"))
    assert [(request.full_url, request.get_header("Authorization")) for request in sent] == [
        ("https://queue.fal.run/alibaba/wan-3.0/text-to-video", f"Key {KEY}")]
    assert KEY not in str(error.value)
