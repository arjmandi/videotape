import re
from collections import deque
from dataclasses import dataclass
from enum import Enum

from videotape.screenplay import Scene, Screenplay, ScreenplayError

OPENING_MOVE = "The camera slowly pushes in."
DEFAULT_MOVE = "The camera glides smoothly to the next view."
CLOSE = "The camera settles and holds still. Large, crisp, legible lettering."


class Mode(Enum):
    TEXT_TO_VIDEO = "text-to-video"
    IMAGE_TO_VIDEO = "image-to-video"
    FIRST_AND_LAST_FRAME = "first-and-last-frame"


@dataclass(frozen=True)
class Shot:
    mode: Mode
    start: str | None
    land: str
    label: str | None
    prompt: str

    @property
    def title(self) -> str:
        return f"{self.start or 'opening'} -> {self.land}" + (f' "{self.label}"' if self.label else "")

    @property
    def move(self) -> str:
        if self.label is None:
            return "opening"
        return f"{self.start}--{re.sub(r'[^a-z0-9]+', '-', self.label.lower()).strip('-')}"


def _quoted(items) -> str:
    quoted = [f'"{item}"' for item in items]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _prompt(look: str, press: str | None, move: str, land: Scene) -> str:
    parts = [look]
    if press is not None:
        parts.append(f'The button labelled "{press}" is pressed.')
    parts += [move, land.direction]
    if land.shows:
        parts.append(f"The lettering reads {_quoted(land.shows)}.")
    if len(land.actions) == 1:
        parts.append(f"A button is labelled {_quoted(land.actions)}.")
    elif land.actions:
        parts.append(f"Buttons are labelled {_quoted(land.actions)}.")
    parts.append(CLOSE)
    return " ".join(part for part in parts if part)


def plan(screenplay: Screenplay) -> list[Shot]:
    if not screenplay.scenes:
        raise ScreenplayError("the screenplay has no scenes")
    scenes = screenplay.scenes
    first = next(iter(scenes.values()))
    shots = [Shot(Mode.TEXT_TO_VIDEO, None, first.name, None, _prompt(screenplay.look, None, OPENING_MOVE, first))]
    # A scene is keyed once a shot has landed on it, so the keyed set doubles as the walk's visited set.
    keyed = {first.name}
    queue = deque([first])
    while queue:
        source = queue.popleft()
        for label, action in source.actions.items():
            land = scenes.get(action.to)
            if land is None:
                raise ScreenplayError(f'scene "{source.name}": action "{label}" goes to missing scene "{action.to}"')
            if land.name in keyed:
                mode = Mode.FIRST_AND_LAST_FRAME
            else:
                mode = Mode.IMAGE_TO_VIDEO
                keyed.add(land.name)
                queue.append(land)
            prompt = _prompt(screenplay.look, label, action.move or DEFAULT_MOVE, land)
            shots.append(Shot(mode, source.name, land.name, label, prompt))
    unreached = [name for name in scenes if name not in keyed]
    if unreached:
        raise ScreenplayError(f"no action reaches scene(s): {', '.join(unreached)}")
    return shots
