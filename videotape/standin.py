"""The stand-in is a model that needs no GPU: it draws each of a prompt's quoted lines as a labelled box, the line
the prompt says is chosen as an inverted one, and its eye reads them back from the pixels. A key drawn from a start
picture opens on that picture and ends on the boxes; a rehearsal's prompt names the control pressed before it says
the clip ends held still on the next screen, and the boxes are that screen's lines. Every clip travels from its first picture to its last by a wipe,
which shows a part of each and blends nothing, unless a flaw makes it dissolve or cut instead; its judge tells a frame
that blends the clip's two ends from one that shows a part of each. A render with it proves everything around the
model."""

import hashlib
import re
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
from pathlib import Path

from videotape import frames
from videotape.checks import Dissolve, Free, Purse, Read, Spot
from videotape.errors import ModelError
from videotape.frames import HEIGHT, WIDTH, Box, Frame
from videotape.plan import Mode
from videotape.story import ARRIVES

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


class Flaw(Enum):
    NONE = "none"
    MISSPELL = "misspell"
    DROP_LINE = "drop line"
    EXTRA_BOX = "extra box"
    WRONG_START = "wrong start"
    WRONG_END = "wrong end"
    DISSOLVE = "dissolve"
    CUT = "cut"


KEY_FLAWS = (Flaw.MISSPELL, Flaw.DROP_LINE, Flaw.EXTRA_BOX)
"""A misspelt line (VT502), a line left out (VT501 and VT502), or a box the prompt never asked for (VT503)."""
TRAVEL_FLAWS = (Flaw.DISSOLVE, Flaw.CUT)
"""A crossfade in place of the wipe (VT507), or a jump through the last picture's negative (VT506)."""
FLAWS = {
    Mode.TEXT_TO_VIDEO: KEY_FLAWS,
    Mode.FIRST_FRAME: KEY_FLAWS,
    Mode.FIRST_AND_LAST_FRAME: (Flaw.WRONG_START, Flaw.WRONG_END, *TRAVEL_FLAWS),
}
"""The flaws a take of each mode may carry by default, so the checks have something to reject: a key flaw on a key,
and on a move a first or last frame that is not its key (VT508) or a travel flaw."""
ASKED = {**FLAWS, Mode.FIRST_FRAME: (*KEY_FLAWS, *TRAVEL_FLAWS)}
"""The flaws a take of each mode carries when asked: a key drawn from a start picture is a move too, so it may
crossfade or jump, though by default it carries a key flaw."""
FLAWED_SEEDS = (1, 2)
"""The seeds that may carry a flaw by default; every later seed is clean."""


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
    modes = frozenset(Mode)

    def __init__(self, flaw: Callable[[Mode, str, int], Flaw] | None = None):
        self.flaw = flaw
        self.calls: list[Call] = []
        self.drawn: dict[Path, tuple[Drawn, ...]] = {}

    @staticmethod
    def settings(mode: Mode) -> dict:
        return {}

    def text_to_video(self, prompt: str, seed: int, out: Path) -> None:
        self._film(Mode.TEXT_TO_VIDEO, prompt, seed, None, None, out)

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> None:
        self._film(Mode.FIRST_AND_LAST_FRAME, prompt, seed, start, end, out)

    def first_frame(self, prompt: str, start: Path, seed: int, out: Path) -> None:
        self._film(Mode.FIRST_FRAME, prompt, seed, start, None, out)

    def download_again(self, out: Path) -> None:
        return None

    def _film(self, mode: Mode, prompt: str, seed: int, start: Path | None, end: Path | None, out: Path) -> None:
        self.calls.append(Call(mode, prompt, seed, start, end, out))
        screen = prompt.partition(ARRIVES.text)[2] or prompt
        rows, marked = quoted(screen), chosen(screen)
        digest = hashlib.sha256(f"{seed}\n{prompt}".encode()).digest()
        kinds = [kind for kind in FLAWS[mode] if mode is Mode.FIRST_AND_LAST_FRAME or rows]
        flaw = self.flaw(mode, prompt, seed) if self.flaw else _default_flaw(digest, seed, kinds)
        if flaw is not Flaw.NONE and (flaw not in ASKED[mode] or (flaw in KEY_FLAWS and not rows)):
            raise ValueError(f"{flaw.name} does not apply to this {mode.value} take")
        if flaw in (Flaw.MISSPELL, Flaw.DROP_LINE):
            rows, (r, i) = _spoil(rows, flaw, digest)
            if flaw is Flaw.DROP_LINE:
                # The lines after the dropped one in its row move up one place, and a dropped chosen line marks nothing.
                marked = {(row, column - (row == r and column > i)) for row, column in marked if (row, column) != (r, i)}
        elif flaw is Flaw.EXTRA_BOX:
            rows = rows + [[EXTRA]]
        with tempfile.TemporaryDirectory() as scratch:
            scratch = Path(scratch)
            drawn: tuple[Drawn, ...] = ()
            if mode is Mode.FIRST_AND_LAST_FRAME:
                first, last = start, end
            else:
                frame, drawn = draw(rows, prompt, marked)
                last = _png(frame, scratch / "drawn.png")
                first = start if mode is Mode.FIRST_FRAME else _png(draw([], prompt)[0], scratch / "background.png")
            if flaw is Flaw.WRONG_START:
                first = _png(_negative(frames.read_png(first)), scratch / "wrong-start.png")
            if flaw is Flaw.WRONG_END:
                last = _png(_negative(frames.read_png(last)), scratch / "wrong-end.png")
            if flaw is Flaw.DISSOLVE:
                frames.crossfade(first, last, out)
            elif flaw is Flaw.CUT:
                frames.cut((first, _png(_negative(frames.read_png(last)), scratch / "flash.png"), last), out)
            else:
                frames.wipe(first, last, out)
        self.drawn[out] = drawn


class StandInEye:
    """Reads the stand-in's boxes back from the pixels. Every box it draws is a control, and a box drawn inverted
    is marked. It reports no charts, and caches nothing in the tape."""

    name = "stand-in"
    key = None
    paid = False

    @staticmethod
    def most(width: int, height: int) -> float:
        return 0.0

    def __init__(self, tape: Path | None = None) -> None:
        pass

    def see(self, frame: Frame, purse: Purse = Free()) -> Read:
        found = _segment(frame)
        return Read(self.name, tuple(Spot(text, box, True) for box, text, _ in found),
                    marked=tuple(box for box, _, inverted in found if inverted))


BLEND = (0.1, 0.9)
"""How far from the first frame toward the last a blend must lie, as a share, to show both: nearer either end it
shows that end."""
BLEND_RESIDUAL = 0.1
"""How far a frame may sit from the nearest blend of the first and last frames, as a share of how far those two sit
apart, and still be one. A crossfade's middle frame sits within 0.03 of its blend, encoding and all; a wipe's, which
shows a part of each picture, sits 0.18 and further from any blend, whatever the pictures show."""
BLEND_APART = 0.001
"""How far the first and last frames must sit from each other, as a mean grey difference, before a frame can be a
blend of them: nearer, they are alike but for the encoding, and every frame shows the one picture. Two of the
stand-in's keys sit about 0.007 apart, and one key encoded twice 0.00004."""


class StandInJudge:
    """Judges the stand-in's moves without a model. A frame shows two pictures overlaid when it is a blend of the
    clip's first and last frames, which a crossfade makes its middle frames; the first and last frames, a frame all
    of one or the other, and a frame that is neither nor a blend of them, as a wipe's middle frames are, show one
    picture. It costs nothing and caches nothing."""

    name = "stand-in"
    key = None
    paid = False

    def __init__(self, tape: Path | None = None) -> None:
        pass

    @staticmethod
    def most(width: int, height: int) -> float:
        return 0.0

    def judge(self, sampled: Sequence[tuple[int, Frame]], purse: Purse = Free()) -> Dissolve:
        greys = frames.gray(*(picture for _, picture in sampled))
        verdicts = [blended(greys[0], greys[-1], grey) for grey in greys]
        return Dissolve(self.name, tuple(number for number, _ in sampled), tuple(overlaid for overlaid, _ in verdicts),
                        tuple(seen for _, seen in verdicts))


def blended(first: bytes, last: bytes, grey: bytes) -> tuple[bool, str]:
    """Whether a grey frame is a blend of the first and last frames that shows both, and what it shows. The blend
    nearest the frame is found by least squares, and the frame is that blend when it sits within BLEND_RESIDUAL of
    it, measured against how far the first and last frames sit apart."""
    apart = sum(abs(b - a) for a, b in zip(first, last))
    if apart / (255 * len(grey)) < BLEND_APART:
        return False, "the first and last frames, which are alike"
    span = sum((b - a) ** 2 for a, b in zip(first, last))
    along = sum((x - a) * (b - a) for a, b, x in zip(first, last, grey)) / span
    residual = sum(abs(x - (a + along * (b - a))) for a, b, x in zip(first, last, grey)) / apart
    if residual > BLEND_RESIDUAL:
        return False, "a picture that is neither the first frame nor the last"
    if along <= BLEND[0]:
        return False, "the first frame"
    if along >= BLEND[1]:
        return False, "the last frame"
    return True, f"the first frame fading into the last, {along:.0%} of the way"


def quoted(prompt: str) -> list[list[str]]:
    """The lines a prompt quotes, in rows: a sentence, or a part of one that ends at a colon or semicolon, is a row.
    A line the prompt quotes again to say it is the chosen one, as in with "Home" chosen, is drawn once."""
    return [[text for text, _ in row] for row in _quotes(prompt)]


def chosen(prompt: str) -> set[tuple[int, int]]:
    """Where the lines a prompt says are chosen sit among its rows, as row and place in the row. A chosen line is
    the one of its own element's sentence, so a heading that shares its words stays as it is."""
    return {(r, i) for r, row in enumerate(_quotes(prompt)) for i, (_, chosen) in enumerate(row) if chosen}


def _quotes(prompt: str) -> list[list[tuple[str, bool]]]:
    """The prompt's quoted lines in rows, each with whether its sentence says it is chosen."""
    rows, row, sentence = list[list[tuple[str, bool]]](), list[tuple[str, bool]](), 0
    parts = re.split(r'"([^"]*)"', prompt)
    for index, part in enumerate(parts):
        if index % 2 and part and parts[index + 1].startswith(" chosen"):
            for at, (text, _) in enumerate(row):
                if text == part:
                    row[at] = (text, True)
                    break
            else:
                for earlier in rows[sentence:]:
                    if (found := next((at for at, (text, _) in enumerate(earlier) if text == part), None)) is not None:
                        earlier[found] = (part, True)
                        break
        elif index % 2:
            if part:
                row.append((part, False))
        else:
            if row and re.search("[.:;]", part):
                rows.append(row)
                row = []
            if "." in part:
                sentence = len(rows)
    return rows + [row] if row else rows


def _default_flaw(digest: bytes, seed: int, kinds: list[Flaw]) -> Flaw:
    """The flaw a take carries by default: one of its kinds on a flawed seed, picked by the hash of the seed and the
    prompt, and none on the other seeds or on half the hashes."""
    if seed not in FLAWED_SEEDS or not kinds or digest[0] % 2:
        return Flaw.NONE
    return kinds[digest[1] % len(kinds)]


def _spoil(rows: list[list[str]], flaw: Flaw, digest: bytes) -> tuple[list[list[str]], tuple[int, int]]:
    """The rows with one line misspelt by a letter, or with one line missing, and where that line was."""
    places = [(r, i) for r, row in enumerate(rows) for i in range(len(row))]
    r, i = places[digest[2] % len(places)]
    text = rows[r][i]
    at = digest[3] % len(text)
    spoilt = [text[:at] + ("x" if text[at] != "x" else "z") + text[at + 1:]] if flaw is Flaw.MISSPELL else []
    return [row[:i] + spoilt + row[i + 1:] if number == r else row for number, row in enumerate(rows)], (r, i)


def _png(frame: Frame, path: Path) -> Path:
    frames.write_png(frame, path)
    return path


def _negative(frame: Frame) -> Frame:
    return Frame(frame.width, frame.height, frame.rgb.translate(bytes(range(255, -1, -1))))


def draw(rows: list[list[str]], prompt: str = "", marked: set[tuple[int, int]] | None = None) -> tuple[Frame, tuple[Drawn, ...]]:
    """Each line as a labelled box, and a line the prompt says is chosen as an inverted one, or the lines at the
    places marked names. A row's boxes run left to right and wrap at the right edge. The prompt leaves its mark along
    the bottom edge."""
    canvas = bytearray(BACKGROUND * (WIDTH * HEIGHT))
    _mark(canvas, prompt)
    marked = chosen(prompt) if marked is None else marked
    drawn = list[Drawn]()
    y = MARGIN
    for r, row in enumerate(rows):
        x = MARGIN
        for i, text in enumerate(row):
            w = (6 * len(text) - 1 + 2 * PAD) * SCALE
            if x > MARGIN and x + w > WIDTH - MARGIN:
                x, y = MARGIN, y + BOX_HEIGHT + GAP * SCALE
            if x + w > WIDTH - MARGIN or y + BOX_HEIGHT > HEIGHT - MARGIN:
                raise _undrawable(f'the stand-in has no room to draw "{text}"')
            box = Box(x, y, w, BOX_HEIGHT)
            fill, ink = (INK, BOX) if (r, i) in marked else (BOX, INK)
            _fill(canvas, box, fill)
            for i, char in enumerate(text):
                _letter(canvas, box.x + (PAD + 6 * i) * SCALE, box.y + PAD * SCALE, char, ink)
            drawn.append(Drawn(text, box))
            x += w + GAP * SCALE
        y += BOX_HEIGHT + GAP * SCALE
    return Frame(WIDTH, HEIGHT, bytes(canvas)), tuple(drawn)


def _undrawable(message: str) -> ModelError:
    """VT406: a line the stand-in cannot draw, on any seed."""
    return ModelError(message, "VT406", "show fewer or shorter lines in the state, in plain ASCII as VT211 asks, or "
                      "render with a Wan model")


def _mark(canvas: bytearray, prompt: str) -> None:
    """A real model draws a look, a direction and an appearance, and the stand-in draws only quoted lines. So that two
    prompts never give one picture, each cell is lighter or darker by one bit of the whole prompt's hash."""
    bits = int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:MARK_CELLS // 8])
    width = WIDTH // MARK_CELLS
    for cell in range(MARK_CELLS):
        shade = MARK_SHADE if bits >> cell & 1 else -MARK_SHADE
        _fill(canvas, Box(cell * width, HEIGHT - MARK_HEIGHT, width, MARK_HEIGHT), bytes(c + shade for c in BACKGROUND))


def _letter(canvas: bytearray, x: int, y: int, char: str, ink: bytes = INK) -> None:
    index = ord(char) - 32
    if not 0 <= index < len(CHARACTERS):
        raise _undrawable(f"the stand-in cannot draw {char!r}")
    for c, column in enumerate(GLYPHS[5 * index:5 * index + 5]):
        for r in range(7):
            if column >> r & 1:
                _fill(canvas, Box(x + c * SCALE, y + r * SCALE, SCALE, SCALE), ink)


def _fill(canvas: bytearray, box: Box, colour: bytes) -> None:
    row = colour * box.w
    for y in range(box.y, box.y + box.h):
        at = (y * WIDTH + box.x) * 3
        canvas[at:at + len(row)] = row


def _segment(frame: Frame) -> list[tuple[Box, str, bool]]:
    """Every box in reading order, with the text in it and whether it is drawn inverted."""
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
                text, fill = _letters(green, width, box)
                found.append((box, text, abs(fill - INK[1]) < abs(fill - BOX[1])))
            left = padding.find(1, right)
    return found


def _letters(green: bytes, width: int, box: Box) -> tuple[str, int]:
    """The text in a box, and the green of its fill, which is the ink's when the box is inverted."""
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
    return text, fill


def _bits_apart(a: bytes, b: bytes) -> int:
    return sum((x ^ y).bit_count() for x, y in zip(a, b))
