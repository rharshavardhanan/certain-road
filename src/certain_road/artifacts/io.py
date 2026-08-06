"""Read and write artifacts, enforcing the schema contract on every access."""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ValidationError

from certain_road.artifacts.schema import ArtifactModel

META_ARTIFACT = b"certain_road.artifact"
META_VERSION = b"certain_road.schema_version"


class SchemaMismatch(Exception):
    """An artifact on disk does not match the model used to access it."""


def _check_columns(df: pd.DataFrame, model: type[ArtifactModel]) -> None:
    expected = set(model.columns())
    actual = set(df.columns)
    if missing := sorted(expected - actual):
        raise SchemaMismatch(f"{model.artifact_name}: missing columns {missing}")
    if extra := sorted(actual - expected):
        raise SchemaMismatch(f"{model.artifact_name}: unexpected columns {extra}")


def write_artifact(
    df: pd.DataFrame,
    path: Path,
    model: type[ArtifactModel],
    *,
    validate_rows: bool = True,
) -> None:
    """Write `df` as the artifact described by `model`, stamping name and version."""
    _check_columns(df, model)
    df = df[model.columns()]

    if validate_rows:
        for i, record in enumerate(df.to_dict("records")):
            try:
                model.model_validate(record)
            except ValidationError as exc:
                raise SchemaMismatch(f"{model.artifact_name}: row {i} invalid: {exc}") from exc

    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            META_ARTIFACT: model.artifact_name.encode(),
            META_VERSION: model.schema_version.encode(),
        }
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def read_artifact(
    path: Path,
    model: type[ArtifactModel],
    *,
    validate_rows: bool = False,
) -> pd.DataFrame:
    """Read an artifact, refusing anything whose name or version does not match."""
    table = pq.read_table(Path(path))
    meta = table.schema.metadata or {}

    name = meta.get(META_ARTIFACT, b"").decode()
    version = meta.get(META_VERSION, b"").decode()

    if name != model.artifact_name:
        raise SchemaMismatch(
            f"artifact name mismatch: file holds {name!r}, expected {model.artifact_name!r}"
        )
    if version != model.schema_version:
        raise SchemaMismatch(
            f"{name}: schema version mismatch: file is {version!r}, "
            f"code expects {model.schema_version!r}"
        )

    df = table.to_pandas()
    _check_columns(df, model)
    df = df[model.columns()]

    if validate_rows:
        for i, record in enumerate(df.to_dict("records")):
            try:
                model.model_validate(record)
            except ValidationError as exc:
                raise SchemaMismatch(f"{name}: row {i} invalid: {exc}") from exc

    return df
