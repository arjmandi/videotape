"""A project is the folder that holds an app's pyproject.toml, whose [tool.videotape] table names its screenplay."""

import importlib
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from videotape import errors
from videotape.plan import MAX_STATES
from videotape.screenplay import Screenplay


class ProjectError(RuntimeError):
    pass


@dataclass(frozen=True)
class Project:
    root: Path
    version: str | None
    screenplay: str
    model: str | None
    max_states: int

    def load(self) -> Screenplay:
        """Import the module [tool.videotape] names, with the project on the import path, and return its screenplay."""
        module, _, name = self.screenplay.partition(":")
        sys.path.insert(0, str(self.root))
        try:
            found = getattr(importlib.import_module(module), name, None)
        except ModuleNotFoundError as error:
            if error.name is None or not f"{module}.".startswith(f"{error.name}."):
                raise
            raise ProjectError(f'[tool.videotape] names the screenplay "{self.screenplay}", and the project has no '
                               f"module {error.name}") from None
        if not isinstance(found, Screenplay):
            raise ProjectError(f'[tool.videotape] names the screenplay "{self.screenplay}", and {name} in {module} '
                               f"is {'missing' if found is None else 'not a vt.Screenplay'}")
        return found


def find(start: Path) -> Project:
    """The project a command runs in: the nearest folder, from start upward, that holds a pyproject.toml."""
    root = next((folder for folder in (start, *start.parents) if (folder / "pyproject.toml").is_file()), None)
    if root is None:
        raise ProjectError("no pyproject.toml here or in any folder above; run videotape in an app's project")
    file = errors.shown(root / "pyproject.toml")
    try:
        settings = tomllib.loads((root / "pyproject.toml").read_text())
    except tomllib.TOMLDecodeError as error:
        raise ProjectError(f"{file} is not valid TOML: {error}") from None
    table = settings.get("tool", {}).get("videotape")
    if not isinstance(table, dict):
        raise ProjectError(f'{file} has no [tool.videotape] table; add one with screenplay = "module:app"')
    screenplay, model, max_states = table.get("screenplay"), table.get("model"), table.get("max_states", MAX_STATES)
    if not isinstance(screenplay, str) or not all(screenplay.partition(":")):
        raise ProjectError(f'{file}: [tool.videotape] needs screenplay = "module:app", the module and the name '
                           f"of its vt.Screenplay, and has {screenplay!r}")
    if model is not None and not isinstance(model, str):
        raise ProjectError(f"{file}: [tool.videotape] model is {model!r}, not a model's name")
    if isinstance(max_states, bool) or not isinstance(max_states, int) or max_states < 1:
        raise ProjectError(f"{file}: [tool.videotape] max_states is {max_states!r}, not a whole number of states")
    version = settings.get("project", {}).get("version")
    return Project(root, version if isinstance(version, str) else None, screenplay, model, max_states)
