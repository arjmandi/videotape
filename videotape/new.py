"""videotape new: a project to start an app from, written from the starter under videotape/starter. The starter is
a screenplay of two scenes, a table of data, and a story, and it renders with the stand-in as it is."""

import json
import keyword
import sys
from importlib import metadata
from pathlib import Path

from videotape import errors
from videotape.errors import PACKAGE
from videotape.project import ProjectError

STARTER = PACKAGE / "starter"
RENAMED = {"gitignore": ".gitignore", "env.example": ".env.example"}
"""The starter's files that a project names with a dot. The starter's folder app is the project's package."""


def dependency(direct_url: str | None, version: str) -> str:
    """The requirement that installs videotape from where this one came from, per its PEP 610 direct_url.json: a git
    commit, a folder or another URL, or the index when there is no direct_url.json."""
    if direct_url is None:
        return f"videotape=={version}"
    source = json.loads(direct_url)
    url = source["url"]
    if "vcs_info" in source:
        url = f"{source['vcs_info']['vcs']}+{url}@{source['vcs_info']['commit_id']}"
    if "subdirectory" in source:
        url += f"#subdirectory={source['subdirectory']}"
    return f"videotape @ {url}"


def project(name: str, where: Path) -> Path:
    """Write the starter as a project named name in a new or empty folder of that name, and return the folder."""
    if not name.isidentifier() or keyword.iskeyword(name):
        raise ProjectError(f'"{name}" cannot name a project: it names the project\'s Python package too, so it is '
                           "letters, digits and _, as in my_app")
    if name in sys.stdlib_module_names or name == "videotape":
        raise ProjectError(f'"{name}" cannot name a project: its package would hide the module {name} that '
                           "videotape needs; pick another name")
    folder = where / name
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ProjectError(f"{errors.shown(folder)} is not an empty folder; new writes a project only into a new or "
                           "empty one")
    installed = metadata.distribution("videotape")
    words = {"{{name}}": name, "{{title}}": name.replace("_", " ").title(),
             "{{dependency}}": dependency(installed.read_text("direct_url.json"), installed.version)}
    for template in sorted(STARTER.rglob("*")):
        if not template.is_file() or template.name.startswith("."):
            continue
        parts = [name if part == "app" else RENAMED.get(part, part) for part in template.relative_to(STARTER).parts]
        text = template.read_text()
        for word, value in words.items():
            text = text.replace(word, value)
        folder.joinpath(*parts).parent.mkdir(parents=True, exist_ok=True)
        folder.joinpath(*parts).write_text(text)
    return folder
