import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from videotape import dailies, frames
from videotape.checks import Checks, Eye, check, rank
from videotape.frames import FPS, HEIGHT, WIDTH, Box
from videotape.loader import load
from videotape.model import Model
from videotape.publish import publish
from videotape.screenplay import Scene, Screenplay, ScreenplayError
from videotape.shots import Mode, Shot, plan


@dataclass(frozen=True)
class Take:
    seed: int
    path: Path
    cached: bool
    checks: Checks


@dataclass(frozen=True)
class Filmed:
    shot: Shot
    takes: tuple[Take, ...]
    kept: Take
    key: Path | None

    @property
    def rendered(self) -> int:
        return sum(not take.cached for take in self.takes)


@dataclass(frozen=True)
class Render:
    tape: Path
    shots: tuple[Filmed, ...]


def render(directory, model: Model, eye: Eye, takes: int = 3) -> Render:
    screenplay = load(directory)
    shots = plan(screenplay)
    moves = {}
    for shot in shots:
        if shot.move in moves:
            raise ScreenplayError(f'scene "{shot.start}": actions "{moves[shot.move].label}" and "{shot.label}" '
                                  f'would share the clip moves/{shot.move}.mp4')
        moves[shot.move] = shot
    tape = Path(directory) / "tape"
    for folder in ("takes", "keys", "moves"):
        (tape / folder).mkdir(parents=True, exist_ok=True)
    filmed = []
    for shot in shots:
        start = tape / "keys" / f"{shot.start}.png" if shot.start else None
        end = tape / "keys" / f"{shot.land}.png" if shot.mode is Mode.FIRST_AND_LAST_FRAME else None
        scene = screenplay.scenes[shot.land]
        shot_takes = tuple(_take(model, eye, shot, scene, start, end, seed, tape / "takes") for seed in range(1, takes + 1))
        kept = min(shot_takes, key=lambda take: rank(take.checks, take.seed))
        publish(tape / "moves" / f"{shot.move}.mp4", lambda partial: shutil.copyfile(kept.path, partial))
        key = None
        # The first shot to land on a scene keys it; every later shot there is first-and-last-frame and ends on that key.
        if shot.mode is not Mode.FIRST_AND_LAST_FRAME:
            key = tape / "keys" / f"{shot.land}.png"
            publish(key, lambda partial: frames.write_png(frames.last_frame(kept.path), partial))
        filmed.append(Filmed(shot, shot_takes, kept, key))
    result = Render(tape, tuple(filmed))
    publish(tape / "tape.json", lambda partial: partial.write_text(json.dumps(_tape(screenplay, result), indent=2) + "\n"))
    keyed = {filmed.shot.land: filmed for filmed in result.shots if filmed.key}
    scored = [(name, keyed[name].key.relative_to(tape).as_posix(), replace(keyed[name].kept.checks, start=None, end=None))
              for name in screenplay.scenes]
    dailies.write(tape, dailies.record(screenplay.title, result, dailies.keys(eye.name, scored)))
    return result


def _take(model: Model, eye: Eye, shot: Shot, scene: Scene, start: Path | None, end: Path | None, seed: int,
          folder: Path) -> Take:
    fields = [shot.mode.value, shot.prompt, _sha256(start), _sha256(end), model.name, seed]
    # A model with settings gets them in its key, so changing steps or frames re-renders. The stand-in has none, so its keys stay as they were.
    if settings := model.settings(shot.mode):
        fields.append(settings)
    path = folder / f"{hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()}.mp4"
    cached = path.exists()
    if not cached:
        publish(path, lambda partial: _film(model, shot, start, end, seed, partial))
    return Take(seed, path, cached, check(path, scene, start, end, eye))


def _film(model: Model, shot: Shot, start: Path | None, end: Path | None, seed: int, out: Path) -> None:
    match shot.mode:
        case Mode.TEXT_TO_VIDEO:
            model.text_to_video(shot.prompt, seed, out)
        case Mode.IMAGE_TO_VIDEO:
            model.image_to_video(shot.prompt, start, seed, out)
        case Mode.FIRST_AND_LAST_FRAME:
            model.first_last_frame(shot.prompt, start, end, seed, out)


def _sha256(path: Path | None) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path else None


def _fraction(box: Box | None) -> dict | None:
    if box is None:
        return None
    return {"x": round(box.x / WIDTH, 4), "y": round(box.y / HEIGHT, 4),
            "w": round(box.w / WIDTH, 4), "h": round(box.h / HEIGHT, 4)}


def _tape(screenplay: Screenplay, result: Render) -> dict:
    keyed = {filmed.shot.land: filmed for filmed in result.shots if filmed.key}
    moves = {(filmed.shot.start, filmed.shot.label): filmed.shot.move for filmed in result.shots}
    opening, *actions = result.shots
    return {
        "size": {"width": WIDTH, "height": HEIGHT},
        "fps": FPS,
        "opening": {"clip": f"moves/{opening.shot.move}.mp4", "lands": opening.shot.land},
        "scenes": {
            name: {
                "key": f"keys/{name}.png",
                "hotspots": [{"label": label, "box": _fraction(keyed[name].kept.checks.buttons[label]),
                              "move": moves[(name, label)]} for label in scene.actions],
            }
            for name, scene in screenplay.scenes.items()
        },
        "moves": {filmed.shot.move: {"clip": f"moves/{filmed.shot.move}.mp4", "lands": filmed.shot.land}
                  for filmed in actions},
    }
