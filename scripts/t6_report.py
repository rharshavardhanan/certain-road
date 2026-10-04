"""T6 — the generalization gap, per class, with the confusion structure behind it.

A single mAP number says a model got worse. It does not say whether it stopped
finding damage or started misnaming it, and those have different remedies: the
first is a recall problem that more India data may fix, the second is a class
confusion that would point at the taxonomy. The confusion rows below separate
them.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.assess.conformal import iou_matrix  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.metrics_coco import (  # noqa: E402
    coco_eval,
    load_predictions,
    yolo_to_coco_gt,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
EVAL, YOLO_DIR = CFG["eval"], repo_root() / CFG["paths"]["yolo"]
NAMES = {int(k): v for k, v in CFG["classes"].items()}
IOU_MATCH = 0.5


def load_gt_boxes(stems):
    out = {}
    for s in stems:
        rows = []
        for line in (YOLO_DIR / "labels" / f"{s}.txt").read_text().splitlines():
            if line.strip():
                c, cx, cy, w, h = map(float, line.split())
                rows.append((int(c), cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
        out[s] = rows
    return out


def load_pred_boxes(pred_json, conf):
    """image stem -> list of (cls, x1, y1, x2, y2, score) in normalised coords."""
    raw = json.loads(Path(pred_json).read_text())
    out = defaultdict(list)
    for r in raw:
        if r["score"] < conf:
            continue
        out[Path(str(r["image_id"])).stem].append(
            (int(r["category_id"]) - 1, *r["bbox"], float(r["score"]))
        )
    return out


def confusion(stems, gt, preds, sizes):
    """Rows = GT class, cols = predicted class or 'background' (missed)."""
    table = {NAMES[k]: Counter() for k in NAMES}
    for s in stems:
        g = gt[s]
        if not g:
            continue
        w, h = sizes[s]
        p = preds.get(s, [])
        gb = np.array([[x1 * w, y1 * h, x2 * w, y2 * h] for _, x1, y1, x2, y2 in g])
        if p:
            pb = np.array([[x, y, x + bw, y + bh] for _, x, y, bw, bh, _ in p])
            scores = np.array([r[5] for r in p])
            ious = iou_matrix(pb, gb)
        taken = set()
        for gi, (gc, *_) in enumerate(g):
            best, best_iou = None, IOU_MATCH
            if p:
                for pi in np.argsort(-scores):
                    if pi in taken or ious[pi, gi] < best_iou:
                        continue
                    best, best_iou = int(pi), ious[pi, gi]
                    break
            if best is None:
                table[NAMES[gc]]["background"] += 1
            else:
                taken.add(best)
                table[NAMES[gc]][NAMES[p[best][0]]] += 1
    return table


def pr_at(stems, gt, preds, sizes):
    tp = fp = fn = 0
    for s in stems:
        g, p = gt[s], preds.get(s, [])
        w, h = sizes[s]
        matched = set()
        if g and p:
            gb = np.array([[x1 * w, y1 * h, x2 * w, y2 * h] for _, x1, y1, x2, y2 in g])
            pb = np.array([[x, y, x + bw, y + bh] for _, x, y, bw, bh, _ in p])
            ious = iou_matrix(pb, gb)
            order = np.argsort(-np.array([r[5] for r in p]))
            for pi in order:
                cand = [
                    gi
                    for gi in range(len(g))
                    if gi not in matched and ious[pi, gi] >= IOU_MATCH and g[gi][0] == p[pi][0]
                ]
                if cand:
                    matched.add(max(cand, key=lambda gi: ious[pi, gi]))
                    tp += 1
                else:
                    fp += 1
        else:
            fp += len(p)
        fn += len(g) - len(matched)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def analyse(name, split, pred_json):
    from PIL import Image

    stems = [
        Path(x).stem for x in (YOLO_DIR / f"{split}.txt").read_text().splitlines() if x.strip()
    ]
    gt = load_gt_boxes(stems)
    sizes = {}
    for s in stems:
        with Image.open(YOLO_DIR / "images" / f"{s}.jpg") as im:
            sizes[s] = im.size
    preds = load_pred_boxes(pred_json, EVAL["report_conf"])
    return (
        {
            "set": split,
            "images": len(stems),
            "confusion_at_report_conf": {
                k: dict(v) for k, v in confusion(stems, gt, preds, sizes).items()
            },
            "pr_at_report_conf": pr_at(stems, gt, preds, sizes),
        },
        stems,
        gt,
        sizes,
    )


def main() -> int:
    non_pred = next(
        (repo_root() / "results" / "T6_A_nonindia_val" / "val").glob("predictions.json")
    )
    ind_pred = next(
        (repo_root() / "results" / "LOCKED" / "A_india_full_run" / "val").glob("predictions.json")
    )

    report = {"report_conf": EVAL["report_conf"], "iou_match": IOU_MATCH}
    report["nonindia_val"], _, _, _ = analyse("nonindia", "nonindia_val", non_pred)
    report["india_full"], ind_stems, ind_gt, ind_sizes = analyse("india", "india_full", ind_pred)

    # Slice the locked India predictions by subset - no new inference.
    slices = {}
    for sub in ("india_train", "india_val", "india_cal", "india_test"):
        sub_stems = [
            Path(x).stem for x in (YOLO_DIR / f"{sub}.txt").read_text().splitlines() if x.strip()
        ]
        paths = [YOLO_DIR / "images" / f"{s}.jpg" for s in sub_stems]
        gt, stem_to_id = yolo_to_coco_gt(paths, YOLO_DIR / "labels", NAMES)
        preds = load_predictions(ind_pred, stem_to_id, len(NAMES))
        res = coco_eval(gt, preds, NAMES)
        slices[sub] = {
            "images": len(sub_stems),
            "map50": round(res["map50"], 4),
            "map50_95": round(res["map50_95"], 4),
            "per_class_ap50": {k: round(v["ap50"], 4) for k, v in res["per_class"].items()},
        }
        print(f"  {sub:<12} n={len(sub_stems):<5} mAP50={res['map50']:.4f}", flush=True)
    report["india_slices"] = slices

    out = repo_root() / "results" / "T6"
    out.mkdir(parents=True, exist_ok=True)
    (out / "gap_analysis.json").write_text(json.dumps(report, indent=2))
    print("\n" + json.dumps({k: report[k] for k in ("nonindia_val", "india_full")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
