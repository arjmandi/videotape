import json
import os
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

# The size and rate of the clips videotape encodes itself, which are the stand-in's and Wan 2.2 5B's. A clip from any other
# model keeps its own, which decoding reads from the clip.
WIDTH, HEIGHT, FPS = 1280, 704, 24
SMALL = (160, 88)


class FfmpegError(RuntimeError):
    pass


class NoTool(FfmpegError):
    """ffmpeg or ffprobe is not on PATH."""


class DecodeError(FfmpegError):
    """A file that did not decode into one frame, which a take's file is when it is corrupt."""


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    rgb: bytes


@dataclass(frozen=True)
class Shape:
    """A clip's frame size and frame rate."""

    width: int
    height: int
    fps: int | float


def _tool(tool: str, *args: str, feed: bytes | None = None) -> bytes:
    command = [tool, "-hide_banner", "-loglevel", "error", *args]
    stdin = {"input": feed} if feed is not None else {"stdin": subprocess.DEVNULL}
    try:
        run = subprocess.run(command, capture_output=True, **stdin)
    except FileNotFoundError:
        raise NoTool(f"{tool} is not on PATH") from None
    if run.returncode != 0:
        raise FfmpegError(f"{' '.join(command)}\n{run.stderr.decode(errors='replace').strip()}")
    return run.stdout


def _ffmpeg(*args: str, feed: bytes | None = None) -> bytes:
    return _tool("ffmpeg", *args, feed=feed)


def shape(clip: Path) -> Shape:
    probe = json.loads(_tool("ffprobe", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                             "-of", "json", str(clip)))
    [stream] = probe["streams"]
    fps = Fraction(stream["r_frame_rate"])
    return Shape(stream["width"], stream["height"], int(fps) if fps.denominator == 1 else round(float(fps), 3))


def _raw(frame: Frame) -> tuple[str, ...]:
    return ("-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{frame.width}x{frame.height}", "-i", "-")


def _decode(source: Path, *filters: str) -> Frame:
    # A PPM names its own size in its header, so one decode reads a frame of whatever size the clip has.
    try:
        ppm = _ffmpeg("-i", str(source), *filters, "-frames:v", "1", "-f", "image2pipe", "-c:v", "ppm", "-")
    except NoTool:
        raise
    except FfmpegError as error:
        said = str(error).partition("\n")[2].strip().splitlines()
        raise DecodeError(f"{_shown(source)} did not decode to one frame: {said[-1] if said else 'ffmpeg failed'}") from None
    header = re.match(rb"P6\s(\d+)\s(\d+)\s255\s", ppm)
    width, height = (int(header[1]), int(header[2])) if header else (0, 0)
    if not header or len(ppm) != header.end() + width * height * 3:
        raise DecodeError(f"{_shown(source)} did not decode to one frame: no rgb24 frame came out")
    return Frame(width, height, ppm[header.end():])


def _shown(path: Path) -> str:
    """A path as an error names it: relative to the working directory when it is inside it."""
    return os.path.relpath(path) if path.is_absolute() and path.is_relative_to(Path.cwd()) else str(path)


def write_png(frame: Frame, path: Path) -> None:
    path.write_bytes(_ffmpeg(*_raw(frame), "-f", "image2pipe", "-c:v", "png", "-", feed=frame.rgb))


def read_png(path: Path) -> Frame:
    return _decode(path)


def first_frame(clip: Path) -> Frame:
    return _decode(clip)


def last_frame(clip: Path) -> Frame:
    return _decode(clip, "-vf", "reverse")


def difference(a: Frame, b: Frame) -> float:
    if (a.width, a.height) != (b.width, b.height):
        raise FfmpegError(f"cannot compare a {a.width}x{a.height} frame with a {b.width}x{b.height} one")
    w, h = SMALL
    grey = _ffmpeg(*_raw(a), "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-", feed=a.rgb + b.rgb)
    n = w * h
    return sum(abs(x - y) for x, y in zip(grey[:n], grey[n:])) / (255 * n)


ENCODE = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), "-movflags", "+faststart", "-f", "mp4", "-y")


def crossfade(start: Path, end: Path, out: Path) -> None:
    _ffmpeg("-loop", "1", "-framerate", str(FPS), "-t", "0.5", "-i", str(start),
            "-loop", "1", "-framerate", str(FPS), "-t", "0.9", "-i", str(end),
            "-filter_complex", "[0][1]xfade=transition=fade:duration=0.4:offset=0.1,format=yuv420p", *ENCODE, str(out))


def write_video(rgb_frames: list[bytes], out: Path) -> None:
    """Encode rgb24 frames of WIDTH x HEIGHT into a clip with the same codec settings as every other clip in a tape."""
    for number, frame in enumerate(rgb_frames):
        if len(frame) != WIDTH * HEIGHT * 3:
            raise FfmpegError(f"frame {number} has {len(frame)} bytes, not the {WIDTH * HEIGHT * 3} of a {WIDTH}x{HEIGHT} rgb24 frame")
    _ffmpeg("-framerate", str(FPS), *_raw(Frame(WIDTH, HEIGHT, b"")), "-vf", "format=yuv420p", *ENCODE, str(out),
            feed=b"".join(rgb_frames))
