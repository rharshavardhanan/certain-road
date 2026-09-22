"""D072 — Model B vs Model P on india_val, pothole only, one scorer, one eval block.

The question is narrow on purpose: **does adding BharatPotHole to india_train buy
pothole detection on Indian roads?** Overall 3-class mAP does not answer it, and
BharatPotHole's own val split cannot (D073: 107 of its 112 valid videos are in
its train split, so it measures memorisation). The only set that answers it is
`india_val`, and selection happens there alone.

Fairness is the whole design here, because B and P are not the same shape of
model and the comparison would be easy to rig by accident:

- **Ground truth is pothole-only for both**, taken from `data/yolo_pothole/labels`
  — verified to be exactly the 342 pothole boxes the 3-class labels carry for the
  same 772 stems, on byte-identical images.
- **Each model runs NMS under the class count it was trained with.** B is scored
  as a 3-class model and then filtered to its pothole channel; scoring it against
  a 1-class yaml would change its NMS and measure the harness. Cracks it emits
  are discarded rather than counted as false alarms, which is the *generous*
  reading for B.
- **One scorer.** Both prediction sets are pushed through the same pycocotools
  path against the same ground truth object, under the frozen eval block.

Reported at two operating points, because AP alone hides the trade a crew feels:
the fixed `report_conf`, and a **matched recall**, where the thresholds are moved
until both models find the same share of potholes and the only remaining
difference is how many false alarms each pays for it.
"""

import argparse
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
from certain_road.perception.metrics_coco import coco_eval, yolo_to_coco_gt  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
EVAL = CFG["eval"]
NAMES = {int(k): v for k, v in CFG["classes"].items()}
POTHOLE = int(CFG["pothole_class"])
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
POTHOLE_DIR = repo_root() / "data" / "yolo_pothole"
OUT = repo_root() / "results" / "T9"

SPLIT = "india_val"
IOU_MATCH = 0.5
MATCH_RECALL = 0.8
PONLY = {0: "pothole"}


def predictions_for(tag: str, weights: Path, root: Path, list_name: str,
                    names: dict[int, str]) -> Path:
    """Run the frozen eval block and return the predictions.json path.

    Cached: 772 images on CPU is minutes, and re-running it cannot change the
    answer. Delete the run directory to force fresh inference.
    """
    run_dir = OUT / f"{tag}_{SPLIT}_run"
    existing = next(run_dir.glob("val/predictions.json"), None) if run_dir.exists() else None
    if existing:
        print(f"{tag}: reusing {existing}", flush=True)
        return existing

    from ultralytics import YOLO

    run_dir.mkdir(parents=True, exist_ok=True)
    data_yaml = run_dir / "data.yaml"
    with open(data_yaml, "w") as fh:
        yaml.safe_dump({"path": str(root.resolve()), "train": f"{list_name}.txt",
                        "val": f"{list_name}.txt", "names": names}, fh, sort_keys=False)
    YOLO(str(weights)).val(
        data=str(data_yaml), split="val", save_json=True, plots=False,
        project=str(run_dir), name="val", exist_ok=True, verbose=False,
        conf=EVAL["conf"], iou=EVAL["iou"], max_det=EVAL["max_det"],
        imgsz=EVAL["imgsz"], rect=EVAL["rect"], half=EVAL["half"], device=EVAL["device"],
    )
    return next(run_dir.glob("val/predictions.json"))


def pothole_detections(pred_json: Path, keep: int, num_classes: int,
                       stems: set[str]) -> dict[str, list[tuple]]:
    """(x, y, w, h, score) per stem, restricted to the pothole channel.

    Ultralytics writes 1-indexed `category_id` for non-COCO data (val.py:90), so
    the pothole channel is `keep + 1`. The range is asserted rather than assumed:
    a future ultralytics that changes convention must fail loudly, not quietly
    score cracks as potholes.
    """
    raw = json.loads(pred_json.read_text())
    cats = {int(r["category_id"]) for r in raw}
    if raw and not cats <= set(range(1, num_classes + 1)):
        raise ValueError(f"category_id {sorted(cats)} outside 1..{num_classes} "
                         "(val.py:90 convention); re-check before trusting this")
    out: dict[str, list[tuple]] = defaultdict(list)
    for r in raw:
        if int(r["category_id"]) - 1 != keep:
            continue
        stem = Path(str(r["image_id"])).stem
        if stem in stems:
            out[stem].append((*[float(v) for v in r["bbox"]], float(r["score"])))
    return out


def label_by_image(dets: dict[str, list[tuple]], gt: dict[str, np.ndarray]):
    """Greedy per-image assignment in descending confidence; one GT box each.

    Kept per image rather than flattened, because the bootstrap resamples
    images: a pothole and the detection that found it have to travel together
    or the resampled recall is meaningless.
    """
    out: dict[str, list[tuple[float, bool]]] = {}
    for stem, boxes in gt.items():
        d = sorted(dets.get(stem, []), key=lambda r: -r[4])
        if not d:
            out[stem] = []
            continue
        ious = (iou_matrix(np.array([[x, y, x + w, y + h] for x, y, w, h, _ in d]), boxes)
                if len(boxes) else None)
        taken: set[int] = set()
        rows = []
        for i, rec in enumerate(d):
            hit = False
            if ious is not None:
                for gi in np.argsort(-ious[i]):
                    if ious[i, gi] < IOU_MATCH:
                        break
                    if int(gi) not in taken:
                        taken.add(int(gi))
                        hit = True
                        break
            rows.append((rec[4], hit))
        out[stem] = rows
    return out


def label_detections(dets: dict[str, list[tuple]], gt: dict[str, np.ndarray]):
    """Flattened, confidence-descending view of `label_by_image`."""
    labelled = [r for rows in label_by_image(dets, gt).values() for r in rows]
    labelled.sort(key=lambda t: -t[0])
    return labelled


def ap50_from_labels(per_image: dict[str, list], n_gt: int, max_det: int = 100) -> float:
    """COCO-style 101-point interpolated AP at IoU 0.5, from matched detections.

    pycocotools cannot bootstrap: resampling images produces duplicate image ids
    it will not accept. So AP is recomputed here, and the self-check asserts this
    reproduces the pycocotools number on the full sample before any resampled
    number is believed. `max_det` mirrors COCOeval's per-image cap of 100.
    """
    c = _curve(per_image, n_gt, 1, max_det)
    return 0.0 if c is None else _ap(c[0], c[2])


def _curve(per_image: dict[str, list], n_gt: int, n_images: int, max_det: int = 100):
    """(recall, false-alarms-per-image, precision) arrays, confidence descending."""
    rows = [r for v in per_image.values() for r in v[:max_det]]
    if not rows or n_gt == 0:
        return None
    rows.sort(key=lambda t: -t[0])
    hits = np.array([h for _, h in rows], dtype=float)
    tp, fp = np.cumsum(hits), np.cumsum(1.0 - hits)
    return tp / n_gt, fp / n_images, tp / np.maximum(tp + fp, 1e-12)


def _ap(recall: np.ndarray, precision: np.ndarray) -> float:
    precision = np.maximum.accumulate(precision[::-1])[::-1]
    grid = np.linspace(0, 1, 101)
    idx = np.searchsorted(recall, grid, side="left")
    take = idx < len(precision)
    out = np.zeros(101)
    out[take] = precision[idx[take]]
    return float(out.mean())


def _fa_at(recall: np.ndarray, fa: np.ndarray, target: float) -> float | None:
    hit = np.nonzero(recall >= target)[0]
    return float(fa[hit[0]]) if len(hit) else None


def bootstrap_delta(b_img: dict, p_img: dict, gt_counts: dict[str, int],
                    stems: list[str], recalls: list[float],
                    draws: int = 2000, seed: int = 0) -> dict:
    """Paired bootstrap over images: pothole AP50, and false alarms at matched recall.

    Paired and over *images*: both models are scored on the same resampled
    india_val each draw, so the shared difficulty of a hard image cancels and
    what is left is the difference between the models. 342 pothole boxes is not
    many, and a gap that does not clear its own resampling noise is not a reason
    to prefer either model.

    False alarms at matched recall get the same treatment as AP, because the
    recommendation rests on them. Reporting one difference with an interval and
    the other bare would be choosing which number gets scrutinised.
    """
    rng = np.random.default_rng(seed)
    n = len(stems)
    ap_delta = np.empty(draws)
    fa_delta: dict[float, list[float]] = {r: [] for r in recalls}
    for d in range(draws):
        pick = [stems[i] for i in rng.integers(0, n, n)]
        n_gt = sum(gt_counts[s] for s in pick)
        bi = {f"{s}#{k}": b_img[s] for k, s in enumerate(pick)}
        pi = {f"{s}#{k}": p_img[s] for k, s in enumerate(pick)}
        bc, pc = _curve(bi, n_gt, n), _curve(pi, n_gt, n)
        if bc is None or pc is None:
            ap_delta[d] = 0.0
            continue
        ap_delta[d] = _ap(pc[0], pc[2]) - _ap(bc[0], bc[2])
        for r in recalls:
            fb, fp_ = _fa_at(bc[0], bc[1], r), _fa_at(pc[0], pc[1], r)
            if fb is not None and fp_ is not None:
                fa_delta[r].append(fp_ - fb)

    def summary(v: np.ndarray, favour_negative: bool) -> dict:
        lo, hi = np.percentile(v, [2.5, 97.5])
        share = float((v < 0).mean()) if favour_negative else float((v > 0).mean())
        return {"draws": int(len(v)), "mean_delta": round(float(v.mean()), 4),
                "ci95": [round(float(lo), 4), round(float(hi), 4)],
                "share_favouring_P": round(share, 4),
                "separates_from_zero": bool(lo > 0 or hi < 0)}

    return {"pothole_ap50": summary(ap_delta, favour_negative=False),
            # Fewer false alarms is better, so a NEGATIVE delta favours P.
            "false_alarms_at_matched_recall": {
                f"{r:.1f}": summary(np.array(fa_delta[r]), favour_negative=True)
                for r in recalls if fa_delta[r]}}


def sweep(labelled, n_gt: int, n_images: int) -> np.ndarray:
    """rows of (score, recall, false_alarms_per_image), confidence descending."""
    if not labelled:
        return np.zeros((0, 3))
    scores = np.array([s for s, _ in labelled])
    hits = np.array([h for _, h in labelled], dtype=float)
    tp = np.cumsum(hits)
    fp = np.cumsum(1.0 - hits)
    return np.stack([scores, tp / n_gt, fp / n_images], axis=1)


def at_conf(rows: np.ndarray, conf: float) -> dict:
    keep = rows[rows[:, 0] >= conf]
    if not len(keep):
        return {"conf": conf, "recall": 0.0, "false_alarms_per_image": 0.0, "detections": 0}
    return {"conf": conf, "recall": round(float(keep[-1, 1]), 4),
            "false_alarms_per_image": round(float(keep[-1, 2]), 4),
            "detections": int(len(keep))}


def at_recall(rows: np.ndarray, target: float) -> dict:
    hit = np.nonzero(rows[:, 1] >= target)[0]
    if not len(hit):
        best = float(rows[-1, 1]) if len(rows) else 0.0
        return {"target_recall": target, "reachable": False,
                "max_recall": round(best, 4),
                "false_alarms_per_image_at_max_recall":
                    round(float(rows[-1, 2]), 4) if len(rows) else 0.0}
    i = int(hit[0])
    return {"target_recall": target, "reachable": True,
            "conf": round(float(rows[i, 0]), 4), "recall": round(float(rows[i, 1]), 4),
            "false_alarms_per_image": round(float(rows[i, 2]), 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b-weights", required=True, type=Path)
    ap.add_argument("--p-weights", required=True, type=Path)
    args = ap.parse_args()

    stems = [Path(x).stem for x in (YOLO_DIR / f"{SPLIT}.txt").read_text().split() if x.strip()]
    keep = set(stems)
    OUT.mkdir(parents=True, exist_ok=True)

    # One ground truth object for both models: pothole-only, 0-indexed.
    paths = [POTHOLE_DIR / "images" / f"{s}.jpg" for s in stems]
    gt_coco, stem_to_id = yolo_to_coco_gt(paths, POTHOLE_DIR / "labels", PONLY)

    gt_boxes: dict[str, np.ndarray] = {}
    n_gt = 0
    for s in stems:
        with Image.open(POTHOLE_DIR / "images" / f"{s}.jpg") as im:
            w, h = im.size
        rows = []
        lab = POTHOLE_DIR / "labels" / f"{s}.txt"
        for line in lab.read_text().splitlines() if lab.exists() else []:
            if line.strip():
                _, cx, cy, bw, bh = map(float, line.split())
                rows.append([(cx - bw / 2) * w, (cy - bh / 2) * h,
                             (cx + bw / 2) * w, (cy + bh / 2) * h])
        gt_boxes[s] = np.array(rows) if rows else np.zeros((0, 4))
        n_gt += len(rows)

    spec = {
        "B": (args.b_weights, YOLO_DIR, SPLIT, NAMES, POTHOLE),
        "P": (args.p_weights, POTHOLE_DIR, "p_val", PONLY, 0),
    }
    report = {"split": SPLIT, "images": len(stems), "pothole_instances": n_gt,
              "eval_settings": EVAL, "iou_match": IOU_MATCH,
              "gt": "pothole-only, data/yolo_pothole/labels", "models": {}}

    conf_key = f"at_conf_{EVAL['report_conf']}"
    recall_key = f"at_recall_{MATCH_RECALL}"
    curves, per_image = {}, {}
    gt_counts = {s: int(len(gt_boxes[s])) for s in stems}
    for tag, (weights, root, list_name, names, channel) in spec.items():
        pj = predictions_for(tag, weights, root, list_name, names)
        dets = pothole_detections(pj, channel, len(names), keep)
        coco_preds = [{"image_id": stem_to_id[s], "category_id": 0,
                       "bbox": list(b[:4]), "score": b[4]}
                      for s, bs in dets.items() for b in bs]
        coco = coco_eval(gt_coco, coco_preds, PONLY)
        per_image[tag] = label_by_image(dets, gt_boxes)
        curves[tag] = sweep(label_detections(dets, gt_boxes), n_gt, len(stems))

        # The bootstrap uses our own AP. It is only trustworthy if it reproduces
        # pycocotools on the full sample, so that is checked, not assumed.
        own = ap50_from_labels(per_image[tag], n_gt)
        ref = coco["per_class"]["pothole"]["ap50"]
        report["models"][tag] = {
            "weights": str(weights),
            "pothole_ap50": round(ref, 4),
            "pothole_ap50_95": round(coco["per_class"]["pothole"]["ap50_95"], 4),
            "ap50_self_check": {"own": round(own, 4), "pycocotools": round(ref, 4),
                                "abs_delta": round(abs(own - ref), 4),
                                "ok": abs(own - ref) <= 0.01},
            "total_detections": int(sum(len(v) for v in dets.values())),
            conf_key: at_conf(curves[tag], EVAL["report_conf"]),
            recall_key: at_recall(curves[tag], MATCH_RECALL),
        }

    # Recall 0.8 may be out of reach for either model. A comparison at a recall
    # only one of them can hit is not a comparison, so also report the highest
    # recall BOTH reach, where the false-alarm difference is the whole story.
    both_max = min(float(c[-1, 1]) if len(c) else 0.0 for c in curves.values())
    report["highest_recall_both_reach"] = round(both_max, 4)
    for tag in spec:
        report["models"][tag]["at_highest_common_recall"] = at_recall(curves[tag], both_max)

    # A single matched recall can flatter either model if the curves cross, and
    # on this data they do. The grid shows where, so the choice is made against
    # the operating point a crew would actually run at.
    grid = [r for r in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9) if r <= both_max]
    report["false_alarms_per_image_at_matched_recall"] = {
        f"{r:.1f}": {t: at_recall(curves[t], r).get("false_alarms_per_image")
                     for t in spec} for r in grid}

    report["bootstrap_P_minus_B"] = bootstrap_delta(
        per_image["B"], per_image["P"], gt_counts, stems, grid)

    (OUT / "B_vs_P_india_val.json").write_text(json.dumps(report, indent=2))

    b, p = report["models"]["B"], report["models"]["P"]
    print(f"\n=== B vs P on {SPLIT}, pothole only "
          f"({len(stems)} images, {n_gt} pothole boxes) ===")
    print(f"{'':<34}{'B':>10}{'P':>10}{'delta':>10}")
    for key, label in (("pothole_ap50", "pothole AP50"),
                       ("pothole_ap50_95", "pothole AP50-95")):
        print(f"{label:<34}{b[key]:>10.4f}{p[key]:>10.4f}{p[key] - b[key]:>+10.4f}")
    for m in ("recall", "false_alarms_per_image"):
        bv, pv = b[conf_key][m], p[conf_key][m]
        label = f"{m} @conf {EVAL['report_conf']}"
        print(f"{label:<34}{bv:>10.4f}{pv:>10.4f}{pv - bv:>+10.4f}")
    rk = recall_key
    print(f"\nmatched recall {MATCH_RECALL}: "
          f"B {'reachable' if b[rk]['reachable'] else 'NOT reachable'}, "
          f"P {'reachable' if p[rk]['reachable'] else 'NOT reachable'}")
    print(json.dumps({"B": b[rk], "P": p[rk]}, indent=2))
    print("\nfalse alarms per image at matched recall:")
    print(f"{'recall':<12}{'B':>10}{'P':>10}{'P - B':>10}")
    for r, vals in report["false_alarms_per_image_at_matched_recall"].items():
        bb, pp = vals["B"], vals["P"]
        print(f"{r:<12}{bb:>10.3f}{pp:>10.3f}{pp - bb:>+10.3f}")

    bs = report["bootstrap_P_minus_B"]
    ap = bs["pothole_ap50"]
    print(f"\npaired bootstrap over images, {ap['draws']} draws (P - B):")
    print(f"  pothole AP50   {ap['mean_delta']:+.4f}  95% CI "
          f"[{ap['ci95'][0]:+.4f}, {ap['ci95'][1]:+.4f}]  P ahead "
          f"{ap['share_favouring_P']:.1%}  separates={ap['separates_from_zero']}")
    print("  false alarms/image at matched recall (negative favours P):")
    for r, v in bs["false_alarms_at_matched_recall"].items():
        print(f"    recall {r}  {v['mean_delta']:+.3f}  95% CI "
              f"[{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}]  P ahead "
              f"{v['share_favouring_P']:.1%}  separates={v['separates_from_zero']}")
    for t in ("B", "P"):
        c = report["models"][t]["ap50_self_check"]
        print(f"  AP50 self-check {t}: own {c['own']:.4f} vs pycocotools "
              f"{c['pycocotools']:.4f} (delta {c['abs_delta']:.4f}, ok={c['ok']})")

    print(f"\nhighest recall both reach: {both_max:.4f}")
    print(json.dumps({"B": b["at_highest_common_recall"],
                      "P": p["at_highest_common_recall"]}, indent=2))
    print(f"\nwritten: {OUT / 'B_vs_P_india_val.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
