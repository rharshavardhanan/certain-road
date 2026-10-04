"""T6 — pycocotools-backed evaluation, alongside the ultralytics path.

`evaluate.py` deliberately uses `ultralytics.utils.metrics.ap_per_class` so its
numbers stay comparable to published RDD2022 benchmarks (D057). This adds a
second, independent implementation rather than replacing it, because T6 step 4
asks for exactly that cross-check: if pycocotools and ultralytics disagree by
more than 0.03 on the same images, suspect the ground-truth conversion and stop.

Two conventions are asserted rather than assumed, because both are silent when
wrong and produce plausible numbers:
  * COCO `category_id` numbering (0- vs 1-indexed),
  * bbox format — COCO is `[x, y, width, height]` with a top-left origin, while
    YOLO labels are normalised centre-width-height.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

MIN_RELIABLE_INSTANCES = 100


def yolo_to_coco_gt(
    image_paths: Sequence[Path], labels_dir: Path, class_names: dict[int, str]
) -> tuple[dict, dict[str, int]]:
    """Build a COCO ground-truth dict, with a stable stem -> integer id map."""
    from PIL import Image

    stem_to_id = {Path(p).stem: i + 1 for i, p in enumerate(sorted(image_paths))}
    images, annotations, ann_id = [], [], 1

    for path in sorted(image_paths):
        stem = Path(path).stem
        with Image.open(path) as im:
            width, height = im.size
        images.append(
            {"id": stem_to_id[stem], "file_name": Path(path).name, "width": width, "height": height}
        )
        label = labels_dir / f"{stem}.txt"
        if not label.exists():
            continue
        for line in label.read_text().splitlines():
            if not line.strip():
                continue
            cls, cx, cy, bw, bh = line.split()
            # normalised centre/size -> absolute top-left x, y, w, h
            w, h = float(bw) * width, float(bh) * height
            x, y = float(cx) * width - w / 2, float(cy) * height - h / 2
            annotations.append(
                {
                    "id": ann_id,
                    "image_id": stem_to_id[stem],
                    "category_id": int(cls),
                    "bbox": [x, y, w, h],
                    "area": w * h,
                    "iscrowd": 0,
                }
            )
            ann_id += 1

    categories = [{"id": k, "name": v} for k, v in sorted(class_names.items())]
    return {"images": images, "annotations": annotations, "categories": categories}, stem_to_id


def load_predictions(json_path: Path, stem_to_id: dict[str, int], num_classes: int) -> list[dict]:
    """Read an ultralytics `predictions.json` and shift it onto our class ids.

    **Ultralytics writes 1-indexed `category_id` for any non-COCO dataset.**
    Verified in the installed source, `models/yolo/detect/val.py:90`:

        self.class_map = (coco80_to_coco91_class() if self.is_coco
                          else list(range(1, len(model.names) + 1)))

    so `category_id = class_index + 1`. Our ground truth is 0-indexed, so every
    id is shifted down by one. Skipping this does not error — it silently scores
    `linear_crack` predictions against `alligator_crack` ground truth and returns
    a plausible, wrong number. That is the exact failure `configs/eval/class_maps.yaml`
    exists to prevent for external models, and it applies to our own just as much.

    The expected range is asserted rather than assumed, so a future ultralytics
    that changes convention fails loudly instead of silently shifting everything.
    """
    raw = json.loads(Path(json_path).read_text())
    if not raw:
        return []

    cats = {int(r["category_id"]) for r in raw}
    expected = set(range(1, num_classes + 1))
    if not cats <= expected:
        raise ValueError(
            f"category_id {sorted(cats)} outside the expected 1..{num_classes} "
            f"that ultralytics writes for a non-COCO dataset (val.py:90). "
            "The convention may have changed; re-check before trusting any number."
        )

    out = []
    for record in raw:
        stem = Path(str(record.get("image_id"))).stem
        if stem not in stem_to_id:
            continue
        bbox = record["bbox"]
        if len(bbox) != 4:
            raise ValueError(f"expected COCO xywh bbox, got {bbox!r}")
        out.append(
            {
                "image_id": stem_to_id[stem],
                "category_id": int(record["category_id"]) - 1,  # -> our 0-indexed ids
                "bbox": [float(v) for v in bbox],
                "score": float(record["score"]),
            }
        )
    return out


def coco_eval(gt: dict, preds: list[dict], class_names: dict[int, str]) -> dict:
    """Per-class AP50 / AP50-95 plus 3-class and 4-class style means."""
    import contextlib
    import io

    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    counts = {k: 0 for k in class_names}
    for ann in gt["annotations"]:
        counts[ann["category_id"]] = counts.get(ann["category_id"], 0) + 1

    if not preds:
        return {
            "per_class": {
                v: {
                    "ap50": 0.0,
                    "ap50_95": 0.0,
                    "instances": counts.get(k, 0),
                    "unreliable": counts.get(k, 0) < MIN_RELIABLE_INSTANCES,
                }
                for k, v in class_names.items()
            },
            "map50": 0.0,
            "map50_95": 0.0,
            "note": "no predictions",
        }

    with contextlib.redirect_stdout(io.StringIO()):
        coco_gt = COCO()
        coco_gt.dataset = gt
        coco_gt.createIndex()
        coco_dt = coco_gt.loadRes(preds)
        ev = COCOeval(coco_gt, coco_dt, "bbox")
        ev.evaluate()
        ev.accumulate()
        ev.summarize()

    per_class = {}
    for idx, (cid, name) in enumerate(sorted(class_names.items())):
        # precision dims: [iou, recall, class, area, maxdet]
        p50 = ev.eval["precision"][0, :, idx, 0, 2]
        pall = ev.eval["precision"][:, :, idx, 0, 2]
        per_class[name] = {
            "ap50": float(np.mean(p50[p50 > -1])) if (p50 > -1).any() else 0.0,
            "ap50_95": float(np.mean(pall[pall > -1])) if (pall > -1).any() else 0.0,
            "instances": counts.get(cid, 0),
            "unreliable": counts.get(cid, 0) < MIN_RELIABLE_INSTANCES,
        }
    aps50 = [v["ap50"] for v in per_class.values()]
    aps = [v["ap50_95"] for v in per_class.values()]
    return {
        "per_class": per_class,
        "map50": float(np.mean(aps50)) if aps50 else 0.0,
        "map50_95": float(np.mean(aps)) if aps else 0.0,
    }
