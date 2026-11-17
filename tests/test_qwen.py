import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest

import videotape as vt
from conftest import FIXTURES, copy_of
from videotape import qwen, standin
from videotape.checks import Reading, Spot, cer, find, read, score
from videotape.errors import CODES
from videotape.frames import Box, Frame
from videotape.plan import plan
from videotape.qwen import QwenEye, spots

# Measured on MPS in bf16: the sign read at CER 0 with IoU 0.870.
MAX_SIGN_CER = 0.1
MIN_SIGN_IOU = 0.7

REPLY = '[{"text": "Enter shop", "bbox_2d": [398, 557, 602, 631], "button": true}, ' \
        '{"text": "Brushstroke Surf Co.", "bbox_2d": [418, 102, 582, 153], "button": false}]'


def test_spots_read_bare_json_in_coordinates_relative_to_1000():
    assert spots(REPLY, 1280, 704) == (
        Spot("Enter shop", Box(509, 392, 261, 52), True),
        Spot("Brushstroke Surf Co.", Box(535, 72, 210, 36), False),
    )


def test_spots_read_fenced_json():
    assert spots(f"Here they are:\n```json\n{REPLY}\n```\n", 1280, 704) == spots(REPLY, 1280, 704)


def test_spots_scale_to_the_frame():
    assert spots('[{"text": "x", "bbox_2d": [0, 0, 1000, 1000]}]', 1024, 768) == (Spot("x", Box(0, 0, 1024, 768), False),)


@pytest.mark.parametrize("reply", [
    "",
    "I can't read this image.",
    '[{"text": "Enter shop", "bbox_2d": [398, 557',
    '{"text": "Enter shop", "bbox_2d": [398, 557, 602, 631]}',
])
def test_malformed_replies_give_no_spots(reply):
    assert spots(reply, 1280, 704) == ()


def test_a_reply_cut_off_mid_array_keeps_its_complete_elements():
    reply = ('```json\n[\n\t{"text": "Toast", "bbox_2d": [493, 350, 595, 432], "button": false},\n'
             '\t{"text": "D:", "bbox_2d": [265, 284, 285, 316], "button": false},\n\t{"text": "D:", "bbox_2d": [265,')
    assert [spot.text for spot in spots(reply, 1000, 1000)] == ["Toast", "D:"]


def test_elements_without_text_or_a_box_are_skipped():
    reply = '[{"text": "", "bbox_2d": [0, 0, 1, 1]}, {"text": "a"}, {"bbox_2d": [0, 0, 1, 1]}, ' \
            '{"text": "b", "bbox_2d": [0, 0]}, {"text": "c", "bbox_2d": [0, 0, 500, 500]}]'
    assert spots(reply, 1000, 1000) == (Spot("c", Box(0, 0, 500, 500), False),)


def test_a_model_other_than_the_stand_in_is_checked_by_qwen_which_needs_its_extra(tmp_path, cli, capsys, monkeypatch):
    real = qwen.distribution

    def without_torch(name: str):
        if name == "torch":
            raise qwen.PackageNotFoundError(name)
        return real(name)
    monkeypatch.setattr(qwen, "distribution", without_torch)
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setenv("FAL_KEY", "fal-test-key-0123456789abcdef")
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: sent.append(args))
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--model", "wan3.0", "--out", "tape-wan3") == 1
    assert capsys.readouterr() == ("", "error VT105 qwen3-vl-8b: is a reader of this model's eye and runs through "
                                       f"videotape's qwen extra, which is not installed here\nfix: {CODES['VT105'].fix}\n")
    assert sent == [] and not (directory / "tape-wan3").exists()


def test_takes_read_at_once_load_qwen_once_and_ask_it_one_at_a_time(tmp_path, monkeypatch):
    """A model that films two shots at once has both read at once, and every tape of a screen test reads with its own
    eye: they share one Qwen3-VL-8B, loaded once, and ask it one picture at a time."""
    built, asking, most = [], [0], [0]

    class Slow:
        def __init__(self):
            time.sleep(0.2)
            built.append(self)

        def ask(self, frame: Frame) -> str:
            asking[0] += 1
            most[0] = max(most[0], asking[0])
            time.sleep(0.05)
            asking[0] -= 1
            return "[]"
    monkeypatch.setattr(qwen, "installed", lambda: True)
    monkeypatch.setattr(qwen, "_Qwen", Slow)
    monkeypatch.setattr(qwen, "_LOADED", [])
    eyes = [QwenEye(tmp_path / f"tape-{n}") for n in range(2)]
    frames = [Frame(4, 4, bytes([n]) * 48) for n in range(4)]
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda n: eyes[n % 2].see(frames[n]), range(4)))
    assert (len(built), most[0]) == (1, 1)


def test_the_stand_in_is_checked_by_its_own_reader_and_needs_no_extra(tmp_path, cli, monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    directory = copy_of("cafe", tmp_path)
    cli(directory, "render", "--story", "chalk", "--takes", "1")
    assert '"checks": "stand-in"' in (directory / "tapes" / "chalk" / "dailies.json").read_text()


def iou(a: Box, b: Box) -> float:
    w = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    h = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    return w * h / (a.w * a.h + b.w * b.h - w * h)


@pytest.fixture(scope="module")
def looks(tmp_path_factory):
    return tmp_path_factory.mktemp("looks")


@pytest.fixture(scope="module")
def eye(looks):
    return QwenEye(looks)


@pytest.mark.qwen
def test_qwen_reads_a_misspelling_as_written(eye):
    app = vt.Screenplay("Surf")
    app.scene(lambda: [vt.Heading("Brushstroke Surf Co."), vt.Text("Hand-painted surfboards from California")]).name = "home"
    frame, _ = standin.draw([["Brushstroke Surf Co."], ["Hand-painted surfboards from Califxrnia"]])
    checks = score(plan(app).keys[0], [eye.see(frame)])
    assert checks.text[1].line == "Hand-painted surfboards from California"
    [seen] = checks.text[1].seen
    assert (seen.reader, seen.text, seen.cer) == ("qwen3-vl-8b", "Hand-painted surfboards from Califxrnia", 1 / 39)
    assert [(item.code, item.about) for item in checks.failures] == [("VT502", "Hand-painted surfboards from California")]


@pytest.mark.qwen
def test_qwen_reads_and_finds_a_hand_painted_shop_sign(eye, capsys):
    from PIL import Image

    fixture = dict(line.split(": ", 1) for line in (FIXTURES / "local-oysters.txt").read_text().splitlines())
    image = Image.open(FIXTURES / "local-oysters.jpg").convert("RGB")
    photo = Frame(image.width, image.height, image.tobytes())
    seen = eye.see(photo).spots
    reading = min((cer(fixture["text"], line), line) for line in read(seen))
    box = find(seen, fixture["text"])
    overlap = iou(box, Box(*map(int, fixture["box"].split(",")))) if box else 0.0
    with capsys.disabled():
        print(f"\n  read {read(seen)}\n  sign CER {reading[0]:.3f} ({reading[1]!r}), box {box}, IoU {overlap:.3f}")
    assert reading[0] <= MAX_SIGN_CER
    assert overlap >= MIN_SIGN_IOU


def test_qwen_reads_the_slanted_signs_of_a_paid_take_under_its_prompt():
    """Under the prompt before this one, Qwen read neither the slanted member line nor the hanging tabs of this take,
    which Claude and a person read. A prompt change has to read this take again and record what it reads."""
    recorded = json.loads((FIXTURES / "recorded" / "qwen" / "profile-take-2.json").read_text())
    assert recorded["prompt"] == qwen.PROMPT
    read = [spot.text for spot in spots(recorded["reply"], recorded["width"], recorded["height"])]
    assert {"Silver member, 48,250 miles", "Home", "Trips", "Profile"} <= set(read)
