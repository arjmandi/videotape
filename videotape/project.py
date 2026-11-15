"""A project is the folder that holds an app's pyproject.toml, whose [tool.videotape] section names its screenplay."""

import importlib
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from videotape import errors
from videotape.errors import ScreenplayError
from videotape.model import MODELS
from videotape.plan import MAX_STATES
from videotape.screenplay import Screenplay

TAKES = 4
"""How many takes a shot gets at most, unless [tool.videotape] sets takes. A shot stops at the first take that passes."""


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
        file = errors.shown(self.root / "pyproject.toml")
        sys.path.insert(0, str(self.root))
        try:
            found = getattr(importlib.import_module(module), name, None)
        except ModuleNotFoundError as error:
            if error.name is None or not f"{module}.".startswith(f"{error.name}."):
                raise
            raise ScreenplayError("VT107", file, f'[tool.videotape] screenplay is "{self.screenplay}", and the '
                                  f"project has no module {error.name}", "name the module that holds the "
                                  "screenplay, from the project's folder, as in shop.screenplay for "
                                  "shop/screenplay.py") from None
        if not isinstance(found, Screenplay):
            raise ScreenplayError("VT107", file, f'[tool.videotape] screenplay is "{self.screenplay}", and {name} in '
                                  f"{module} is {'missing' if found is None else 'not a vt.Screenplay'}",
                                  f'name the vt.Screenplay that {module} makes, as in {name} = vt.Screenplay("Shop")')
        return found


def find(start: Path) -> Project:
    """The project a command runs in: the nearest folder, from start upward, that holds a pyproject.toml."""
    root = next((folder for folder in (start, *start.parents) if (folder / "pyproject.toml").is_file()), None)
    if root is None:
        raise ScreenplayError("VT106", errors.shown(start / "pyproject.toml"), "no pyproject.toml here or in any "
                              "folder above", "run videotape in an app's project, or start one with videotape new <name>")
    file = errors.shown(root / "pyproject.toml")

    def wrong(message: str, fix: str) -> ScreenplayError:
        return ScreenplayError("VT107", file, f"[tool.videotape] {message}", fix)

    try:
        settings = tomllib.loads((root / "pyproject.toml").read_text())
    except tomllib.TOMLDecodeError as error:
        raise ScreenplayError("VT107", file, f"is not TOML: {error}", "write it as TOML, at the line the error "
                              "names") from None
    table = settings.get("tool", {}).get("videotape")
    if not isinstance(table, dict):
        raise ScreenplayError("VT106", file, "has no [tool.videotape] section", "add one that names the screenplay, "
                              'its module and the name of its vt.Screenplay: [tool.videotape] screenplay = "shop.screenplay:app"')
    screenplay, model = table.get("screenplay"), table.get("model")
    max_states, takes, cap = table.get("max_states", MAX_STATES), table.get("takes", TAKES), table.get("cap_usd")
    models = ", ".join(sorted(MODELS))
    if not isinstance(screenplay, str) or not all(screenplay.partition(":")):
        raise wrong(f'screenplay is {screenplay!r}, not "module:app"', "set it to the module and the name of its "
                    'vt.Screenplay, as in screenplay = "shop.screenplay:app"')
    if model is not None and not isinstance(model, str):
        raise wrong(f"model is {model!r}, not a model's name", f"set model to one of {models}")
    if model is not None and model not in MODELS:
        raise wrong(f'model is "{model}", and videotape has no such model', f"set model to one of {models}")
    for setting, value, noun, default in (("max_states", max_states, "states", MAX_STATES),
                                          ("takes", takes, "takes", TAKES)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise wrong(f"{setting} is {value!r}, not a whole number of {noun}",
                        f"set it to a whole number of at least 1, as in {setting} = {default}")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0):
        raise wrong(f"cap_usd is {cap!r}, not a number of dollars",
                    "set it to the most a render may spend, in dollars, as in cap_usd = 20")
    name, version = (settings.get("project", {}).get(key) for key in ("name", "version"))
    load_keys(root / ".env")
    return Project(root, name if isinstance(name, str) else root.name, version if isinstance(version, str) else None,
                   screenplay, model, max_states, takes, float(cap) if cap is not None else None)


def load_keys(file: Path) -> None:
    """Set each KEY=VALUE line of a .env file in the environment, unless the environment has that key already. Blank
    lines, # comments and empty values are skipped, and a value in quotes loses them. Nothing prints a value."""
    if not file.is_file():
        return
    for line in file.read_text().splitlines():
        key, equals, value = line.strip().removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if equals and key and not key.startswith("#") and value:
            os.environ.setdefault(key, value)
