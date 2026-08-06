"""Write synthetic artifacts to runs/synthetic/ for manual pipeline exercise.

Usage: uv run python scripts/make_fixtures.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from certain_road.artifacts.io import write_artifact  # noqa: E402
from certain_road.artifacts.schema import DetectionRow, FrameRow  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402
from tests.fixtures.synthetic import synthetic_detections, synthetic_frames  # noqa: E402

OUT = repo_root() / "runs" / "synthetic" / "artifacts"


def main() -> None:
    frames = synthetic_frames(n_segments=102, frames_per_segment=15, seed=0)
    detections = synthetic_detections(frames, seed=0)

    write_artifact(frames, OUT / "frames.parquet", FrameRow)
    write_artifact(detections, OUT / "detections.parquet", DetectionRow)

    print(f"wrote {len(frames)} frames and {len(detections)} detections to {OUT}")


if __name__ == "__main__":
    main()
