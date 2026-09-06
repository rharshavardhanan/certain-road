"""Where frames come from.

The perception stage does not care whether an image arrived from a camera, a
recorded drive, or a directory of stills. Making that a seam is what lets the
Sep 20 demo run on recorded video while a live camera slots in later as a
configured swap rather than a rewrite (D052).

`CameraSource` is the deferred sibling of `VideoSource`. It is not built here
because the Pi Camera Module 3's IMX708 is not officially JetPack-supported
(D048) and the demo does not need it. When a supported sensor is mounted it is a
new subclass and nothing downstream moves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Frame:
    """One image, with enough identity to trace a detection back to it."""

    frame_id: str
    image: np.ndarray  # BGR, as OpenCV delivers it
    timestamp_s: float

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


class FrameSource(ABC):
    """An iterable supply of frames."""

    @abstractmethod
    def frames(self) -> Iterator[Frame]: ...

    def close(self) -> None:  # pragma: no cover - default no-op
        return None

    def __enter__(self) -> FrameSource:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class VideoSource(FrameSource):
    """Frames from a video file.

    `stride` samples every Nth frame. That is not a performance knob: D006 samples
    by distance travelled so a hazard is never counted twice, and on recorded
    footage frame stride is the available approximation of it. Set it from the
    footage's frame rate and the vehicle's speed, not from how fast inference runs.
    """

    def __init__(self, path: Path, *, stride: int = 1, max_frames: int | None = None) -> None:
        import cv2

        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"no video at {self.path}")
        if stride < 1:
            raise ValueError(f"stride must be >= 1, got {stride}")

        self.stride = stride
        self.max_frames = max_frames
        self._cv2 = cv2
        self._capture = cv2.VideoCapture(str(self.path))
        if not self._capture.isOpened():
            raise OSError(f"could not open video {self.path}")
        self.fps = float(self._capture.get(cv2.CAP_PROP_FPS)) or 30.0

    def frames(self) -> Iterator[Frame]:
        index = 0
        emitted = 0
        while True:
            ok, image = self._capture.read()
            if not ok:
                return
            if index % self.stride == 0:
                yield Frame(
                    frame_id=f"{self.path.stem}_{index:06d}",
                    image=image,
                    timestamp_s=index / self.fps,
                )
                emitted += 1
                if self.max_frames is not None and emitted >= self.max_frames:
                    return
            index += 1

    def close(self) -> None:
        self._capture.release()
