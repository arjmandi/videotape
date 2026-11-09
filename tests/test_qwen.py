import shutil
import sys
from pathlib import Path

import pytest

from videotape import frames
from videotape.checks import Reading, cer, score
from videotape.cli import main
from videotape.frames import Box, Frame
from videotape.loader import load
from videotape.qwen import QwenEye, Spot, spots
from videotape.render import render
from videotape.standin import StandIn, StandInEye, _draw

# Measured on MPS in bf16: the lowest button IoU on the stand-in keys was 0.833, every line read at CER 0,
# and the sign read at CER 0 with IoU 0.870.
MIN_BUTTON_IOU = 0.75
MAX_STAND_IN_CER = 0.0
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


def test_qwen_checks_without_the_extra_name_the_install_command(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    (tmp_path / "tape").mkdir()
    for name in ("tape.json", "dailies.json"):
        (tmp_path / "tape" / name).write_text("{}")
    (tmp_path / "screenplay.py").write_text('import videotape as vt\n\nplay = vt.Screenplay("T", look="L")\n')
    assert main(["check", str(tmp_path / "tape"), "--checks", "qwen3-vl-8b"]) == 1
    assert capsys.readouterr().err == "error: qwen3-vl-8b needs the qwen extra; install it with uv sync --extra qwen\n"


FIXTURES = Path(__file__).parent / "fixtures"
SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"


def iou(a: Box, b: Box) -> float:
    w = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    h = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    return w * h / (a.w * a.h + b.w * b.h - w * h)


@pytest.fixture(scope="module")
def stand_in_tape(tmp_path_factory):
    directory = tmp_path_factory.mktemp("qwen") / "surf_shop"
    shutil.copytree(SURF_SHOP, directory, ignore=shutil.ignore_patterns("tape"))
    model = StandIn()
    result = render(directory, model, StandInEye())
    drawn = {}
    for filmed in result.shots:
        if filmed.key:
            call = next(c for c in model.calls if c.prompt == filmed.shot.prompt and c.seed == filmed.kept.seed)
            drawn[filmed.shot.land] = {d.text: d.box for d in model.drawn[call.out] if d.button}
    return directory / "tape", load(directory), drawn


@pytest.fixture(scope="module")
def looks(tmp_path_factory):
    return tmp_path_factory.mktemp("looks")


@pytest.fixture(scope="module")
def eye(looks):
    return QwenEye(looks)


@pytest.mark.qwen
def test_qwen_finds_every_button_and_reads_every_line_on_the_stand_in_keys(stand_in_tape, eye, looks, capsys):
    tape, screenplay, drawn = stand_in_tape
    measured = []
    for name, scene in screenplay.scenes.items():
        checks = score(frames.read_png(tape / "keys" / f"{name}.png"), scene, eye)
        for label, truth in drawn[name].items():
            measured.append((name, f'button "{label}"', iou(checks.buttons[label], truth) if checks.buttons[label] else 0.0))
        measured += [(name, f'text "{text}"', reading.cer) for text, reading in checks.text.items()]
    with capsys.disabled():
        print("\n" + "\n".join(f"  {name}  {item}  {'IoU' if item.startswith('button') else 'CER'} {value:.3f}"
                               for name, item, value in measured))
    assert [m for m in measured if m[1].startswith("button") and m[2] < MIN_BUTTON_IOU] == []
    assert [m for m in measured if m[1].startswith("text") and m[2] > MAX_STAND_IN_CER] == []
    again = QwenEye(looks)
    assert [score(frames.read_png(tape / "keys" / f"{name}.png"), scene, again) for name, scene in screenplay.scenes.items()] \
        == [score(frames.read_png(tape / "keys" / f"{name}.png"), scene, eye) for name, scene in screenplay.scenes.items()]
    assert again.qwen is None


@pytest.mark.qwen
def test_qwen_reads_a_misspelling_as_written(eye):
    frame, _ = _draw(["Brushstroke Surf Co.", "Hand-painted surfboards from Califxrnia"], ["Enter shop"])
    checks = score(frame, load(SURF_SHOP).scenes["welcome"], eye)
    assert checks.text["Hand-painted surfboards from California"] == Reading("Hand-painted surfboards from Califxrnia", 1 / 39)
    assert [item.name for item in checks.failures] == ['text "Hand-painted surfboards from California"']


@pytest.mark.qwen
def test_qwen_reads_and_finds_a_hand_painted_shop_sign(eye, capsys):
    from PIL import Image

    fixture = dict(line.split(": ", 1) for line in (FIXTURES / "local-oysters.txt").read_text().splitlines())
    image = Image.open(FIXTURES / "local-oysters.jpg").convert("RGB")
    photo = Frame(image.width, image.height, image.tobytes())
    reading = min((cer(fixture["text"], line), line) for line in eye.read(photo))
    box = eye.find(photo, fixture["text"])
    overlap = iou(box, Box(*map(int, fixture["box"].split(",")))) if box else 0.0
    with capsys.disabled():
        print(f"\n  read {eye.read(photo)}\n  sign CER {reading[0]:.3f} ({reading[1]!r}), box {box}, IoU {overlap:.3f}")
    assert reading[0] <= MAX_SIGN_CER
    assert overlap >= MIN_SIGN_IOU
