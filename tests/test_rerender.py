"""A change re-renders the keys whose prompts it changes, every key drawn from the picture of a key it re-renders, down
the walk, the pinned moves that touch such a key or whose own prompt changed, and nothing else. Contrail is rendered
once in the terminal story, one take per shot. Each change is then made in its own copy of that render and rendered
again. What should render again comes from comparing the prompts before and after the change and from which key each
key is drawn from, and never from the render."""

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
from videotape.standin import Flaw, StandIn, StandInEye, StandInJudge
from videotape.story import Story

STORY = "terminal"
CHANGES = {
    "direction": ("stories/terminal.toml", 'results = "The departure board, showing one day\'s flights."',
                  'results = "The departure board at dusk, showing one day\'s flights."'),
    "appearance": ("stories/terminal.toml", 'DatePicker = "a wall calendar page',
                   'DatePicker = "a brass calendar plate'),
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
        """Each shot's prompt, by the shot's id: a rehearsal's is the move's words and the state's."""
        return {shot.id: words(shot, self.story) for shot in self.plan.shots}


@dataclass(frozen=True)
class Change:
    plan: Plan
    changed: set[str]
    """The keys whose prompts the change changed."""
    expected_keys: set[str]
    """The changed keys, and every key drawn from the picture of a key here, down the walk: a variant from its
    base, a rehearsal from the key of the state it is reached from."""
    expected_moves: set[str]
    """The pinned moves whose prompts it changed, and those that start or land on one of those keys."""
    again: set[str]
    """The shots the render filmed again."""
    calls: int

    @property
    def surely(self) -> set[str]:
        """The shots whose take surely changed: the keys whose prompts changed, whose pictures the stand-in marks with
        the prompt, the keys drawn from those pictures, and the pinned moves whose prompts changed or that touch a
        changed key. A key drawn again from a changed picture ends on the same boxes, and whether its encoded last
        frame is the same bytes is the encoder's to say, so what is drawn from it may or may not film again."""
        ids = {key.state: key.id for key in self.plan.keys}
        keys = self.changed | {key.id for key in self.plan.keys if isinstance(key, FromKey) and ids[key.start] in self.changed}
        return keys | {move.id for move in self.expected_moves_of(self.changed)}

    def expected_moves_of(self, keys: set[str]):
        states = {key.state for key in self.plan.keys if key.id in keys}
        return [move for move in self.plan.pinned if move.id in self.expected_moves and {move.start, move.land} & states]

    def touching(self, keys: set[str]) -> set[str]:
        """The pinned moves that start or land on one of these keys."""
        states = {key.state for key in self.plan.keys if key.id in keys}
        return {move.id for move in self.plan.pinned if {move.start, move.land} & states}

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
    result = render(found.plan, found.story, model, [StandInEye()], StandInJudge(), tape, ledger.of(directory, tape),
                    made(project.find(directory), found.story, model), takes=1, limit=8)
    return {filmed.shot.id for filmed in result.shots if filmed.rendered}, len(model.calls)


def downstream(plan: Plan, changed: set[str]) -> set[str]:
    """The changed keys and every key drawn, down the walk, from the picture of one of them."""
    ids = {key.state: key.id for key in plan.keys}
    redrawn = set[str]()
    for key in plan.keys:
        if key.id in changed or (isinstance(key, FromKey) and ids[key.start] in redrawn):
            redrawn.add(key.id)
    return redrawn


@pytest.fixture(scope="module")
def changes(tmp_path_factory) -> dict[str, Change]:
    root = tmp_path_factory.mktemp("rerender")
    first = read(contrail_copy(root / "first"))
    before = first.prompts
    assert film(first.directory) == (set(before), 150)
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
        keys = downstream(plan, changed_keys)
        redrawn = {key.state for key in plan.keys if key.id in keys}
        moves = {move.id for move in plan.pinned
                 if now[move.id] != before.get(move.id) or {move.start, move.land} & redrawn}
        found[name] = Change(plan, changed_keys, keys, moves, *filmed[name])
    return found


@pytest.mark.parametrize("name", sorted(CHANGES))
def test_a_change_films_again_the_keys_whose_prompts_it_changed_what_is_drawn_from_their_pictures_and_the_pinned_moves_that_touch_them_and_nothing_else(
        changes, name):
    change = changes[name]
    assert change.surely <= change.again <= change.expected_keys | change.expected_moves
    assert change.calls == len(change.again)


def test_one_scenes_direction_rerenders_the_whole_scene_and_every_scene_first_reached_through_it(changes):
    """The results scene's base is rehearsed from dates(HNL), and the flight scene's base from it, and booked's from
    flight's, so a new direction for results draws those three scenes again and the pinned moves that touch them."""
    change = changes["direction"]
    assert change.changed == change.of_scenes("results")
    assert change.expected_keys == change.of_scenes("results", "flight", "booked") > change.changed
    assert change.expected_moves == change.touching(change.expected_keys)
    assert (len(change.changed), len(change.expected_keys), len(change.expected_moves)) == (9, 45, 78)
    results = change.of_scenes("results")
    reached = {key.id for key in change.plan.rehearsals if key.start.scene.name == "results"}
    assert change.surely == results | reached | change.touching(results) and len(change.surely) == 53


def test_one_element_types_appearance_rerenders_the_keys_that_show_it_and_everything_down_the_walk(changes):
    change = changes["appearance"]
    assert change.changed == {key.id for key in change.plan.keys
                              if any(element.type == "DatePicker" for element in key.shown)}
    assert change.changed == change.of_scenes("dates")
    assert change.expected_keys == change.of_scenes("dates", "results", "flight", "booked")
    assert change.expected_moves == change.touching(change.expected_keys)
    assert (len(change.changed), len(change.expected_keys), len(change.expected_moves)) == (3, 48, 80)


def test_the_look_rerenders_everything(changes):
    change = changes["look"]
    assert (len(change.expected_keys), len(change.expected_moves)) == (58, 92)
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
    assert change.again == change.expected_keys | change.expected_moves


def test_one_fare_that_three_bases_show_rerenders_those_bases_and_every_key_down_the_walk_from_them(changes):
    """The fare is on the keys of dates(HNL), results(HNL, ...) and flight(CT 500, ...), and in the label of the move
    that first reaches booked(CT 500, ...), whose key is rehearsed from it. From dates(HNL) the walk reaches every
    results, flight and booked key."""
    change = changes["base"]
    shows = {key.state.name: key.id for key in change.plan.keys if any("$281" in line for line in key.lines)}
    assert sorted(shows) == ["dates(HNL)", "flight(CT 500, 2026-12-11)", "results(HNL, 2026-12-11)",
                             "results(HNL, 2026-12-12)", "results(HNL, 2026-12-13)"]
    assert change.changed == set(shows.values()) | {"booked-ct-500-2026-12-11"}
    assert change.expected_keys == change.of_scenes("flight", "results", "dates", "booked") > change.changed
    assert change.expected_moves == change.touching(change.expected_keys)
    assert (len(change.changed), len(change.expected_keys), len(change.expected_moves)) == (6, 48, 80)
