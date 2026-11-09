from collections.abc import Callable
from pathlib import Path

from videotape.checks import Eye
from videotape.qwen import QwenEye
from videotape.standin import StandInEye

CHECKS: dict[str, Callable[[Path], Eye]] = {
    "stand-in": lambda tape: StandInEye(),
    "qwen3-vl-8b": QwenEye,
}
