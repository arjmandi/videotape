import subprocess

import pytest

from videotape import frames
from videotape.errors import ScreenplayError
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
    with pytest.raises(ScreenplayError, match="VT407 frames: frame 1 has 3 bytes"):
        frames.write_video([solid(0, 0, 0).rgb, b"abc"], tmp_path / "clip.mp4")


def test_a_clip_of_another_size_decodes_at_its_own_size_and_rate(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30000/1001",
                    "-t", "0.5", "-pix_fmt", "yuv420p", str(clip)], check=True)
    first, last = frames.first_frame(clip), frames.last_frame(clip)
    assert (first.width, first.height, len(first.rgb)) == (1280, 720, 1280 * 720 * 3)
    assert frames.difference(first, last) > 0.01
    assert frames.shape(clip) == frames.Shape(1280, 720, 29.97)
    with pytest.raises(ScreenplayError, match="VT407 frames: cannot compare a 1280x720 frame with a 1280x704 one"):
        frames.difference(first, solid(0, 0, 0))


def test_a_file_that_does_not_decode_is_a_decode_error_and_a_missing_ffmpeg_is_not(tmp_path, monkeypatch):
    corrupt = tmp_path / "take.mp4"
    corrupt.write_bytes(b"not a clip at all")
    with pytest.raises(DecodeError):
        frames.last_frame(corrupt)
    with pytest.raises(DecodeError):
        frames.first_frame(tmp_path / "missing.mp4")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(FfmpegError, match="VT102 PATH: ffmpeg is not on PATH") as error:
        frames.last_frame(corrupt)
    assert not isinstance(error.value, DecodeError)


def ramp(*levels: int) -> list[bytes]:
    """A grey frame per level."""
    return [solid(level, level, level).rgb for level in levels]


def test_sampled_frames_are_spread_evenly_across_the_clip_the_first_and_the_last_among_them(tmp_path):
    clip = tmp_path / "clip.mp4"
    frames.write_video(ramp(*(10 * number for number in range(24))), clip)
    picked = frames.sampled(clip, 8)
    assert [number for number, _ in picked] == [0, 3, 7, 10, 13, 16, 20, 23]
    for number, frame in picked:
        assert frames.difference(frame, solid(10 * number, 10 * number, 10 * number)) < 0.02
        far = 10 * ((number + 12) % 24)
        assert frames.difference(frame, solid(far, far, far)) > 0.4
    assert [number for number, _ in frames.sampled(clip, 3)] == [0, 12, 23]
    assert [number for number, _ in frames.sampled(clip, 1)] == [0]
    short = tmp_path / "short.mp4"
    frames.write_video(ramp(0, 120, 240), short)
    picked = frames.sampled(short, 8)
    assert [number for number, _ in picked] == [0, 0, 1, 1, 1, 1, 2, 2] and picked[0][1] == picked[1][1]
    assert frames.count(short) == 3


def test_scene_scores_are_high_at_a_cut_and_low_through_a_fade(tmp_path):
    cut, fade = tmp_path / "cut.mp4", tmp_path / "fade.mp4"
    frames.write_video(ramp(*([20] * 12 + [230] * 12)), cut)
    frames.write_video(ramp(*(20 + 9 * number for number in range(24))), fade)
    scores = frames.scene_scores(cut)
    assert len(scores) == 24 and scores[0] == 0.0
    assert scores[12] > 0.3 and max(score for number, score in enumerate(scores) if number != 12) < 0.05
    faded = frames.scene_scores(fade)
    assert len(faded) == 24 and 0 < max(faded) < 0.1


def test_a_corrupt_clip_gives_no_sample_and_no_scores(tmp_path):
    corrupt = tmp_path / "take.mp4"
    corrupt.write_bytes(b"not a clip at all")
    with pytest.raises(FfmpegError):
        frames.sampled(corrupt, 8)
    with pytest.raises(FfmpegError):
        frames.scene_scores(corrupt)
