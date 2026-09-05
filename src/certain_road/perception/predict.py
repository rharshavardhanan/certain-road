"""Weights + images -> a `DetectionRow` frame, with taxonomy remap applied.

External RDD2022 models emit four classes (D00, D10, D20, D40) whose indices
do not align with our frozen three-class taxonomy (`configs/eval/
class_maps.yaml`). Class 2 in the external taxonomy is alligator crack; class
2 in ours is pothole. Scoring an external model's raw output against our
labels without remapping silently scores potholes against alligator cracks
and produces plausible-looking, wrong numbers -- the exact failure this
project exists to prevent.

The boundary is kept explicit: `_raw_predictions` is the only function here
that touches ultralytics and returns an unmapped `class_id`; `remap_class_ids`
relabels those ids; `predict_to_detections` glues the two together and maps
ids to the `class_name` strings `DetectionRow` requires. This lets the
remap/schema logic be tested without a trained model.
"""

from pathlib import Path

import pandas as pd
import yaml

from certain_road.artifacts.schema import DetectionRow
from certain_road.core.paths import repo_root
from certain_road.perception.dataset.convert import ID_TO_CLASS

CLASS_MAPS_PATH = repo_root() / "configs" / "eval" / "class_maps.yaml"
THRESHOLDS_PATH = repo_root() / "configs" / "eval" / "thresholds.yaml"

# Columns `_raw_predictions` returns, before the class remap is applied.
_RAW_COLUMNS = ["frame_id", "det_id", "class_id", "score", "x1", "y1", "x2", "y2", "img_w", "img_h"]


def load_class_map(name: str) -> dict[int, int]:
    """Load a named class remap from `configs/eval/class_maps.yaml`."""
    maps = yaml.safe_load(CLASS_MAPS_PATH.read_text())["maps"]
    if name not in maps:
        raise ValueError(f"unknown class map {name!r}; choices: {sorted(maps)}")
    return {int(k): int(v) for k, v in maps[name]["mapping"].items()}


def load_thresholds() -> dict:
    """Load `configs/eval/thresholds.yaml` -- the single source for conf/iou defaults."""
    return yaml.safe_load(THRESHOLDS_PATH.read_text())


def remap_class_ids(df: pd.DataFrame, class_map: dict[int, int]) -> pd.DataFrame:
    """Relabel `class_id` per `class_map`. A pure relabel: boxes are never combined.

    Raises `ValueError` naming the offending id(s) if any row's class is absent
    from the map -- silently dropping an unmapped class is exactly the failure
    this harness exists to prevent.
    """
    unmapped = sorted(set(df["class_id"]) - set(class_map))
    if unmapped:
        raise ValueError(f"class id(s) {unmapped} absent from class map {class_map}")
    out = df.copy()
    out["class_id"] = out["class_id"].map(class_map)
    return out


def _raw_predictions(
    weights: Path, image_dir: Path, *, conf: float, device: str, imgsz: int
) -> pd.DataFrame:
    """Run ultralytics inference over every image in `image_dir`.

    Returns one row per predicted box with an unmapped `class_id`. An image
    with zero detections simply contributes no rows -- ultralytics never
    yields boxes for it -- so it is never dropped from consideration, it just
    has nothing to report.
    """
    from ultralytics import YOLO

    model = YOLO(str(weights))
    results = model.predict(
        source=str(image_dir),
        conf=conf,
        device=device,
        imgsz=imgsz,
        verbose=False,
        stream=True,
    )

    rows: list[dict] = []
    for result in results:
        frame_id = Path(result.path).stem
        img_h, img_w = result.orig_shape
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue
        class_ids = boxes.cls.cpu().numpy().astype(int)
        scores = boxes.conf.cpu().numpy()
        xyxy = boxes.xyxy.cpu().numpy()
        for k in range(len(boxes)):
            rows.append(
                {
                    "frame_id": frame_id,
                    "det_id": f"{frame_id}-{k}",
                    "class_id": int(class_ids[k]),
                    "score": float(scores[k]),
                    "x1": float(xyxy[k, 0]),
                    "y1": float(xyxy[k, 1]),
                    "x2": float(xyxy[k, 2]),
                    "y2": float(xyxy[k, 3]),
                    "img_w": int(img_w),
                    "img_h": int(img_h),
                }
            )

    return pd.DataFrame(rows, columns=_RAW_COLUMNS)


def predict_to_detections(
    weights: Path,
    image_dir: Path,
    *,
    class_map: dict[int, int],
    conf: float,
    device: str,
    imgsz: int,
) -> pd.DataFrame:
    """Run `weights` over `image_dir`, remap classes, return a `DetectionRow` frame.

    An empty prediction set (no boxes anywhere above `conf`) returns a frame
    with zero rows but the full `DetectionRow` column set, so it still
    validates through `write_artifact` rather than producing a malformed or
    columnless frame.
    """
    raw = _raw_predictions(weights, image_dir, conf=conf, device=device, imgsz=imgsz)
    remapped = remap_class_ids(raw, class_map)
    remapped["class_name"] = remapped["class_id"].map(ID_TO_CLASS)
    return remapped[DetectionRow.columns()]
