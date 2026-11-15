"""TapePlayer, the macOS app that plays a tape. Its source ships in the package as videotape/macos, and in a checkout
it is clients/macos beside the package. It is built in Release into a cache, once for each version of its source, and
never into the package. play opens a tape in the built app with the tape's path as its argument, which TapePlayer
takes as it is when the path is absolute."""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from videotape import errors
from videotape.errors import PACKAGE, ScreenplayError
from videotape.made import digest

SOURCE = next((folder for folder in (PACKAGE / "macos", PACKAGE.parent / "clients" / "macos")
               if (folder / "build.sh").is_file()), PACKAGE / "macos")
LEFT_OUT = {"build", ".build", ".swiftpm", "xcuserdata", "project.xcworkspace", "Tests", "TapePlayerUITests", "test.sh"}
"""What under the source a Release build of TapePlayer does not read: what a build or Xcode leaves, and the tests."""


def sources(source: Path = SOURCE) -> list[Path]:
    """Every file TapePlayer is built from: all of its source but what LEFT_OUT names and hidden files."""
    return [path for path in source.rglob("*") if path.is_file()
            and not any(part in LEFT_OUT or part.startswith(".") for part in path.relative_to(source).parts)]


def cache() -> Path:
    return Path(os.environ.get("VIDEOTAPE_CACHE_DIR") or Path.home() / "Library" / "Caches" / "videotape")


def _build(folder: Path) -> subprocess.CompletedProcess[str]:
    """Run the source's build script, which leaves build/TapePlayer.app in the folder."""
    return subprocess.run(["bash", str(folder / "build.sh")], capture_output=True, text=True)


def built(source: Path | None = None) -> Path:
    """TapePlayer.app, built from the source unless this version of it was built before. A build copies the source
    into the cache, builds there, and moves the app into place only when the build succeeds, so a cached app is
    always whole."""
    source = source or SOURCE
    if not (source / "build.sh").is_file():
        raise ScreenplayError("VT603", errors.shown(source), "TapePlayer's source is not here, so it cannot build",
                              "install videotape again, so that its package holds macos/build.sh")
    files = sources(source)
    home = cache() / "player" / digest(source, files)[:16]
    app, log = home / "TapePlayer.app", home / "build.log"
    if app.is_dir():
        return app
    print("building TapePlayer, once for this version of it", flush=True)
    started = time.monotonic()
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=home) as scratch:
        folder = Path(scratch)
        for path in files:
            (folder / path.relative_to(source)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, folder / path.relative_to(source))
        ran = _build(folder)
        if ran.returncode != 0:
            said = (ran.stdout + ran.stderr).splitlines()
            log.write_text("\n".join(said) + "\n")
            line = next((line for line in said if "error:" in line),
                        next((line for line in reversed(said) if line.strip()), "nothing"))
            raise ScreenplayError("VT603", errors.shown(log), f"the build exited with {ran.returncode}: {line.strip()}",
                                  "run videotape doctor, which looks for Xcode; when it finds Xcode, the log "
                                  "says what failed")
        (folder / "build" / "TapePlayer.app").rename(app)
    log.unlink(missing_ok=True)
    print(f"built TapePlayer in {time.monotonic() - started:.1f} s", flush=True)
    return app


def _launch(command: list[str]) -> None:
    subprocess.run(command, check=True)


def play(tape: Path) -> list[str]:
    """Open the tape in TapePlayer, built first when it has to be, and return the command that opened it."""
    command = ["open", str(built()), "--args", str(tape.resolve())]
    _launch(command)
    return command
