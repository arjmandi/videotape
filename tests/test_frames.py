import subprocess

import pytest

from videotape import frames
from videotape.frames import HEIGHT, WIDTH, FfmpegError, Frame


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
