"""The plan: every state an app can reach, walked breadth first from its entry before anything renders. It holds the
screenplay's words and nothing of how they look, which a story adds when it gives each shot its prompt. A scene's
first state in the walk is its base, drawn from its own prompt, and each later state of the scene is a variant, drawn
from the base's picture so that the scene keeps one layout whatever its data."""

import inspect
import re
from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from videotape import errors
from videotape.errors import ScreenplayError
from videotape.screenplay import Action, Element, Scene, Screenplay, Shown, State

MAX_STATES = 500
MAX_WORDS = 12
PLAIN = "plain ASCII letters, digits, spaces, and . , ' ? ! $ % ( ) : -"
NOT_PLAIN = re.compile(r"[^A-Za-z0-9 .,'?!$%():-]")


class Mode(Enum):
    TEXT_TO_VIDEO = "text-to-video"
    FIRST_AND_LAST_FRAME = "first-and-last-frame"
    FIRST_FRAME = "first-frame"
    """Image to video from a start picture alone: the take opens on it and the prompt draws the rest."""


@dataclass(frozen=True)
class Key:
    """A state at rest, drawn from its own prompt. Its kept take's last frame is the state's key image."""

    id: str
    state: State
    shown: tuple[Shown, ...]
    """What the state shows: each element, in reading order."""
    mode: ClassVar[Mode] = Mode.TEXT_TO_VIDEO

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(line.words for element in self.shown for line in element.lines)

    @property
    def actions(self) -> tuple[Action, ...]:
        return tuple(line.action for element in self.shown for line in element.lines if line.action)

    @property
    def title(self) -> str:
        return f"key {self.state.name}"

    @property
    def image(self) -> str:
        """Where its key image is in a tape."""
        return f"keys/{self.id}.png"


@dataclass(frozen=True)
class FromKey(Key):
    """A variant: a state drawn from its base's key picture, image to video from that picture alone, with the state's
    own prompt, so the picture's layout carries over. Its kept take's last frame is its key image, as a Key's is."""

    start: State
    """The base, which is the first state of the variant's scene in walk order."""
    mode: ClassVar[Mode] = Mode.FIRST_FRAME

    @property
    def title(self) -> str:
        return f"key {self.state.name} from {self.start.name}"


@dataclass(frozen=True)
class Move:
    """A press on one action of a state, drawn between that state's key and the key of the state it leads to."""

    id: str
    start: State
    action: Action
    element: str
    """The type of the element that holds the action."""
    mode: ClassVar[Mode] = Mode.FIRST_AND_LAST_FRAME

    @property
    def land(self) -> State:
        return self.action.to

    @property
    def label(self) -> str:
        return self.action.label

    @property
    def title(self) -> str:
        return f'{self.start.name} -> {self.land.name} "{self.label}"'

    @property
    def clip(self) -> str:
        """Where its kept take is in a tape."""
        return f"moves/{self.id}.mp4"


Shot = Key | Move


@dataclass(frozen=True)
class Plan:
    """Every state's key in walk order, then every action's move in walk order. The first key is the entry's, and
    the first key of each scene is a Key, the scene's base, which the scene's later keys are FromKeys of."""

    title: str
    scenes: tuple[str, ...]
    keys: tuple[Key, ...]
    moves: tuple[Move, ...]
    warnings: tuple[ScreenplayError, ...]

    @property
    def shots(self) -> tuple[Shot, ...]:
        return *self.keys, *self.moves


def plan(screenplay: Screenplay, max_states: int = MAX_STATES) -> Plan:
    entry = _entry(screenplay)
    keys, ids, warned = list[Key](), set[str](), dict[str, ScreenplayError]()
    bases = dict[Scene, State]()
    reached, queue = {entry}, deque([entry])
    while queue:
        state = queue.popleft()
        name, shown, base = _unique(_slug(state.name), ids), _show(state), bases.setdefault(state.scene, state)
        key = Key(name, state, shown) if base is state else FromKey(name, state, shown, base)
        _told_apart(state, key.actions)
        for words in key.lines:
            for warning in _hard_to_letter(state, words):
                warned.setdefault(warning.message, warning)
        for action in key.actions:
            if action.to not in reached:
                if len(reached) == max_states:
                    raise ScreenplayError("VT210", action.to.name, f"the plan reached more than {max_states} states",
                                          "let a scene's arguments come from the data, which ends, or raise max_states "
                                          "in [tool.videotape]")
                reached.add(action.to)
                queue.append(action.to)
        keys.append(key)
    unreached = [scene for scene in screenplay.scenes if scene not in {state.scene for state in reached}]
    if unreached:
        names = [scene.name for scene in unreached]
        raise ScreenplayError("VT204", f"{errors.shown(unreached[0].defined[0])}:{unreached[0].defined[1]}",
                              f"no action reaches the scene{'' if len(names) == 1 else 's'} {' and '.join(names)}",
                              f"lead to it from a scene that is reached, as in to={unreached[0].called}, or delete it")
    moves = [Move(_unique(f"{key.id}--{_slug(line.action.words)}", ids), key.state, line.action, element.type)
             for key in keys for element in key.shown for line in element.lines if line.action]
    return Plan(screenplay.title, tuple(scene.name for scene in screenplay.scenes), tuple(keys), tuple(moves),
                tuple(warned.values()))


def _entry(screenplay: Screenplay) -> State:
    if not screenplay.scenes:
        raise ScreenplayError("VT201", screenplay.defined, "the screenplay has no scenes",
                              "add a scene with @app.scene; the first one is where the app opens")
    first = screenplay.scenes[0]
    needed = [name for name, parameter in first.signature.parameters.items()
              if parameter.default is inspect.Parameter.empty]
    if needed:
        raise ScreenplayError("VT201", f"{errors.shown(first.defined[0])}:{first.defined[1]}",
                              f"the first scene, {first.name}, needs {' and '.join(needed)}, so the app has no state "
                              "to open on", "put a scene with no arguments first")
    return first()


def _show(state: State) -> tuple[Shown, ...]:
    scene = state.scene
    try:
        shown = list[Shown]()
        for element in scene.build(*state.args):
            if not isinstance(element, Element):
                raise TypeError(f"{scene.name} returned {element!r}, which is not an element")
            shown.append(element.show(state))
        return tuple(shown)
    except ScreenplayError as error:
        raise error.in_state(state.name) from None
    except Exception as error:
        raise ScreenplayError("VT203", errors.raised(error.__traceback__, scene.defined),
                              f"the scene raised {type(error).__name__}: {error}, in state {state.name}",
                              "make the scene build for these arguments, or keep this state out of every to=") from error


def _told_apart(state: State, actions: tuple[Action, ...]) -> None:
    for what, values, fix in (
            ("have the spoken name", [action.label for action in actions], "give each action words of its own"),
            ("are found by the words", [action.words for action in actions],
             "make the words differ, such as each row's title")):
        shared = [value for value, count in Counter(values).items() if count > 1]
        if shared:
            raise ScreenplayError("VT209", state.name, f'two actions {what} "{shared[0]}"', fix)


def _hard_to_letter(state: State, words: str) -> list[ScreenplayError]:
    found = list[ScreenplayError]()
    count = len(words.split())
    if count > MAX_WORDS:
        found.append(ScreenplayError("VT211", state.name, f'the line "{words}" has {count} words',
                                     f"shorten it to {MAX_WORDS} words or fewer"))
    odd = sorted(set(NOT_PLAIN.findall(words)))
    if odd:
        found.append(ScreenplayError("VT211", state.name, f'the line "{words}" has the character'
                                     f'{"" if len(odd) == 1 else "s"} {" ".join(odd)}', f"write it with {PLAIN}"))
    return found


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _unique(name: str, taken: set[str]) -> str:
    """A file-safe name no other state or move has. Two that slug alike are told apart by a number."""
    unique, number = name, 1
    while unique in taken:
        number += 1
        unique = f"{name}-{number}"
    taken.add(unique)
    return unique
