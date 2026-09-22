"""T7 — Model A vs Model B on india_test, same scorer, same settings.

Both numbers come from locked predictions already written: A's from
`A_india_full` sliced to `india_test`, B's from `B_india_heldout` sliced the same
way. No new inference, so nothing here can be tuned against the result.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

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
SPLIT = "india_test"
IOUS = [0.1, 0.3, 0.5]


def stems():
    return [Path(x).stem for x in (YOLO_DIR / f"{SPLIT}.txt").read_text().splitlines()
            if x.strip()]


def gt_of(ss):
    out = {}
    for s in ss:
        rows = []
        for line in (YOLO_DIR / "labels" / f"{s}.txt").read_text().splitlines():
            if line.strip():
                c, cx, cy, w, h = map(float, line.split())
                rows.append((int(c), cx, cy, w, h))
        out[s] = rows
    return out


def preds_of(pj, keep):
    out = defaultdict(list)
    for r in json.loads(Path(pj).read_text()):
        s = Path(str(r["image_id"])).stem
        if s in keep:
            out[s].append((int(r["category_id"]) - 1, *r["bbox"], float(r["score"])))
    return out


def analyse(pj, ss, gt, sizes):
    paths = [YOLO_DIR / "images" / f"{s}.jpg" for s in ss]
    gtc, stem_to_id = yolo_to_coco_gt(paths, YOLO_DIR / "labels", NAMES)
    coco = coco_eval(gtc, load_predictions(pj, stem_to_id, len(NAMES)), NAMES)

    preds = preds_of(pj, set(ss))
    conf = {NAMES[k]: Counter() for k in NAMES}
    tp = fp = fn = 0
    recall = {NAMES[k]: dict({f"iou_{t}": 0 for t in IOUS}, centre=0, total=0) for k in NAMES}

    for s in ss:
        g = gt[s]
        w, h = sizes[s]
        loose = [r for r in preds.get(s, [])]
        strict = [r for r in loose if r[5] >= EVAL["report_conf"]]
        gb = np.array([[(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w,
                        (cy + bh / 2) * h] for _, cx, cy, bw, bh in g]) if g else np.zeros((0, 4))

        # recall curve at conf 0.001
        if g and loose:
            pb = np.array([[x, y, x + bw, y + bh] for _, x, y, bw, bh, _ in loose])
            pc = np.array([r[0] for r in loose])
            ious = iou_matrix(pb, gb)
            ctr = np.stack([(pb[:, 0] + pb[:, 2]) / 2, (pb[:, 1] + pb[:, 3]) / 2], 1)
        for gi, (gc, *_) in enumerate(g):
            recall[NAMES[gc]]["total"] += 1
            if not loose:
                continue
            same = pc == gc
            if not same.any():
                continue
            for t in IOUS:
                if (ious[same, gi] >= t).any():
                    recall[NAMES[gc]][f"iou_{t}"] += 1
            if ((ctr[same, 0] >= gb[gi, 0]) & (ctr[same, 0] <= gb[gi, 2])
                    & (ctr[same, 1] >= gb[gi, 1]) & (ctr[same, 1] <= gb[gi, 3])).any():
                recall[NAMES[gc]]["centre"] += 1

        # confusion + P/R at report_conf
        matched = set()
        if g and strict:
            pb = np.array([[x, y, x + bw, y + bh] for _, x, y, bw, bh, _ in strict])
            ious = iou_matrix(pb, gb)
            order = np.argsort(-np.array([r[5] for r in strict]))
            taken = set()
            for gi, (gc, *_) in enumerate(g):
                best = None
                for pi in order:
                    if pi in taken or ious[pi, gi] < 0.5:
                        continue
                    best = int(pi)
                    break
                if best is None:
                    conf[NAMES[gc]]["background"] += 1
                else:
                    taken.add(best)
                    conf[NAMES[gc]][NAMES[strict[best][0]]] += 1
                    if strict[best][0] == gc:
                        matched.add(gi)
            for pi in order:
                if pi in taken:
                    continue
                fp += 1
            tp += len(matched)
            fp += len(taken) - len(matched)
        else:
            fp += len(strict)
            for gc, *_ in g:
                conf[NAMES[gc]]["background"] += 1
        fn += len(g) - len(matched)

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {
        "map50": round(coco["map50"], 4), "map50_95": round(coco["map50_95"], 4),
        "per_class_ap50": {k: round(v["ap50"], 4) for k, v in coco["per_class"].items()},
        "per_class_instances": {k: v["instances"] for k, v in coco["per_class"].items()},
        "confusion_at_report_conf": {k: dict(v) for k, v in conf.items()},
        "pr_at_report_conf": {"precision": round(prec, 4), "recall": round(rec, 4),
                              "tp": tp, "fp": fp, "fn": fn},
        "recall_curve_conf0.001": {
            k: {kk: (round(vv / v["total"], 4) if kk != "total" and v["total"] else vv)
                for kk, vv in v.items()} for k, v in recall.items()},
    }


def main() -> int:
    ss = stems()
    gt = gt_of(ss)
    sizes = {}
    for s in ss:
        with Image.open(YOLO_DIR / "images" / f"{s}.jpg") as im:
            sizes[s] = im.size

    locked = repo_root() / "results" / "LOCKED"
    a_pj = next((locked / "A_india_full_run" / "val").glob("predictions.json"))
    b_pj = next((locked / "B_india_heldout_run" / "val").glob("predictions.json"))

    out = {"split": SPLIT, "images": len(ss), "eval_settings": EVAL,
           "A": analyse(a_pj, ss, gt, sizes), "B": analyse(b_pj, ss, gt, sizes)}
    dest = repo_root() / "results" / "T7"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "A_vs_B_india_test.json").write_text(json.dumps(out, indent=2))

    print(f"=== A vs B on {SPLIT} ({len(ss)} images), pycocotools ===")
    print(f"{'':<20}{'A':>10}{'B':>10}{'delta':>10}")
    print(f"{'mAP50':<20}{out['A']['map50']:>10.4f}{out['B']['map50']:>10.4f}"
          f"{out['B']['map50'] - out['A']['map50']:>+10.4f}")
    print(f"{'mAP50-95':<20}{out['A']['map50_95']:>10.4f}{out['B']['map50_95']:>10.4f}"
          f"{out['B']['map50_95'] - out['A']['map50_95']:>+10.4f}")
    for c in NAMES.values():
        a, b = out["A"]["per_class_ap50"][c], out["B"]["per_class_ap50"][c]
        print(f"{'  ' + c:<20}{a:>10.4f}{b:>10.4f}{b - a:>+10.4f}")
    for m in ("precision", "recall"):
        a, b = out["A"]["pr_at_report_conf"][m], out["B"]["pr_at_report_conf"][m]
        print(f"{m + ' @0.25':<20}{a:>10.4f}{b:>10.4f}{b - a:>+10.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
