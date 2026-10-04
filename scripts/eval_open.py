"""T6 — open evaluation on a non-held-out set, under the frozen settings.

Separate from `eval_locked` on purpose: this may be re-run freely, because the
sets it touches are not the ones any claim rests on. It carries no lock and no
clean-tree requirement.

It exists so the generalization gap is a like-for-like subtraction. The 0.5912
that appears in the training log came from a different pipeline — a GPU, fp16,
ultralytics' own aggregation — and subtracting India's CPU/fp32/pycocotools
number from it would measure the pipelines as much as the domains.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.metrics_coco import (  # noqa: E402
    coco_eval,
    load_predictions,
    yolo_to_coco_gt,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
EVAL = CFG["eval"]
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--set", required=True, dest="eval_set")
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    if args.eval_set in {"india_cal", "india_test", "india_heldout", "india_full"}:
        raise SystemExit(f"{args.eval_set} is held out; use eval_locked")

    from ultralytics import YOLO

    names = {int(k): v for k, v in CFG["classes"].items()}
    out_dir = repo_root() / "results" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)

    data_yaml = out_dir / "data.yaml"
    with open(data_yaml, "w") as fh:
        yaml.safe_dump(
            {
                "path": str(YOLO_DIR.resolve()),
                "train": f"{args.eval_set}.txt",
                "val": f"{args.eval_set}.txt",
                "names": names,
            },
            fh,
            sort_keys=False,
        )

    model = YOLO(str(args.weights))
    result = model.val(
        data=str(data_yaml),
        split="val",
        save_json=True,
        plots=True,
        project=str(out_dir),
        name="val",
        exist_ok=True,
        verbose=False,
        conf=EVAL["conf"],
        iou=EVAL["iou"],
        max_det=EVAL["max_det"],
        imgsz=EVAL["imgsz"],
        rect=EVAL["rect"],
        half=EVAL["half"],
        device=EVAL["device"],
    )

    image_paths = [
        YOLO_DIR / "images" / f"{Path(x).stem}.jpg"
        for x in (YOLO_DIR / f"{args.eval_set}.txt").read_text().splitlines()
        if x.strip()
    ]
    gt, stem_to_id = yolo_to_coco_gt(image_paths, YOLO_DIR / "labels", names)
    pred_json = next((out_dir / "val").glob("predictions.json"), None)
    coco = coco_eval(
        gt, load_predictions(pred_json, stem_to_id, len(names)) if pred_json else [], names
    )

    per_class_ultra = {
        names[i]: float(result.box.ap50[i]) for i in range(len(names)) if i < len(result.box.ap50)
    }
    payload = {
        "set": args.eval_set,
        "weights": str(args.weights),
        "images": len(image_paths),
        "eval_settings": EVAL,
        "ultralytics_metrics": {
            "map50": float(result.box.map50),
            "map50_95": float(result.box.map),
            "precision": float(result.box.mp),
            "recall": float(result.box.mr),
            "per_class_ap50": per_class_ultra,
        },
        "pycocotools_metrics": coco,
        "cross_check": {
            "map50_abs_delta": round(abs(float(result.box.map50) - coco["map50"]), 4),
            "tolerance": 0.03,
            "ok": abs(float(result.box.map50) - coco["map50"]) <= 0.03,
        },
    }
    (out_dir / "metrics.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
