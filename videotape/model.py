from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Protocol

from videotape import hosted, wan
from videotape.checks import Judge, Reader
from videotape.claude import ClaudeJudge, ClaudeReader
from videotape.fal import Price, Receipt
from videotape.frames import HEIGHT, WIDTH
from videotape.plan import Mode
from videotape.qwen import QwenEye
from videotape.standin import StandIn, StandInEye, StandInJudge
from videotape.story import PromptLimit
from videotape.wan import Wan


class Kind(Protocol):
    """A model's name, settings and modes, which is all a tape's made block and a plan read of it. A model's class, or a
    model on fal's FalModel, gives them without the model being built, so publish can say what made a tape, and a plan
    what the model cannot draw, without a model's key or GPU."""

    name: str
    modes: frozenset[Mode]
    """The modes the model films."""

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

    def first_frame(self, prompt: str, start: Path, seed: int, out: Path) -> Receipt | None:
        """Image to video from the start picture alone, so the take's last frame is a key drawn in that picture's
        layout. A model without the mode raises a ModelError that names one with it."""
        ...

    def download_again(self, out: Path) -> Receipt | None:
        """Write the take at out again from the request the model recorded beside it, which submits nothing and
        costs nothing, and return its receipt. None when no request is recorded there."""
        ...


@dataclass(frozen=True)
class Listing:
    """A model a render can name, the readers of the eye that checks its keys, and the judge of its moves. Each
    reader and the judge is built for the tape it may cache its reads or judgments in. The model's class, the prompt
    limit, the price and the limit on calls at once are here, and not on the model, so a plan or a publish can read
    them without building the model."""

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
    judge: type[Judge] = field(kw_only=True)
    """What judges every move's take for a dissolve: the stand-in's own judge, and Claude for every other model."""

    def keys(self, name: str) -> tuple[tuple[str, str], ...]:
        """Each API key the model, by this name, or one of its readers needs, with what needs it."""
        return tuple((what, key) for what, key in ((name, self.key), *((f"{name}'s reader {reader.name}", reader.key)
                                                                      for reader in self.readers)) if key)


SIZES = {
    # tests/fixtures/wan3.0.txt: the prototype run's clips came back 1280x720. VTR-Bench lists Wan3.0 at 1280x720.
    "wan3.0": (1280, 720),
    # 768P at 16:9 is 1344x768, which VTR-Bench (arXiv 2610.01499, 2026-10-01) ran H3 at.
    "minimax-h3": (1344, 768),
    # 720p at 16:9. fal states no pixel size for it, so this is a guess.
    "gemini-omni-flash-1.2": (1280, 720),
}
"""The picture size each model films, which the most a read of its picture costs depends on. A model not here is
priced at the stand-in's size."""

MODELS: dict[str, Listing] = {
    "stand-in": Listing(StandIn, (StandInEye,), limit=8, kind=StandIn, judge=StandInJudge),
    # One GPU on one pod draws one take at a time.
    "wan2.2-5b": Listing(Wan, (QwenEye, ClaudeReader), PromptLimit(Wan.name, wan.TEXT_TOKENS, "about {:,} tokens",
                                                                    wan.tokens), limit=1, kind=Wan, judge=ClaudeJudge),
    # fal.ai/docs/documentation/model-apis/concurrency-limits, read 2026-11-14: "Every new account starts with a
    # concurrency limit of 2 concurrent requests." The limit is the account's, so it holds for every model on fal.
    **{model.name: Listing(partial(hosted.from_environment, model), (QwenEye, ClaudeReader),
                           PromptLimit(model.name, model.prompt_characters, "{:,} characters", len), model.price,
                           limit=2, key="FAL_KEY", kind=model, judge=ClaudeJudge) for model in hosted.FAL_MODELS},
}


def estimate(name: str, listing: Listing, shots: int, keys: int, moves: int, takes: int) -> str:
    """What a render of these shots will cost at most, from one take each up to the limit, what the paid readers of
    its eye will cost at most for one read of each key's take, and what a paid judge will cost at most for one
    judgment of each move's take, a rehearsal's or a pinned move's."""
    least, most = shots, shots * takes
    calls = f"{least} to {most} calls" if most > least else f"{least} call{'' if least == 1 else 's'}"
    cost = listing.price.span(least, most) if listing.price else "free"
    line = f"{name}: {shots} shot{'' if shots == 1 else 's'}, {calls}, {cost}"
    paid = [reader for reader in listing.readers if reader.paid]
    if paid:
        each = sum(reader.most(WIDTH, HEIGHT) for reader in paid)
        line += f", and {_span(keys, takes, 'read')} by {' and '.join(reader.name for reader in paid)}, at most {_prices(keys, takes, each)}"
    if listing.judge.paid and moves:
        line += (f", and {_span(moves, takes, 'judgment')} by {listing.judge.name}, at most "
                 f"{_prices(moves, takes, listing.judge.most(WIDTH, HEIGHT))}")
    return line


def _span(count: int, takes: int, noun: str) -> str:
    return f"{count} to {count * takes} {noun}s" if takes > 1 else f"{count} {noun}{'' if count == 1 else 's'}"


def _prices(count: int, takes: int, each: float) -> str:
    return f"${count * each:.2f} to ${count * takes * each:.2f}" if takes > 1 else f"${count * each:.2f}"
