"""minimax-h3 and gemini-omni-flash-1.2 film on fal through the adapter wan3.0 films through, each with its own
endpoints, request fields, seed, price and prompt limit. No paid call recorded their answers: tests/fixtures/
fal-models.txt says where the shape of each comes from."""

import base64
import dataclasses
import json
import subprocess
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import FIXTURES, copy_of, planned, told, words
from videotape import claude, frames, ledger
from videotape.fal import Fal, Receipt
from videotape.hosted import OnFal
from videotape.model import MODELS
from videotape.plan import Mode
from videotape.standin import StandInEye

KEY = "fal-test-key-0123456789abcdef"


@dataclass(frozen=True)
class Case:
    name: str
    endpoints: tuple[str, str]
    key: dict
    """A key's request body beyond its prompt and seed."""
    move: dict
    """A move's request body beyond its prompt, seed and two images."""
    start_image: str
    seeded: bool
    usd: float
    """What one five-second call costs."""
    rate: str
    """How the estimate shows the price."""
    size: tuple[int, int]
    """The size of the clips fal answers with."""
    prompt_characters: int


H3 = Case("minimax-h3", ("minimax/h3/text-to-video", "minimax/h3/image-to-video"),
          key={"resolution": "768P", "aspect_ratio": "16:9", "duration": 5, "prompt_expansion_mode": "disabled"},
          move={"resolution": "768P", "duration": 5, "prompt_expansion_mode": "disabled"},
          start_image="image_url", seeded=True, usd=0.30, rate="$0.06/s", size=(1344, 768), prompt_characters=7_000)
GEMINI = Case("gemini-omni-flash-1.2",
              ("google/gemini-omni-flash/v1.2/text-to-video", "google/gemini-omni-flash/v1.2/image-to-video"),
              key={"resolution": "720p", "aspect_ratio": "16:9", "duration": 5},
              move={"resolution": "720p", "aspect_ratio": "16:9", "duration": 5},
              start_image="image_url", seeded=False, usd=0.4395, rate="$0.0819/s plus $0.03 a call for the prompt",
              size=(1280, 720), prompt_characters=20_000)
CASES = pytest.mark.parametrize("case", [H3, GEMINI], ids=lambda case: case.name)


def recorded(name: str, mode: str) -> dict:
    return json.loads((FIXTURES / f"{name}-{mode}.json").read_text())


def png(path: Path, colour: str) -> Path:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:size=64x36", "-frames:v", "1",
                    "-y", str(path)], check=True)
    return path


def seed(case: Case, number: int) -> dict:
    """The seed a request sends: its number on a model fal takes a seed for, and nothing on one it does not."""
    return {"seed": number} if case.seeded else {}


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


class Queue:
    """fal's queue for one model: each submit gets its own request id, the model's answer with no duration, and a solid
    clip of its own colour at the model's size. The first two submits wait for each other, for a second at most, so a
    render that films two at once is seen to."""

    def __init__(self, name: str, scratch: Path, size: tuple[int, int]):
        self.name, self.scratch, self.size = name, scratch, size
        self.answers: dict[str, bytes] = {}
        self.posts: list[tuple[str, dict]] = []
        self.lock = threading.Lock()
        self.pair = threading.Barrier(2, timeout=1.0)
        self.flying = self.most = 0

    def __call__(self, request: urllib.request.Request) -> bytes:
        if request.get_method() == "POST" and len(self.posts) < 2:
            try:
                self.pair.wait()
            except threading.BrokenBarrierError:
                pass
        with self.lock:
            return self._answer(request)

    def _answer(self, request: urllib.request.Request) -> bytes:
        if request.get_method() != "POST":
            if request.full_url.startswith("https://v3b.fal.media/"):
                self.flying -= 1
            return self.answers[request.full_url]
        endpoint = request.full_url.removeprefix("https://queue.fal.run/")
        number = len(self.posts)
        self.posts.append((endpoint, json.loads(request.data)))
        self.flying += 1
        self.most = max(self.most, self.flying)
        response = recorded(self.name, endpoint.rsplit("/", 1)[1])
        queue = f"https://queue.fal.run/test/requests/request-{number}"
        video = f"https://v3b.fal.media/files/test/request-{number}.mp4"
        self.answers[f"{queue}/status"] = json.dumps(response["status"]).encode()
        self.answers[queue] = json.dumps({**response["result"], "video": {**response["result"]["video"], "url": video}}).encode()
        clip = self.scratch / f"{number}.mp4"
        width, height = self.size
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"color=c=0x{(number * 0x1F3D5B) % 0xFFFFFF:06x}:size={width}x{height}:rate=24:duration=0.5",
                        "-pix_fmt", "yuv420p", "-y", str(clip)], check=True)
        self.answers[video] = clip.read_bytes()
        return json.dumps({**response["submitted"], "request_id": f"request-{number}", "status_url": f"{queue}/status",
                           "response_url": queue}).encode()


def on_fal(case: Case, tmp_path: Path, monkeypatch) -> tuple[Path, Queue]:
    """The cafe, with the model answered by a queue that is not the network. Its solid clips show the stand-in's eye
    nothing."""
    directory = copy_of("cafe", tmp_path)
    (tmp_path / "clips").mkdir()
    fal = Queue(case.name, tmp_path / "clips", case.size)
    listing = MODELS[case.name]
    monkeypatch.setitem(MODELS, case.name, dataclasses.replace(
        listing, model=lambda: OnFal(listing.kind, Fal(KEY, send=fal, sleep=lambda _: None)), readers=(StandInEye,)))
    return directory, fal


def render_args(case: Case, cap: str = "20") -> tuple[str, ...]:
    return "render", "--story", "chalk", "--model", case.name, "--takes", "1", "--out", "tape-fal", "--cap-usd", cap


@CASES
def test_a_key_and_a_move_send_fal_the_models_own_fields(case, tmp_path):
    fal = Queue(case.name, tmp_path, (64, 36))
    model = OnFal(MODELS[case.name].kind, Fal(KEY, send=fal, sleep=lambda _: None))
    start, end = png(tmp_path / "start.png", "red"), png(tmp_path / "end.png", "blue")
    (tmp_path / "takes").mkdir()
    model.text_to_video("a key", 1, tmp_path / "takes" / "key.partial.mp4")
    model.first_last_frame("a move", start, end, 2, tmp_path / "takes" / "move.partial.mp4")
    assert fal.posts == [
        (case.endpoints[0], {"prompt": "a key", **case.key, **seed(case, 1)}),
        (case.endpoints[1], {"prompt": "a move", **case.move, **seed(case, 2), case.start_image: data_uri(start),
                             "end_image_url": data_uri(end)})]


@CASES
def test_an_answer_without_a_duration_is_billed_for_the_five_seconds_the_request_asked_for(case):
    for mode in ("text-to-video", "image-to-video"):
        response = recorded(case.name, mode)
        assert "duration" not in response["result"]
        url, receipt = MODELS[case.name].kind.bill(response)
        assert url == response["result"]["video"]["url"]
        assert receipt == Receipt(response["submitted"]["request_id"], 5.0, case.usd, response)


@CASES
def test_a_render_films_every_shot_on_fal_and_writes_each_calls_price_in_the_ledger(case, tmp_path, monkeypatch, cli,
                                                                                  capsys):
    directory, fal = on_fal(case, tmp_path, monkeypatch)
    out = directory / "tape-fal"
    assert cli(directory, *render_args(case)) == 1
    stdout = capsys.readouterr().out
    assert stdout.splitlines()[0] == f"{case.name}: 11 shots, 11 calls, ${11 * case.usd:.2f} at {case.rate}, cap $20.00, $0.00 spent"
    assert fal.most == 2
    plan = planned(directory)
    images = {key.state: out / key.image for key in plan.keys}
    keys = {words(key, told(directory)) for key in plan.keys}
    moves = {(words(move, told(directory)), data_uri(images[move.start]), data_uri(images[move.land])) for move in plan.moves}
    assert sorted(endpoint for endpoint, _ in fal.posts) == sorted([case.endpoints[0]] * 5 + [case.endpoints[1]] * 6)
    for endpoint, body in fal.posts:
        if endpoint == case.endpoints[0]:
            assert body == {"prompt": body["prompt"], **case.key, **seed(case, 1)} and body["prompt"] in keys
        else:
            assert body == {"prompt": body["prompt"], **case.move, **seed(case, 1), case.start_image: body[case.start_image],
                            "end_image_url": body["end_image_url"]}
            assert (body["prompt"], body[case.start_image], body["end_image_url"]) in moves
    lines = ledger.of(directory, out).lines()
    assert sorted((line["tape"], line["model"], line["shot"], line["mode"], line["seed"], line["gpu"], line["duration"],
                   line["usd"]) for line in lines) == sorted(
        ("tape-fal", case.name, shot.title, shot.mode.value, 1, "fal", 5.0, case.usd) for shot in plan.shots)
    assert {line["request_id"] for line in lines} == {f"request-{number}" for number in range(11)}
    assert ledger.of(directory, out).totals()["usd"] == round(11 * case.usd, 2)
    assert json.loads((out / "tape.json").read_text())["size"] == {"width": case.size[0], "height": case.size[1]}

    posts = len(fal.posts)
    capsys.readouterr()
    cli(directory, *render_args(case))
    assert len(fal.posts) == posts and len(ledger.of(directory, out).lines()) == 11


@CASES
def test_a_render_stops_at_the_cap_before_the_call_that_would_pass_it(case, tmp_path, monkeypatch, cli, capsys):
    directory, fal = on_fal(case, tmp_path, monkeypatch)
    cap = f"{3 * case.usd + 0.001:.4f}"
    assert cli(directory, *render_args(case, cap)) == 1
    assert capsys.readouterr().err.startswith("error VT402 ")
    assert len(fal.posts) == 3
    lines = ledger.of(directory, directory / "tape-fal").lines()
    assert [line["usd"] for line in lines] == [case.usd] * 3 and sum(line["usd"] for line in lines) <= float(cap)


@CASES
def test_a_model_on_fal_without_fal_key_says_so_and_sends_nothing(case, tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    monkeypatch.delenv("FAL_KEY", raising=False)
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: sent.append(args))
    assert cli(directory, "render", "--story", "chalk", "--model", case.name, "--cap-usd", "20", "--out", "tape-fal") == 1
    assert capsys.readouterr() == ("", f"error VT104 .env: {case.name} needs FAL_KEY, and it is not in the environment or "
                                       ".env\nfix: copy .env.example to .env and set FAL_KEY there, or export it\n")
    assert sent == []
    assert not (directory / "tape-fal").exists()


@CASES
def test_doctor_checks_fal_key_for_a_project_on_the_model(case, tmp_path, cli, capsys, monkeypatch):
    directory = copy_of("cafe", tmp_path)
    pyproject = directory / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('model = "stand-in"', f'model = "{case.name}"'))
    monkeypatch.delenv("FAL_KEY", raising=False)
    cli(directory, "doctor")
    assert f"fail VT104 {case.name} needs FAL_KEY, and it is not in the environment or .env" in capsys.readouterr().out
    (directory / ".env").write_text("FAL_KEY=fal-not-a-real-key\n")
    cli(directory, "doctor")
    assert f"ok   VT104 FAL_KEY is set, for {case.name}" in capsys.readouterr().out.splitlines()


@CASES
def test_plan_estimates_the_model_and_warns_of_a_prompt_past_its_limit(case, tmp_path, cli, capsys):
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "plan", "--story", "chalk", "--model", case.name) == 0
    read = claude.estimate(1280, 704)
    assert capsys.readouterr().out.splitlines()[-1] == (
        f"{case.name}: 11 shots, 11 to 44 calls, ${11 * case.usd:.2f} to ${44 * case.usd:.2f} at {case.rate}, and 5 to "
        f"20 reads by claude-opus-5-5, at most ${5 * read:.2f} to ${20 * read:.2f}")
    chalk = directory / "stories" / "chalk.toml"
    look = "A chalkboard cafe. " * 400
    assert 7_000 < len(look) < 20_000
    chalk.write_text(chalk.read_text().replace('look = """\n', f'look = """\n{look}', 1))
    cli(directory, "plan", "--story", "chalk", "--model", case.name)
    warned = [line.split(":")[0] for line in capsys.readouterr().err.splitlines()
              if f"{case.name} allows no more than {case.prompt_characters:,}" in line]
    # Every key's prompt starts with the look, and a move's does not.
    assert sorted(warned) == (sorted(f"warning VT307 {key.title}" for key in planned(directory).keys)
                              if case.prompt_characters == 7_000 else [])


def test_a_1344x768_tape_keeps_its_size_through_its_keys_its_seams_and_its_dailies(tmp_path, monkeypatch, cli, capsys):
    directory, fal = on_fal(H3, tmp_path, monkeypatch)
    out = directory / "tape-fal"
    cli(directory, *render_args(H3))
    assert {(frames.read_png(key).width, frames.read_png(key).height) for key in (out / "keys").iterdir()} == {(1344, 768)}
    assert {frames.shape(move) for move in (out / "moves").iterdir()} == {frames.Shape(1344, 768, 24)}
    record = json.loads((out / "dailies.json").read_text())
    assert all(isinstance(take["start"], float) and isinstance(take["end"], float)
               for move in record["moves"] for take in move["takes"])
    assert record["failures"] and all((out / failure["crop"]).is_file() for failure in record["failures"])
    assert "aspect-ratio: auto 1344 / 768" in (out / "dailies.html").read_text()
