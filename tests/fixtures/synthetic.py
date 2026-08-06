"""Synthetic artifact generators.

These exist so that `assess`, `calibrate`, `optimize` and `report` can be built
and tested with no trained model, no GPU, no camera and no Jetson. They are the
practical expression of the stage-artifact contract.

Values are plausible but arbitrary; nothing here should ever be reported as a
result.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from certain_road.detect.dataset.convert import ID_TO_CLASS

CLASS_NAMES = [ID_TO_CLASS[i] for i in sorted(ID_TO_CLASS)]
IMG_W, IMG_H = 600, 600
SAMPLE_SPACING_M = 6.0
SEGMENT_APPARENT_SEVERITY_RANGE = (0.3, 2.0)
BOX_SIZE_RANGE_PX = (20.0, 140.0)
SCORE_RANGE = (0.25, 0.98)
ROAD_ROI_TOP_FRACTION = 0.4
SPEED_RANGE_MPS = (6.0, 9.0)


def synthetic_frames(
    n_segments: int,
    frames_per_segment: int,
    *,
    seed: int = 0,
) -> pd.DataFrame:
    """Frames laid out along a straight synthetic track at fixed spacing."""
    rng = np.random.default_rng(seed)
    start = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
    base_lat, base_lon = 13.0827, 80.2707  # arbitrary origin, not a real survey

    rows = []
    frame_index = 0
    for seg in range(n_segments):
        for _ in range(frames_per_segment):
            distance = frame_index * SAMPLE_SPACING_M
            rows.append(
                {
                    "frame_id": f"f{frame_index:06d}",
                    "ts_utc": start + timedelta(seconds=frame_index * 0.8),
                    "survey_date": start.date(),
                    "lat": base_lat + distance * 9e-6,
                    "lon": base_lon,
                    "speed_mps": float(rng.uniform(*SPEED_RANGE_MPS)),
                    "cum_dist_m": float(distance),
                    "segment_id": f"seg{seg:04d}",
                    "image_path": f"synthetic/seg{seg:04d}/f{frame_index:06d}.jpg",
                }
            )
            frame_index += 1

    return pd.DataFrame(rows)


def synthetic_detections(
    frames: pd.DataFrame,
    *,
    seed: int = 0,
    damage_rate: float = 2.0,
) -> pd.DataFrame:
    """Poisson-distributed detections per frame, with per-segment apparent_severity drift.

    Segments differ systematically in damage level so that downstream
    vision-estimated PCI values span a usable range rather than clustering.
    """
    rng = np.random.default_rng(seed)
    segments = sorted(frames["segment_id"].unique())
    apparent_severity = {s: rng.uniform(*SEGMENT_APPARENT_SEVERITY_RANGE) for s in segments}

    rows = []
    for frame in frames.itertuples():
        n = rng.poisson(damage_rate * apparent_severity[frame.segment_id])
        for k in range(int(n)):
            w = float(rng.uniform(*BOX_SIZE_RANGE_PX))
            h = float(rng.uniform(*BOX_SIZE_RANGE_PX))
            x1 = float(rng.uniform(0, IMG_W - w))
            y1 = float(
                rng.uniform(IMG_H * ROAD_ROI_TOP_FRACTION, IMG_H - h)
            )  # lower part: road surface
            rows.append(
                {
                    "frame_id": frame.frame_id,
                    "det_id": f"{frame.frame_id}-{k}",
                    "class_name": str(rng.choice(CLASS_NAMES)),
                    "score": float(rng.uniform(*SCORE_RANGE)),
                    "x1": x1,
                    "y1": y1,
                    "x2": x1 + w,
                    "y2": y1 + h,
                    "img_w": IMG_W,
                    "img_h": IMG_H,
                }
            )

    columns = [
        "frame_id",
        "det_id",
        "class_name",
        "score",
        "x1",
        "y1",
        "x2",
        "y2",
        "img_w",
        "img_h",
    ]
    return pd.DataFrame(rows, columns=columns)
