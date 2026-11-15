"""The stand-in is a model that needs no GPU: it draws each of a prompt's quoted lines as a labelled box, and its eye
reads them back from the pixels. A render with it proves everything around the model."""

import hashlib
import re
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
from pathlib import Path

from videotape import frames
from videotape.checks import Spot
from videotape.frames import HEIGHT, WIDTH, Box, Frame
from videotape.plan import Mode

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
SCALE = 3
PAD = 2
GAP = 3
MARGIN = 24
BOX_HEIGHT = (7 + 2 * PAD) * SCALE
BACKGROUND, BOX, INK = bytes.fromhex("2f6f7e"), bytes.fromhex("f7f1e3"), bytes.fromhex("1a1a1a")
CONTRAST = 30
# The mark is a row of cells along the bottom edge, below every box. A cell is this much lighter or darker than the
# background, which is too little for the eye to take it for a box.
MARK_CELLS, MARK_HEIGHT, MARK_SHADE = 64, 16, 8
# What the extra box flaw letters: a line no screenplay shows, drawn as one more row.
EXTRA = "Not in the script"


class StandInError(RuntimeError):
    pass


class Flaw(Enum):
    NONE = "none"
    MISSPELL = "misspell"
    DROP_LINE = "drop line"
    EXTRA_BOX = "extra box"
    WRONG_START = "wrong start"
    WRONG_END = "wrong end"


# Seeds 1 and 2 may carry a flaw of their kind, so the checks have something to reject. Seed 3 is always clean. A key
# flaw is a misspelt line (VT502), a line left out (VT501 and VT502), or a box the prompt never asked for (VT503).
FLAWS = {
    Mode.TEXT_TO_VIDEO: (Flaw.MISSPELL, Flaw.DROP_LINE, Flaw.EXTRA_BOX),
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
    box: Box


class StandIn:
    name = "stand-in"
    device = "cpu"
    price = None

    def __init__(self, flaw: Callable[[Mode, str, int], Flaw] | None = None):
        self.flaw = flaw
        self.calls: list[Call] = []
        self.drawn: dict[Path, tuple[Drawn, ...]] = {}

    def settings(self, mode: Mode) -> dict:
        return {}

    def text_to_video(self, prompt: str, seed: int, out: Path) -> None:
        self._film(Mode.TEXT_TO_VIDEO, prompt, seed, None, None, out)

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> None:
        self._film(Mode.FIRST_AND_LAST_FRAME, prompt, seed, start, end, out)

    def download_again(self, out: Path) -> None:
        return None

    def _film(self, mode: Mode, prompt: str, seed: int, start: Path | None, end: Path | None, out: Path) -> None:
        self.calls.append(Call(mode, prompt, seed, start, end, out))
        rows = quoted(prompt)
        digest = hashlib.sha256(f"{seed}\n{prompt}".encode()).digest()
        kinds = [kind for kind in FLAWS[mode] if mode is Mode.FIRST_AND_LAST_FRAME or rows]
        flaw = self.flaw(mode, prompt, seed) if self.flaw else _default_flaw(digest, seed, kinds)
        if flaw is not Flaw.NONE and flaw not in kinds:
            raise ValueError(f"{flaw.name} does not apply to this {mode.value} take")
        if flaw in (Flaw.MISSPELL, Flaw.DROP_LINE):
            rows = _spoil(rows, flaw, digest)
        elif flaw is Flaw.EXTRA_BOX:
            rows = rows + [[EXTRA]]
        with tempfile.TemporaryDirectory() as scratch:
            scratch = Path(scratch)
            drawn: tuple[Drawn, ...] = ()
            if mode is Mode.FIRST_AND_LAST_FRAME:
                first, last = start, end
            else:
                frame, drawn = draw(rows, prompt)
                last = _png(frame, scratch / "drawn.png")
                first = _png(draw([], prompt)[0], scratch / "background.png")
            if flaw is Flaw.WRONG_START:
                first = _png(_negative(frames.read_png(first)), scratch / "wrong-start.png")
            if flaw is Flaw.WRONG_END:
                last = _png(_negative(frames.read_png(last)), scratch / "wrong-end.png")
            frames.crossfade(first, last, out)
        self.drawn[out] = drawn


class StandInEye:
    """Reads the stand-in's boxes back from the pixels. Every box it draws is a control."""

    name = "stand-in"

    def see(self, frame: Frame) -> tuple[Spot, ...]:
        return tuple(Spot(text, box, True) for box, text in _segment(frame))


def quoted(prompt: str) -> list[list[str]]:
    """The lines a prompt quotes, in rows: a sentence, or a part of one that ends at a colon or semicolon, is a row.
    A line the prompt quotes again to say it is the chosen one, as in with "Home" chosen, is drawn once."""
    rows, row = list[list[str]](), list[str]()
    parts = re.split(r'"([^"]*)"', prompt)
    for index, part in enumerate(parts):
        if index % 2:
            if part and not parts[index + 1].startswith(" chosen"):
                row.append(part)
        elif row and re.search("[.:;]", part):
            rows.append(row)
            row = []
    return rows + [row] if row else rows


def _default_flaw(digest: bytes, seed: int, kinds: list[Flaw]) -> Flaw:
    if seed not in (1, 2) or not kinds or digest[0] % 2:
        return Flaw.NONE
    return kinds[digest[1] % len(kinds)]


def _spoil(rows: list[list[str]], flaw: Flaw, digest: bytes) -> list[list[str]]:
    """The rows with one line misspelt by a letter, or with one line missing."""
    places = [(r, i) for r, row in enumerate(rows) for i in range(len(row))]
    r, i = places[digest[2] % len(places)]
    text = rows[r][i]
    at = digest[3] % len(text)
    spoilt = [text[:at] + ("x" if text[at] != "x" else "z") + text[at + 1:]] if flaw is Flaw.MISSPELL else []
    return [row[:i] + spoilt + row[i + 1:] if number == r else row for number, row in enumerate(rows)]


def _png(frame: Frame, path: Path) -> Path:
    frames.write_png(frame, path)
    return path


def _negative(frame: Frame) -> Frame:
    return Frame(frame.width, frame.height, frame.rgb.translate(bytes(range(255, -1, -1))))


def draw(rows: list[list[str]], prompt: str = "") -> tuple[Frame, tuple[Drawn, ...]]:
    """Each line as a labelled box. A row's boxes run left to right and wrap at the right edge. The prompt leaves its
    mark along the bottom edge."""
    canvas = bytearray(BACKGROUND * (WIDTH * HEIGHT))
    _mark(canvas, prompt)
    drawn = list[Drawn]()
    y = MARGIN
    for row in rows:
        x = MARGIN
        for text in row:
            w = (6 * len(text) - 1 + 2 * PAD) * SCALE
            if x > MARGIN and x + w > WIDTH - MARGIN:
                x, y = MARGIN, y + BOX_HEIGHT + GAP * SCALE
            if x + w > WIDTH - MARGIN or y + BOX_HEIGHT > HEIGHT - MARGIN:
                raise StandInError(f'the stand-in has no room to draw "{text}"')
            box = Box(x, y, w, BOX_HEIGHT)
            _fill(canvas, box, BOX)
            for i, char in enumerate(text):
                _letter(canvas, box.x + (PAD + 6 * i) * SCALE, box.y + PAD * SCALE, char)
            drawn.append(Drawn(text, box))
            x += w + GAP * SCALE
        y += BOX_HEIGHT + GAP * SCALE
    return Frame(WIDTH, HEIGHT, bytes(canvas)), tuple(drawn)


def _mark(canvas: bytearray, prompt: str) -> None:
    """A real model draws a look, a direction and an appearance, and the stand-in draws only quoted lines. So that two
    prompts never give one picture, each cell is lighter or darker by one bit of the whole prompt's hash."""
    bits = int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:MARK_CELLS // 8])
    width = WIDTH // MARK_CELLS
    for cell in range(MARK_CELLS):
        shade = MARK_SHADE if bits >> cell & 1 else -MARK_SHADE
        _fill(canvas, Box(cell * width, HEIGHT - MARK_HEIGHT, width, MARK_HEIGHT), bytes(c + shade for c in BACKGROUND))


def _letter(canvas: bytearray, x: int, y: int, char: str) -> None:
    index = ord(char) - 32
    if not 0 <= index < len(CHARACTERS):
        raise StandInError(f"the stand-in cannot draw {char!r}")
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
    """Every box in reading order with the text in it."""
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
        # A row of pixels inside the boxes' padding is lit across each whole box and dark between boxes.
        padding = mask[(rows[0] + SCALE) * width:(rows[0] + SCALE + 1) * width]
        left = padding.find(1)
        while left != -1:
            right = padding.find(0, left)
            right = width if right == -1 else right
            if right - left >= (4 + 2 * PAD) * SCALE:
                box = Box(left, rows[0], right - left, len(rows))
                found.append((box, _letters(green, width, box)))
            left = padding.find(1, right)
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
