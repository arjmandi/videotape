from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from videotape import wan, wan3
from videotape.checks import Eye
from videotape.fal import Price, Receipt
from videotape.plan import Mode
from videotape.qwen import QwenEye
from videotape.standin import StandIn, StandInEye
from videotape.wan import Wan


class Model(Protocol):
    name: str
    device: str
    # Set for a model that bills per call, so a render can say what it will spend before it spends it.
    price: Price | None

    def settings(self, mode: Mode) -> dict:
        """The generation settings a take depends on beyond its mode, prompt, images and seed. They go into the take's cache key."""
        ...

    # A model that bills per call returns its receipt. A model on a GPU that bills by the hour returns None.
    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt | None: ...

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> Receipt | None: ...


@dataclass(frozen=True)
class PromptLimit:
    """The longest prompt a model reads, in the unit it counts in, and how a count in that unit reads in a warning."""

    model: str
    most: int
    says: str
    count: Callable[[str], int]


@dataclass(frozen=True)
class Listing:
    """A model a render can name, and the eye that checks its keys. The eye is given the tape it may cache in. The
    prompt limit is here, and not on the model, so a plan can read it without building the model."""

    model: Callable[[], Model]
    eye: Callable[[Path], Eye]
    prompt_limit: PromptLimit | None = None


MODELS: dict[str, Listing] = {
    "stand-in": Listing(StandIn, lambda tape: StandInEye()),
    "wan2.2-5b": Listing(Wan, QwenEye, PromptLimit(Wan.name, wan.TEXT_TOKENS, "about {:,} tokens", wan.tokens)),
    "wan3.0": Listing(wan3.from_environment, QwenEye,
                      PromptLimit(wan3.Wan3.name, wan3.PROMPT_CHARACTERS, "{:,} characters", len)),
}
