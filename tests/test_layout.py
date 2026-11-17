"""The layout check compares two keys outside the text the readers found, and a person's marks set its threshold."""

import pytest

from videotape import layout
from videotape.errors import ScreenplayError
from videotape.frames import Box, Frame
from videotape.layout import Bar, Layout, bar, distances

WIDTH, HEIGHT = 320, 176
GREY, INK, AMBER = (120, 120, 120), (20, 20, 20), (230, 160, 40)
TEXT = Box(40, 40, 120, 30)
BANNER = Box(180, 100, 120, 60)


def picture(*painted: tuple[Box, tuple[int, int, int]]) -> Frame:
    """A grey picture with each box painted in its colour."""
    canvas = bytearray(bytes(GREY) * (WIDTH * HEIGHT))
    for box, colour in painted:
        for y in range(box.y, box.y + box.h):
            at = (y * WIDTH + box.x) * 3
            canvas[at:at + box.w * 3] = bytes(colour) * box.w
    return Frame(WIDTH, HEIGHT, bytes(canvas))


def test_one_picture_twice_is_at_no_distance_with_the_whole_picture_compared():
    plain = picture((TEXT, INK))
    assert distances(plain, [], plain, []) == Layout(0.0, 0.0, 1.0)


def test_text_inside_a_readers_box_is_left_out_of_both_and_what_is_painted_outside_counts():
    a, b = picture((TEXT, INK)), picture((Box(TEXT.x + 10, TEXT.y, 60, TEXT.h), AMBER))
    unmasked, masked = distances(a, [], b, []), distances(a, [TEXT], b, [TEXT])
    assert unmasked.shading > 0 and unmasked.edges > 0 and unmasked.kept == 1.0
    assert (masked.shading, masked.edges) == (0.0, 0.0) and 0.8 < masked.kept < 1.0
    banner = distances(a, [TEXT], picture((TEXT, INK), (BANNER, AMBER)), [TEXT])
    assert banner.shading > 0.02 and banner.edges > 0.5 and banner.kept == masked.kept


def test_the_mask_reaches_a_little_past_the_box_so_a_readers_loose_box_still_hides_the_letters():
    a, b = picture((TEXT, INK)), picture((Box(TEXT.x - 2, TEXT.y - 1, TEXT.w + 4, TEXT.h + 2), INK))
    assert distances(a, [TEXT], b, [TEXT]) == Layout(0.0, 0.0, distances(a, [TEXT], b, [TEXT]).kept)


def test_two_pictures_of_two_sizes_cannot_be_compared():
    with pytest.raises(ScreenplayError) as refused:
        distances(picture(), [], Frame(WIDTH, HEIGHT // 2, bytes(GREY) * (WIDTH * HEIGHT // 2)), [])
    assert refused.value.code == "VT407"


def at(shading: float, edges: float = 0.5) -> Layout:
    return Layout(shading, edges, 0.9)


def test_without_marks_there_is_no_bar():
    assert bar([]) is None


def test_the_bar_is_the_metric_and_threshold_that_agree_with_the_most_marks_midway_between_the_pairs_they_part():
    found = bar([(at(0.01), True), (at(0.02), True), (at(0.2), False), (at(0.3), False)])
    assert found == Bar("shading", 0.11, 4, 4) and found.held and found.share == 1.0
    assert found.same(at(0.11)) and not found.same(at(0.12))


def test_edges_are_the_metric_when_they_part_the_marks_and_shading_does_not():
    found = bar([(at(0.1, 0.1), True), (at(0.3, 0.2), True), (at(0.2, 0.8), False), (at(0.4, 0.9), False)])
    assert found == Bar("edges", 0.5, 4, 4)


def test_a_tie_between_the_metrics_goes_to_shading_and_every_pair_the_same_puts_the_bar_at_the_highest_distance():
    assert bar([(at(0.1, 0.1), True), (at(0.5, 0.9), False)]).metric == "shading"
    assert bar([(at(0.1), True), (at(0.4), True)]) == Bar("shading", 0.4, 2, 2)


def test_marks_the_distances_cannot_part_leave_the_bar_short_of_agreement_and_not_held():
    marks = [(at(0.1), True), (at(0.2), False), (at(0.3), True), (at(0.4), False), (at(0.5), True)]
    found = bar(marks)
    assert found is not None and found.of == 5 and found.agreed == 3 and not found.held


@pytest.mark.parametrize("agreed, of, held", [(9, 10, True), (18, 20, True), (17, 20, False), (0, 0, False)])
def test_the_bar_holds_at_90_percent_of_the_marks(agreed, of, held):
    assert layout.AGREEMENT == 0.9 and Bar("shading", 0.1, agreed, of).held is held


def test_the_bar_a_render_judges_by_is_the_one_the_marks_of_the_variants_test_set():
    assert layout.BAR == Bar("shading", 0.1525, 72, 75) and layout.BAR.held
    assert layout.BAR.same(at(0.1525)) and not layout.BAR.same(at(0.1526))
