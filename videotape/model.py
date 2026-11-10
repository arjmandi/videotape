from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from videotape.fal import Receipt
from videotape.shots import Mode
from videotape.standin import StandIn
from videotape.wan import Wan


class Model(Protocol):
    name: str
    device: str

    def settings(self, mode: Mode) -> dict:
        """The generation settings a take depends on beyond its mode, prompt, images and seed. They go into the take's cache key."""
        ...

    # A model that bills per call returns its receipt. A model on a GPU that bills by the hour returns None.
    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt | None: ...

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> Receipt | None: ...


MODELS: dict[str, Callable[[], Model]] = {
    "stand-in": StandIn,
    "wan2.2-5b": Wan,
}
