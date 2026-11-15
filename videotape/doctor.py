"""What videotape needs of this machine, checked one line at a time: the Python, ffmpeg, and Xcode for TapePlayer, and
in a project, the API key its model needs and what its eye needs."""

import importlib.metadata
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from videotape import project, qwen
from videotape.errors import ScreenplayError
from videotape.model import MODELS
from videotape.qwen import QwenEye


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
        return Check("VT104", True, f"{model} needs no API key")
    value = os.environ.get(needed, "").strip()
    if not value:
        return Check("VT104", False, f"{model} needs {needed}, and it is not in the environment or .env",
                     f"copy .env.example to .env and set {needed} there, or export it")
    if not value.isprintable():
        return Check("VT104", False, f"{needed} holds a character an HTTP header cannot carry, such as a line break",
                     f"set {needed} to the API key alone, in .env or the environment")
    return Check("VT104", True, f"{needed} is set, for {model}")


def eye(model: str) -> Check:
    """What the model's eye needs to read a take back. Qwen3-VL-8B, the Wan models' eye, runs on Apple silicon or a
    CUDA GPU, through videotape's qwen extra."""
    if MODELS[model].eye is not QwenEye:
        return Check("VT105", True, f"{model}'s checks need no GPU")
    gpu = ("Apple silicon" if platform.system() == "Darwin" and platform.machine() == "arm64"
           else "a CUDA GPU" if shutil.which("nvidia-smi") else None)
    if gpu is None:
        return Check("VT105", False, f"{model}'s checks need Apple silicon or a CUDA GPU, and this machine is "
                     f"{platform.system()} on {platform.machine()} without nvidia-smi",
                     "render on a Mac with Apple silicon or a machine with a CUDA GPU, or with the stand-in, as in "
                     "videotape render --story starter --model stand-in")
    if not qwen.installed():
        return Check("VT105", False, f"{model}'s checks run Qwen3-VL-8B through videotape's qwen extra, which is not "
                     "installed here", qwen.ADD_EXTRA)
    return Check("VT105", True, f"{gpu} and videotape's qwen extra, for {model}'s checks")


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
    return [*machine, key(found.model), eye(found.model)] if found.model else machine
