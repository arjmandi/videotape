from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Protocol

from videotape import hosted, wan
from videotape.checks import Reader
from videotape.claude import ClaudeReader
from videotape.fal import Price, Receipt
from videotape.frames import HEIGHT, WIDTH
from videotape.plan import Mode
from videotape.qwen import QwenEye
from videotape.standin import StandIn, StandInEye
from videotape.wan import Wan


class Kind(Protocol):
    """A model's name and settings, which is all a tape's made block reads of it. A model's class, or a model on fal's
    FalModel, gives both without the model being built, so publish can say what made a tape without a model's key or
    GPU."""

    name: str

    def settings(self, mode: Mode) -> dict:
        """The generation settings a take depends on beyond its mode, prompt, images and seed. They go into the take's cache key."""
        ...


class Model(Kind, Protocol):
    device: str
    # Set for a model that bills per call, so a render can say what it will spend before it spends it.
    price: Price | None

    # A model that bills per call returns its receipt. A model on a GPU that bills by the hour returns None.
    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt | None: ...

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> Receipt | None: ...

    def download_again(self, out: Path) -> Receipt | None:
        """Write the take at out again from the request the model recorded beside it, which submits nothing and
        costs nothing, and return its receipt. None when no request is recorded there."""
        ...


@dataclass(frozen=True)
class PromptLimit:
    """The longest prompt a model takes, in the unit it counts in, and how a count in that unit reads in a warning."""

    model: str
    most: int
    says: str
    count: Callable[[str], int]


@dataclass(frozen=True)
class Listing:
    """A model a render can name, and the readers of the eye that checks its keys. Each reader is built for the tape
    it may cache its reads in. The model's class, the prompt limit, the price and the limit on calls at once are
    here, and not on the model, so a plan or a publish can read them without building the model."""

    model: Callable[[], Model]
    readers: tuple[type[Reader], ...]
    prompt_limit: PromptLimit | None = None
    price: Price | None = None
    """What one call costs, for a model that bills per call."""
    limit: int = 1
    """How many shots the model films at once."""
    key: str | None = None
    """The environment variable that holds the key a model run as a service needs. The environment or the project's
    .env sets it."""
    kind: Kind = field(kw_only=True)
    """The model's name and settings, which a tape's made block reads, without building the model: its class, or for a
    model on fal its FalModel. Building a model on fal needs its key, and building wan2.2-5b a CUDA GPU."""

    def keys(self, name: str) -> tuple[tuple[str, str], ...]:
        """Each API key the model, by this name, or one of its readers needs, with what needs it."""
        return tuple((what, key) for what, key in ((name, self.key), *((f"{name}'s reader {reader.name}", reader.key)
                                                                      for reader in self.readers)) if key)


MODELS: dict[str, Listing] = {
    "stand-in": Listing(StandIn, (StandInEye,), limit=8, kind=StandIn),
    # One GPU on one pod draws one take at a time.
    "wan2.2-5b": Listing(Wan, (QwenEye, ClaudeReader), PromptLimit(Wan.name, wan.TEXT_TOKENS, "about {:,} tokens",
                                                                    wan.tokens), limit=1, kind=Wan),
    # fal.ai/docs/documentation/model-apis/concurrency-limits, read 2026-11-14: "Every new account starts with a
    # concurrency limit of 2 concurrent requests." The limit is the account's, so it holds for every model on fal.
    **{model.name: Listing(partial(hosted.from_environment, model), (QwenEye, ClaudeReader),
                           PromptLimit(model.name, model.prompt_characters, "{:,} characters", len), model.price,
                           limit=2, key="FAL_KEY", kind=model) for model in hosted.FAL_MODELS},
}


def estimate(name: str, listing: Listing, shots: int, keys: int, takes: int) -> str:
    """What a render of these shots will cost at most, from one take each up to the limit, and what the paid readers
    of its eye will cost at most for one read of each key's take."""
    least, most = shots, shots * takes
    calls = f"{least} to {most} calls" if most > least else f"{least} call{'' if least == 1 else 's'}"
    cost = listing.price.span(least, most) if listing.price else "free"
    line = f"{name}: {shots} shot{'' if shots == 1 else 's'}, {calls}, {cost}"
    paid = [reader for reader in listing.readers if reader.paid]
    if paid:
        each = sum(reader.most(WIDTH, HEIGHT) for reader in paid)
        reads = f"{keys} to {keys * takes} reads" if takes > 1 else f"{keys} read{'' if keys == 1 else 's'}"
        prices = f"${keys * each:.2f} to ${keys * takes * each:.2f}" if takes > 1 else f"${keys * each:.2f}"
        line += f", and {reads} by {' and '.join(reader.name for reader in paid)}, at most {prices}"
    return line
