"""Frame sources, exercised against a real video file written on the fly."""

import cv2
import numpy as np
import pytest

from certain_road.perception.source import VideoSource


@pytest.fixture
def video(tmp_path):
    """A real 20-frame video, so this tests decoding rather than a mock."""
    path = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for i in range(20):
        frame = np.full((48, 64, 3), i * 10 % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def test_reads_every_frame_by_default(video):
    with VideoSource(video) as src:
        assert len(list(src.frames())) == 20


def test_stride_samples_every_nth_frame(video):
    with VideoSource(video, stride=5) as src:
        assert len(list(src.frames())) == 4


def test_max_frames_caps_the_run(video):
    with VideoSource(video, max_frames=7) as src:
        assert len(list(src.frames())) == 7


def test_frames_carry_identity_and_time(video):
    with VideoSource(video) as src:
        first = next(src.frames())
    assert first.frame_id.endswith("_000000")
    assert first.timestamp_s == 0.0
    assert (first.width, first.height) == (64, 48)


def test_timestamps_increase_with_stride(video):
    with VideoSource(video, stride=5) as src:
        times = [f.timestamp_s for f in src.frames()]
    assert times == sorted(times)
    assert times[1] > times[0]


def test_missing_file_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        VideoSource(tmp_path / "nope.mp4")


def test_zero_stride_is_rejected(video):
    with pytest.raises(ValueError, match="stride"):
        VideoSource(video, stride=0)
