"""Writing a file so that no reader ever sees it half written."""

from collections.abc import Callable
from pathlib import Path


def partial(path: Path) -> Path:
    """Where a file is written before it replaces path, so no reader sees it half written."""
    return path.with_name(f"{path.stem}.partial{path.suffix}")


def write_atomically[T](path: Path, write: Callable[[Path], T]) -> T:
    """Write path through write, which is given the partial file, then move the partial file into place."""
    written = write(partial(path))
    partial(path).replace(path)
    return written
