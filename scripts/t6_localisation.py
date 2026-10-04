"""T6 follow-up — is the India gap blindness, or boxes in the wrong place?

The confusion matrix showed ~91% of India potholes matching nothing at IoU 0.5,
and the T6 narrative called that "doesn't see them". That conclusion does not
follow from IoU-0.5 matching alone: a prediction sitting on the right damage but
drawn to a different convention - a whole cracked stretch versus each crack, a
tight pothole versus its wet halo - fails at 0.5 while being a perfectly useful
detection.

Loosening the matching threshold separates the two. If recall climbs steeply from
IoU 0.5 to 0.1, the model is finding damage and disagreeing about extent. If it
stays flat, nothing is there to localise and blindness is the right word.

Centre-hit is the loosest useful test: is the prediction's centre inside the GT
box at all? It ignores extent entirely.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.assess.conformal import iou_matrix  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
NAMES = {int(k): v for k, v in CFG["classes"].items()}
IOUS = [0.1, 0.3, 0.5]
CONFS = [0.25, 0.001]


def stems_of(split):
    return [Path(x).stem for x in (YOLO_DIR / f"{split}.txt").read_text().splitlines() if x.strip()]


def gt_of(stems):
    out = {}
    for s in stems:
        rows = []
        for line in (YOLO_DIR / "labels" / f"{s}.txt").read_text().splitlines():
            if line.strip():
                c, cx, cy, w, h = map(float, line.split())
                rows.append((int(c), cx, cy, w, h))
        out[s] = rows
    return out


def preds_of(pred_json):
    out = defaultdict(list)
    for r in json.loads(Path(pred_json).read_text()):
        out[Path(str(r["image_id"])).stem].append(
            (int(r["category_id"]) - 1, *r["bbox"], float(r["score"]))
        )
    return out


def recall_table(stems, gt, preds, sizes):
    """Per class: recall at each IoU and by centre-hit, at each confidence."""
    result = {}
    for conf in CONFS:
        per_class = {
            NAMES[c]: dict({f"iou_{t}": 0 for t in IOUS}, centre=0, total=0) for c in NAMES
        }
        for s in stems:
            g = gt[s]
            if not g:
                continue
            w, h = sizes[s]
            p = [r for r in preds.get(s, []) if r[5] >= conf]
            gb = np.array(
                [
                    [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]
                    for _, cx, cy, bw, bh in g
                ]
            )
            gcls = np.array([r[0] for r in g])
            if p:
                pb = np.array([[x, y, x + bw, y + bh] for _, x, y, bw, bh, _ in p])
                pcls = np.array([r[0] for r in p])
                ious = iou_matrix(pb, gb)
                centres = np.stack([(pb[:, 0] + pb[:, 2]) / 2, (pb[:, 1] + pb[:, 3]) / 2], 1)
            for gi in range(len(g)):
                name = NAMES[int(gcls[gi])]
                per_class[name]["total"] += 1
                if not p:
                    continue
                same = pcls == gcls[gi]
                if not same.any():
                    continue
                for t in IOUS:
                    if (ious[same, gi] >= t).any():
                        per_class[name][f"iou_{t}"] += 1
                inside = (
                    (centres[same, 0] >= gb[gi, 0])
                    & (centres[same, 0] <= gb[gi, 2])
                    & (centres[same, 1] >= gb[gi, 1])
                    & (centres[same, 1] <= gb[gi, 3])
                )
                if inside.any():
                    per_class[name]["centre"] += 1
        result[f"conf_{conf}"] = {
            k: {
                kk: (round(vv / v["total"], 4) if kk != "total" and v["total"] else vv)
                for kk, vv in v.items()
            }
            for k, v in per_class.items()
        }
    return result


def box_stats(stems, gt, sizes):
    """GT geometry per class - the thing an annotation convention would change."""
    areas = defaultdict(list)
    aspects = defaultdict(list)
    per_image = []
    crowded = defaultdict(int)
    for s in stems:
        g = gt[s]
        per_image.append(len(g))
        counts = defaultdict(int)
        for c, _cx, _cy, bw, bh in g:
            areas[NAMES[c]].append(bw * bh)  # already relative to the image
            aspects[NAMES[c]].append(bw / bh if bh > 0 else 0.0)
            counts[c] += 1
        for c, n in counts.items():
            if n >= 3:
                crowded[NAMES[c]] += 1
    out = {}
    for name in NAMES.values():
        a = np.array(areas[name]) if areas[name] else np.array([0.0])
        r = np.array(aspects[name]) if aspects[name] else np.array([0.0])
        out[name] = {
            "n": len(areas[name]),
            "rel_area_median": round(float(np.median(a)), 5),
            "rel_area_iqr": [
                round(float(np.percentile(a, 25)), 5),
                round(float(np.percentile(a, 75)), 5),
            ],
            "aspect_median": round(float(np.median(r)), 3),
            "aspect_iqr": [
                round(float(np.percentile(r, 25)), 3),
                round(float(np.percentile(r, 75)), 3),
            ],
            "images_with_3plus": crowded[name],
            "share_images_3plus": round(crowded[name] / len(stems), 4),
        }
    out["_boxes_per_image_mean"] = round(float(np.mean(per_image)), 3)
    return out


def main() -> int:
    non_dir = repo_root() / "results" / "T6_A_nonindia_val" / "val"
    ind_dir = repo_root() / "results" / "LOCKED" / "A_india_full_run" / "val"
    non_pred = next(non_dir.glob("predictions.json"))
    ind_pred = next(ind_dir.glob("predictions.json"))

    report = {"ious": IOUS, "confs": CONFS}
    for tag, split, pj in (
        ("nonindia_val", "nonindia_val", non_pred),
        ("india_full", "india_full", ind_pred),
    ):
        print(f"analysing {tag} ...", flush=True)
        stems = stems_of(split)
        gt = gt_of(stems)
        sizes = {}
        for s in stems:
            with Image.open(YOLO_DIR / "images" / f"{s}.jpg") as im:
                sizes[s] = im.size
        preds = preds_of(pj)
        report[tag] = {
            "recall": recall_table(stems, gt, preds, sizes),
            "gt_box_stats": box_stats(stems, gt, sizes),
        }

    out = repo_root() / "results" / "T6"
    (out / "localisation.json").write_text(json.dumps(report, indent=2))
    for tag in ("nonindia_val", "india_full"):
        print(f"\n=== {tag} recall @ conf 0.25 ===")
        for c, v in report[tag]["recall"]["conf_0.25"].items():
            print(
                f"  {c:<18} IoU.5 {v['iou_0.5']:.3f}  IoU.3 {v['iou_0.3']:.3f}  "
                f"IoU.1 {v['iou_0.1']:.3f}  centre {v['centre']:.3f}  n={v['total']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
