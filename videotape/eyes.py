from collections.abc import Callable
from pathlib import Path

from videotape.checks import Eye
from videotape.standin import StandInEye

CHECKS: dict[str, Callable[[Path], Eye]] = {
    "stand-in": lambda tape: StandInEye(),
}
