import hashlib
import re
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
from pathlib import Path
from statistics import median

from videotape import frames
from videotape.checks import cer
from videotape.frames import HEIGHT, WIDTH, Box, Frame
from videotape.shots import Mode

# Printable ASCII from " " to "~", five column bytes per glyph, bit 0 at the top row.
GLYPHS = bytes.fromhex(
    "0000000000" "00005f0000" "0007000700" "147f147f14" "242a7f2a12" "2313086462" "3649552250" "0005030000"
    "001c224100" "0041221c00" "082a1c2a08" "08083e0808" "0050300000" "0808080808" "0060600000" "2010080402"
    "3e5149453e" "00427f4000" "4261514946" "2141454b31" "1814127f10" "2745454539" "3c4a494930" "0171090503"
    "3649494936" "064949291e" "0036360000" "0056360000" "0814224100" "1414141414" "0041221408" "0201510906"
    "324979413e" "7e1111117e" "7f49494936" "3e41414122" "7f4141221c" "7f49494941" "7f09090101" "3e41415132"
    "7f0808087f" "00417f4100" "2040413f01" "7f08142241" "7f40404040" "7f020c027f" "7f0408107f" "3e4141413e"
    "7f09090906" "3e4151215e" "7f09192946" "4649494931" "01017f0101" "3f4040403f" "1f2040201f" "3f4038403f"
    "6314081463" "0708700807" "6151494543" "007f414100" "0204081020" "0041417f00" "0402010204" "4040404040"
    "0001020400" "2054545478" "7f48444438" "3844444420" "384444487f" "3854545418" "087e090102" "0c5252523e"
    "7f08040478" "00447d4000" "2040443d00" "7f10284400" "00417f4000" "7c04180478" "7c08040478" "3844444438"
    "7c14141408" "081414187c" "7c08040408" "4854545420" "043f444020" "3c4040207c" "1c2040201c" "3c4030403c"
    "4428102844" "0c5050503c" "4464544c44" "0008364100" "00007f0000" "0041360800" "0804081008"
)
CHARACTERS = {GLYPHS[i:i + 5]: chr(32 + i // 5) for i in range(0, len(GLYPHS), 5)}
SCALE = 4
PAD = 3
GAP = 3
LINES_TOP, BUTTONS_TOP, BOTTOM = 72, 392, HEIGHT - 40
BACKGROUND, LINE, BUTTON, INK = bytes.fromhex("2f6f7e"), bytes.fromhex("f7f1e3"), bytes.fromhex("f2a541"), bytes.fromhex("1a1a1a")
CONTRAST = 30
FIND_MAX_CER = 0.2


class Flaw(Enum):
    NONE = "none"
    MISSPELL = "misspell"
    DROP_BUTTON = "drop button"
    WRONG_START = "wrong start"
    WRONG_END = "wrong end"


FLAWS = {
    Mode.TEXT_TO_VIDEO: (Flaw.MISSPELL, Flaw.DROP_BUTTON),
    Mode.IMAGE_TO_VIDEO: (Flaw.MISSPELL, Flaw.DROP_BUTTON, Flaw.WRONG_START),
    Mode.FIRST_AND_LAST_FRAME: (Flaw.WRONG_START, Flaw.WRONG_END),
}


@dataclass(frozen=True)
class Call:
    mode: Mode
    prompt: str
    seed: int
    start: Path | None
    end: Path | None
    out: Path


@dataclass(frozen=True)
class Drawn:
    text: str
    button: bool
    box: Box


class StandIn:
    name = "stand-in"

    def __init__(self, flaw: Callable[[str, int], Flaw] | None = None):
        self.flaw = flaw
        self.calls: list[Call] = []
        self.drawn: dict[Path, tuple[Drawn, ...]] = {}

    def text_to_video(self, prompt: str, seed: int, out: Path) -> None:
        self._film(Mode.TEXT_TO_VIDEO, prompt, seed, None, None, out)

    def image_to_video(self, prompt: str, start: Path, seed: int, out: Path) -> None:
        self._film(Mode.IMAGE_TO_VIDEO, prompt, seed, start, None, out)

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> None:
        self._film(Mode.FIRST_AND_LAST_FRAME, prompt, seed, start, end, out)

    def _film(self, mode: Mode, prompt: str, seed: int, start: Path | None, end: Path | None, out: Path) -> None:
        self.calls.append(Call(mode, prompt, seed, start, end, out))
        lines, buttons = _quoted_after("The lettering reads", prompt), _quoted_after("(?:A button is|Buttons are) labelled", prompt)
        digest = hashlib.sha256(f"{seed}\n{prompt}".encode()).digest()
        kinds = [kind for kind in FLAWS[mode]
                 if (kind is not Flaw.MISSPELL or lines or buttons) and (kind is not Flaw.DROP_BUTTON or buttons)]
        flaw = self.flaw(prompt, seed) if self.flaw else _default_flaw(digest, seed, kinds)
        if flaw is not Flaw.NONE and flaw not in kinds:
            raise ValueError(f"{flaw.name} does not apply to this {mode.value} take")
        if flaw is Flaw.MISSPELL:
            lines, buttons = _misspell(lines, buttons, digest)
        if flaw is Flaw.DROP_BUTTON:
            buttons = [b for i, b in enumerate(buttons) if i != digest[2] % len(buttons)]
        with tempfile.TemporaryDirectory() as scratch:
            scratch = Path(scratch)
            drawn: tuple[Drawn, ...] = ()
            if mode is Mode.FIRST_AND_LAST_FRAME:
                first, last = start, end
            else:
                frame, drawn = _draw(lines, buttons)
                last = _png(frame, scratch / "drawn.png")
                first = start or _png(Frame(WIDTH, HEIGHT, BACKGROUND * (WIDTH * HEIGHT)), scratch / "background.png")
            if flaw is Flaw.WRONG_START:
                first = _png(_negative(frames.read_png(first)), scratch / "wrong-start.png")
            if flaw is Flaw.WRONG_END:
                last = _png(_negative(frames.read_png(last)), scratch / "wrong-end.png")
            frames.crossfade(first, last, out)
        self.drawn[out] = drawn


class StandInEye:
    name = "stand-in"

    def read(self, frame: Frame) -> list[str]:
        return [text for _, text in _segment(frame)]

    def find(self, frame: Frame, label: str) -> Box | None:
        scored = [(cer(label, text), box) for box, text in _segment(frame)]
        error, box = min(scored, key=lambda pair: pair[0], default=(1.0, None))
        return box if error <= FIND_MAX_CER else None


def _quoted_after(lead: str, prompt: str) -> list[str]:
    sentence = re.search(rf'{lead} ((?:"[^"]*"(?:, | and )?)+)\.', prompt)
    return re.findall(r'"([^"]*)"', sentence.group(1)) if sentence else []


def _default_flaw(digest: bytes, seed: int, kinds: list[Flaw]) -> Flaw:
    if seed not in (1, 2) or not kinds or digest[0] % 2:
        return Flaw.NONE
    return kinds[digest[1] % len(kinds)]


def _misspell(lines: list[str], buttons: list[str], digest: bytes) -> tuple[list[str], list[str]]:
    texts = [*lines, *buttons]
    which = digest[2] % len(texts)
    text = texts[which]
    at = digest[3] % len(text)
    texts[which] = text[:at] + ("x" if text[at] != "x" else "z") + text[at + 1:]
    return texts[:len(lines)], texts[len(lines):]


def _png(frame: Frame, path: Path) -> Path:
    frames.write_png(frame, path)
    return path


def _negative(frame: Frame) -> Frame:
    return Frame(frame.width, frame.height, frame.rgb.translate(bytes(range(255, -1, -1))))


def _draw(lines: list[str], buttons: list[str]) -> tuple[Frame, tuple[Drawn, ...]]:
    canvas = bytearray(BACKGROUND * (WIDTH * HEIGHT))
    drawn = (*_stack(canvas, lines, False, LINES_TOP, BUTTONS_TOP), *_stack(canvas, buttons, True, BUTTONS_TOP, BOTTOM))
    return Frame(WIDTH, HEIGHT, bytes(canvas)), drawn


def _stack(canvas: bytearray, texts: list[str], button: bool, top: int, bottom: int) -> list[Drawn]:
    drawn = []
    for text in texts:
        w, h = (6 * len(text) - 1 + 2 * PAD) * SCALE, (7 + 2 * PAD) * SCALE
        box = Box((WIDTH - w) // 2, top, w, h)
        if w > WIDTH or top + h > bottom:
            raise ValueError(f'the stand-in has no room to draw "{text}"')
        _fill(canvas, box, BUTTON if button else LINE)
        for i, char in enumerate(text):
            _letter(canvas, box.x + (PAD + 6 * i) * SCALE, box.y + PAD * SCALE, char)
        drawn.append(Drawn(text, button, box))
        top += h + GAP * SCALE
    return drawn


def _letter(canvas: bytearray, x: int, y: int, char: str) -> None:
    index = ord(char) - 32
    if not 0 <= index < len(CHARACTERS):
        raise ValueError(f"the stand-in cannot draw {char!r}")
    for c, column in enumerate(GLYPHS[5 * index:5 * index + 5]):
        for r in range(7):
            if column >> r & 1:
                _fill(canvas, Box(x + c * SCALE, y + r * SCALE, SCALE, SCALE), INK)


def _fill(canvas: bytearray, box: Box, colour: bytes) -> None:
    row = colour * box.w
    for y in range(box.y, box.y + box.h):
        at = (y * WIDTH + box.x) * 3
        canvas[at:at + len(row)] = row


def _segment(frame: Frame) -> list[tuple[Box, str]]:
    # The palette differs most in green, so one channel separates the boxes without a per-pixel loop.
    green = frame.rgb[1::3]
    width = frame.width
    background = Counter(green[:width]).most_common(1)[0][0]
    mask = green.translate(bytes(abs(v - background) > CONTRAST for v in range(256)))
    lit = [mask.count(1, y * width, (y + 1) * width) > 2 * SCALE for y in range(frame.height)]
    found = []
    for on, rows in groupby(range(frame.height), key=lit.__getitem__):
        rows = list(rows)
        if not on or len(rows) < 7 * SCALE:
            continue
        left = int(median(mask.find(1, y * width, (y + 1) * width) - y * width for y in rows))
        right = int(median(mask.rfind(1, y * width, (y + 1) * width) - y * width for y in rows))
        box = Box(left, rows[0], right - left + 1, len(rows))
        found.append((box, _letters(green, width, box)))
    return found


def _letters(green: bytes, width: int, box: Box) -> str:
    padding_row = (box.y + SCALE) * width
    fill = Counter(green[padding_row + box.x:padding_row + box.x + box.w]).most_common(1)[0][0]
    count = round((box.w / SCALE - 2 * PAD + 1) / 6)
    x0, y0 = box.x + PAD * SCALE + SCALE // 2, box.y + PAD * SCALE + SCALE // 2
    text = ""
    for i in range(count):
        glyph = bytes(sum(1 << r for r in range(7)
                          if abs(green[(y0 + r * SCALE) * width + x0 + (6 * i + c) * SCALE] - fill) > CONTRAST)
                      for c in range(5))
        text += CHARACTERS.get(glyph) or min(CHARACTERS.items(), key=lambda item: _bits_apart(item[0], glyph))[1]
    return text


def _bits_apart(a: bytes, b: bytes) -> int:
    return sum((x ^ y).bit_count() for x, y in zip(a, b))
