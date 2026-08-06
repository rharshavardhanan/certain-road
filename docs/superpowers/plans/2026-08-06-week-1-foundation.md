# Week 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `certain-road` repo skeleton with an enforced stage-isolation contract and versioned artifact IO, convert the RDD2022 India subset into a four-way split, and get YOLOv8n training running unattended on MPS.

**Architecture:** One `uv` project. Stages (`ingest`, `detect`, `assess`, `calibrate`, `rsl`, `optimize`, `report`) communicate only through typed Parquet artifacts on disk and never import each other — enforced by `import-linter` in CI. Only `artifacts/` (schemas) and `core/` (config, run context) are shared. This is what lets weeks 2–4 build `assess` and `calibrate` against synthetic fixtures while training runs unattended.

**Tech Stack:** Python 3.12, `uv`, pydantic v2, pandas + pyarrow, typer, ultralytics YOLOv8n, PyTorch MPS backend, pytest, ruff, import-linter.

## Global Constraints

- **Python 3.12 exactly.** System Python is 3.14; ultralytics 8.4.115 declares support only through 3.13 (D032).
- **Torch device is MPS**, never CUDA: `torch.device("mps" if torch.backends.mps.is_available() else "cpu")`. `PYTORCH_ENABLE_MPS_FALLBACK=1` is already set globally on this machine.
- **`uv` only** — `uv add`, `uv run`, `uv sync`. Never `pip`, never the shared `~/PROJECTS/venv`.
- **Stages never import each other.** Only `certain_road.artifacts` and `certain_road.core` are importable across stages. A violation must fail CI.
- **No magic numbers in code.** Every tunable lives in `configs/`.
- **Terminology is load-bearing** (D011, D015, D028) and applies to code, schemas, comments and docs:
  - `vision_density`, never bare `density`
  - `apparent_severity`, never bare `severity`
  - `pci_ref` / "reference PCI", never `pci_true`
  - "vision-estimated PCI", never bare "PCI"
  - "evaluation segment", never "road segment", for RDD2022 partitions
- **Splits:** `train` 60% / `val` 10% / `calib` 20% / `test` 10%, carved **only** from the 7,706 annotated India training images. The published RDD2022 test split is unlabelled and must not be used (D032).
- **`calib` is sacred.** It must never be seen by detector training or model selection — conformal validity depends on it (D009).
- **Classes:** exactly four — `D00`, `D10`, `D20`, `D40` → ids `0,1,2,3`. Any other class string in the XMLs is dropped and counted.
- **`docs/DECISIONS.md` must be updated in the same commit** as any change that alters a design decision.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Verified facts (do not re-derive)

| Fact | Value |
|---|---|
| RDD2022 download | Single zip, **13.26 GB**, no per-country option |
| Download URL | `https://ndownloader.figshare.com/files/38030910` |
| Figshare API (for size check) | `https://api.figshare.com/v2/articles/21431547` |
| Licence | CC BY 4.0, DOI `10.6084/m9.figshare.21431547.v1` |
| Zip internal layout | `RDD2022/<Country>/train/{images,annotations/xmls}` |
| India images / annotated | 9,665 / **7,706** |
| Resulting splits | train 4,624 · val 771 · calib 1,541 · test 770 |
| Water-pothole zip | `Potholes.zip`, 290 MB, ships `IMG/`, `XML/` (VOC) **and** `TXT/` (YOLO) |
| Free disk | 798 GB — ample |

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | deps, ruff, pytest config, console script |
| `.importlinter` | the stage-isolation contract |
| `.github/workflows/ci.yml` | ruff + pytest + lint-imports |
| `src/certain_road/cli.py` | typer entrypoint, one sub-app per stage |
| `src/certain_road/artifacts/schema.py` | `ArtifactModel` base + one model per artifact |
| `src/certain_road/artifacts/io.py` | `write_artifact` / `read_artifact` + version enforcement |
| `src/certain_road/core/paths.py` | repo-root and data-directory resolution |
| `src/certain_road/detect/dataset/fetch.py` | download, size-verify, selective extract, checksum |
| `src/certain_road/detect/dataset/voc.py` | VOC XML parsing + class census |
| `src/certain_road/detect/dataset/convert.py` | VOC → YOLO label conversion |
| `src/certain_road/detect/dataset/split.py` | deterministic four-way split + manifest |
| `src/certain_road/detect/train.py` | ultralytics training entrypoint |
| `tests/fixtures/synthetic.py` | synthetic artifact generators (unblocks weeks 2–4) |

---

### Task 1: Project skeleton with enforced stage isolation

The architecture's central promise — stages never import each other — must be mechanically enforced from the first commit, or it will not hold.

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.importlinter`, `.github/workflows/ci.yml`
- Create: `src/certain_road/{__init__,cli}.py`
- Create: `src/certain_road/{artifacts,core,ingest,detect,assess,calibrate,rsl,optimize,report}/__init__.py`
- Test: `tests/test_cli.py`, `tests/test_architecture.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: console script `certain-road`; typer app object `certain_road.cli.app`; the nine package namespaces above

- [ ] **Step 1: Initialise the uv project**

```bash
cd /Users/harshav/PROJECTS/certain-road
uv init --package --python 3.12 --name certain-road
uv add pydantic pandas pyarrow typer pyyaml tqdm requests
uv add ultralytics torch torchvision
uv add --dev pytest ruff import-linter
```

- [ ] **Step 2: Verify the interpreter and MPS**

```bash
uv run python -c "
import sys, torch
print('python', sys.version.split()[0])
print('torch', torch.__version__)
print('mps available', torch.backends.mps.is_available())
assert sys.version_info[:2] == (3, 12), 'must be Python 3.12'
assert torch.backends.mps.is_available(), 'MPS unavailable'
print('OK')
"
```

Expected: `python 3.12.x`, `mps available True`, `OK`.

- [ ] **Step 3: Create the package namespaces**

```bash
cd /Users/harshav/PROJECTS/certain-road/src/certain_road
for p in artifacts core ingest detect assess calibrate rsl optimize report; do
  mkdir -p "$p" && printf '"""%s stage."""\n' "$p" > "$p/__init__.py"
done
mkdir -p detect/dataset && printf '"""RDD2022 dataset preparation."""\n' > detect/dataset/__init__.py
```

- [ ] **Step 4: Write the failing CLI test**

`tests/__init__.py` must exist from the start. Without it, pytest treats test
files as top-level modules and inserts `tests/` onto `sys.path` instead of the
repo root — which breaks `from tests.fixtures.synthetic import ...` in Task 3.
Adding it later also leaves stale pytest caches behind.

```bash
cd /Users/harshav/PROJECTS/certain-road
mkdir -p tests && touch tests/__init__.py
```

Create `tests/test_cli.py`:

```python
from typer.testing import CliRunner

from certain_road.cli import app

runner = CliRunner()

STAGES = ["ingest", "detect", "assess", "calibrate", "rsl", "optimize", "report"]


def test_help_lists_every_stage():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for stage in STAGES:
        assert stage in result.stdout, f"{stage} missing from --help"
```

- [ ] **Step 5: Run it and watch it fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'certain_road.cli'`

- [ ] **Step 6: Implement the CLI**

Create `src/certain_road/cli.py`:

```python
"""Single entrypoint. One sub-app per pipeline stage.

Stages are wired here and nowhere else; this module is the only place allowed
to know about more than one stage at a time.
"""

import typer

app = typer.Typer(
    name="certain-road",
    help="Road segment repair prioritisation under budget constraint.",
    no_args_is_help=True,
    add_completion=False,
)

STAGE_HELP = {
    "ingest": "Video/camera + track -> frames.parquet",
    "detect": "YOLOv8n training and inference",
    "assess": "Detections -> vision-estimated PCI per segment",
    "calibrate": "Fit or apply conformal intervals on segment PCI",
    "rsl": "PCI interval -> remaining service life interval",
    "optimize": "Budget-constrained repair selection",
    "report": "Self-contained offline HTML report",
}

# Keep references so later tasks attach commands to the right stage rather than
# inventing parallel top-level apps.
STAGE_APPS: dict[str, typer.Typer] = {}
for _name, _help in STAGE_HELP.items():
    _sub = typer.Typer(name=_name, help=_help, no_args_is_help=True)
    STAGE_APPS[_name] = _sub
    app.add_typer(_sub, name=_name)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Register the console script**

In `pyproject.toml`, add (or confirm) under `[project.scripts]`:

```toml
[project.scripts]
certain-road = "certain_road.cli:main"
```

Then `uv sync`.

- [ ] **Step 8: Run the CLI test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v && uv run certain-road --help`
Expected: PASS, and the help text lists all seven stages.

- [ ] **Step 9: Write the import-linter contract**

Create `.importlinter`:

```ini
[importlinter]
root_package = certain_road

[importlinter:contract:stages-are-independent]
name = Stages must never import each other
type = independence
modules =
    certain_road.ingest
    certain_road.detect
    certain_road.assess
    certain_road.calibrate
    certain_road.rsl
    certain_road.optimize
    certain_road.report

[importlinter:contract:contract-layer-is-a-leaf]
name = artifacts and core must not import stages
type = forbidden
source_modules =
    certain_road.artifacts
    certain_road.core
forbidden_modules =
    certain_road.ingest
    certain_road.detect
    certain_road.assess
    certain_road.calibrate
    certain_road.rsl
    certain_road.optimize
    certain_road.report
```

`certain_road.cli` is deliberately outside both contracts — wiring stages together is its job.

- [ ] **Step 10: Prove the contract actually catches a violation**

This step exists because an enforcement mechanism nobody has seen fire is an assumption, not a guarantee.

```bash
cd /Users/harshav/PROJECTS/certain-road
echo "from certain_road.assess import *  # deliberate violation" >> src/certain_road/rsl/__init__.py
uv run lint-imports; echo "exit=$?"
```

Expected: non-zero exit, naming the `stages-are-independent` contract.

Now revert it:

```bash
cd /Users/harshav/PROJECTS/certain-road
printf '"""rsl stage."""\n' > src/certain_road/rsl/__init__.py
uv run lint-imports; echo "exit=$?"
```

Expected: `exit=0`, contracts kept.

- [ ] **Step 11: Add the architecture test**

Create `tests/test_architecture.py`:

```python
"""The stage-isolation contract is part of the test suite, not just CI."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_import_contracts_hold():
    # cwd must be the repo root: import-linter reads .importlinter relative to it.
    # Resolved from __file__ rather than core.paths, which does not exist yet.
    result = subprocess.run(
        ["lint-imports"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"import-linter failed:\n{result.stdout}\n{result.stderr}"
```

- [ ] **Step 12: Configure ruff and pytest**

Append to `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 13: Add CI**

Create `.github/workflows/ci.yml`:

```yaml
name: ci
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --all-extras --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run lint-imports
      - run: uv run pytest
```

- [ ] **Step 14: Run everything green**

Run: `uv run ruff check . && uv run ruff format . && uv run lint-imports && uv run pytest -v`
Expected: all pass.

- [ ] **Step 15: Commit**

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
feat: project skeleton with enforced stage isolation

uv project on Python 3.12, typer CLI with one sub-app per stage,
import-linter contracts preventing cross-stage imports, ruff + pytest,
CI running all four checks.

The independence contract was verified by deliberately introducing a
cross-stage import and confirming lint-imports fails.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Versioned artifact schemas and IO

The contract every other stage depends on. Version enforcement on read is what stops a week-6 schema change from silently producing wrong numbers against week-3 data.

**Files:**
- Create: `src/certain_road/artifacts/schema.py`, `src/certain_road/artifacts/io.py`
- Create: `src/certain_road/core/paths.py`
- Test: `tests/test_artifacts_io.py`

**Interfaces:**
- Consumes: package namespaces from Task 1
- Produces:
  - `ArtifactModel` base class with `artifact_name: ClassVar[str]`, `schema_version: ClassVar[str]`, `columns() -> list[str]`
  - `FrameRow`, `DetectionRow` models
  - `write_artifact(df: pd.DataFrame, path: Path, model: type[ArtifactModel], *, validate_rows: bool = True) -> None`
  - `read_artifact(path: Path, model: type[ArtifactModel], *, validate_rows: bool = False) -> pd.DataFrame`
  - `SchemaMismatch(Exception)`
  - `repo_root() -> Path`, `data_dir() -> Path`

- [ ] **Step 1: Write the failing IO test**

Create `tests/test_artifacts_io.py`:

```python
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
    df = _valid_df()
    df.loc[0, "score"] = "not a number"
    with pytest.raises(SchemaMismatch):
        write_artifact(df, tmp_path / "d.parquet", DetectionRow)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_artifacts_io.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'certain_road.artifacts.io'`

- [ ] **Step 3: Implement the schemas**

Create `src/certain_road/artifacts/schema.py`:

```python
"""Artifact row schemas. Definitions only — this module contains no logic.

Every artifact written to disk is described here by exactly one model. Bumping
`schema_version` makes older files unreadable by design: a silent read of a
stale-shaped artifact is the failure mode this guards against.
"""

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
```

- [ ] **Step 4: Implement the IO layer**

Create `src/certain_road/artifacts/io.py`:

```python
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
```

- [ ] **Step 5: Implement path resolution**

Create `src/certain_road/core/paths.py`:

```python
"""Repository-relative path resolution.

Every path in the project derives from here, so nothing depends on the
current working directory.
"""

from pathlib import Path


def repo_root() -> Path:
    """Walk upward from this file until the directory holding pyproject.toml."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("repository root not found: no pyproject.toml in any parent")


def data_dir() -> Path:
    return repo_root() / "data"


def raw_dir() -> Path:
    return data_dir() / "raw"


def processed_dir() -> Path:
    return data_dir() / "processed"


def models_dir() -> Path:
    return repo_root() / "models"
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_artifacts_io.py -v`
Expected: all six PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
feat: versioned artifact schemas and IO

pydantic row models for frames and detections, parquet IO that stamps
artifact name and schema version into file metadata and refuses to read
anything that does not match.

Version enforcement on read is what prevents a later schema change from
silently producing wrong numbers against older artifacts.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Synthetic fixtures

This task is what unblocks weeks 2–4. With these generators, `assess` and `calibrate` are fully buildable and testable while the detector is still training and while hardware does not exist.

**Files:**
- Create: `tests/fixtures/__init__.py`, `tests/fixtures/synthetic.py`
- Create: `scripts/make_fixtures.py`
- Test: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: `write_artifact`, `FrameRow`, `DetectionRow` from Task 2
- Produces:
  - `synthetic_frames(n_segments: int, frames_per_segment: int, *, seed: int = 0) -> pd.DataFrame`
  - `synthetic_detections(frames: pd.DataFrame, *, seed: int = 0, damage_rate: float = 2.0) -> pd.DataFrame`

- [ ] **Step 1: Write the failing fixtures test**

Create `tests/test_fixtures.py`:

```python
import pandas as pd

from certain_road.artifacts.io import read_artifact, write_artifact
from certain_road.artifacts.schema import DetectionRow, FrameRow
from tests.fixtures.synthetic import synthetic_detections, synthetic_frames

CLASSES = {"D00", "D10", "D20", "D40"}


def test_frames_have_expected_shape():
    frames = synthetic_frames(n_segments=4, frames_per_segment=15, seed=1)
    assert len(frames) == 60
    assert frames["segment_id"].nunique() == 4
    assert list(frames.columns) == FrameRow.columns()


def test_generation_is_deterministic():
    a = synthetic_frames(n_segments=3, frames_per_segment=5, seed=7)
    b = synthetic_frames(n_segments=3, frames_per_segment=5, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_different_seeds_differ():
    a = synthetic_detections(synthetic_frames(3, 5, seed=1), seed=1)
    b = synthetic_detections(synthetic_frames(3, 5, seed=1), seed=2)
    assert not a.equals(b)


def test_detections_reference_real_frames_and_valid_classes():
    frames = synthetic_frames(n_segments=3, frames_per_segment=10, seed=2)
    dets = synthetic_detections(frames, seed=2)
    assert set(dets["frame_id"]) <= set(frames["frame_id"])
    assert set(dets["class_name"]) <= CLASSES
    assert (dets["x2"] > dets["x1"]).all()
    assert (dets["y2"] > dets["y1"]).all()
    assert (dets["score"].between(0, 1)).all()


def test_fixtures_satisfy_the_artifact_contract(tmp_path):
    frames = synthetic_frames(n_segments=2, frames_per_segment=5, seed=3)
    dets = synthetic_detections(frames, seed=3)

    write_artifact(frames, tmp_path / "frames.parquet", FrameRow)
    write_artifact(dets, tmp_path / "detections.parquet", DetectionRow)

    assert len(read_artifact(tmp_path / "frames.parquet", FrameRow, validate_rows=True)) == 10
    assert len(
        read_artifact(tmp_path / "detections.parquet", DetectionRow, validate_rows=True)
    ) == len(dets)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_fixtures.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.fixtures'`

- [ ] **Step 3: Implement the generators**

Create `tests/fixtures/__init__.py` (empty; `tests/__init__.py` already exists from
Task 1 Step 4, which is what makes `tests.fixtures` importable), then
`tests/fixtures/synthetic.py`:

```python
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

CLASS_NAMES = ["D00", "D10", "D20", "D40"]
IMG_W, IMG_H = 600, 600
SAMPLE_SPACING_M = 6.0


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
                    "speed_mps": float(rng.uniform(6.0, 9.0)),
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
    """Poisson-distributed detections per frame, with per-segment severity drift.

    Segments differ systematically in damage level so that downstream PCI values
    span a usable range rather than clustering.
    """
    rng = np.random.default_rng(seed)
    segments = sorted(frames["segment_id"].unique())
    severity = {s: rng.uniform(0.3, 2.0) for s in segments}

    rows = []
    for frame in frames.itertuples():
        n = rng.poisson(damage_rate * severity[frame.segment_id])
        for k in range(int(n)):
            w = float(rng.uniform(20, 140))
            h = float(rng.uniform(20, 140))
            x1 = float(rng.uniform(0, IMG_W - w))
            y1 = float(rng.uniform(IMG_H * 0.4, IMG_H - h))  # lower half: road surface
            rows.append(
                {
                    "frame_id": frame.frame_id,
                    "det_id": f"{frame.frame_id}-{k}",
                    "class_name": str(rng.choice(CLASS_NAMES)),
                    "score": float(rng.uniform(0.25, 0.98)),
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_fixtures.py -v`
Expected: all five PASS.

- [ ] **Step 5: Add the fixture-writing script**

Create `scripts/make_fixtures.py`:

```python
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
```

`n_segments=102` deliberately matches the real evaluation-segment count from D032, so downstream work is sized against reality rather than a round number.

- [ ] **Step 6: Run it**

Run: `uv run python scripts/make_fixtures.py`
Expected: `wrote 1530 frames and ~3000 detections to .../runs/synthetic/artifacts`

- [ ] **Step 7: Commit**

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
feat: synthetic artifact fixtures

Deterministic generators for frames.parquet and detections.parquet, with
per-segment severity drift so downstream PCI spans a usable range.

These unblock weeks 2-4: assess and calibrate can now be built and tested
with no trained model, no GPU and no hardware. Default fixture size is 102
segments, matching the real evaluation-segment count from D032.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Acquire the RDD2022 India subset

13.26 GB over the network with no per-country option. Resumable, size-verified, and extracting only what is needed.

**Files:**
- Create: `src/certain_road/detect/dataset/fetch.py`
- Modify: `src/certain_road/cli.py` (add `dataset` sub-app)
- Test: `tests/test_dataset_fetch.py`

**Interfaces:**
- Consumes: `raw_dir()` from Task 2
- Produces:
  - `expected_zip_size() -> int`
  - `download_rdd2022(dest: Path) -> Path`
  - `extract_country(zip_path: Path, country: str, dest: Path) -> Path`
  - `sha256_of(path: Path) -> str`
  - CLI: `certain-road dataset fetch`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dataset_fetch.py`:

```python
import hashlib
import zipfile

import pytest

from certain_road.detect.dataset.fetch import extract_country, sha256_of


def test_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"certain-road")
    assert sha256_of(f) == hashlib.sha256(b"certain-road").hexdigest()


def _fake_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("RDD2022/India/train/images/India_000004.jpg", b"jpeg")
        z.writestr("RDD2022/India/train/annotations/xmls/India_000004.xml", b"<annotation/>")
        z.writestr("RDD2022/Japan/train/images/Japan_000001.jpg", b"jpeg")


def test_extract_country_takes_only_that_country(tmp_path):
    zip_path = tmp_path / "rdd.zip"
    _fake_zip(zip_path)

    out = extract_country(zip_path, "India", tmp_path / "raw")

    assert (out / "train" / "images" / "India_000004.jpg").exists()
    assert (out / "train" / "annotations" / "xmls" / "India_000004.xml").exists()
    assert not (tmp_path / "raw" / "RDD2022" / "Japan").exists()


def test_extract_country_rejects_unknown_country(tmp_path):
    zip_path = tmp_path / "rdd.zip"
    _fake_zip(zip_path)
    with pytest.raises(ValueError, match="Atlantis"):
        extract_country(zip_path, "Atlantis", tmp_path / "raw")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_dataset_fetch.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement fetch**

Create `src/certain_road/detect/dataset/fetch.py`:

```python
"""Acquire RDD2022.

RDD2022 ships as a single 13.26 GB zip with no per-country download (D032), so
we fetch the whole archive once and extract only the country we need.
"""

import hashlib
import subprocess
import zipfile
from pathlib import Path

import requests

FIGSHARE_API = "https://api.figshare.com/v2/articles/21431547"
ZIP_NAME = "RDD2022_released_through_CRDDC2022.zip"
ZIP_URL = "https://ndownloader.figshare.com/files/38030910"
COUNTRIES = {
    "China_Drone",
    "China_MotorBike",
    "Czech",
    "India",
    "Japan",
    "Norway",
    "United_States",
}


def expected_zip_size() -> int:
    """Authoritative size from the Figshare API, so we never trust a partial file."""
    response = requests.get(FIGSHARE_API, timeout=30)
    response.raise_for_status()
    for entry in response.json()["files"]:
        if entry["name"] == ZIP_NAME:
            return int(entry["size"])
    raise RuntimeError(f"{ZIP_NAME} not present in Figshare article listing")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_rdd2022(dest: Path) -> Path:
    """Download the archive, resuming if a partial file is present."""
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / ZIP_NAME
    expected = expected_zip_size()

    if zip_path.exists() and zip_path.stat().st_size == expected:
        print(f"already complete: {zip_path}")
        return zip_path

    print(f"downloading {expected / 1e9:.2f} GB -> {zip_path}")
    subprocess.run(
        ["curl", "-L", "-C", "-", "--fail", "-o", str(zip_path), ZIP_URL],
        check=True,
    )

    actual = zip_path.stat().st_size
    if actual != expected:
        raise RuntimeError(f"size mismatch: got {actual}, expected {expected}")

    return zip_path


def extract_country(zip_path: Path, country: str, dest: Path) -> Path:
    """Extract only `RDD2022/<country>/` from the archive."""
    if country not in COUNTRIES:
        raise ValueError(f"unknown country {country!r}; expected one of {sorted(COUNTRIES)}")

    prefix = f"RDD2022/{country}/"
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.startswith(prefix)]
        if not members:
            raise ValueError(f"no entries under {prefix!r} in {zip_path}")
        archive.extractall(dest, members=members)

    return dest / "RDD2022" / country
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_dataset_fetch.py -v`
Expected: all three PASS.

- [ ] **Step 5: Wire the `dataset` sub-app**

In `src/certain_road/cli.py`, replace the auto-generated `detect` sub-app registration with an explicit one and add `dataset`. Add after the `for` loop:

```python
dataset_app = typer.Typer(
    name="dataset", help="RDD2022 acquisition and preparation.", no_args_is_help=True
)
app.add_typer(dataset_app, name="dataset")


@dataset_app.command("fetch")
def dataset_fetch(country: str = "India") -> None:
    """Download RDD2022 and extract one country."""
    from certain_road.core.paths import raw_dir
    from certain_road.detect.dataset.fetch import download_rdd2022, extract_country, sha256_of

    zip_path = download_rdd2022(raw_dir())
    checksum = sha256_of(zip_path)

    checks = raw_dir() / "CHECKSUMS.txt"
    checks.write_text(f"{checksum}  {zip_path.name}\n")
    print(f"sha256 {checksum}")
    print(
        "(recorded for our own reproducibility; Figshare publishes no checksum to verify against)"
    )

    out = extract_country(zip_path, country, raw_dir())
    images = len(list((out / "train" / "images").glob("*.jpg")))
    xmls = len(list((out / "train" / "annotations" / "xmls").glob("*.xml")))
    print(f"{country}: {images} train images, {xmls} annotations -> {out}")
```

- [ ] **Step 6: Inspect the archive layout before committing to a 13 GB download**

Confirm the published listing matches what the code assumes:

```bash
curl -sL "https://api.figshare.com/v2/articles/21431547" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for f in d['files']:
    print(f\"{f['size']:>13,} bytes  {f['name']}\")
"
```

Expected: `RDD2022_released_through_CRDDC2022.zip` at ~13.26 GB.

- [ ] **Step 7: Run the fetch**

This takes 20–60 minutes depending on connection. It is resumable — re-running after an interruption continues rather than restarting.

```bash
cd /Users/harshav/PROJECTS/certain-road
uv run certain-road dataset fetch --country India
```

Expected final lines: `India: 9665 train images, 7706 annotations -> .../data/raw/RDD2022/India`

If the image count is 7,706 rather than 9,665, the `train/images` directory holds only annotated images and the split arithmetic is unaffected — record whichever you observe in the dataset card in Task 6.

- [ ] **Step 8: Verify on disk**

```bash
cd /Users/harshav/PROJECTS/certain-road
ls data/raw/RDD2022/India/train/images | wc -l
ls data/raw/RDD2022/India/train/annotations/xmls | wc -l
du -sh data/raw/RDD2022/India data/raw/*.zip
cat data/raw/CHECKSUMS.txt
```

- [ ] **Step 9: Commit**

`data/` is gitignored, so only code is committed.

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
feat: RDD2022 acquisition with selective country extraction

Resumable download of the 13.26 GB archive with size verified against the
Figshare API, sha256 recorded, and only RDD2022/India/ extracted.

There is no per-country download option (D032), so the full archive must be
fetched regardless of the India-only scope.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Class census and VOC → YOLO conversion

The census runs **before** conversion because RDD2022 XMLs are known to contain class strings beyond the four official ones, and silently dropping them without counting would leave an unexplained gap between annotation and label counts.

**Files:**
- Create: `src/certain_road/detect/dataset/voc.py`, `src/certain_road/detect/dataset/convert.py`
- Modify: `src/certain_road/cli.py`
- Test: `tests/test_dataset_convert.py`

**Interfaces:**
- Consumes: `raw_dir()`, `processed_dir()`
- Produces:
  - `parse_voc(xml_path: Path) -> VocAnnotation` with `.width, .height, .objects: list[VocObject]`; `VocObject` has `.name, .xmin, .ymin, .xmax, .ymax`
  - `class_census(xml_dir: Path) -> collections.Counter`
  - `CLASS_TO_ID: dict[str, int]` = `{"D00": 0, "D10": 1, "D20": 2, "D40": 3}`
  - `to_yolo_lines(ann: VocAnnotation) -> tuple[list[str], collections.Counter]` returning lines and a counter of rejections
  - CLI: `certain-road dataset census`, `certain-road dataset convert`

- [ ] **Step 1: Write the failing conversion test**

Create `tests/test_dataset_convert.py`:

```python
import pytest

from certain_road.detect.dataset.convert import CLASS_TO_ID, to_yolo_lines
from certain_road.detect.dataset.voc import class_census, parse_voc

XML_TEMPLATE = """<annotation>
  <size><width>{w}</width><height>{h}</height><depth>3</depth></size>
  {objects}
</annotation>"""

OBJ = """<object><name>{name}</name>
  <bndbox><xmin>{xmin}</xmin><ymin>{ymin}</ymin><xmax>{xmax}</xmax><ymax>{ymax}</ymax></bndbox>
</object>"""


def write_xml(path, objects, w=600, h=600):
    body = "\n".join(OBJ.format(**o) for o in objects)
    path.write_text(XML_TEMPLATE.format(w=w, h=h, objects=body))
    return path


def test_parses_size_and_objects(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=10, ymin=20, xmax=110, ymax=120)])
    ann = parse_voc(p)
    assert (ann.width, ann.height) == (600, 600)
    assert len(ann.objects) == 1
    assert ann.objects[0].name == "D40"


def test_converts_to_normalised_centre_format(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D00", xmin=100, ymin=200, xmax=200, ymax=400)])
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert rejected.total() == 0
    cls, cx, cy, w, h = lines[0].split()
    assert int(cls) == CLASS_TO_ID["D00"]
    assert float(cx) == pytest.approx(150 / 600)
    assert float(cy) == pytest.approx(300 / 600)
    assert float(w) == pytest.approx(100 / 600)
    assert float(h) == pytest.approx(200 / 600)


def test_unknown_class_is_dropped_and_counted(tmp_path):
    p = write_xml(
        tmp_path / "a.xml",
        [
            dict(name="D40", xmin=10, ymin=10, xmax=50, ymax=50),
            dict(name="D43", xmin=10, ymin=10, xmax=50, ymax=50),
        ],
    )
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert len(lines) == 1
    assert rejected["unknown_class:D43"] == 1


def test_degenerate_box_is_dropped_and_counted(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=50, ymin=50, xmax=50, ymax=90)])
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert lines == []
    assert rejected["degenerate_box"] == 1


def test_inverted_box_is_normalised_not_dropped(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=200, ymin=300, xmax=100, ymax=150)])
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert len(lines) == 1
    assert rejected.total() == 0


def test_out_of_bounds_box_is_clamped(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=-30, ymin=10, xmax=900, ymax=200)])
    lines, _ = to_yolo_lines(parse_voc(p))
    _, cx, cy, w, h = (float(v) for v in lines[0].split())
    assert 0.0 <= cx <= 1.0 and 0.0 <= w <= 1.0


def test_census_counts_every_class_string(tmp_path):
    d = tmp_path / "xmls"
    d.mkdir()
    write_xml(d / "a.xml", [dict(name="D00", xmin=1, ymin=1, xmax=9, ymax=9)])
    write_xml(
        d / "b.xml",
        [
            dict(name="D00", xmin=1, ymin=1, xmax=9, ymax=9),
            dict(name="D43", xmin=1, ymin=1, xmax=9, ymax=9),
        ],
    )
    counts = class_census(d)
    assert counts["D00"] == 2
    assert counts["D43"] == 1
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_dataset_convert.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement VOC parsing**

Create `src/certain_road/detect/dataset/voc.py`:

```python
"""PASCAL VOC annotation parsing for RDD2022."""

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VocObject:
    name: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float


@dataclass(frozen=True)
class VocAnnotation:
    path: Path
    width: int
    height: int
    objects: list[VocObject]


def _text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    if found is None or found.text is None:
        raise ValueError(f"missing <{tag}>")
    return found.text.strip()


def parse_voc(xml_path: Path) -> VocAnnotation:
    root = ET.parse(xml_path).getroot()

    size = root.find("size")
    if size is None:
        raise ValueError(f"{xml_path}: missing <size>")
    width, height = int(_text(size, "width")), int(_text(size, "height"))

    objects = []
    for obj in root.findall("object"):
        box = obj.find("bndbox")
        if box is None:
            continue
        objects.append(
            VocObject(
                name=_text(obj, "name"),
                xmin=float(_text(box, "xmin")),
                ymin=float(_text(box, "ymin")),
                xmax=float(_text(box, "xmax")),
                ymax=float(_text(box, "ymax")),
            )
        )

    return VocAnnotation(path=xml_path, width=width, height=height, objects=objects)


def class_census(xml_dir: Path) -> Counter:
    """Count every class string present, including ones we will later drop."""
    counts: Counter = Counter()
    for xml_path in sorted(Path(xml_dir).glob("*.xml")):
        try:
            annotation = parse_voc(xml_path)
        except (ET.ParseError, ValueError) as exc:
            counts[f"PARSE_ERROR:{type(exc).__name__}"] += 1
            continue
        for obj in annotation.objects:
            counts[obj.name] += 1
    return counts
```

- [ ] **Step 4: Implement conversion**

Create `src/certain_road/detect/dataset/convert.py`:

```python
"""VOC -> YOLO label conversion.

Only the four CRDDC2022 classes survive. Everything dropped is counted, so the
gap between annotation count and label count is always explainable.
"""

from collections import Counter
from pathlib import Path

from certain_road.detect.dataset.voc import VocAnnotation, parse_voc

CLASS_TO_ID = {"D00": 0, "D10": 1, "D20": 2, "D40": 3}
ID_TO_CLASS = {v: k for k, v in CLASS_TO_ID.items()}


def to_yolo_lines(ann: VocAnnotation) -> tuple[list[str], Counter]:
    """Return YOLO label lines plus a counter of everything rejected and why."""
    rejected: Counter = Counter()
    lines: list[str] = []

    if ann.width <= 0 or ann.height <= 0:
        rejected["bad_image_size"] += len(ann.objects)
        return lines, rejected

    for obj in ann.objects:
        if obj.name not in CLASS_TO_ID:
            rejected[f"unknown_class:{obj.name}"] += 1
            continue

        # Some annotations have the corners transposed; that is a recoverable
        # ordering problem, not a bad box.
        xmin, xmax = sorted((obj.xmin, obj.xmax))
        ymin, ymax = sorted((obj.ymin, obj.ymax))

        xmin = max(0.0, min(xmin, ann.width))
        xmax = max(0.0, min(xmax, ann.width))
        ymin = max(0.0, min(ymin, ann.height))
        ymax = max(0.0, min(ymax, ann.height))

        if xmax - xmin <= 0 or ymax - ymin <= 0:
            rejected["degenerate_box"] += 1
            continue

        cx = (xmin + xmax) / 2 / ann.width
        cy = (ymin + ymax) / 2 / ann.height
        w = (xmax - xmin) / ann.width
        h = (ymax - ymin) / ann.height

        lines.append(f"{CLASS_TO_ID[obj.name]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

    return lines, rejected


def convert_directory(xml_dir: Path, label_dir: Path) -> tuple[int, int, Counter]:
    """Convert every XML in `xml_dir`. Returns (files, boxes, rejections)."""
    label_dir.mkdir(parents=True, exist_ok=True)
    rejected: Counter = Counter()
    files = boxes = 0

    for xml_path in sorted(Path(xml_dir).glob("*.xml")):
        annotation = parse_voc(xml_path)
        lines, dropped = to_yolo_lines(annotation)
        rejected.update(dropped)
        # An empty label file is meaningful: it marks a genuine negative frame.
        (label_dir / f"{xml_path.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        files += 1
        boxes += len(lines)

    return files, boxes, rejected
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_dataset_convert.py -v`
Expected: all seven PASS.

- [ ] **Step 6: Add census and convert commands**

Append to the `dataset_app` section of `src/certain_road/cli.py`:

```python
@dataset_app.command("census")
def dataset_census(country: str = "India") -> None:
    """Count every class string in the annotations before converting anything."""
    from certain_road.core.paths import raw_dir
    from certain_road.detect.dataset.convert import CLASS_TO_ID
    from certain_road.detect.dataset.voc import class_census

    xml_dir = raw_dir() / "RDD2022" / country / "train" / "annotations" / "xmls"
    counts = class_census(xml_dir)

    print(f"{'class':<24} {'count':>8}   status")
    for name, count in counts.most_common():
        status = "KEEP" if name in CLASS_TO_ID else "DROP"
        print(f"{name:<24} {count:>8}   {status}")

    kept = sum(c for n, c in counts.items() if n in CLASS_TO_ID)
    print(f"\ntotal boxes {counts.total()}, keeping {kept}, dropping {counts.total() - kept}")


@dataset_app.command("convert")
def dataset_convert(country: str = "India") -> None:
    """Convert VOC XML annotations to YOLO label files."""
    from certain_road.core.paths import processed_dir, raw_dir
    from certain_road.detect.dataset.convert import convert_directory

    xml_dir = raw_dir() / "RDD2022" / country / "train" / "annotations" / "xmls"
    label_dir = processed_dir() / country.lower() / "labels_all"

    files, boxes, rejected = convert_directory(xml_dir, label_dir)
    print(f"converted {files} files, {boxes} boxes -> {label_dir}")
    if rejected:
        print("rejected:")
        for reason, count in rejected.most_common():
            print(f"  {reason:<30} {count}")
```

- [ ] **Step 7: Run the census on real data**

```bash
cd /Users/harshav/PROJECTS/certain-road
uv run certain-road dataset census --country India
```

Record the output — the DROP rows go into the dataset card in Task 6. Any class beyond `D00/D10/D20/D40` appearing in quantity is worth a note in `docs/DECISIONS.md`.

- [ ] **Step 8: Run the conversion**

```bash
cd /Users/harshav/PROJECTS/certain-road
uv run certain-road dataset convert --country India
ls data/processed/india/labels_all | wc -l
```

Expected: ~7,706 label files.

- [ ] **Step 9: Spot-check one conversion by hand**

```bash
cd /Users/harshav/PROJECTS/certain-road
STEM=$(ls data/raw/RDD2022/India/train/annotations/xmls | head -1 | sed 's/.xml//')
echo "--- VOC ---"; cat "data/raw/RDD2022/India/train/annotations/xmls/${STEM}.xml"
echo "--- YOLO ---"; cat "data/processed/india/labels_all/${STEM}.txt"
```

Verify by hand that centre and size correspond to the VOC corners. Automated tests prove the arithmetic; this proves it was applied to the real files.

- [ ] **Step 10: Commit**

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
feat: class census and VOC to YOLO conversion

Census runs before conversion so that every dropped box is counted and the
gap between annotation and label counts is always explainable.

Handles transposed corners (recoverable), out-of-bounds coordinates
(clamped) and degenerate boxes (dropped and counted). Empty label files are
written deliberately: they mark genuine negative frames.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Deterministic four-way split

The `calib` split is load-bearing for every conformal guarantee in the project. Disjointness is asserted, not assumed.

**Files:**
- Create: `src/certain_road/detect/dataset/split.py`
- Create: `configs/dataset/rdd2022_india.yaml` (generated)
- Create: `docs/dataset-card-rdd2022-india.md`
- Modify: `src/certain_road/cli.py`
- Test: `tests/test_dataset_split.py`

**Interfaces:**
- Consumes: `processed_dir()`, label files from Task 5
- Produces:
  - `SPLIT_BOUNDS: dict[str, tuple[float, float]]`
  - `assign_split(stem: str, salt: str = "certain-road-v1") -> str`
  - `build_splits(stems: list[str], salt: str = "certain-road-v1") -> dict[str, list[str]]`
  - `materialise(splits, image_src, label_src, out_root) -> None`
  - CLI: `certain-road dataset split`

- [ ] **Step 1: Write the failing split test**

Create `tests/test_dataset_split.py`:

```python
from certain_road.detect.dataset.split import SPLIT_BOUNDS, assign_split, build_splits

STEMS = [f"India_{i:06d}" for i in range(4000)]


def test_assignment_is_deterministic():
    assert assign_split("India_000004") == assign_split("India_000004")


def test_salt_changes_assignment_distribution():
    a = [assign_split(s, salt="one") for s in STEMS]
    b = [assign_split(s, salt="two") for s in STEMS]
    assert a != b


def test_splits_are_disjoint_and_complete():
    splits = build_splits(STEMS)
    assert set(splits) == set(SPLIT_BOUNDS)

    seen = set()
    for names in splits.values():
        assert not (seen & set(names)), "a stem appears in more than one split"
        seen |= set(names)
    assert seen == set(STEMS)


def test_proportions_are_within_tolerance():
    splits = build_splits(STEMS)
    total = len(STEMS)
    expected = {"train": 0.60, "val": 0.10, "calib": 0.20, "test": 0.10}
    for name, share in expected.items():
        actual = len(splits[name]) / total
        assert abs(actual - share) < 0.02, f"{name}: {actual:.3f} vs {share}"


def test_calib_never_overlaps_train_or_val():
    """Conformal validity depends on this and nothing else enforces it."""
    splits = build_splits(STEMS)
    calib = set(splits["calib"])
    assert not (calib & set(splits["train"]))
    assert not (calib & set(splits["val"]))


def test_adding_files_does_not_move_existing_ones():
    """Hash-based assignment must be stable as the dataset grows."""
    before = build_splits(STEMS[:2000])
    after = build_splits(STEMS)
    for name, names in before.items():
        assert set(names) <= set(after[name])
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_dataset_split.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the split**

Create `src/certain_road/detect/dataset/split.py`:

```python
"""Deterministic four-way split.

Assignment is by salted hash of the filename rather than a seeded shuffle, so
that adding or removing files never reshuffles the existing ones. That
stability matters: `calib` leaking into `train` at any point would silently
void every conformal guarantee in the project (D009).
"""

import hashlib
import json
from pathlib import Path

SALT = "certain-road-v1"

# Cumulative upper bounds over a uniform [0, 1) hash.
SPLIT_BOUNDS: dict[str, tuple[float, float]] = {
    "train": (0.00, 0.60),
    "val": (0.60, 0.70),
    "calib": (0.70, 0.90),
    "test": (0.90, 1.00),
}


def _unit_hash(stem: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{stem}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def assign_split(stem: str, salt: str = SALT) -> str:
    value = _unit_hash(stem, salt)
    for name, (low, high) in SPLIT_BOUNDS.items():
        if low <= value < high:
            return name
    return "test"  # only reachable at exactly 1.0


def build_splits(stems: list[str], salt: str = SALT) -> dict[str, list[str]]:
    splits: dict[str, list[str]] = {name: [] for name in SPLIT_BOUNDS}
    for stem in stems:
        splits[assign_split(stem, salt)].append(stem)
    for names in splits.values():
        names.sort()
    return splits


def materialise(
    splits: dict[str, list[str]],
    image_src: Path,
    label_src: Path,
    out_root: Path,
) -> None:
    """Lay out images/<split>/ and labels/<split>/ for ultralytics.

    Images are symlinked rather than copied: same result, no duplicated GB.
    """
    for split, stems in splits.items():
        img_dir = out_root / "images" / split
        lbl_dir = out_root / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for stem in stems:
            source_image = image_src / f"{stem}.jpg"
            if not source_image.exists():
                continue
            link = img_dir / f"{stem}.jpg"
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(source_image.resolve())

            source_label = label_src / f"{stem}.txt"
            if source_label.exists():
                (lbl_dir / f"{stem}.txt").write_text(source_label.read_text())


def write_manifest(splits: dict[str, list[str]], path: Path, salt: str = SALT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "salt": salt,
                "bounds": {k: list(v) for k, v in SPLIT_BOUNDS.items()},
                "counts": {k: len(v) for k, v in splits.items()},
                "stems": splits,
            },
            indent=2,
        )
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_dataset_split.py -v`
Expected: all six PASS.

- [ ] **Step 5: Add the split command**

Append to the `dataset_app` section of `src/certain_road/cli.py`:

```python
@dataset_app.command("split")
def dataset_split(country: str = "India") -> None:
    """Build the deterministic four-way split and the ultralytics data yaml."""
    import yaml

    from certain_road.core.paths import processed_dir, raw_dir, repo_root
    from certain_road.detect.dataset.convert import ID_TO_CLASS
    from certain_road.detect.dataset.split import build_splits, materialise, write_manifest

    root = processed_dir() / country.lower()
    label_src = root / "labels_all"
    image_src = raw_dir() / "RDD2022" / country / "train" / "images"

    stems = sorted(p.stem for p in label_src.glob("*.txt"))
    if not stems:
        raise SystemExit(f"no labels in {label_src}; run `dataset convert` first")

    splits = build_splits(stems)
    materialise(splits, image_src, label_src, root)
    write_manifest(splits, root / "splits.json")

    for name, names in splits.items():
        print(f"{name:<6} {len(names):>6}")

    data_yaml = repo_root() / "configs" / "dataset" / f"rdd2022_{country.lower()}.yaml"
    data_yaml.parent.mkdir(parents=True, exist_ok=True)
    data_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(root),
                "train": "images/train",
                "val": "images/val",
                "names": {i: ID_TO_CLASS[i] for i in sorted(ID_TO_CLASS)},
            },
            sort_keys=False,
        )
    )
    print(f"\nwrote {data_yaml}")
    print("calib and test are deliberately absent from the yaml: ultralytics must never see them")
```

- [ ] **Step 6: Run the split**

```bash
cd /Users/harshav/PROJECTS/certain-road
uv run certain-road dataset split --country India
```

Expected, approximately: `train 4624 · val 771 · calib 1541 · test 770`.

- [ ] **Step 7: Verify the layout and the calib firewall**

```bash
cd /Users/harshav/PROJECTS/certain-road
for s in train val calib test; do
  printf "%-6s images=%-6s labels=%s\n" "$s" \
    "$(ls data/processed/india/images/$s | wc -l | tr -d ' ')" \
    "$(ls data/processed/india/labels/$s | wc -l | tr -d ' ')"
done
echo "--- data.yaml must not mention calib or test ---"
grep -E "calib|test" configs/dataset/rdd2022_india.yaml && echo "LEAK" || echo "clean"
```

Expected: matching image/label counts per split, and `clean`.

- [ ] **Step 8: Write the dataset card**

Create `docs/dataset-card-rdd2022-india.md`, filling the bracketed values from the census output of Task 5 Step 7 and the split output above:

```markdown
# Dataset card — RDD2022 India subset

**Source:** RDD2022, DOI `10.6084/m9.figshare.21431547.v1`, CC BY 4.0
**Archive:** single 13.26 GB zip; no per-country download exists
**sha256 of archive:** [from data/raw/CHECKSUMS.txt]

## Contents used

| | Count |
|---|---|
| India images shipped | [observed] |
| India annotations (VOC XML) | [observed] |
| Label files after conversion | [observed] |
| Boxes kept | [from census] |
| Boxes dropped | [from census] |

The published RDD2022 **test split is unlabelled and is not used**. All four of
our splits are carved from the annotated training images (D032).

## Class census

| Class | Boxes | Status |
|---|---|---|
| D00 longitudinal crack | [n] | keep |
| D10 transverse crack | [n] | keep |
| D20 alligator crack | [n] | keep |
| D40 pothole | [n] | keep |
| [others observed] | [n] | drop |

## Splits

Assignment is by salted SHA-256 of the filename stem (salt `certain-road-v1`),
not a seeded shuffle, so adding files never reshuffles existing assignments.

| Split | Share | Count | Purpose |
|---|---|---|---|
| train | 60% | [n] | detector weights |
| val | 10% | [n] | early stopping, model selection |
| calib | 20% | [n] | conformal calibration only |
| test | 10% | [n] | final reported numbers |

**`calib` is never exposed to training or model selection.** The generated
`configs/dataset/rdd2022_india.yaml` deliberately references only `train` and
`val`, so ultralytics cannot reach the other two.

## Known limitations

- ~4,624 training images is small, and India is the hardest RDD2022 subset.
  Published multi-country mAP figures are not a fair benchmark for this model
  and must not be cited as though they were (D032).
- No severity annotations exist, which is why `apparent_severity` is derived
  from area quantiles as a visual-prominence proxy (D014, D028).
- No GPS or route continuity, which is why calibration uses evaluation
  segments rather than physical road segments (D010).
```

- [ ] **Step 9: Commit**

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
feat: deterministic four-way split with calib firewall

Salted-hash assignment rather than seeded shuffle, so adding files never
reshuffles existing assignments. Images symlinked, labels copied.

The generated ultralytics data.yaml references only train and val, so calib
and test are structurally unreachable from training. Tests assert
disjointness and stability explicitly, since conformal validity depends on
calib never leaking.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Water-pothole dataset viability spike

Timeboxed. This is a go/no-go investigation with a written verdict, not a feature. D032 downgraded the risk — the ReadMe confirms VOC **and** YOLO annotations ship — so the remaining question is the class set and whether the potholes are genuinely water-filled.

**Files:**
- Create: `docs/water-pothole-viability.md`
- Modify: `docs/DECISIONS.md`

**Interfaces:**
- Consumes: `raw_dir()`, `class_census` from Task 5
- Produces: a written go/no-go verdict; no production code

- [ ] **Step 1: Download and extract**

```bash
cd /Users/harshav/PROJECTS/certain-road
mkdir -p data/raw/water_potholes
curl -sL "https://data.mendeley.com/public-api/datasets/tp95cdvgm8/files?folder_id=root&version=1" \
  | python3 -c "
import json,sys
for f in json.load(sys.stdin):
    if f['filename']=='Potholes.zip':
        print(f['content_details']['download_url'])
" > /tmp/wp_url.txt
curl -L -A "Mozilla/5.0" -o data/raw/water_potholes/Potholes.zip "$(cat /tmp/wp_url.txt)"
unzip -q -o data/raw/water_potholes/Potholes.zip -d data/raw/water_potholes/
find data/raw/water_potholes -maxdepth 2 -type d
```

- [ ] **Step 2: Census the classes**

```bash
cd /Users/harshav/PROJECTS/certain-road
XMLDIR=$(find data/raw/water_potholes -type d -name "XML" | head -1)
echo "XML dir: $XMLDIR"
uv run python -c "
from pathlib import Path
from certain_road.detect.dataset.voc import class_census
counts = class_census(Path('$XMLDIR'))
for name, n in counts.most_common():
    print(f'{name:<24} {n}')
print('total', counts.total())
"
```

- [ ] **Step 3: Count files and inspect images**

```bash
cd /Users/harshav/PROJECTS/certain-road
for d in IMG XML TXT; do
  p=$(find data/raw/water_potholes -type d -name "$d" | head -1)
  [ -n "$p" ] && echo "$d: $(ls "$p" | wc -l | tr -d ' ') files"
done
IMGDIR=$(find data/raw/water_potholes -type d -name "IMG" | head -1)
open "$IMGDIR"
```

Look at 20–30 images. The question to answer is specific: **are these potholes actually water-filled, or is this a general pothole dataset?** If the water content is incidental, this is not the distribution shift the spec needs and the synthetic sweep carries the experiment alone.

- [ ] **Step 4: Write the verdict**

Create `docs/water-pothole-viability.md`:

```markdown
# Water-pothole dataset — viability verdict

**Source:** Mendeley `tp95cdvgm8`, `Potholes.zip` (290 MB)
**Assessed:** [date]
**Verdict:** [GO / NO-GO]

## What ships

| Directory | Contents | Count |
|---|---|---|
| `IMG/` | images | [n] |
| `XML/` | PASCAL VOC annotations | [n] |
| `TXT/` | YOLO annotations | [n] |

## Class census

| Class | Boxes |
|---|---|
| [observed] | [n] |

## Are the potholes water-filled?

[Verdict from visual inspection of 20-30 images. Estimate the fraction that
are genuinely water-filled or wet.]

## Class compatibility

RDD2022 uses D00/D10/D20/D40. This dataset uses [observed].

[If pothole-only: reference PCI computed here is pothole-only, so the shift
comparison is partly apples-to-oranges. State whether the comparison is
restricted to the pothole contribution or dropped.]

## Decision

[GO — usable as the secondary real-shift experiment, with the class-set
caveat recorded. / NO-GO — the synthetic severity sweep carries the shift
experiment alone, as D025 anticipated.]
```

- [ ] **Step 5: Record the decision**

Append a `D033` entry to `docs/DECISIONS.md` (and its index row) stating the verdict and the reasoning. Follow the existing entry format: date, status, context, decision, consequence.

- [ ] **Step 6: Commit**

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
docs: water-pothole dataset viability verdict

Timeboxed spike per D025/D032. Records what ships, the class census,
whether the potholes are genuinely water-filled, and the go/no-go for using
this as the secondary real-shift experiment.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Launch YOLOv8n training on MPS

Smoke-test first on a handful of images. A four-hour run that fails in minute three because of a device or dataloader problem is the most avoidable way to lose a day.

**Files:**
- Create: `configs/train/yolov8n.yaml`
- Create: `src/certain_road/detect/train.py`
- Modify: `src/certain_road/cli.py`
- Test: `tests/test_train_config.py`

**Interfaces:**
- Consumes: `configs/dataset/rdd2022_india.yaml` from Task 6
- Produces:
  - `load_train_config(path: Path) -> dict`
  - `train(config_path: Path, data_yaml: Path, *, smoke: bool = False) -> Path` returning the results directory
  - CLI: `certain-road detect train [--smoke]`

- [ ] **Step 1: Write the training config**

Create `configs/train/yolov8n.yaml`:

```yaml
# YOLOv8n on the RDD2022 India subset (D025).
# Every value here is a knob; none may be hardcoded in train.py.

model: yolov8n.pt
epochs: 100
patience: 20
imgsz: 640
batch: 16
device: mps
workers: 8
seed: 0
project: models/yolo
name: india_v1
exist_ok: false

# Augmentation. Defaults are close to right for road imagery; vertical flip is
# off because road scenes have a fixed up-down orientation.
fliplr: 0.5
flipud: 0.0
degrees: 0.0
translate: 0.1
scale: 0.5
mosaic: 1.0
close_mosaic: 10
```

- [ ] **Step 2: Write the failing config test**

Create `tests/test_train_config.py`:

```python
from certain_road.core.paths import repo_root
from certain_road.detect.train import load_train_config

CONFIG = repo_root() / "configs" / "train" / "yolov8n.yaml"


def test_config_loads_and_targets_mps():
    cfg = load_train_config(CONFIG)
    assert cfg["device"] == "mps", "must not silently train on CPU"
    assert cfg["model"] == "yolov8n.pt"


def test_required_keys_present():
    cfg = load_train_config(CONFIG)
    for key in ("epochs", "patience", "imgsz", "batch", "seed", "project", "name"):
        assert key in cfg, f"missing {key}"


def test_vertical_flip_is_disabled():
    """Road scenes have a fixed orientation; flipud would fabricate impossible views."""
    assert load_train_config(CONFIG)["flipud"] == 0.0
```

- [ ] **Step 3: Run it and watch it fail**

Run: `uv run pytest tests/test_train_config.py -v`
Expected: FAIL — `certain_road.detect.train` not found.

- [ ] **Step 4: Implement the trainer**

Create `src/certain_road/detect/train.py`:

```python
"""YOLOv8n training on Apple Silicon MPS.

Training happens here and only here. The Jetson is an inference target, never a
training device.
"""

from pathlib import Path

import yaml


def load_train_config(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def train(config_path: Path, data_yaml: Path, *, smoke: bool = False) -> Path:
    """Run training. `smoke=True` runs two epochs to prove the setup works."""
    import torch
    from ultralytics import YOLO

    cfg = load_train_config(config_path)

    if cfg["device"] == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("config requests MPS but it is unavailable")

    model_name = cfg.pop("model")
    if smoke:
        cfg |= {"epochs": 2, "name": f"{cfg['name']}_smoke", "exist_ok": True}

    model = YOLO(model_name)
    results = model.train(data=str(data_yaml), **cfg)
    return Path(results.save_dir)
```

- [ ] **Step 5: Run the config tests to verify they pass**

Run: `uv run pytest tests/test_train_config.py -v`
Expected: all three PASS.

- [ ] **Step 6: Add the train command**

Append to `src/certain_road/cli.py`:

Attach to the existing `detect` stage app from Task 1 rather than creating a parallel
top-level app:

```python
@STAGE_APPS["detect"].command("train")
def detect_train(smoke: bool = False, country: str = "India") -> None:
    """Train YOLOv8n. Use --smoke for a two-epoch setup check."""
    from certain_road.core.paths import repo_root
    from certain_road.detect.train import train

    save_dir = train(
        repo_root() / "configs" / "train" / "yolov8n.yaml",
        repo_root() / "configs" / "dataset" / f"rdd2022_{country.lower()}.yaml",
        smoke=smoke,
    )
    print(f"results -> {save_dir}")
```

- [ ] **Step 7: Smoke test**

```bash
cd /Users/harshav/PROJECTS/certain-road
uv run certain-road detect train --smoke
```

Expected: two epochs complete, `results -> models/yolo/india_v1_smoke`.

**If it hangs at "Scanning" or during the first epoch,** the macOS dataloader is the usual cause. Set `workers: 0` in `configs/train/yolov8n.yaml` and retry. If that fixes it, commit the change with a comment recording why.

**If it reports `device=cpu`,** stop. Do not proceed to the full run — a CPU run will take days rather than hours.

- [ ] **Step 8: Launch the real run unattended**

```bash
cd /Users/harshav/PROJECTS/certain-road
mkdir -p runs/logs
nohup uv run certain-road detect train > runs/logs/train_india_v1.log 2>&1 &
echo "pid $!"
sleep 120 && tail -20 runs/logs/train_india_v1.log
```

Expect 4–6 hours for 100 epochs over 4,624 images. Monitor with:

```bash
tail -f /Users/harshav/PROJECTS/certain-road/runs/logs/train_india_v1.log
```

**This is the point where weeks 2–4 unblock.** Do not wait for training — `assess` and `calibrate` are built against the Task 3 fixtures while this runs, and only need the real weights in week 4.

- [ ] **Step 9: Set expectations for the result**

When the run finishes, record `mAP50` and `mAP50-95` per class in `docs/dataset-card-rdd2022-india.md`.

Calibrate expectations before reading them: **4,624 training images is small and India is the hardest RDD2022 subset.** Published multi-country RDD2022 numbers are not a fair comparison and must not be cited as though they were (D032). A modest mAP is an accepted consequence of the D025 scope cut, not a defect — and the project's contribution is the uncertainty and decision layers, not detector mAP.

- [ ] **Step 10: Commit**

```bash
cd /Users/harshav/PROJECTS/certain-road
git add -A
git commit -m "$(cat <<'EOF'
feat: YOLOv8n training on MPS

Config-driven trainer with a --smoke two-epoch mode, and a hard failure if
MPS is requested but unavailable so a run can never silently fall back to
CPU. Vertical flip disabled: road scenes have a fixed orientation.

Weeks 2-4 now proceed against synthetic fixtures while this runs unattended.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Week 1 definition of done

- [ ] `uv run pytest` green; `uv run lint-imports` green; `uv run ruff check .` green
- [ ] A deliberate cross-stage import has been shown to fail CI (Task 1 Step 10)
- [ ] `data/processed/india/` holds four disjoint splits, counts ≈ 4,624 / 771 / 1,541 / 770
- [ ] `configs/dataset/rdd2022_india.yaml` references **only** train and val
- [ ] `runs/synthetic/artifacts/` holds fixtures for 102 evaluation segments
- [ ] `docs/dataset-card-rdd2022-india.md` complete with real census numbers
- [ ] `docs/water-pothole-viability.md` written with a GO/NO-GO verdict, recorded as D033
- [ ] Training running unattended, log at `runs/logs/train_india_v1.log`

## Notes for week 2

`assess` is built next, against the Task 3 fixtures, with no dependence on the training run. Its first components are the ROI trapezoid geometry and `vision_density`; `apparent_severity` quantile cutpoints must be computed on the **train split only** and frozen into `configs/assess/severity_bands.yaml` — computing them on the full dataset would leak calibration data into the assessment model.
