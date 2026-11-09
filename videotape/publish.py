from collections.abc import Callable
from pathlib import Path


def publish(path: Path, write: Callable[[Path], object]) -> None:
    partial = path.with_name(f"{path.stem}.partial{path.suffix}")
    write(partial)
    partial.replace(path)
