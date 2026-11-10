import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from videotape import dailies, frames, ledger
from videotape.checks import Checks, Eye, score, seams
from videotape.frames import FPS, HEIGHT, WIDTH, Box
from videotape.loader import load
from videotape.model import Model
from videotape.publish import publish
from videotape.screenplay import Screenplay, ScreenplayError
from videotape.shots import Key, Move, Shot, plan


@dataclass(frozen=True)
class Take:
    seed: int
    path: Path
    cached: bool
    checks: Checks
    seconds: float | None
    gpu: str | None


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


def render(directory, model: Model, eye: Eye, takes: int = 3) -> Render:
    screenplay = load(directory)
    shots = plan(screenplay)
    keys = [shot for shot in shots if isinstance(shot, Key)]
    moves = [shot for shot in shots if isinstance(shot, Move)]
    clips: dict[str, Move] = {}
    for move in moves:
        if move.move in clips:
            raise ScreenplayError(f'scene "{move.start}": actions "{clips[move.move].label}" and "{move.label}" '
                                  f'would share the clip moves/{move.move}.mp4')
        clips[move.move] = move
    tape = Path(directory) / "tape"
    for folder in ("takes", "keys", "moves"):
        (tape / folder).mkdir(parents=True, exist_ok=True)
    seeds = range(1, takes + 1)
    # Every key first, so each move is pinned to two kept keys, and Wan swaps its checkpoint once per render.
    filmed_keys = []
    for key in keys:
        scene = screenplay.scenes[key.scene]
        key_takes = tuple(_key_take(model, eye, key, scene, seed, tape) for seed in seeds)
        kept = min(key_takes, key=lambda take: take.checks.rank(take.seed))
        publish(tape / "keys" / f"{key.scene}.png", lambda partial: frames.write_png(frames.last_frame(kept.path), partial))
        filmed_keys.append(Filmed(key, key_takes, kept))
    opening = filmed_keys[0].kept
    publish(tape / "moves" / "opening.mp4", lambda partial: shutil.copyfile(opening.path, partial))
    filmed_moves = []
    for move in moves:
        start, end = tape / "keys" / f"{move.start}.png", tape / "keys" / f"{move.land}.png"
        move_takes = tuple(_move_take(model, move, start, end, seed, tape) for seed in seeds)
        kept = min(move_takes, key=lambda take: take.checks.rank(take.seed))
        publish(tape / "moves" / f"{move.move}.mp4", lambda partial: shutil.copyfile(kept.path, partial))
        filmed_moves.append(Filmed(move, move_takes, kept))
    result = Render(tape, tuple(filmed_keys), tuple(filmed_moves))
    publish(tape / "tape.json", lambda partial: partial.write_text(json.dumps(_tape(screenplay, result), indent=2) + "\n"))
    dailies.write(tape, dailies.record(screenplay.title, eye.name, result))
    return result


def _key_take(model: Model, eye: Eye, key: Key, scene, seed: int, tape: Path) -> Take:
    path, cached, timing = _film(model, key, (), seed, tape, lambda out: model.text_to_video(key.prompt, seed, out))
    return Take(seed, path, cached, score(frames.last_frame(path), scene, eye), timing.get("seconds"), timing.get("gpu"))


def _move_take(model: Model, move: Move, start: Path, end: Path, seed: int, tape: Path) -> Take:
    path, cached, timing = _film(model, move, (start, end), seed, tape,
                                 lambda out: model.first_last_frame(move.prompt, start, end, seed, out))
    return Take(seed, path, cached, seams(path, start, end), timing.get("seconds"), timing.get("gpu"))


def _film(model: Model, shot: Shot, images: tuple[Path, ...], seed: int, tape: Path,
          film: Callable[[Path], None]) -> tuple[Path, bool, dict]:
    """The take for this shot and seed, filmed unless it is already in the cache. Its name hashes everything the pixels
    depend on: the mode, the prompt, the key images a move is pinned to, the model, the seed and the model's settings."""
    fields = [shot.mode.value, shot.prompt, *(hashlib.sha256(image.read_bytes()).hexdigest() for image in images),
              model.name, seed]
    if settings := model.settings(shot.mode):
        fields.append(settings)
    path = tape / "takes" / f"{hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()}.mp4"
    # The render time lives in a sidecar next to the take, so it survives caching.
    timing = path.with_suffix(".json")
    cached = path.exists()
    if not cached:
        started = time.perf_counter()
        publish(path, film)
        filmed = {"seconds": round(time.perf_counter() - started, 3), "gpu": model.device}
        publish(timing, lambda partial: partial.write_text(json.dumps(filmed) + "\n"))
        ledger.append(tape, {"kind": "take", "at": ledger.now(), "model": model.name, "shot": shot.title,
                             "mode": shot.mode.value, "seed": seed, **filmed})
    return path, cached, json.loads(timing.read_text()) if timing.exists() else {}


def _fraction(box: Box) -> dict:
    return {"x": round(box.x / WIDTH, 4), "y": round(box.y / HEIGHT, 4),
            "w": round(box.w / WIDTH, 4), "h": round(box.h / HEIGHT, 4)}


def _tape(screenplay: Screenplay, result: Render) -> dict:
    buttons = {filmed.shot.scene: filmed.kept.checks.buttons for filmed in result.keys}
    clips = {(filmed.shot.start, filmed.shot.label): filmed.shot.move for filmed in result.moves}
    return {
        "size": {"width": WIDTH, "height": HEIGHT},
        "fps": FPS,
        "opening": {"clip": "moves/opening.mp4", "lands": result.keys[0].shot.scene},
        "scenes": {
            name: {
                "key": f"keys/{name}.png",
                # A hotspot needs a box, and a box is never invented, so a button the checks did not find has no hotspot.
                "hotspots": [{"label": label, "box": _fraction(box), "move": clips[(name, label)]}
                             for label in scene.actions if (box := buttons[name][label])],
            }
            for name, scene in screenplay.scenes.items()
        },
        "moves": {filmed.shot.move: {"clip": f"moves/{filmed.shot.move}.mp4", "lands": filmed.shot.land}
                  for filmed in result.moves},
    }
