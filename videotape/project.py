"""A project is the folder that holds an app's pyproject.toml, whose [tool.videotape] table names its screenplay."""

import importlib
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from videotape import errors
from videotape.plan import MAX_STATES
from videotape.screenplay import Screenplay

TAKES = 4
"""How many takes a shot gets at most, unless [tool.videotape] sets takes. A shot stops at the first take that passes."""


class ProjectError(RuntimeError):
    pass


@dataclass(frozen=True)
class Project:
    root: Path
    name: str
    """The app's name, which is [project] name, or the folder's name when pyproject.toml gives none."""
    version: str | None
    screenplay: str
    model: str | None
    max_states: int
    takes: int
    cap_usd: float | None
    """The most a render of this project may spend on a model that bills per call, before it stops."""

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
    screenplay, model = table.get("screenplay"), table.get("model")
    max_states, takes, cap = table.get("max_states", MAX_STATES), table.get("takes", TAKES), table.get("cap_usd")
    if not isinstance(screenplay, str) or not all(screenplay.partition(":")):
        raise ProjectError(f'{file}: [tool.videotape] needs screenplay = "module:app", the module and the name '
                           f"of its vt.Screenplay, and has {screenplay!r}")
    if model is not None and not isinstance(model, str):
        raise ProjectError(f"{file}: [tool.videotape] model is {model!r}, not a model's name")
    for setting, value, noun in (("max_states", max_states, "states"), ("takes", takes, "takes")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ProjectError(f"{file}: [tool.videotape] {setting} is {value!r}, not a whole number of {noun}")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0):
        raise ProjectError(f"{file}: [tool.videotape] cap_usd is {cap!r}, not a number of dollars")
    name, version = (settings.get("project", {}).get(key) for key in ("name", "version"))
    return Project(root, name if isinstance(name, str) else root.name, version if isinstance(version, str) else None,
                   screenplay, model, max_states, takes, float(cap) if cap is not None else None)
