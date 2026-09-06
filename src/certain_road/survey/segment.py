"""Group a drive's detections into evaluation segments.

**Why frames and not metres.** Condition indices are defined per unit of road, so
the natural unit is a fixed distance. This pipeline cannot measure distance: there
is no GPS on the demo path and no odometry anywhere, and the commanded speed in the
drive log is what the vehicle was *told* to do, not what it did. Integrating it
would produce a number that looks like metres and is not.

D010 already settled this for RDD2022, where the same gap exists: an **evaluation
segment** is a fixed block of consecutive frames. The name is deliberate and is
enforced in review — these are not road segments, and describing them as such would
claim a spatial extent nothing here measures.

The consequence to state wherever segments are reported: two segments contain the
same number of frames, not the same length of road. If the vehicle slowed down, one
covers less ground.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

CLASS_COLUMNS = {
    "linear_crack": "n_linear_crack",
    "alligator_crack": "n_alligator_crack",
    "pothole": "n_pothole",
}


def segment_drive(
    detections: pd.DataFrame,
    drive_log: pd.DataFrame,
    *,
    frames_per_segment: int,
) -> pd.DataFrame:
    """Group a drive into evaluation segments of `frames_per_segment` frames.

    Segments come from the **drive log**, not from the detections, so a stretch of
    road with no damage still produces a segment. A missing segment and a segment
    with a perfect score mean very different things to a maintenance decision, and
    conflating them would silently drop the good road from the report.

    A trailing partial block is kept and its `n_frames` reports the real count —
    dropping it would discard the end of every drive.
    """
    if frames_per_segment < 1:
        raise ValueError(f"frames_per_segment must be >= 1, got {frames_per_segment}")
    if drive_log.empty:
        return pd.DataFrame(columns=_columns())

    log = drive_log.sort_values("timestamp_s").reset_index(drop=True)
    log["_segment_index"] = log.index // frames_per_segment

    counts = _detection_counts(detections)
    rows = []

    for index, block in log.groupby("_segment_index", sort=True):
        frame_ids = list(block["frame_id"])
        block_dets = counts[counts["frame_id"].isin(frame_ids)] if not counts.empty else counts

        row = {
            "segment_id": f"seg{int(index):04d}",
            "survey_date": _survey_date(block),
            "n_frames": len(block),
            "first_frame_id": frame_ids[0],
            "last_frame_id": frame_ids[-1],
            "first_timestamp_s": float(block["timestamp_s"].iloc[0]),
            "last_timestamp_s": float(block["timestamp_s"].iloc[-1]),
            "n_detections": int(len(block_dets)),
            "mean_score": float(block_dets["score"].mean()) if len(block_dets) else 0.0,
        }
        for class_name, column in CLASS_COLUMNS.items():
            row[column] = (
                int((block_dets["class_name"] == class_name).sum()) if len(block_dets) else 0
            )
        rows.append(row)

    return pd.DataFrame(rows, columns=_columns())


def _detection_counts(detections: pd.DataFrame) -> pd.DataFrame:
    if detections.empty:
        return pd.DataFrame(columns=["frame_id", "class_name", "score"])
    return detections[["frame_id", "class_name", "score"]]


def _survey_date(block: pd.DataFrame) -> date:
    return block["survey_date"].iloc[0]


def _columns() -> list[str]:
    from certain_road.artifacts.schema import SegmentRow

    return SegmentRow.columns()
