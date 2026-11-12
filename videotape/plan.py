"""The plan: every state an app can reach, walked breadth first from its entry before anything renders."""

import inspect
import re
from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from videotape import errors
from videotape.errors import ScreenplayError
from videotape.screenplay import Action, Element, Screenplay, Shown, State

MAX_STATES = 500
MAX_WORDS = 12
PLAIN = "plain ASCII letters, digits, spaces, and . , ' ? ! $ % ( ) : -"
NOT_PLAIN = re.compile(r"[^A-Za-z0-9 .,'?!$%():-]")


class Mode(Enum):
    TEXT_TO_VIDEO = "text-to-video"
    FIRST_AND_LAST_FRAME = "first-and-last-frame"


@dataclass(frozen=True)
class Key:
    """A state at rest, drawn from its own prompt. Its kept take's last frame is the state's key image."""

    id: str
    state: State
    prompt: str
    lines: tuple[str, ...]
    actions: tuple[Action, ...]
    mode: ClassVar[Mode] = Mode.TEXT_TO_VIDEO

    @property
    def title(self) -> str:
        return f"key {self.state.name}"

    @property
    def image(self) -> str:
        """Where its key image is in a tape."""
        return f"keys/{self.id}.png"


@dataclass(frozen=True)
class Move:
    """A press on one action of a state, drawn between that state's key and the key of the state it leads to."""

    id: str
    start: State
    land: State
    label: str
    prompt: str
    mode: ClassVar[Mode] = Mode.FIRST_AND_LAST_FRAME

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
    """Every state's key in walk order, then every action's move in walk order. The first key is the entry's."""

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
    title = screenplay.title
    keys, ids, warned = list[Key](), set[str](), dict[str, ScreenplayError]()
    reached, queue = {entry}, deque([entry])
    while queue:
        state = queue.popleft()
        shown = _show(state)
        lines = tuple(line for element in shown for line in element.lines)
        actions = tuple(line.action for line in lines if line.action)
        _told_apart(state, actions)
        for line in lines:
            for warning in _hard_to_letter(state, line.words):
                warned.setdefault(warning.message, warning)
        for action in actions:
            if action.to not in reached:
                if len(reached) == max_states:
                    raise ScreenplayError("VT210", action.to.name, f"the plan reached more than {max_states} states",
                                          "take a scene's arguments from the data, which ends, or raise max_states "
                                          "in [tool.videotape]")
                reached.add(action.to)
                queue.append(action.to)
        prompt = f"The {title} app at rest, flat and head-on. {' '.join(element.sentence for element in shown)} " \
                 "Sharp, legible lettering."
        keys.append(Key(_unique(_slug(state.name), ids), state, prompt, tuple(line.words for line in lines), actions))
    unreached = [scene for scene in screenplay.scenes if scene not in {state.scene for state in reached}]
    if unreached:
        names = [scene.name for scene in unreached]
        raise ScreenplayError("VT204", f"{errors.shown(unreached[0].defined[0])}:{unreached[0].defined[1]}",
                              f"no action reaches the scene{'' if len(names) == 1 else 's'} {' and '.join(names)}",
                              f"lead to it from a scene that is reached, as in to={unreached[0].called}, or delete it")
    moves = list[Move]()
    for key in keys:
        for action in key.actions:
            prompt = f'The {action.kind} "{action.words}" is pressed. The app changes smoothly to what it shows next.'
            moves.append(Move(_unique(f"{key.id}--{_slug(action.words)}", ids), key.state, action.to, action.label,
                              prompt))
    return Plan(title, tuple(scene.name for scene in screenplay.scenes), tuple(keys), tuple(moves),
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
                              "to open on", "put a scene that takes no arguments first")
    return first()


def _show(state: State) -> list[Shown]:
    scene = state.scene
    try:
        shown = list[Shown]()
        for element in scene.build(*state.args):
            if not isinstance(element, Element):
                raise TypeError(f"{scene.name} returned {element!r}, which is not an element")
            shown.append(element.show(state))
        return shown
    except ScreenplayError as error:
        raise error.in_state(state.name) from None
    except Exception as error:
        raise ScreenplayError("VT203", errors.raised(error.__traceback__, scene.defined),
                              f"the scene raised {type(error).__name__}: {error}, in state {state.name}",
                              "make the scene build for these arguments, or keep this state out of every to=") from error


def _told_apart(state: State, actions: tuple[Action, ...]) -> None:
    for what, values, fix in (
            ("have the label", [action.label for action in actions], "give each action its own label"),
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
