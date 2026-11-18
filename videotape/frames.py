import json
import os
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from videotape.errors import ScreenplayError

# The size and rate of the clips videotape encodes itself, which are the stand-in's and Wan 2.2 5B's. A clip from any other
# model keeps its own, which decoding reads from the clip.
WIDTH, HEIGHT, FPS = 1280, 704, 24
SMALL = (160, 88)


class FfmpegError(ScreenplayError):
    """ffmpeg or ffprobe failed: VT404. A render reports it at the shot, with the next step it needs."""

    def __init__(self, tool: str, message: str, code: str = "VT404",
                 fix: str = "run videotape doctor, which checks ffmpeg and ffprobe, then run the command again; when "
                            "ffmpeg names a file of the tape, render the story again first") -> None:
        super().__init__(code, tool, message, fix)


class NoTool(FfmpegError):
    """ffmpeg or ffprobe is not on PATH: doctor's VT102."""

    def __init__(self, tool: str) -> None:
        super().__init__("PATH", f"{tool} is not on PATH", "VT102",
                         "install ffmpeg, which brings ffprobe, as in brew install ffmpeg")


class DecodeError(FfmpegError):
    """A file that did not decode into one frame, which a take's file is when it is corrupt."""

    def __init__(self, message: str) -> None:
        super().__init__("ffmpeg", message, fix="delete the file it names, render the story again, which writes it "
                         "again, then run the command again")


def two_sizes(place: str, message: str) -> ScreenplayError:
    """VT407: frames of two sizes, where one tape needs one."""
    return ScreenplayError("VT407", place, message, "render the story again, which writes every key's picture again; "
                           "when it stops here too, the model films takes of two sizes, so render with another model, "
                           "as in:\nvideotape render --story <story> --model stand-in")


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
        raise NoTool(tool) from None
    if run.returncode != 0:
        raise FfmpegError(tool, f"{' '.join(command)}\n{run.stderr.decode(errors='replace').strip()}")
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


def _decode(source: Path | bytes, *filters: str) -> Frame:
    """One frame of a clip or an image at a path, or of an image given as its bytes."""
    # A PPM names its own size in its header, so one decode reads a frame of whatever size the clip has.
    where = ("-f", "image2pipe", "-i", "-") if isinstance(source, bytes) else ("-i", str(source))
    try:
        ppm = _ffmpeg(*where, *filters, "-frames:v", "1", "-f", "image2pipe", "-c:v", "ppm", "-",
                      feed=source if isinstance(source, bytes) else None)
    except NoTool:
        raise
    except FfmpegError as error:
        said = error.message.partition("\n")[2].strip().splitlines()
        raise DecodeError(f"{_shown(source)} did not decode to one frame: {said[-1] if said else 'ffmpeg failed'}") from None
    header = re.match(rb"P6\s(\d+)\s(\d+)\s255\s", ppm)
    width, height = (int(header[1]), int(header[2])) if header else (0, 0)
    if not header or len(ppm) != header.end() + width * height * 3:
        raise DecodeError(f"{_shown(source)} did not decode to one frame: no rgb24 frame came out")
    return Frame(width, height, ppm[header.end():])


def _shown(source: Path | bytes) -> str:
    """A path as an error names it: relative to the working directory when it is inside it."""
    if isinstance(source, bytes):
        return f"a PNG of {len(source)} bytes"
    return os.path.relpath(source) if source.is_absolute() and source.is_relative_to(Path.cwd()) else str(source)


def png(frame: Frame) -> bytes:
    return _ffmpeg(*_raw(frame), "-f", "image2pipe", "-c:v", "png", "-", feed=frame.rgb)


def write_png(frame: Frame, path: Path) -> None:
    path.write_bytes(png(frame))


def read_png(path: Path) -> Frame:
    return _decode(path)


def png_frame(data: bytes) -> Frame:
    """The frame of a PNG given as its bytes."""
    return _decode(data)


def first_frame(clip: Path) -> Frame:
    return _decode(clip)


def last_frame(clip: Path) -> Frame:
    return _decode(clip, "-vf", "reverse")


def gray(*same: Frame) -> list[bytes]:
    """Each frame scaled to SMALL in grey, a byte a pixel, in one pass of ffmpeg: VT407 when two differ in size."""
    first = same[0]
    for other in same[1:]:
        if (other.width, other.height) != (first.width, first.height):
            raise two_sizes("frames", f"cannot compare a {first.width}x{first.height} frame with a {other.width}x"
                            f"{other.height} one")
    w, h = SMALL
    grey = _ffmpeg(*_raw(first), "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-",
                   feed=b"".join(frame.rgb for frame in same))
    n = w * h
    return [grey[at:at + n] for at in range(0, n * len(same), n)]


def difference(a: Frame, b: Frame) -> float:
    small_a, small_b = gray(a, b)
    return sum(abs(x - y) for x, y in zip(small_a, small_b)) / (255 * len(small_a))


ENCODE = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), "-movflags", "+faststart", "-f", "mp4", "-y")


# libx265 runs in software and gives the same bytes from the same clip on every run, where VideoToolbox's file differs
# from run to run, so publishing a tape again encodes the frames its checks passed on. hvc1 is the tag AVFoundation plays.
HEVC = ("-c:v", "libx265", "-crf", "23", "-x265-params", "log-level=error", "-tag:v", "hvc1", "-pix_fmt", "yuv420p", "-an",
        "-movflags", "+faststart", "-f", "mp4", "-y")


def hevc(clip: Path, out: Path) -> None:
    """The clip encoded as HEVC, frame for frame."""
    _ffmpeg("-i", str(clip), *HEVC, str(out))


def crossfade(start: Path, end: Path, out: Path) -> None:
    _ffmpeg("-loop", "1", "-framerate", str(FPS), "-t", "0.5", "-i", str(start),
            "-loop", "1", "-framerate", str(FPS), "-t", "0.9", "-i", str(end),
            "-filter_complex", "[0][1]xfade=transition=fade:duration=0.4:offset=0.1,format=yuv420p", *ENCODE, str(out))


def write_video(rgb_frames: list[bytes], out: Path) -> None:
    """Encode rgb24 frames of WIDTH x HEIGHT into a clip with the same codec settings as every other clip in a tape."""
    for number, frame in enumerate(rgb_frames):
        if len(frame) != WIDTH * HEIGHT * 3:
            raise two_sizes("frames", f"frame {number} has {len(frame)} bytes, not the {WIDTH * HEIGHT * 3} of a "
                            f"{WIDTH}x{HEIGHT} rgb24 frame")
    _ffmpeg("-framerate", str(FPS), *_raw(Frame(WIDTH, HEIGHT, b"")), "-vf", "format=yuv420p", *ENCODE, str(out),
            feed=b"".join(rgb_frames))
