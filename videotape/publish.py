from collections.abc import Callable
from pathlib import Path


def publish[T](path: Path, write: Callable[[Path], T]) -> T:
    partial = path.with_name(f"{path.stem}.partial{path.suffix}")
    written = write(partial)
    partial.replace(path)
    return written
