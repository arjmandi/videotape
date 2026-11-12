import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from videotape import dailies, frames
from videotape.checks import Checks, Eye, score, seams
from videotape.fal import Receipt
from videotape.frames import Box, FfmpegError, Frame, Shape
from videotape.ledger import Ledger, now
from videotape.model import Model
from videotape.plan import Key, Move, Plan, Shot
from videotape.publish import publish


@dataclass(frozen=True)
class Take:
    seed: int
    path: Path
    cached: bool
    checks: Checks
    seconds: float | None
    gpu: str | None
    usd: float | None


@dataclass(frozen=True)
class Filmed:
    shot: Shot
    takes: tuple[Take, ...]
    kept: Take

    @property
    def rendered(self) -> int:
        return sum(not take.cached for take in self.takes)


@dataclass(frozen=True)
class Render:
    tape: Path
    keys: tuple[Filmed, ...]
    moves: tuple[Filmed, ...]

    @property
    def shots(self) -> tuple[Filmed, ...]:
        return *self.keys, *self.moves


def render(plan: Plan, model: Model, eye: Eye, tape: Path, ledger: Ledger, takes: int = 3) -> Render:
    """Draw a key for every state of the plan and a move for every action, and write them into the tape."""
    for folder in ("takes", "keys", "moves"):
        (tape / folder).mkdir(parents=True, exist_ok=True)
    seeds = range(1, takes + 1)
    # Every key first, so each move is pinned to two kept keys, and Wan swaps its checkpoint once per render.
    filmed_keys = []
    for key in plan.keys:
        key_takes = tuple(_key_take(model, eye, key, seed, tape, ledger) for seed in seeds)
        kept = min(key_takes, key=lambda take: take.checks.rank(take.seed))
        publish(tape / key.image, lambda partial: frames.write_png(frames.last_frame(kept.path), partial))
        filmed_keys.append(Filmed(key, key_takes, kept))
    opening = filmed_keys[0].kept
    publish(tape / "moves" / "opening.mp4", lambda partial: shutil.copyfile(opening.path, partial))
    images = {key.state: tape / key.image for key in plan.keys}
    filmed_moves = []
    for move in plan.moves:
        start, end = images[move.start], images[move.land]
        pinned = frames.read_png(start), frames.read_png(end)
        move_takes = tuple(_move_take(model, move, start, end, pinned, seed, tape, ledger) for seed in seeds)
        kept = min(move_takes, key=lambda take: take.checks.rank(take.seed))
        publish(tape / move.clip, lambda partial: shutil.copyfile(kept.path, partial))
        filmed_moves.append(Filmed(move, move_takes, kept))
    result = Render(tape, tuple(filmed_keys), tuple(filmed_moves))
    publish(tape / "tape.json", lambda partial: partial.write_text(json.dumps(_tape(plan, result), indent=2) + "\n"))
    dailies.write(tape, dailies.record(plan.title, eye.name, result), ledger.totals())
    return result


def _key_take(model: Model, eye: Eye, key: Key, seed: int, tape: Path, ledger: Ledger) -> Take:
    path, cached, timing = _film(model, key, (), seed, tape, ledger,
                                 lambda out: model.text_to_video(key.prompt, seed, out))
    return Take(seed, path, cached, score(frames.last_frame(path), key, eye), timing.get("seconds"), timing.get("gpu"),
                timing.get("usd"))


def _move_take(model: Model, move: Move, start: Path, end: Path, pinned: tuple[Frame, Frame], seed: int, tape: Path,
               ledger: Ledger) -> Take:
    path, cached, timing = _film(model, move, (start, end), seed, tape, ledger,
                                 lambda out: model.first_last_frame(move.prompt, start, end, seed, out))
    return Take(seed, path, cached, seams(frames.first_frame(path), frames.last_frame(path), *pinned),
                timing.get("seconds"), timing.get("gpu"), timing.get("usd"))


def uncached(plan: Plan, model: Model, takes: int, tape: Path) -> int:
    """How many takes a render will film. A move counts every take unless both its keys are cached and their images
    are on the tape, since a key that renders again may change and move every take pinned to it."""
    seeds = range(1, takes + 1)
    count, changing = 0, set()
    for key in plan.keys:
        missing = sum(not _take_path(model, key, (), seed, tape).exists() for seed in seeds)
        count += missing
        if missing:
            changing.add(key.state)
    images = {key.state: tape / key.image for key in plan.keys}
    for move in plan.moves:
        pinned = images[move.start], images[move.land]
        if {move.start, move.land} & changing or not all(image.exists() for image in pinned):
            count += takes
        else:
            count += sum(not _take_path(model, move, pinned, seed, tape).exists() for seed in seeds)
    return count


def _take_path(model: Model, shot: Shot, images: tuple[Path, ...], seed: int, tape: Path) -> Path:
    """A take's name hashes everything its pixels depend on: the mode, the prompt, the key images a move is pinned to,
    the model, the seed and the model's settings."""
    fields = [shot.mode.value, shot.prompt, *(hashlib.sha256(image.read_bytes()).hexdigest() for image in images),
              model.name, seed]
    if settings := model.settings(shot.mode):
        fields.append(settings)
    return tape / "takes" / f"{hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()}.mp4"


def _film(model: Model, shot: Shot, images: tuple[Path, ...], seed: int, tape: Path, ledger: Ledger,
          film: Callable[[Path], Receipt | None]) -> tuple[Path, bool, dict]:
    """The take for this shot and seed, filmed unless it is already in the cache."""
    path = _take_path(model, shot, images, seed, tape)
    # The render time and any price live in a sidecar next to the take, so they survive caching.
    timing = path.with_suffix(".json")
    cached = path.exists()
    if not cached:
        started = time.perf_counter()
        receipt = publish(path, film)
        filmed = {"seconds": round(time.perf_counter() - started, 3), "gpu": model.device}
        if receipt:
            filmed |= {"request_id": receipt.request_id, "duration": receipt.duration, "usd": receipt.usd}
        response = {"response": receipt.response} if receipt else {}
        publish(timing, lambda partial: partial.write_text(json.dumps({**filmed, **response}) + "\n"))
        ledger.append({"kind": "take", "at": now(), "model": model.name, "shot": shot.title,
                       "mode": shot.mode.value, "seed": seed, **filmed})
    return path, cached, json.loads(timing.read_text()) if timing.exists() else {}


def _fraction(box: Box, size: Shape) -> dict:
    return {"x": round(box.x / size.width, 4), "y": round(box.y / size.height, 4),
            "w": round(box.w / size.width, 4), "h": round(box.h / size.height, 4)}


def _shape(result: Render) -> Shape:
    """The one size and frame rate every kept clip shares, which the player sizes its window to."""
    shapes = {filmed.kept.path: frames.shape(filmed.kept.path) for filmed in result.shots}
    if len(set(shapes.values())) > 1:
        raise FfmpegError("the kept clips differ in size or frame rate, so no one window plays them: " +
                          ", ".join(f"{path.name} {s.width}x{s.height} at {s.fps} fps" for path, s in shapes.items()))
    return next(iter(shapes.values()))


def _tape(plan: Plan, result: Render) -> dict:
    """tape.json: one scene for each state, named as the plan names it."""
    found = {filmed.shot.state: filmed.kept.checks.hotspots for filmed in result.keys}
    moves = {(move.start, move.label): move for move in plan.moves}
    size = _shape(result)
    return {
        "size": {"width": size.width, "height": size.height},
        "fps": size.fps,
        "opening": {"clip": "moves/opening.mp4", "lands": plan.keys[0].state.name},
        "scenes": {
            key.state.name: {
                "key": key.image,
                # A hotspot needs a box, and a box is never invented, so an action the checks did not find has none.
                "hotspots": [{"label": action.label, "box": _fraction(box, size),
                              "move": moves[(key.state, action.label)].id}
                             for action in key.actions if (box := found[key.state][action.label])],
            }
            for key in plan.keys
        },
        "moves": {move.id: {"clip": move.clip, "lands": move.land.name} for move in plan.moves},
    }
