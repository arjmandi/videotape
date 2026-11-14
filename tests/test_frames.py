import subprocess

import pytest

from videotape import frames
from videotape.frames import HEIGHT, WIDTH, DecodeError, FfmpegError, Frame


def solid(red: int, green: int, blue: int) -> Frame:
    return Frame(WIDTH, HEIGHT, bytes((red, green, blue)) * (WIDTH * HEIGHT))


def test_write_video_encodes_frames_like_every_other_clip(tmp_path):
    first, middle, last = solid(230, 230, 230), solid(40, 200, 40), solid(20, 20, 20)
    clip = tmp_path / "clip.mp4"
    frames.write_video([first.rgb, middle.rgb, last.rgb], clip)
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries",
                            "stream=codec_name,width,height,pix_fmt,r_frame_rate,nb_read_frames", "-of", "csv=p=0", str(clip)],
                           capture_output=True, text=True, check=True)
    assert probe.stdout.strip() == "h264,1280,704,yuv420p,24/1,3"
    assert frames.difference(frames.first_frame(clip), first) < 0.02
    assert frames.difference(frames.last_frame(clip), last) < 0.02
    assert frames.difference(frames.last_frame(clip), first) > 0.3


def test_write_video_rejects_a_frame_of_the_wrong_size(tmp_path):
    with pytest.raises(FfmpegError, match="frame 1 has 3 bytes"):
        frames.write_video([solid(0, 0, 0).rgb, b"abc"], tmp_path / "clip.mp4")


def test_a_clip_of_another_size_decodes_at_its_own_size_and_rate(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30000/1001",
                    "-t", "0.5", "-pix_fmt", "yuv420p", str(clip)], check=True)
    first, last = frames.first_frame(clip), frames.last_frame(clip)
    assert (first.width, first.height, len(first.rgb)) == (1280, 720, 1280 * 720 * 3)
    assert frames.difference(first, last) > 0.01
    assert frames.shape(clip) == frames.Shape(1280, 720, 29.97)
    with pytest.raises(FfmpegError, match="cannot compare a 1280x720 frame with a 1280x704 one"):
        frames.difference(first, solid(0, 0, 0))


def test_a_file_that_does_not_decode_is_a_decode_error_and_a_missing_ffmpeg_is_not(tmp_path, monkeypatch):
    corrupt = tmp_path / "take.mp4"
    corrupt.write_bytes(b"not a clip at all")
    with pytest.raises(DecodeError):
        frames.last_frame(corrupt)
    with pytest.raises(DecodeError):
        frames.first_frame(tmp_path / "missing.mp4")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(FfmpegError, match="ffmpeg is not on PATH") as error:
        frames.last_frame(corrupt)
    assert not isinstance(error.value, DecodeError)
