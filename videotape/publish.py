from collections.abc import Callable
from pathlib import Path


def partial(path: Path) -> Path:
    """Where a file is written before it is published as path, so no reader sees it half written."""
    return path.with_name(f"{path.stem}.partial{path.suffix}")


def publish[T](path: Path, write: Callable[[Path], T]) -> T:
    written = write(partial(path))
    partial(path).replace(path)
    return written
