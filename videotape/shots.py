import re
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from videotape.screenplay import Scene, Screenplay, ScreenplayError

STATIC = "Static shot."
CLOSE = "Sharp, legible lettering."
DEFAULT_MOVE = "The camera glides smoothly to the next view."
NUMBERS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


class Mode(Enum):
    TEXT_TO_VIDEO = "text-to-video"
    FIRST_AND_LAST_FRAME = "first-and-last-frame"


@dataclass(frozen=True)
class Key:
    """A scene at rest, drawn from its own prompt. Its kept take's last frame is the scene's key image."""

    scene: str
    prompt: str
    mode: ClassVar[Mode] = Mode.TEXT_TO_VIDEO

    @property
    def title(self) -> str:
        return f"key {self.scene}"


@dataclass(frozen=True)
class Move:
    """A press on one scene's button, drawn between that scene's key and the key of the scene it lands on."""

    start: str
    land: str
    label: str
    prompt: str
    mode: ClassVar[Mode] = Mode.FIRST_AND_LAST_FRAME

    @property
    def title(self) -> str:
        return f'{self.start} -> {self.land} "{self.label}"'

    @property
    def move(self) -> str:
        return f"{self.start}--{re.sub(r'[^a-z0-9]+', '-', self.label.lower()).strip('-')}"


Shot = Key | Move


def _quoted(items) -> str:
    quoted = [f'"{item}"' for item in items]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def key_prompt(look: str, scene: Scene) -> str:
    parts = [STATIC, look, scene.direction]
    if scene.shows:
        parts.append(f"The text reads {_quoted(scene.shows)}.")
    if scene.actions:
        count = len(scene.actions)
        number = NUMBERS[count - 1] if count <= len(NUMBERS) else str(count)
        buttons = f"{number} big flat button sits" if count == 1 else f"{number} big flat buttons are stacked"
        below = "Below it, " + buttons if scene.shows else buttons[0].upper() + buttons[1:]
        parts.append(f"{below}, with bold black letters reading {_quoted(scene.actions)}.")
    parts.append(CLOSE)
    return " ".join(part for part in parts if part)


def move_prompt(label: str, move: str | None) -> str:
    return f'The button labelled "{label}" is pressed. {move or DEFAULT_MOVE}'


def plan(screenplay: Screenplay) -> list[Shot]:
    """Every scene's key in walk order, then every move in walk order. The walk is breadth first from the first scene."""
    if not screenplay.scenes:
        raise ScreenplayError("the screenplay has no scenes")
    scenes = screenplay.scenes
    first = next(iter(scenes.values()))
    keys, moves = [Key(first.name, key_prompt(screenplay.look, first))], []
    walked = {first.name}
    queue = deque([first])
    while queue:
        source = queue.popleft()
        for label, action in source.actions.items():
            land = scenes.get(action.to)
            if land is None:
                raise ScreenplayError(f'scene "{source.name}": action "{label}" goes to missing scene "{action.to}"')
            if land.name not in walked:
                walked.add(land.name)
                keys.append(Key(land.name, key_prompt(screenplay.look, land)))
                queue.append(land)
            moves.append(Move(source.name, land.name, label, move_prompt(label, action.move)))
    unreached = [name for name in scenes if name not in walked]
    if unreached:
        raise ScreenplayError(f"no action reaches scene(s): {', '.join(unreached)}")
    return [*keys, *moves]
