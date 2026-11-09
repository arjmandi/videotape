"""Wan 2.2 draws every pixel: TI2V-5B for the opening and the moves that key a scene, Fun-5B-InP between two keys."""

from dataclasses import dataclass, fields
from pathlib import Path

from videotape.frames import FPS, HEIGHT, WIDTH
from videotape.shots import Mode


@dataclass(frozen=True)
class Checkpoint:
    repo: str
    revision: str
    guidance: float


# Both Apache-2.0 on Hugging Face. TI2V-5B is in diffusers format. Fun-5B-InP is in VideoX-Fun's own format.
# Guidance: TI2V-5B from Wan2.2's wan/configs/wan_ti2v_5B.py (sample_guide_scale 5.0) and the model card's diffusers
# example; Fun-5B-InP from VideoX-Fun's examples/wan2.2_fun/predict_i2v_5b.py (guidance_scale 6.0).
TI2V = Checkpoint("Wan-AI/Wan2.2-TI2V-5B-Diffusers", "b8fff7315c768468a5333511427288870b2e9635", guidance=5.0)
FUN = Checkpoint("alibaba-pai/Wan2.2-Fun-5B-InP", "d3e911d57ec9e44f1f06dc565387afbe8d28f25f", guidance=6.0)
# The code that runs Fun-5B-InP, pinned to one commit of github.com/aigc-apps/VideoX-Fun (Apache-2.0).
VIDEOX_FUN = ("aigc-apps/VideoX-Fun", "e8c314fbfa494d0429bbef605c9f6112b79a7ead")

# Wan takes 4n+1 frames. 121 frames is 5.04 s at 24 fps, over the five-second limit, and app moves should feel quick.
FRAMES = 81
# Both sources above use 50 steps with a flow shift of 5 at this size.
STEPS = 50
SHIFT = 5.0
# The negative prompt from Wan2.2's wan/configs/shared_config.py, which the TI2V-5B model card and VideoX-Fun's example reuse.
NEGATIVE_PROMPT = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，"
                   "丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
                   "杂乱的背景，三条腿，背景人很多，倒着走")

# What a shot itself supplies. The take cache already hashes these, so settings() leaves them out.
SHOT_FIELDS = frozenset({"mode", "prompt", "seed", "start", "end"})


@dataclass(frozen=True)
class Request:
    """Everything one generation depends on."""

    checkpoint: str
    revision: str
    mode: Mode
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int
    frames: int
    fps: int
    steps: int
    guidance: float
    shift: float
    start: Path | None
    end: Path | None

    def settings(self) -> dict:
        return {field.name: getattr(self, field.name) for field in fields(self) if field.name not in SHOT_FIELDS}


def request(mode: Mode, prompt: str, start: Path | None, end: Path | None, seed: int) -> Request:
    checkpoint = FUN if mode is Mode.FIRST_AND_LAST_FRAME else TI2V
    return Request(checkpoint.repo, checkpoint.revision, mode, prompt, NEGATIVE_PROMPT, seed, WIDTH, HEIGHT, FRAMES, FPS,
                   STEPS, checkpoint.guidance, SHIFT, start, end)
