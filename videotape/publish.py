"""videotape publish: a tape made into a Mac app that plays it on its own, dist/<Title>-<story>.app, zipped beside it.
Publish refuses a tape that is out of date with its sources (VT601), that has a failing check nobody accepted (VT602),
or whose label videotape.lock holds with another id (VT305). The app is TapePlayer named for the app and the story,
with the tape inside it and each clip encoded as HEVC, which must keep every check its key passed (VT604). It is signed
ad hoc, and videotape.lock records the label, the id and the hashes the id is made of."""

import hashlib
import json
import plistlib
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from videotape import dailies, frames, player, story
from videotape.atomic import partial, write_atomically
from videotape.checks import MAX_DIFFERENCE, ChecksError, Eye, Item, score
from videotape.errors import ScreenplayError, shown
from videotape.frames import Frame
from videotape.made import made
from videotape.model import MODELS
from videotape.plan import Plan, plan
from videotape.project import Project, ProjectError

LOCK = "videotape.lock"
HEADER = ("# What videotape publish shipped: each label, with the id of the tape it holds and the hashes the id is made of.\n"
          "# Commit it. A label ships once, so another tape under the same versions is refused with VT305.\n")
WORDS = {"code": "the app's code", "data": "the data", "story": "the story", "model": "the model",
         "settings": "the model's settings", "engine": "videotape itself"}
"""Each hash the lock records but the id, as a person names what changed."""


@dataclass(frozen=True)
class Published:
    app: Path
    zip: Path
    label: str
    id: str
    locked: bool
    """Whether this publish added the label to videotape.lock. Publishing the same tape again leaves the lock as it is."""

    @property
    def size(self) -> int:
        return sum(path.stat().st_size for path in self.app.rglob("*") if path.is_file() and not path.is_symlink())


def publish(found: Project, tape: Path) -> Published:
    """Refuse the tape, or build its app into dist/, zip it, and record it in videotape.lock. The app is staged beside
    its place and moved there only when whole and signed, so dist/ holds only whole apps."""
    manifest, record = _read(tape)
    block = manifest["made"]
    told = story.named(found.root, block["story"]["name"])
    listing = MODELS[block["model"]["name"]]
    out = record.get("out")
    _fresh(tape, block, made(found, told, listing.kind), record["complete"], out)
    _accepted(tape, record, told.name, out)
    lock = read_lock(found.root)
    _unlocked(found.root, lock, block, told.path)
    planned = plan(found.load(), found.max_states)
    built = player.built()
    app = found.root / "dist" / f"{re.sub(r'[/:]', '-', planned.title)}-{told.name}.app"
    staged = partial(app)
    shutil.rmtree(staged, ignore_errors=True)
    try:
        shutil.copytree(built, staged, symlinks=True)
        _name(staged / "Contents" / "Info.plist", planned.title, found.name, told.name)
        inside = staged / "Contents" / "Resources" / "tape"
        clips = _encode(tape, manifest, inside)
        _rests(planned, record, listing.eye(tape), tape, inside, clips, told.name, out)
        print(f"encoded {len(clips)} clips as HEVC; on each one's last frame, where the player rests, every check its "
              "key passed still passes", flush=True)
        _run("codesign", "--force", "--deep", "--sign", "-", str(staged))
        print("signed ad hoc, not with a Developer ID, so another Mac's Gatekeeper asks before it opens the app",
              flush=True)
        shutil.rmtree(app, ignore_errors=True)
        staged.rename(app)
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    zipped = app.with_suffix(".zip")
    write_atomically(zipped, lambda written: _run("ditto", "-c", "-k", "--keepParent", str(app), str(written)))
    locked = block["label"] not in lock
    if locked:
        write_lock(found.root, {**lock, block["label"]: entry(block)})
    return Published(app, zipped, block["label"], block["id"], locked)


def entry(block: dict) -> dict[str, str]:
    """What the lock records of a tape: its id, and each hash its id is made of, with the model by its name."""
    settings = hashlib.sha256(json.dumps(block["model"]["settings"], sort_keys=True).encode()).hexdigest()
    return {"id": block["id"], "code": block["app"]["code"], "data": block["app"]["data"],
            "story": block["story"]["hash"], "model": block["model"]["name"], "settings": settings,
            "engine": block["engine"]}


def read_lock(root: Path) -> dict[str, dict[str, str]]:
    file = root / LOCK
    if not file.is_file():
        return {}
    try:
        return tomllib.loads(file.read_text())
    except tomllib.TOMLDecodeError as error:
        raise ProjectError(f"{shown(file)} is not TOML: {error}; mend it, or take it back from git") from None


def write_lock(root: Path, lock: dict[str, dict[str, str]]) -> None:
    """The lock as TOML, one table per label in order, so a new label is a few added lines in a diff."""
    tables = (f"\n[{json.dumps(label, ensure_ascii=False)}]\n" +
              "".join(f"{key} = {json.dumps(value, ensure_ascii=False)}\n" for key, value in lock[label].items())
              for label in sorted(lock))
    write_atomically(root / LOCK, lambda out: out.write_text(HEADER + "".join(tables)))


def _read(tape: Path) -> tuple[dict, dict]:
    """tape.json, which says what made the tape, and dailies.json, its record."""
    for name in ("tape.json", "dailies.json"):
        if not (tape / name).is_file():
            raise ChecksError(f"no {name} in {shown(tape)}; render the story first")
    manifest = json.loads((tape / "tape.json").read_text())
    if "made" not in manifest:
        raise ChecksError(f"{shown(tape / 'tape.json')} does not say what made it; render the tape again")
    return manifest, dailies.read(tape)


def _fresh(tape: Path, block: dict, now: dict, complete: bool, out: str | None) -> None:
    """VT601 unless the tape was made from the sources the project has now, by a render that finished."""
    if block["id"] == now["id"] and complete:
        return
    before, after = entry(block), entry(now)
    changed = [f"the app's {part}" for part in ("name", "version") if block["app"][part] != now["app"][part]]
    changed += [words for key, words in WORDS.items() if before[key] != after[key]]
    render = ["videotape", "render", "--story", block["story"]["name"], "--model", block["model"]["name"],
              *(["--out", out] if out else [])]
    message = f"{_and(changed) or 'what made it'} changed since the tape was rendered" if block["id"] != now["id"] \
        else "its last render stopped before its last shot"
    raise ScreenplayError("VT601", shown(tape), message, "render the tape again with the model that made it, then "
                          f"publish it:\n{' '.join(render)}")


def _accepted(tape: Path, record: dict, name: str, out: str | None) -> None:
    """VT602 when a kept take fails a check nobody accepted for it."""
    failing = [failure for failure in record["failures"] if not failure["accepted"]]
    if not failing:
        return
    one = len(failing) == 1
    first = failing[0]["next"]
    raise ScreenplayError(
        "VT602", shown(tape), f"{len(failing)} check{'' if one else 's'} fail{'s' if one else ''} that nobody "
        f"accepted: {', '.join(f'{failure["shot"]} {failure["code"]}' for failure in failing)}",
        f"look at {'it' if one else 'them'} with videotape dailies --story {name}{f' --out {out}' if out else ''}, then "
        f"retake the shot or accept the failure with a reason; for the first:\n{first['retake']}\n{first['accept']}")


def _unlocked(root: Path, lock: dict[str, dict[str, str]], block: dict, story_file: Path) -> None:
    """VT305 when the lock holds the tape's label with another id."""
    held = lock.get(block["label"])
    if held is None or held.get("id") == block["id"]:
        return
    now = entry(block)
    changed = [words for key, words in WORDS.items() if held.get(key) != now[key]]
    raise ScreenplayError("VT305", shown(root / LOCK), f"{block['label']} was published as {held.get('id', '')[:12]}, "
                          f"and this tape under the same label is {block['id'][:12]}"
                          + (f": {_and(changed)} changed" if changed else ""),
                          "give the tape a label of its own: bump version in pyproject.toml, or in "
                          f"{shown(story_file)} for a change to the story, then render and publish again")


def _name(plist: Path, title: str, app: str, name: str) -> None:
    """Name the app for the screenplay and the story, as in Contrail (Starter), with a bundle id of its own."""
    info = plistlib.loads(plist.read_bytes())
    shown_as = f"{title} ({name[:1].upper()}{name[1:]})"
    info |= {"CFBundleName": shown_as, "CFBundleDisplayName": shown_as,
             "CFBundleIdentifier": ".".join(["dev.videotape", *(re.sub(r"[^A-Za-z0-9-]", "-", part) for part in (app, name))])}
    plist.write_bytes(plistlib.dumps(info))


def _encode(tape: Path, manifest: dict, inside: Path) -> dict[str, str]:
    """Put tape.json and every clip it names into the app, each clip encoded as HEVC. The player reads nothing else.
    Each clip by the state it lands on."""
    clips = {manifest["opening"]["clip"]: manifest["opening"]["lands"],
             **{move["clip"]: move["lands"] for move in manifest["moves"].values()}}
    inside.mkdir(parents=True)
    shutil.copyfile(tape / "tape.json", inside / "tape.json")
    for clip in clips:
        (inside / clip).parent.mkdir(parents=True, exist_ok=True)
        frames.hevc(tape / clip, inside / clip)
    return clips


def _rests(planned: Plan, record: dict, eye: Eye, tape: Path, inside: Path, clips: dict[str, str], name: str,
           out: str | None) -> None:
    """VT604 when the last frame of an encoded clip, where the player rests, fails a check that passed in the record:
    the eye's checks of the state it lands on, which its key passed, and the seam with that state's key image, which
    the move's kept take passed."""
    keys = {key.state.name: key for key in planned.keys}
    recorded = {key["state"]: key for key in record["keys"]}
    seams = {move["move"]: next(take for take in move["takes"] if take["kept"]) for move in record["moves"]}
    images: dict[str, Frame] = {}
    for clip, state in clips.items():
        failed = {(item["code"], item["about"]) for item in [*recorded[state]["items"], *seams.get(clip, {}).get("items", [])]
                  if not item["passed"]}
        frame = frames.last_frame(inside / clip)
        image = images.setdefault(state, frames.read_png(tape / recorded[state]["key"]))
        end = frames.difference(frame, image)
        items = [*score(frame, keys[state], eye).items(),
                 Item("VT508", "end", f"difference {end:.3f}", end <= MAX_DIFFERENCE, None)]
        broken = [item for item in items if not item.passed and (item.code, item.about) not in failed]
        if broken:
            shot = next((move for move in planned.moves if move.clip == clip), planned.keys[0])
            checks = "a check its key passed:" if len(broken) == 1 else f"{len(broken)} checks its key passed, the first"
            raise ScreenplayError("VT604", clip, f"its HEVC last frame, where the player rests on {state}, fails "
                                  f"{checks} {broken[0].code} {broken[0].about}: {broken[0].result}",
                                  "retake the shot, whose next take may come through the encoding, then publish again:"
                                  f'\nvideotape retake "{dailies.named(shot)}" --story {name}'
                                  f"{f' --out {out}' if out else ''}")


def _run(*command: str) -> None:
    ran = subprocess.run(command, capture_output=True, text=True)
    if ran.returncode != 0:
        raise ProjectError(f"{command[0]} exited with {ran.returncode}: {(ran.stderr or ran.stdout).strip()}")


def _and(words: list[str]) -> str:
    return " and ".join(filter(None, [", ".join(words[:-1]), *words[-1:]]))
