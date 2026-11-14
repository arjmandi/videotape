"""What made a tape: the app's code and data, the story, the model and the engine, each by a hash, and an id that
hashes them all. Two tapes with one id were drawn from the same everything."""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from videotape.errors import PACKAGE
from videotape.model import Model
from videotape.plan import Mode
from videotape.project import Project
from videotape.story import Story


def made(found: Project, story: Story, model: Model) -> dict:
    """tape.json's made block. The app's code is every .py file of the package that holds its screenplay, or the one
    module when there is no package. Its data is every file under data/."""
    top = found.root / found.screenplay.partition(":")[0].partition(".")[0]
    code = top.rglob("*.py") if top.is_dir() else [top.with_suffix(".py")]
    data = (path for path in (found.root / "data").rglob("*") if path.is_file() and not path.name.startswith("."))
    block = {
        "app": {"name": found.name, "version": found.version, "code": _hash(found.root, code),
                "data": _hash(found.root, data)},
        "story": {"name": story.name, "version": story.version, "hash": story.hash},
        "model": {"name": model.name, "settings": {mode.value: model.settings(mode) for mode in Mode}},
        "engine": _hash(PACKAGE, PACKAGE.rglob("*.py")),
    }
    app = " ".join(filter(None, (found.name, found.version)))
    return {"label": f"{app} + {story.name} {story.version}",
            "id": hashlib.sha256(json.dumps(block, sort_keys=True).encode()).hexdigest(), **block}


def _hash(root: Path, files: Iterable[Path]) -> str:
    """One hash of many files, by each file's path from the root and its bytes. A rename changes it, and the order the
    files are found in does not."""
    digest = hashlib.sha256()
    for name, path in sorted((path.relative_to(root).as_posix(), path) for path in files):
        content = path.read_bytes()
        digest.update(f"{name}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()
