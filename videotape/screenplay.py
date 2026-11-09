from dataclasses import dataclass


class ScreenplayError(Exception):
    pass


@dataclass(frozen=True)
class Go:
    to: str
    move: str | None = None


def go(to: str, move: str | None = None) -> Go:
    return Go(to, move)


@dataclass(frozen=True)
class Scene:
    name: str
    shows: tuple[str, ...]
    direction: str
    actions: dict[str, Go]


class Screenplay:
    def __init__(self, title: str, look: str):
        self.title = title
        self.look = look
        self.scenes: dict[str, Scene] = {}

    def scene(self, name: str, shows=(), direction: str = "", actions: dict[str, Go | str] | None = None) -> None:
        normalized = {label: Go(to) if isinstance(to, str) else to for label, to in (actions or {}).items()}
        self.scenes[name] = Scene(name, tuple(shows), direction, normalized)
