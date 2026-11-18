"""A change re-renders the shots whose prompts it changes, every variant whose base it re-renders, the moves that touch
such a key, and nothing else. Contrail is rendered once in the terminal story, one take per shot. Each change is then
made in its own copy of that render and rendered again. What should render again comes from comparing the prompts
before and after the change and from which key each variant is drawn from, and never from the render."""

import shutil
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import contrail_copy, planned, told, words
from videotape import ledger, project
from videotape.made import made
from videotape.plan import FromKey, Mode, Plan
from videotape.render import render
from videotape.standin import Flaw, StandIn, StandInEye
from videotape.story import Story

STORY = "terminal"
CHANGES = {
    "direction": ("stories/terminal.toml", 'results = "The departure board, showing one day\'s flights."',
                  'results = "The departure board at dusk, showing one day\'s flights."'),
    "appearance": ("stories/terminal.toml", 'DatePicker = "a wall calendar of square white tiles',
                   'DatePicker = "a wall calendar of round brass tokens'),
    "look": ("stories/terminal.toml", "low golden sun", "a low red sun"),
    "fare": ("data/flights.json", '"fare": 89,', '"fare": 91,'),
    "base": ("data/flights.json", '"fare": 279,', '"fare": 281,'),
}


@dataclass(frozen=True)
class Planned:
    directory: Path
    plan: Plan
    story: Story

    @property
    def prompts(self) -> dict[str, str]:
        """Each shot's prompt, by the shot's id."""
        return {shot.id: words(shot, self.story) for shot in self.plan.shots}


@dataclass(frozen=True)
class Change:
    plan: Plan
    changed: set[str]
    """The keys whose prompts the change changed."""
    expected_keys: set[str]
    """The changed keys, and every variant whose base changed."""
    expected_moves: set[str]
    """The moves whose prompts it changed, and the moves that start or land on one of those keys."""
    again: set[str]
    """The shots the render filmed again."""
    calls: int

    def touching(self, keys: set[str]) -> set[str]:
        """The moves that start or land on one of these keys."""
        states = {key.state for key in self.plan.keys if key.id in keys}
        return {move.id for move in self.plan.moves if {move.start, move.land} & states}

    def of_scenes(self, *scenes: str) -> set[str]:
        return {key.id for key in self.plan.keys if key.state.scene.name in scenes}


def clean(mode: Mode, prompt: str, seed: int) -> Flaw:
    return Flaw.NONE


def read(directory: Path) -> Planned:
    return Planned(directory, planned(directory), told(directory, STORY))


def film(directory: Path) -> tuple[set[str], int]:
    """Render the project's terminal tape with one take per shot. Returns the shots that were filmed, and the model's
    calls."""
    found, model, tape = read(directory), StandIn(flaw=clean), directory / "tapes" / STORY
    result = render(found.plan, found.story, model, [StandInEye()], tape, ledger.of(directory, tape),
                    made(project.find(directory), found.story, model), takes=1, limit=8)
    return {filmed.shot.id for filmed in result.shots if filmed.rendered}, len(model.calls)


@pytest.fixture(scope="module")
def changes(tmp_path_factory) -> dict[str, Change]:
    root = tmp_path_factory.mktemp("rerender")
    first = read(contrail_copy(root / "first"))
    before = first.prompts
    assert film(first.directory) == (set(before), 160)
    after = dict[str, Planned]()
    for name, (file, old, new) in CHANGES.items():
        directory = Path(shutil.copytree(first.directory, root / name, ignore=shutil.ignore_patterns("__pycache__")))
        source = (directory / file).read_text()
        assert source.count(old) == 1
        (directory / file).write_text(source.replace(old, new))
        after[name] = read(directory)
    # The renders take a minute each, so they run in processes of their own, at once.
    with ProcessPoolExecutor(len(after)) as pool:
        filmed = dict(zip(after, pool.map(film, (changed.directory for changed in after.values()))))
    found = dict[str, Change]()
    for name, changed in after.items():
        now, plan = changed.prompts, changed.plan
        changed_keys = {key.id for key in plan.keys if now[key.id] != before.get(key.id)}
        ids = {key.state: key.id for key in plan.keys}
        keys = changed_keys | {key.id for key in plan.keys if isinstance(key, FromKey) and ids[key.start] in changed_keys}
        redrawn = {key.state for key in plan.keys if key.id in keys}
        moves = {move.id for move in plan.moves
                 if now[move.id] != before.get(move.id) or {move.start, move.land} & redrawn}
        found[name] = Change(plan, changed_keys, keys, moves, *filmed[name])
    return found


@pytest.mark.parametrize("name", sorted(CHANGES))
def test_a_change_films_again_the_keys_whose_prompts_it_changed_the_variants_of_a_changed_base_and_the_moves_that_touch_them(
        changes, name):
    change = changes[name]
    assert change.again == change.expected_keys | change.expected_moves
    assert change.calls == len(change.expected_keys) + len(change.expected_moves)


def test_one_scenes_direction_rerenders_the_whole_scene_and_the_moves_that_touch_it(changes):
    change = changes["direction"]
    assert change.changed == change.expected_keys == change.of_scenes("results")
    assert change.expected_moves == change.touching(change.expected_keys)
    assert (len(change.expected_keys), len(change.expected_moves)) == (9, 45)


def test_one_element_types_appearance_rerenders_the_keys_that_show_it_and_the_moves_that_touch_them(changes):
    change = changes["appearance"]
    assert change.changed == change.expected_keys == {key.id for key in change.plan.keys
                                             if any(element.type == "DatePicker" for element in key.shown)}
    assert change.expected_moves == change.touching(change.expected_keys)
    assert (len(change.expected_keys), len(change.expected_moves)) == (3, 12)


def test_the_look_rerenders_everything(changes):
    change = changes["look"]
    assert (len(change.expected_keys), len(change.expected_moves)) == (58, 102)
    assert change.again == {shot.id for shot in change.plan.shots}


def test_one_fare_that_no_base_shows_rerenders_only_the_keys_that_show_it_and_the_moves_that_touch_them(changes):
    change = changes["fare"]
    shows = {key.state.name: key.id for key in change.plan.keys if any("$91" in line for line in key.lines)}
    assert sorted(shows) == ["dates(SEA)", "flight(CT 300, 2026-12-12)", "results(SEA, 2026-12-11)",
                             "results(SEA, 2026-12-12)", "results(SEA, 2026-12-13)"]
    assert change.changed == change.expected_keys == set(shows.values())
    assert change.expected_moves == change.touching(change.expected_keys)
    assert "flight-ct-300-2026-12-12--book-for-91" in change.expected_moves and "booked-ct-300-2026-12-12" not in change.expected_keys
    assert (len(change.expected_keys), len(change.expected_moves)) == (5, 17)


def test_one_fare_that_three_bases_show_rerenders_those_bases_every_variant_of_their_scenes_and_the_moves_that_touch_them(
        changes):
    change = changes["base"]
    shows = {key.state.name: key.id for key in change.plan.keys if any("$281" in line for line in key.lines)}
    assert sorted(shows) == ["dates(HNL)", "flight(CT 500, 2026-12-11)", "results(HNL, 2026-12-11)",
                             "results(HNL, 2026-12-12)", "results(HNL, 2026-12-13)"]
    assert change.changed == set(shows.values())
    assert change.expected_keys == change.of_scenes("flight", "results", "dates") > change.changed
    assert change.expected_moves == change.touching(change.expected_keys)
    assert (len(change.changed), len(change.expected_keys), len(change.expected_moves)) == (5, 30, 66)
