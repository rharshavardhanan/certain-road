import pandas as pd
import pytest

from certain_road.artifacts.io import SchemaMismatch, read_artifact, write_artifact
from certain_road.artifacts.schema import DetectionRow


def _valid_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "frame_id": "f0001",
                "det_id": "f0001-0",
                "class_name": "D40",
                "score": 0.91,
                "x1": 10.0,
                "y1": 20.0,
                "x2": 60.0,
                "y2": 80.0,
                "img_w": 600,
                "img_h": 600,
            }
        ]
    )


def test_round_trip_preserves_values(tmp_path):
    path = tmp_path / "detections.parquet"
    original = _valid_df()
    write_artifact(original, path, DetectionRow)
    restored = read_artifact(path, DetectionRow)
    pd.testing.assert_frame_equal(original, restored)


def test_missing_column_is_rejected_on_write(tmp_path):
    df = _valid_df().drop(columns=["score"])
    with pytest.raises(SchemaMismatch, match="score"):
        write_artifact(df, tmp_path / "d.parquet", DetectionRow)


def test_unexpected_column_is_rejected_on_write(tmp_path):
    df = _valid_df().assign(surprise=1)
    with pytest.raises(SchemaMismatch, match="surprise"):
        write_artifact(df, tmp_path / "d.parquet", DetectionRow)


def test_version_mismatch_is_rejected_on_read(tmp_path):
    path = tmp_path / "detections.parquet"
    write_artifact(_valid_df(), path, DetectionRow)

    class FutureDetectionRow(DetectionRow):
        schema_version = "2.0.0"

    with pytest.raises(SchemaMismatch, match="2.0.0"):
        read_artifact(path, FutureDetectionRow)


def test_wrong_artifact_name_is_rejected_on_read(tmp_path):
    path = tmp_path / "detections.parquet"
    write_artifact(_valid_df(), path, DetectionRow)

    class Impostor(DetectionRow):
        artifact_name = "frames"

    with pytest.raises(SchemaMismatch, match="frames"):
        read_artifact(path, Impostor)


def test_row_validation_catches_bad_value(tmp_path):
    # object dtype because pandas 3 refuses to upcast a float64 column in place;
    # this is also how mixed-type data actually arrives (CSV, dicts).
    df = _valid_df().astype({"score": "object"})
    df.loc[0, "score"] = "not a number"
    with pytest.raises(SchemaMismatch):
        write_artifact(df, tmp_path / "d.parquet", DetectionRow)
