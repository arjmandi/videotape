"""What made a tape: the app's screenplay, its code and data, the story, the model and the engine, and an id that
hashes them all. Two tapes with one id were drawn from the same everything."""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from videotape.errors import PACKAGE, ScreenplayError, shown
from videotape.model import Kind
from videotape.plan import Mode
from videotape.project import Project
from videotape.story import Story


def made(found: Project, story: Story, model: Kind) -> dict:
    """tape.json's made block. The app's screenplay is the module:app that [tool.videotape] names, so two screenplays
    of one package are two apps. Its code is every .py file of the package that holds its screenplay, or the one module
    when there is no package. Its data is every file under data/."""
    top = found.root / found.screenplay.partition(":")[0].partition(".")[0]
    code = top.rglob("*.py") if top.is_dir() else [top.with_suffix(".py")]
    data = (path for path in (found.root / "data").rglob("*") if path.is_file() and not path.name.startswith("."))
    block = {
        "app": {"name": found.name, "version": found.version, "screenplay": found.screenplay,
                "code": digest(found.root, code), "data": digest(found.root, data)},
        "story": {"name": story.name, "version": story.version, "hash": story.hash},
        "model": {"name": model.name, "settings": {mode.value: model.settings(mode) for mode in Mode}},
        "engine": digest(PACKAGE, PACKAGE.rglob("*.py")),
    }
    app = " ".join(filter(None, (found.name, found.version)))
    return {"label": f"{app} + {story.name} {story.version}",
            "id": hashlib.sha256(json.dumps(block, sort_keys=True).encode()).hexdigest(), **block}


def manifest(tape: Path, render: str) -> dict:
    """A tape's tape.json, whose made block says what made it: VT405 when no render finished the tape, or when a
    videotape older than the made block wrote it. render is the command that renders the tape."""
    file = tape / "tape.json"
    if not file.is_file():
        raise ScreenplayError("VT405", shown(tape), "has no tape.json, which a render writes when it finishes",
                              f"render the story first, or run a render that stopped again as it ran, which resumes, "
                              f"as in:\n{render}")
    held = json.loads(file.read_text())
    if "made" not in held:
        raise ScreenplayError("VT405", shown(file), "does not say what made the tape", f"render the story again, as in:"
                              f"\n{render}")
    return held


def digest(root: Path, files: Iterable[Path]) -> str:
    """One hash of many files, by each file's path from the root and its bytes. A rename changes it, and the order the
    files are found in does not."""
    hashed = hashlib.sha256()
    for name, path in sorted((path.relative_to(root).as_posix(), path) for path in files):
        content = path.read_bytes()
        hashed.update(f"{name}\0{len(content)}\0".encode())
        hashed.update(content)
    return hashed.hexdigest()
