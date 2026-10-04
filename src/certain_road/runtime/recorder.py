"""Persist what a drive produced.

**Why this lives in `runtime/` and not `survey/`.** The survey pipeline may not
import `driving/` (D049) — that contract is what keeps condition assessment out of
the steering loop. So survey cannot consume a live `Step`, which carries driving
types. Instead the runtime writes artifacts and survey reads them, which is what
the stage-artifact contract (D002) always intended: stages communicate through
typed files on disk, never through shared objects.

Two artifacts per drive, deliberately separate:

- `detections.parquet` — every detection above the record threshold. The survey's
  input, and the same shape the detector produces offline, so segmenting a live
  drive and segmenting a recorded dataset are the same code path.
- `drive_log.parquet` — what the vehicle decided and commanded, frame by frame.
  Needed for the measurement table, and to explain *why* a segment looks the way
  it does.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd

from certain_road.artifacts.io import write_artifact
from certain_road.artifacts.schema import DetectionRow, DriveLogRow
from certain_road.runtime.pipeline import Step


def record(
    steps: Iterable[Step],
    out_dir: Path,
    *,
    survey_date: date | None = None,
) -> dict[str, Path]:
    """Consume a drive and write its artifacts. Returns the paths written."""
    det_rows: list[dict] = []
    log_rows: list[dict] = []
    when = survey_date or date.today()

    for step in steps:
        governing_id = None
        for i, det in enumerate(step.detections):
            det_id = f"{step.frame_id}-{i}"
            if step.governing is not None and det is step.governing:
                governing_id = det_id
            det_rows.append(
                {
                    "frame_id": step.frame_id,
                    "det_id": det_id,
                    "class_name": det.class_name,
                    "score": det.score,
                    "x1": det.x1,
                    "y1": det.y1,
                    "x2": det.x2,
                    "y2": det.y2,
                    "img_w": det.img_w,
                    "img_h": det.img_h,
                }
            )
        log_rows.append(
            {
                "frame_id": step.frame_id,
                "timestamp_s": step.timestamp_s,
                "survey_date": when,
                "drive_state": str(step.drive_state),
                "action": step.command.action.name,
                "speed": step.command.speed,
                "steer": step.command.steer,
                "governing_det_id": governing_id,
            }
        )

    out_dir = Path(out_dir)
    detections = out_dir / "detections.parquet"
    drive_log = out_dir / "drive_log.parquet"

    write_artifact(pd.DataFrame(det_rows, columns=DetectionRow.columns()), detections, DetectionRow)
    write_artifact(pd.DataFrame(log_rows, columns=DriveLogRow.columns()), drive_log, DriveLogRow)
    return {"detections": detections, "drive_log": drive_log}
