"""Recording a drive to artifacts.

Round-trips through real Parquet files rather than asserting on in-memory frames:
the artifacts ARE the interface to the survey pipeline, so their on-disk shape is
what matters.
"""

from datetime import date

import numpy as np

from certain_road.artifacts.io import read_artifact
from certain_road.artifacts.schema import Detection, DetectionRow, DriveLogRow
from certain_road.canbus.transport import NullTransport
from certain_road.core.paths import repo_root
from certain_road.driving.corridor import load_corridor
from certain_road.driving.decision import load_policy
from certain_road.perception.source import Frame, FrameSource
from certain_road.runtime.pipeline import run
from certain_road.runtime.recorder import record

CORRIDOR = load_corridor(repo_root() / "configs" / "driving" / "corridor.yaml")
POLICY = load_policy(repo_root() / "configs" / "driving" / "decision.yaml")
W = H = 640


class FakeSource(FrameSource):
    def __init__(self, n):
        self.n = n

    def frames(self):
        for i in range(self.n):
            yield Frame(f"f{i:04d}", np.zeros((H, W, 3), dtype=np.uint8), i * 0.1)


def pothole(score=0.9):
    return Detection("pothole", score, 290.0, 560.0, 350.0, 620.0, W, H)


def drive(detector, frames=10):
    return run(FakeSource(frames), detector, CORRIDOR, POLICY, NullTransport(), escape_lanes=5.0)


def test_a_drive_writes_both_artifacts(tmp_path):
    paths = record(drive(lambda f: [pothole()]), tmp_path, survey_date=date(2026, 9, 6))
    assert paths["detections"].exists()
    assert paths["drive_log"].exists()


def test_artifacts_validate_against_their_schemas(tmp_path):
    record(drive(lambda f: [pothole()]), tmp_path)
    dets = read_artifact(tmp_path / "detections.parquet", DetectionRow, validate_rows=True)
    log = read_artifact(tmp_path / "drive_log.parquet", DriveLogRow, validate_rows=True)
    assert len(dets) > 0
    assert len(log) == 10


def test_drive_log_has_one_row_per_frame_even_with_no_detections(tmp_path):
    """A frame with nothing in it is still a frame the vehicle drove."""
    record(drive(lambda f: [], frames=7), tmp_path)
    log = read_artifact(tmp_path / "drive_log.parquet", DriveLogRow)
    assert len(log) == 7
    dets = read_artifact(tmp_path / "detections.parquet", DetectionRow)
    assert len(dets) == 0


def test_governing_detection_is_traceable_from_the_log(tmp_path):
    """The log must say WHICH detection drove the decision, not just that one did."""
    record(drive(lambda f: [pothole()]), tmp_path)
    log = read_artifact(tmp_path / "drive_log.parquet", DriveLogRow)
    dets = read_artifact(tmp_path / "detections.parquet", DetectionRow)

    linked = log[log["governing_det_id"].notna()]
    assert len(linked) > 0
    assert set(linked["governing_det_id"]) <= set(dets["det_id"])


def test_detection_ids_are_unique(tmp_path):
    record(drive(lambda f: [pothole(), pothole()]), tmp_path)
    dets = read_artifact(tmp_path / "detections.parquet", DetectionRow)
    assert dets["det_id"].is_unique


def test_survey_date_is_recorded(tmp_path):
    """D024: every segment-level artifact carries it, so longitudinal work needs
    no schema migration later."""
    record(drive(lambda f: []), tmp_path, survey_date=date(2026, 9, 6))
    log = read_artifact(tmp_path / "drive_log.parquet", DriveLogRow)
    assert set(log["survey_date"]) == {date(2026, 9, 6)}


def test_commands_are_recorded_for_the_measurement_table(tmp_path):
    record(drive(lambda f: [pothole()]), tmp_path)
    log = read_artifact(tmp_path / "drive_log.parquet", DriveLogRow)
    assert set(log["action"]) <= {"STOP", "FORWARD", "REVERSE"}
    assert log["speed"].between(0.0, 1.0).all()
    assert log["steer"].between(-1.0, 1.0).all()
