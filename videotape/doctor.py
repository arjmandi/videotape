"""What videotape needs of this machine, checked one line at a time: the Python, ffmpeg, and Xcode for TapePlayer, and
in a project, the key its model needs and the GPU its checks need."""

import importlib.metadata
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from videotape import project
from videotape.errors import ScreenplayError
from videotape.model import MODELS


@dataclass(frozen=True)
class Check:
    code: str
    ok: bool
    what: str
    fix: str = ""

    def __str__(self) -> str:
        return f"ok   {self.code} {self.what}" if self.ok else f"fail {self.code} {self.what}\n  fix: {self.fix}"


def python() -> Check:
    needs = importlib.metadata.metadata("videotape")["Requires-Python"]
    least = tuple(map(int, re.findall(r"\d+", needs)[:2]))
    what = f"Python {'.'.join(map(str, sys.version_info[:3]))}, and videotape needs {needs}"
    return Check("VT101", sys.version_info[:2] >= least, what,
                 f"make the project's environment with a newer Python, as in uv sync --python {'.'.join(map(str, least))}")


def ffmpeg() -> Check:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if not missing:
        return Check("VT102", True, "ffmpeg and ffprobe are on PATH")
    return Check("VT102", False, f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not on PATH",
                 "install ffmpeg, which brings ffprobe, as in brew install ffmpeg")


def _said(command: list[str]) -> str | None:
    """What a command printed, or None when it is not here or fails."""
    try:
        ran = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return ran.stdout.strip() if ran.returncode == 0 else None


def xcode() -> Check:
    """Xcode itself, which TapePlayer's build needs: xcode-select points at it, not at the Command Line Tools alone,
    and xcodebuild runs."""
    selected, version = _said(["xcode-select", "--print-path"]), _said(["xcodebuild", "-version"])
    if selected and version and "CommandLineTools" not in selected:
        return Check("VT103", True, f"{version.splitlines()[0]}, at {selected}, for TapePlayer")
    what = ("xcode-select is not here" if selected is None
            else f"xcode-select points at {selected}, the Command Line Tools without Xcode" if "CommandLineTools" in selected
            else "xcodebuild does not run")
    return Check("VT103", False, f"{what}, so TapePlayer cannot build",
                 "install Xcode from the App Store, then point xcode-select at it, as in "
                 "sudo xcode-select --switch /Applications/Xcode.app")


def key(model: str) -> Check:
    needed = MODELS[model].key
    if needed is None:
        return Check("VT104", True, f"{model} needs no key")
    if os.environ.get(needed, "").strip():
        return Check("VT104", True, f"{needed} is set, for {model}")
    return Check("VT104", False, f"{model} needs {needed}, and it is not in the environment or .env",
                 f"copy .env.example to .env and set {needed} there, or export it")


def gpu(model: str) -> Check:
    if not MODELS[model].eye_gpu:
        return Check("VT105", True, f"{model}'s checks need no GPU")
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return Check("VT105", True, f"Apple silicon, for {model}'s checks")
    if shutil.which("nvidia-smi"):
        return Check("VT105", True, f"a CUDA GPU, for {model}'s checks")
    return Check("VT105", False, f"{model}'s checks need Apple silicon or a CUDA GPU, and this machine is "
                 f"{platform.system()} on {platform.machine()} without nvidia-smi",
                 "render on a Mac with Apple silicon or a machine with a CUDA GPU, or with the stand-in, as in "
                 "videotape render --story starter --model stand-in")


def checks(start: Path) -> list[Check]:
    """The machine's checks, and those of the project at start when there is one. A project with a wrong value fails
    with its own code."""
    machine = [python(), ffmpeg(), xcode()]
    try:
        found = project.find(start)
    except ScreenplayError as error:
        if error.code == "VT106":
            return machine
        return [*machine, Check(error.code, False, f"{error.place}: {error.message}", error.fix)]
    return [*machine, key(found.model), gpu(found.model)] if found.model else machine
