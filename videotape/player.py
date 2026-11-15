"""Playing a tape in TapePlayer, the macOS app under clients/macos beside this package. The app is built when it is
missing or older than any file it is built from, and then opened with the tape's path as its argument, which
TapePlayer takes as it is when the path is absolute."""

import subprocess
from collections.abc import Callable
from pathlib import Path

from videotape.errors import PACKAGE
from videotape.project import ProjectError

MACOS = PACKAGE.parent / "clients" / "macos"
SKIPPED = {"build", ".build", ".swiftpm", "xcuserdata"}
"""Folders under clients/macos that hold what a build leaves, not what it is built from."""

Run = Callable[[list[str]], object]


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def app(macos: Path = MACOS) -> Path:
    return macos / "build" / "TapePlayer.app"


def sources(macos: Path = MACOS) -> list[Path]:
    """Every file the app is built from: all of clients/macos but what a build leaves and hidden files."""
    return [path for path in macos.rglob("*") if path.is_file()
            and not any(part in SKIPPED or part.startswith(".") for part in path.relative_to(macos).parts)]


def stale(macos: Path = MACOS) -> bool:
    """Whether the built app is missing or older than a file it is built from."""
    built = app(macos)
    return not built.exists() or built.stat().st_mtime < max(path.stat().st_mtime for path in sources(macos))


def commands(tape: Path, macos: Path = MACOS) -> list[list[str]]:
    """What play runs: the build when it is needed, then open with the tape's absolute path."""
    if not (macos / "build.sh").is_file():
        raise ProjectError(f"TapePlayer's source is not at {macos}; play needs videotape checked out beside clients/macos")
    build = [[str(macos / "build.sh")]] if stale(macos) else []
    return [*build, ["open", str(app(macos)), "--args", str(tape.resolve())]]


def play(tape: Path, macos: Path | None = None, run: Run | None = None) -> list[list[str]]:
    """Build TapePlayer if it needs to, open the tape in it, and return what was run."""
    ran = commands(tape, macos or MACOS)
    for command in ran:
        (run or _run)(command)
    return ran
