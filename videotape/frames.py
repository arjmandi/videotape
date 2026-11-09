import subprocess
from dataclasses import dataclass
from pathlib import Path

WIDTH, HEIGHT, FPS = 1280, 704, 24
SMALL = (160, 88)


class FfmpegError(RuntimeError):
    pass


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


def _ffmpeg(*args: str, feed: bytes | None = None) -> bytes:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", *args]
    stdin = {"input": feed} if feed is not None else {"stdin": subprocess.DEVNULL}
    try:
        run = subprocess.run(command, capture_output=True, **stdin)
    except FileNotFoundError:
        raise FfmpegError("ffmpeg is not on PATH") from None
    if run.returncode != 0:
        raise FfmpegError(f"{' '.join(command)}\n{run.stderr.decode(errors='replace').strip()}")
    return run.stdout


def _raw(frame: Frame) -> tuple[str, ...]:
    return ("-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{frame.width}x{frame.height}", "-i", "-")


def _decode(source: Path, *filters: str) -> Frame:
    rgb = _ffmpeg("-i", str(source), *filters, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
    if len(rgb) != WIDTH * HEIGHT * 3:
        raise FfmpegError(f"{source} is not a {WIDTH}x{HEIGHT} image")
    return Frame(WIDTH, HEIGHT, rgb)


def write_png(frame: Frame, path: Path) -> None:
    path.write_bytes(_ffmpeg(*_raw(frame), "-f", "image2pipe", "-c:v", "png", "-", feed=frame.rgb))


def read_png(path: Path) -> Frame:
    return _decode(path)


def first_frame(clip: Path) -> Frame:
    return _decode(clip)


def last_frame(clip: Path) -> Frame:
    return _decode(clip, "-vf", "reverse")


def difference(a: Frame, b: Frame) -> float:
    w, h = SMALL
    grey = _ffmpeg(*_raw(a), "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-", feed=a.rgb + b.rgb)
    n = w * h
    return sum(abs(x - y) for x, y in zip(grey[:n], grey[n:])) / (255 * n)


def crossfade(start: Path, end: Path, out: Path) -> None:
    _ffmpeg("-loop", "1", "-framerate", str(FPS), "-t", "0.5", "-i", str(start),
            "-loop", "1", "-framerate", str(FPS), "-t", "0.9", "-i", str(end),
            "-filter_complex", "[0][1]xfade=transition=fade:duration=0.4:offset=0.1,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS),
            "-movflags", "+faststart", "-f", "mp4", "-y", str(out))
