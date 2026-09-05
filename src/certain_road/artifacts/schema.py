"""Artifact row schemas. Definitions only — this module contains no logic.

Every artifact written to disk is described here by exactly one model. Bumping
`schema_version` makes older files unreadable by design: a silent read of a
stale-shaped artifact is the failure mode this guards against.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import ClassVar

from pydantic import BaseModel


class ArtifactModel(BaseModel):
    """One row of one artifact."""

    artifact_name: ClassVar[str]
    schema_version: ClassVar[str]

    @classmethod
    def columns(cls) -> list[str]:
        return list(cls.model_fields.keys())


class FrameRow(ArtifactModel):
    """One sampled frame. Sample spacing and segment length are config, not constants."""

    artifact_name: ClassVar[str] = "frames"
    schema_version: ClassVar[str] = "1.0.0"

    frame_id: str
    ts_utc: datetime
    survey_date: date
    lat: float | None
    lon: float | None
    speed_mps: float | None
    cum_dist_m: float
    segment_id: str
    image_path: str


class DetectionRow(ArtifactModel):
    """One detected distress instance, in pixel coordinates."""

    artifact_name: ClassVar[str] = "detections"
    schema_version: ClassVar[str] = "1.0.0"

    frame_id: str
    det_id: str
    class_name: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float
    img_w: int
    img_h: int


@dataclass(frozen=True)
class Detection:
    """One detection as a lightweight in-memory value, for real-time pipelines.

    Same fields as `DetectionRow`, but not a pydantic Parquet row model:
    `driving/` (and eventually `canbus/`) need a per-frame list they construct
    and discard many times a second, where pydantic validation overhead and a
    Parquet-oriented shape are the wrong tool. `Detection` lives beside
    `DetectionRow` in this leaf module so both the drive and survey pipelines
    can depend on it without depending on each other.
    """

    class_name: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float
    img_w: int
    img_h: int
