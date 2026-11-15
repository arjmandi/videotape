"""Wan 2.2 draws every pixel: TI2V-5B draws each state's key from text, and Fun-5B-InP draws each move between two keys."""

import gc
import io
import os
import re
import sys
import tarfile
import urllib.request
from dataclasses import dataclass, fields
from importlib.util import find_spec
from pathlib import Path

from videotape import frames
from videotape.frames import FPS, HEIGHT, WIDTH
from videotape.plan import Mode


class WanError(RuntimeError):
    pass


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
VIDEOX_FUN_ARCHIVE = "https://github.com/{repo}/archive/{sha}.tar.gz"

# Wan takes 4n+1 frames. 121 frames is 5.04 s at 24 fps, over the five-second limit, and app moves should feel quick.
FRAMES = 81
# Both sources above use 50 steps with a flow shift of 5 at this size.
STEPS = 50
SHIFT = 5.0
# The negative prompt from Wan2.2's wan/configs/shared_config.py, which the TI2V-5B model card and VideoX-Fun's example reuse.
NEGATIVE_PROMPT = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，"
                   "丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
                   "杂乱的背景，三条腿，背景人很多，倒着走")

# Wan2.2's wan/configs/shared_config.py sets text_len = 512 for its umT5 text encoder. Both pipelines here cut a prompt
# there: diffusers' WanPipeline defaults max_sequence_length to 512, and VideoX-Fun's config sets text_length: 512.
TEXT_TOKENS = 512

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


def tokens(prompt: str) -> int:
    """About how many tokens umT5's tokenizer makes of a prompt, counted high, so that a plan warns early and not
    late."""
    # The real tokenizer is a download, and a plan has to count offline: one token for every four letters of a word,
    # one for every other character that is not a space, and one for the end of the text.
    return len(re.findall(r"[A-Za-z]{1,4}|[^A-Za-z\s]", prompt)) + 1


def videox_fun_dir() -> Path:
    """VideoX-Fun's source at the pinned commit, fetched once into VIDEOX_FUN_DIR or the user's cache."""
    repo, sha = VIDEOX_FUN
    target = Path(os.environ.get("VIDEOX_FUN_DIR") or Path.home() / ".cache" / "videotape" / f"VideoX-Fun-{sha}")
    if not (target / "videox_fun").is_dir():
        with urllib.request.urlopen(VIDEOX_FUN_ARCHIVE.format(repo=repo, sha=sha)) as response:
            archive = tarfile.open(fileobj=io.BytesIO(response.read()), mode="r:gz")
        unpacked = target.with_name(f"{target.name}.partial")
        target.parent.mkdir(parents=True, exist_ok=True)
        archive.extractall(unpacked, filter="data")
        # GitHub's archive holds one folder named after the repo and commit.
        next(unpacked.iterdir()).replace(target)
        unpacked.rmdir()
    return target


def prefetch() -> None:
    """Download the pinned weights and code, so the first take pays for neither."""
    from huggingface_hub import snapshot_download

    for checkpoint in (TI2V, FUN):
        print(snapshot_download(checkpoint.repo, revision=checkpoint.revision), flush=True)
    print(videox_fun_dir(), flush=True)


class Wan:
    """One checkpoint lives in VRAM at a time. A render draws every key, then every move, so it swaps once."""

    name = "wan2.2-5b"
    price = None

    def __init__(self):
        if find_spec("torch") is None or find_spec("diffusers") is None:
            raise WanError("wan2.2-5b needs videotape's wan extra, which is not installed here; install videotape[wan]")
        import torch

        if not torch.cuda.is_available():
            have = "Apple silicon (MPS)" if torch.backends.mps.is_available() else "a CPU"
            raise WanError(f"wan2.2-5b needs a CUDA GPU with about 80 GB, and this machine has {have} only; "
                           "rent one with scripts/runpod-render")
        self.device = torch.cuda.get_device_name(0)
        self.offload = bool(os.environ.get("VIDEOTAPE_WAN_OFFLOAD"))
        self.loaded: Checkpoint | None = None
        self.pipelines: dict = {}

    @staticmethod
    def settings(mode: Mode) -> dict:
        return request(mode, "", None, None, 0).settings()

    def text_to_video(self, prompt: str, seed: int, out: Path) -> None:
        self._run(request(Mode.TEXT_TO_VIDEO, prompt, None, None, seed), out)

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> None:
        self._run(request(Mode.FIRST_AND_LAST_FRAME, prompt, start, end, seed), out)

    def download_again(self, out: Path) -> None:
        return None

    def _run(self, req: Request, out: Path) -> None:
        import torch

        checkpoint = FUN if req.mode is Mode.FIRST_AND_LAST_FRAME else TI2V
        self._load(checkpoint)
        generator = torch.Generator("cuda").manual_seed(req.seed)
        with torch.no_grad():
            video = self._fun(req, generator) if checkpoint is FUN else self._ti2v(req, generator)
        frames.write_video(_rgb_frames(video, req), out)

    def _load(self, checkpoint: Checkpoint) -> None:
        if self.loaded is checkpoint:
            return
        import torch

        self.pipelines.clear()
        gc.collect()
        torch.cuda.empty_cache()
        self.pipelines = self._load_ti2v() if checkpoint is TI2V else self._load_fun()
        self.loaded = checkpoint

    def _load_ti2v(self) -> dict:
        import torch
        from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanPipeline

        # As the model card's diffusers example: the VAE in float32, everything else in bfloat16.
        vae = AutoencoderKLWan.from_pretrained(TI2V.repo, subfolder="vae", revision=TI2V.revision, torch_dtype=torch.float32)
        t2v = WanPipeline.from_pretrained(TI2V.repo, revision=TI2V.revision, vae=vae, torch_dtype=torch.bfloat16)
        t2v.scheduler = UniPCMultistepScheduler.from_config(t2v.scheduler.config, flow_shift=SHIFT)
        if self.offload:
            t2v.enable_model_cpu_offload()
        else:
            t2v.to("cuda")
        return {"t2v": t2v}

    def _ti2v(self, req: Request, generator):
        return self.pipelines["t2v"](prompt=req.prompt, negative_prompt=req.negative_prompt, height=req.height,
                                     width=req.width, num_frames=req.frames, guidance_scale=req.guidance,
                                     num_inference_steps=req.steps, generator=generator, output_type="np").frames[0]

    def _load_fun(self) -> dict:
        import torch
        from diffusers import FlowMatchEulerDiscreteScheduler
        from huggingface_hub import snapshot_download
        from omegaconf import OmegaConf

        source = videox_fun_dir()
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        from videox_fun.models import AutoencoderKLWan3_8, AutoTokenizer, Wan2_2Transformer3DModel, WanT5EncoderModel
        from videox_fun.pipeline import Wan2_2FunInpaintPipeline
        from videox_fun.utils import apply_gpu_memory_mode, filter_kwargs

        # Mirrors examples/wan2.2_fun/predict_i2v_5b.py at the pinned commit, without TeaCache or cfg skipping.
        weights = Path(snapshot_download(FUN.repo, revision=FUN.revision))
        config = OmegaConf.load(source / "config" / "wan2.2" / "wan_civitai_5b.yaml")
        transformer_kwargs = OmegaConf.to_container(config["transformer_additional_kwargs"])
        transformer = Wan2_2Transformer3DModel.from_pretrained(
            str(weights / transformer_kwargs["transformer_low_noise_model_subpath"]),
            transformer_additional_kwargs=transformer_kwargs, low_cpu_mem_usage=True, torch_dtype=torch.bfloat16)
        vae_kwargs = OmegaConf.to_container(config["vae_kwargs"])
        vae = AutoencoderKLWan3_8.from_pretrained(str(weights / vae_kwargs["vae_subpath"]), additional_kwargs=vae_kwargs)
        vae = vae.to(torch.bfloat16)
        text_kwargs = OmegaConf.to_container(config["text_encoder_kwargs"])
        tokenizer = AutoTokenizer.from_pretrained(str(weights / text_kwargs["tokenizer_subpath"]))
        text_encoder = WanT5EncoderModel.from_pretrained(str(weights / text_kwargs["text_encoder_subpath"]),
                                                         additional_kwargs=text_kwargs, low_cpu_mem_usage=True,
                                                         torch_dtype=torch.bfloat16).eval()
        scheduler_kwargs = {**OmegaConf.to_container(config["scheduler_kwargs"]), "shift": SHIFT}
        scheduler = FlowMatchEulerDiscreteScheduler(**filter_kwargs(FlowMatchEulerDiscreteScheduler, scheduler_kwargs))
        pipeline = Wan2_2FunInpaintPipeline(transformer=transformer, transformer_2=None, vae=vae, tokenizer=tokenizer,
                                            text_encoder=text_encoder, scheduler=scheduler)
        apply_gpu_memory_mode(pipeline, "model_cpu_offload" if self.offload else "model_full_load", "cuda", torch.bfloat16)
        return {"flf": pipeline, "boundary": transformer_kwargs.get("boundary", 0.900)}

    def _fun(self, req: Request, generator):
        from videox_fun.utils import get_image_to_video_latent

        video, mask, _ = get_image_to_video_latent(str(req.start), str(req.end), video_length=req.frames,
                                                   sample_size=[req.height, req.width])
        return self.pipelines["flf"](req.prompt, num_frames=req.frames, negative_prompt=req.negative_prompt,
                                     height=req.height, width=req.width, generator=generator, guidance_scale=req.guidance,
                                     num_inference_steps=req.steps, boundary=self.pipelines["boundary"],
                                     video=video, mask_video=mask, shift=req.shift).videos


def _rgb_frames(video, req: Request) -> list[bytes]:
    """rgb24 frames from diffusers' (frames, height, width, 3) array or VideoX-Fun's (1, 3, frames, height, width) tensor, both in 0..1."""
    import numpy as np
    import torch

    if isinstance(video, torch.Tensor):
        video = video[0].permute(1, 2, 3, 0).float().cpu().numpy()
    if video.shape != (req.frames, req.height, req.width, 3):
        raise WanError(f"{req.checkpoint} returned frames of shape {video.shape}, not {(req.frames, req.height, req.width, 3)}")
    return [frame.tobytes() for frame in (np.clip(video, 0, 1) * 255).round().astype(np.uint8)]
