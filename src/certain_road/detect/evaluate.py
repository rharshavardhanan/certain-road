"""Detections + ground-truth labels -> mAP and operating-point metrics.

**Metric-implementation decision (D045):** this module computes mAP by
reusing `ultralytics.utils.metrics.box_iou` and `ap_per_class` directly --
the same two functions `model.val()` calls internally -- rather than a
third-party library such as `torchmetrics`. The reason is comparability, not
convenience: the harness must reproduce the pre-registered mAP50 ≈ 0.4220 /
mAP50-95 ≈ 0.1857 that `model.val()` already reported for `multicountry_v8s`
(Task 4), and it must later be comparable to published ultralytics-based
RDD2022 benchmarks. A different, independently "correct" implementation
(e.g. a pycocotools-backed one) can differ by more than the ±0.01 tolerance
purely through IoU-matching and interpolation conventions, which would make
it impossible to tell a harness bug from a genuine implementation
difference. `ap_per_class`'s greedy IoU matching normally lives on
`ultralytics.engine.validator.BaseValidator.match_predictions`, an instance
method that expects a live validator; `_match_predictions` below is a
standalone re-implementation of that same algorithm (not a new one) so it
can run over a plain DataFrame pair instead of a dataloader.

mAP is computed over the full precision-recall curve at `map_conf_floor`
(`configs/eval/thresholds.yaml`); the owner-requested confidence sweep
(0.10/0.15/0.20/0.25) applies only to `compute_operating_metrics`, one
operating point at a time -- see the plan's "two design decisions" section.
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from ultralytics.utils.metrics import ap_per_class, box_iou

from certain_road.detect.dataset.convert import ID_TO_CLASS
from certain_road.detect.predict import load_thresholds

CLASS_NAME_TO_ID = {name: class_id for class_id, name in ID_TO_CLASS.items()}

# The standard COCO / ultralytics definition of "mAP50-95": 10 IoU
# thresholds from 0.50 to 0.95 in steps of 0.05. This is not a tunable --
# it is what the metric name means, the same way ultralytics hardcodes
# `self.iouv = torch.linspace(0.5, 0.95, 10)` in DetectionValidator -- so
# it does not live in configs/eval/thresholds.yaml. The single-threshold
# IoU used for operating-point metrics (0.50) does live there, as
# `iou_thresholds_map50`, because that one genuinely is a choice.
_MAP50_95_IOU_THRESHOLDS = np.linspace(0.50, 0.95, 10)

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

GT_COLUMNS = ["frame_id", "class_id", "x1", "y1", "x2", "y2", "img_w", "img_h"]


def _find_image(images_dir: Path, stem: str) -> Path:
    for ext in _IMAGE_EXTENSIONS:
        candidate = images_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no image for label stem {stem!r} in {images_dir}")


def load_ground_truth(labels_dir: Path, images_dir: Path) -> pd.DataFrame:
    """YOLO-normalised label files -> absolute-pixel xyxy ground truth.

    Reads each image's real dimensions with PIL rather than assuming a fixed
    600x600 or 640x640 -- RDD2022 images are not uniformly sized. A label
    file that exists but is empty marks a genuine negative frame
    (`detect.dataset.convert.to_yolo_lines`); it contributes zero rows here,
    the same convention `predict_to_detections` uses for a frame with no
    detections, and is not otherwise flagged.
    """
    labels_dir = Path(labels_dir)
    images_dir = Path(images_dir)
    rows: list[dict] = []

    for label_path in sorted(labels_dir.glob("*.txt")):
        stem = label_path.stem
        image_path = _find_image(images_dir, stem)
        with Image.open(image_path) as img:
            img_w, img_h = img.size

        text = label_path.read_text().strip()
        if not text:
            continue

        for line in text.splitlines():
            class_id_str, cx_str, cy_str, w_str, h_str = line.split()
            cx, cy, w, h = (float(v) for v in (cx_str, cy_str, w_str, h_str))
            rows.append(
                {
                    "frame_id": stem,
                    "class_id": int(class_id_str),
                    "x1": (cx - w / 2) * img_w,
                    "y1": (cy - h / 2) * img_h,
                    "x2": (cx + w / 2) * img_w,
                    "y2": (cy + h / 2) * img_h,
                    "img_w": img_w,
                    "img_h": img_h,
                }
            )

    return pd.DataFrame(rows, columns=GT_COLUMNS)


def _match_predictions(
    pred_classes: np.ndarray,
    true_classes: np.ndarray,
    iou: np.ndarray,
    iou_thresholds: np.ndarray,
) -> np.ndarray:
    """Greedy class-then-IoU matching, one row per prediction, one column per threshold.

    Re-implements `ultralytics.engine.validator.BaseValidator.match_predictions`
    (the non-scipy / greedy branch) as a free function: same algorithm
    `model.val()` uses to build its tp matrix, extracted because the original
    is an instance method requiring a live validator (`self.iouv`).
    """
    correct = np.zeros((pred_classes.shape[0], len(iou_thresholds)), dtype=bool)
    if iou.size == 0:
        return correct

    correct_class = true_classes[:, None] == pred_classes[None, :]
    iou = iou * correct_class

    for i, threshold in enumerate(iou_thresholds):
        matches = np.array(np.nonzero(iou >= threshold)).T
        if matches.shape[0]:
            if matches.shape[0] > 1:
                matches = matches[iou[matches[:, 0], matches[:, 1]].argsort()[::-1]]
                matches = matches[np.unique(matches[:, 1], return_index=True)[1]]
                matches = matches[np.unique(matches[:, 0], return_index=True)[1]]
            correct[matches[:, 1].astype(int), i] = True

    return correct


def _frame_iou(gt_frame: pd.DataFrame, pred_frame: pd.DataFrame) -> np.ndarray:
    """IoU of every gt box (rows) against every predicted box (cols) in one frame."""
    gt_boxes = torch.tensor(gt_frame[["x1", "y1", "x2", "y2"]].to_numpy(), dtype=torch.float32)
    pred_boxes = torch.tensor(pred_frame[["x1", "y1", "x2", "y2"]].to_numpy(), dtype=torch.float32)
    return box_iou(gt_boxes, pred_boxes).numpy()


def compute_map(preds: pd.DataFrame, gt: pd.DataFrame, *, num_classes: int) -> dict:
    """mAP50, mAP50-95, and per-class AP50 over the whole precision-recall curve.

    Boxes are matched only within the same `frame_id` -- never across images.
    `preds` should already be filtered to `map_conf_floor`, not an operating
    threshold; raising the threshold here would truncate the PR curve and
    depress mAP artificially rather than "tune" it (see module docstring).
    """
    pred_groups = dict(tuple(preds.groupby("frame_id"))) if len(preds) else {}
    gt_groups = dict(tuple(gt.groupby("frame_id"))) if len(gt) else {}
    frame_ids = sorted(set(pred_groups) | set(gt_groups))

    n_iou = len(_MAP50_95_IOU_THRESHOLDS)
    tp_chunks, conf_chunks, cls_chunks = [], [], []

    for frame_id in frame_ids:
        pred_f = pred_groups.get(frame_id)
        if pred_f is None or len(pred_f) == 0:
            continue  # nothing predicted here; any gt just lowers recall via target_cls below

        pred_cls_f = pred_f["class_name"].map(CLASS_NAME_TO_ID).to_numpy()
        conf_f = pred_f["score"].to_numpy(dtype=float)

        gt_f = gt_groups.get(frame_id)
        if gt_f is None or len(gt_f) == 0:
            tp_f = np.zeros((len(pred_f), n_iou), dtype=bool)  # empty image: every pred is a miss
        else:
            iou = _frame_iou(gt_f, pred_f)
            tp_f = _match_predictions(
                pred_cls_f, gt_f["class_id"].to_numpy(), iou, _MAP50_95_IOU_THRESHOLDS
            )

        tp_chunks.append(tp_f)
        conf_chunks.append(conf_f)
        cls_chunks.append(pred_cls_f)

    tp = np.concatenate(tp_chunks, axis=0) if tp_chunks else np.zeros((0, n_iou), dtype=bool)
    conf = np.concatenate(conf_chunks, axis=0) if conf_chunks else np.zeros(0)
    pred_cls = np.concatenate(cls_chunks, axis=0) if cls_chunks else np.zeros(0, dtype=int)
    target_cls = gt["class_id"].to_numpy() if len(gt) else np.zeros(0, dtype=int)

    per_class_ap50 = {ID_TO_CLASS.get(i, str(i)): 0.0 for i in range(num_classes)}

    if target_cls.size == 0:
        # No ground truth at all: mAP is undefined-as-zero, never NaN.
        return {"map50": 0.0, "map50_95": 0.0, "per_class_ap50": per_class_ap50}

    _tp, _fp, _p, _r, _f1, ap, unique_classes, *_ = ap_per_class(tp, conf, pred_cls, target_cls)

    for i, class_id in enumerate(unique_classes):
        per_class_ap50[ID_TO_CLASS.get(int(class_id), str(int(class_id)))] = float(ap[i, 0])

    map50 = float(ap[:, 0].mean()) if ap.size else 0.0
    map50_95 = float(ap.mean()) if ap.size else 0.0

    return {"map50": map50, "map50_95": map50_95, "per_class_ap50": per_class_ap50}


def compute_operating_metrics(preds: pd.DataFrame, gt: pd.DataFrame, conf: float) -> dict:
    """Precision / recall / F1 / per-class recall / FP count at one confidence threshold.

    A single IoU@0.50 greedy match per frame (`iou_thresholds_map50` in
    `configs/eval/thresholds.yaml`), unlike `compute_map`'s 10-threshold
    sweep -- this reports one operating point, not the integrated curve.
    `preds` is filtered to `score >= conf` before matching. An image with no
    ground truth can only ever add to the false-positive count here: it
    contributes nothing to the recall denominator (`len(gt)`), so it can
    never register as a "missed detection".
    """
    filtered = preds[preds["score"] >= conf]
    iou_threshold = np.array([load_thresholds()["iou_thresholds_map50"]])

    pred_groups = dict(tuple(filtered.groupby("frame_id"))) if len(filtered) else {}
    gt_groups = dict(tuple(gt.groupby("frame_id"))) if len(gt) else {}
    frame_ids = sorted(set(pred_groups) | set(gt_groups))

    tp_total = 0
    fp_total = 0
    per_class_tp: Counter = Counter()
    per_class_gt: Counter = Counter(gt["class_id"]) if len(gt) else Counter()

    for frame_id in frame_ids:
        pred_f = pred_groups.get(frame_id)
        if pred_f is None or len(pred_f) == 0:
            continue  # nothing predicted; any gt here is simply unmatched (lowers recall only)

        pred_cls_f = pred_f["class_name"].map(CLASS_NAME_TO_ID).to_numpy()
        gt_f = gt_groups.get(frame_id)

        if gt_f is None or len(gt_f) == 0:
            fp_total += len(pred_f)  # empty image: every surviving prediction is a false positive
            continue

        iou = _frame_iou(gt_f, pred_f)
        matched = _match_predictions(pred_cls_f, gt_f["class_id"].to_numpy(), iou, iou_threshold)[
            :, 0
        ]
        tp_total += int(matched.sum())
        fp_total += int((~matched).sum())
        for class_id in pred_cls_f[matched]:
            per_class_tp[int(class_id)] += 1

    total_gt = int(len(gt))
    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else 0.0
    recall = tp_total / total_gt if total_gt else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    per_class_recall = {
        ID_TO_CLASS[class_id]: (
            per_class_tp[class_id] / per_class_gt[class_id] if per_class_gt[class_id] else 0.0
        )
        for class_id in sorted(ID_TO_CLASS)
    }

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "per_class_recall": per_class_recall,
        "false_positive_count": fp_total,
    }


def measure_latency(weights: Path, *, device: str, imgsz: int, reps: int, warmup: int) -> dict:
    """Mean / p50 / p95 inference latency (ms/image) on a fixed dummy frame.

    Uses a synthetic all-zero image rather than real files so latency
    reflects model compute + NMS overhead, not disk/decode variance; `warmup`
    reps are discarded before timing starts. MPS execution is asynchronous,
    so each rep is bracketed with `torch.mps.synchronize()` when `device`
    is "mps" -- otherwise the wall-clock delta would just measure dispatch,
    not completion.
    """
    import time

    from ultralytics import YOLO

    model = YOLO(str(weights))
    dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)

    def _predict_once() -> None:
        model.predict(source=dummy, device=device, imgsz=imgsz, verbose=False)
        if device == "mps":
            torch.mps.synchronize()

    for _ in range(warmup):
        _predict_once()

    latencies_ms = []
    for _ in range(reps):
        start = time.perf_counter()
        _predict_once()
        latencies_ms.append((time.perf_counter() - start) * 1000.0)

    arr = np.array(latencies_ms)
    return {
        "mean_ms": float(arr.mean()),
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
    }


def render_report(
    *,
    weights: Path,
    country: str,
    split: str,
    class_map: str,
    n_images: int,
    n_positive: int,
    n_empty: int,
    map_metrics: dict,
    operating_thresholds: list[float],
    operating_metrics: list[dict],
    latency: dict,
) -> str:
    """Render the mAP + operating-sweep + latency results as markdown."""
    class_names = [ID_TO_CLASS[i] for i in sorted(ID_TO_CLASS)]

    lines = [
        f"# Detector evaluation: `{weights}`",
        "",
        f"- split: `{country}/{split}` -- {n_images} images "
        f"({n_positive} positive, {n_empty} empty)",
        f"- class map: `{class_map}`",
        "",
        "## mAP (conf floor, whole precision-recall curve)",
        "",
        f"- mAP50: {map_metrics['map50']:.4f}",
        f"- mAP50-95: {map_metrics['map50_95']:.4f}",
        "",
        "| class | AP50 |",
        "|---|---|",
    ]
    for name in class_names:
        lines.append(f"| {name} | {map_metrics['per_class_ap50'][name]:.4f} |")

    lines += [
        "",
        "## Operating-point sweep",
        "",
        "Precision/recall/F1 are computed once per threshold by filtering predictions "
        "to `score >= conf`, not by re-running inference.",
        "",
        "| conf | precision | recall | F1 | FP count | "
        + " | ".join(f"recall({n})" for n in class_names)
        + " |",
        "|---|---|---|---|---|" + "---|" * len(class_names),
    ]
    for conf, metrics in zip(operating_thresholds, operating_metrics, strict=True):
        per_class = " | ".join(f"{metrics['per_class_recall'][name]:.3f}" for name in class_names)
        lines.append(
            f"| {conf:.2f} | {metrics['precision']:.3f} | {metrics['recall']:.3f} | "
            f"{metrics['f1']:.3f} | {metrics['false_positive_count']} | {per_class} |"
        )

    lines += [
        "",
        "## Latency (ms/image)",
        "",
        f"- mean: {latency['mean_ms']:.2f}",
        f"- p50: {latency['p50_ms']:.2f}",
        f"- p95: {latency['p95_ms']:.2f}",
        "",
    ]
    return "\n".join(lines)
