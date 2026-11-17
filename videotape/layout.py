"""The layout check, VT505: two keys of one scene compared outside the text the readers found, so that two states
drawn in one layout with other words on it count as the same layout, and two drawn each in a layout of its own do
not.

Both pictures are scaled to one small grey picture each, the box of every line and control a reader read is left out
of both, padded a little, and what remains is measured two ways:

    shading   the mean absolute difference of the grey values: 0 for one picture twice, 1 for black against white
    edges     one minus the correlation of the edge strength: 0 where the edges lie alike, 1 where they are unrelated

No number says what a person calls the same layout, so the threshold that tells the same from different comes from a
person's marks: scripts/variants-test shows each pair, the person marks it the same layout or different, and bar picks
the metric and the threshold that agree with the most marks. BAR holds the one those marks set, which a render judges
every variant's take by."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from videotape import frames
from videotape.frames import SMALL, Box, Frame

CODE = "VT505"
PAD = 0.01
"""How far past a reader's box the mask reaches, as a share of the picture's width and of its height."""
METRICS = ("shading", "edges")
"""The distances, in the order a tie between them breaks."""
AGREEMENT = 0.9
"""The least share of a person's marks a threshold must agree with before the check judges by it."""


@dataclass(frozen=True)
class Layout:
    """How far one key's layout sits from another's, each way, and how much of the picture was compared."""

    shading: float
    edges: float
    kept: float
    """The share of the small picture outside both masks."""

    def by(self, metric: str) -> float:
        return getattr(self, metric)


@dataclass(frozen=True)
class Bar:
    """The threshold a person's marks set: the metric, the distance up to which two keys share a layout, and how many
    of the marks it agrees with."""

    metric: str
    threshold: float
    agreed: int
    of: int

    @property
    def share(self) -> float:
        return self.agreed / self.of if self.of else 0.0

    @property
    def held(self) -> bool:
        return self.of > 0 and self.share >= AGREEMENT

    def same(self, layout: Layout) -> bool:
        return layout.by(self.metric) <= self.threshold


BAR = Bar("shading", 0.1525, 72, 75)
"""The threshold a render judges VT505 by. It comes from a person's marks in scripts/variants-test on 2026-11-17, on
gemini-omni-flash-1.2's takes of Contrail's terminal story: of the 75 pairs marked, shading at 0.1525 agrees with
the marks on 72."""


def distances(a: Frame, a_text: Sequence[Box], b: Frame, b_text: Sequence[Box]) -> Layout:
    """How far b's layout sits from a's, outside the boxes of the text each reader found on each, which are in each
    picture's own pixels. The mask reaches PAD past each box and a cell of the small picture more, as far as the
    edge strength of a cell beside it reaches."""
    width, height = SMALL
    small_a, small_b = frames.gray(a, b)
    masked = bytearray(width * height)
    for frame, boxes in ((a, a_text), (b, b_text)):
        for box in boxes:
            x0 = max(0, math.floor((box.x / frame.width - PAD) * width) - 1)
            x1 = min(width, math.ceil(((box.x + box.w) / frame.width + PAD) * width) + 1)
            y0 = max(0, math.floor((box.y / frame.height - PAD) * height) - 1)
            y1 = min(height, math.ceil(((box.y + box.h) / frame.height + PAD) * height) + 1)
            for y in range(y0, y1):
                masked[y * width + x0:y * width + x1] = b"\x01" * (x1 - x0)
    kept = [at for at, hidden in enumerate(masked) if not hidden]
    if not kept:
        return Layout(0.0, 0.0, 0.0)
    shading = sum(abs(small_a[at] - small_b[at]) for at in kept) / (255 * len(kept))
    edges_a, edges_b = _edges(small_a, width, height), _edges(small_b, width, height)
    edges = 1 - _correlation([edges_a[at] for at in kept], [edges_b[at] for at in kept])
    return Layout(round(shading, 4), round(edges, 4), round(len(kept) / len(masked), 4))


def _edges(grey: bytes, width: int, height: int) -> list[float]:
    """The edge strength at each pixel, the magnitude of the Sobel gradient, and 0 along the border."""
    strength = [0.0] * (width * height)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            at = y * width + x
            above, below = at - width, at + width
            across = (grey[above + 1] + 2 * grey[at + 1] + grey[below + 1]) - (grey[above - 1] + 2 * grey[at - 1] + grey[below - 1])
            down = (grey[below - 1] + 2 * grey[below] + grey[below + 1]) - (grey[above - 1] + 2 * grey[above] + grey[above + 1])
            strength[at] = math.hypot(across, down)
    return strength


def _correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson's, and when one side is flat, 1 when both are, since nothing sets them apart, else 0."""
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    spread_a, spread_b = sum((x - mean_a) ** 2 for x in a), sum((y - mean_b) ** 2 for y in b)
    if not spread_a or not spread_b:
        return 1.0 if spread_a == spread_b else 0.0
    return sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / math.sqrt(spread_a * spread_b)


def bar(marked: Sequence[tuple[Layout, bool]]) -> Bar | None:
    """The metric and the threshold that agree with the most marks, each mark a pair's distances and whether a person
    called the pair the same layout. For each metric the thresholds tried lie midway between two neighbouring
    distances among the marked pairs, midway between 0 and the lowest, and at the highest, which calls every pair the
    same. A tie goes to the metric listed first, then to the threshold farthest from any marked distance. None without
    marks."""
    if not marked:
        return None
    best: tuple[tuple[int, int, float], Bar] | None = None
    for place, metric in enumerate(METRICS):
        values = sorted({layout.by(metric) for layout, _ in marked})
        steps = [0.0, *values]
        for threshold in [*((low + high) / 2 for low, high in zip(steps, steps[1:])), values[-1]]:
            agreed = sum((layout.by(metric) <= threshold) == same for layout, same in marked)
            margin = min(abs(threshold - value) for value in values)
            rank = (agreed, -place, margin)
            if best is None or rank > best[0]:
                best = rank, Bar(metric, threshold, agreed, len(marked))
    return best[1]
