import ast
import runpy
from pathlib import Path

from videotape.screenplay import Screenplay, ScreenplayError


def _check_duplicate_labels(source: str, path: Path) -> None:
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "scene"):
            continue
        actions = next((kw.value for kw in node.keywords if kw.arg == "actions"), None)
        if not isinstance(actions, ast.Dict):
            continue
        name = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else "?"
        seen = set()
        for key in actions.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in seen:
                    raise ScreenplayError(f'{path}:{key.lineno}: scene "{name}" has two actions labelled "{key.value}"')
                seen.add(key.value)


def load(directory) -> Screenplay:
    path = Path(directory) / "screenplay.py"
    if not path.is_file():
        raise ScreenplayError(f"no screenplay.py in {directory}")
    # A dict literal silently drops a repeated key at runtime, so duplicates are only visible in the source.
    _check_duplicate_labels(path.read_text(), path)
    found = [value for value in runpy.run_path(str(path)).values() if isinstance(value, Screenplay)]
    if len(found) != 1:
        raise ScreenplayError(f"{path} must define exactly one Screenplay, found {len(found)}")
    return found[0]
