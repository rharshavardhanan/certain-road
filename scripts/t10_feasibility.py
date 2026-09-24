"""T10 feasibility — what miss rate can conformal risk control actually certify?

CRC returns the largest tau whose bound holds. If even tau = 0.001 — keeping
every prediction the detector emits — misses more than alpha of the potholes,
**no tau satisfies the bound and the procedure correctly returns nothing.**

That floor is a property of the detector on that domain, not of the conformal
machinery. Computing it first turns "CRC failed" into "CRC cannot certify below
X here, and here is X", which is a result rather than a bug report.

Run before any India conformal experiment so the alpha grid is chosen from the
feasible range instead of from habit.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.assess.conformal import (  # noqa: E402
    crc_threshold,
    empirical_risk,
    matched_confidences,
)
from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
POTHOLE = CFG["pothole_class"]
IOU = CFG["conformal"]["iou"]
TAU_STEP = CFG["conformal"]["tau_step"]
# The loosest threshold the search may consider. It must equal the grid's first
# step, or the floor is computed somewhere the curve can never reach.
FLOOR_TAU = TAU_STEP


def per_image_matched(split, pred_json, channel=POTHOLE):
    """Matched confidence per GT pothole, for images that contain one.

    `channel` is the model's pothole class index, which is not the same number
    for every model: the 3-class models emit pothole as index 2, Model P is a
    1-class detector and emits it as index 0. Ground truth is always read from
    the 3-class labels and filtered to `POTHOLE`, so all models are measured
    against identical potholes.
    """
    preds = defaultdict(list)
    for r in json.loads(Path(pred_json).read_text()):
        if int(r["category_id"]) - 1 == channel:
            preds[Path(str(r["image_id"])).stem].append((*r["bbox"], float(r["score"])))

    out = []
    for line in (YOLO_DIR / f"{split}.txt").read_text().splitlines():
        if not line.strip():
            continue
        s = Path(line).stem
        label_lines = (YOLO_DIR / "labels" / f"{s}.txt").read_text().splitlines()
        rows = [ln.split() for ln in label_lines if ln.strip()]
        g = [tuple(map(float, r[1:])) for r in rows if int(r[0]) == POTHOLE]
        if not g:
            continue
        with Image.open(YOLO_DIR / "images" / f"{s}.jpg") as im:
            w, h = im.size
        gb = np.array([[(cx - bw / 2) * w, (cy - bh / 2) * h,
                        (cx + bw / 2) * w, (cy + bh / 2) * h] for cx, cy, bw, bh in g])
        p = preds.get(s, [])
        if p:
            pb = np.array([[x, y, x + bw, y + bh] for x, y, bw, bh, _ in p])
            sc = np.array([r[4] for r in p])
        else:
            pb, sc = np.zeros((0, 4)), np.zeros(0)
        out.append(matched_confidences(gb, pb, sc, iou_threshold=IOU))
    return out


def main() -> int:
    locked = repo_root() / "results" / "LOCKED"
    sources = {
        "A_nonindia_val": ("nonindia_val",
                           next((repo_root() / "results" / "T6_A_nonindia_val" / "val")
                                .glob("predictions.json"))),
        "A_india_cal": ("india_cal", next((locked / "A_india_full_run" / "val")
                                          .glob("predictions.json"))),
        "A_india_test": ("india_test", next((locked / "A_india_full_run" / "val")
                                            .glob("predictions.json"))),
        "B_india_cal": ("india_cal", next((locked / "B_india_heldout_run" / "val")
                                          .glob("predictions.json"))),
        "B_india_test": ("india_test", next((locked / "B_india_heldout_run" / "val")
                                            .glob("predictions.json"))),
        "P_india_cal": ("india_cal", next((locked / "P_india_heldout_run" / "val")
                                          .glob("predictions.json"))),
        "P_india_test": ("india_test", next((locked / "P_india_heldout_run" / "val")
                                            .glob("predictions.json"))),
    }
    # Model P is 1-class; its pothole channel is 0, not 2.
    channels = {"P_india_cal": 0, "P_india_test": 0}

    report = {"iou": IOU, "floor_tau": FLOOR_TAU, "sources": {}}
    matched = {}
    for tag, (split, pj) in sources.items():
        print(f"{tag} ...", flush=True)
        m = per_image_matched(split, pj, channels.get(tag, POTHOLE))
        matched[tag] = m
        floor = empirical_risk(m, FLOOR_TAU)
        n = len(m)
        report["sources"][tag] = {
            "split": split, "images_with_pothole": n,
            "miss_rate_floor": round(floor, 4),
            "finite_sample_floor": round((floor * n + 1) / (n + 1), 4),
            "min_certifiable_alpha": round((floor * n + 1) / (n + 1), 4),
        }
        print(f"   floor {floor:.4f}  min certifiable alpha "
              f"{(floor * n + 1) / (n + 1):.4f}  (n={n})", flush=True)

    # Risk vs alpha across the whole feasible range, not a fixed habit list.
    # The tau grid must start at FLOOR_TAU. It used to start at 0.01 while the
    # floor was measured at 0.001, and risk climbs steeply in between - 0.0827
    # to 0.2198 for B on india_cal. The curve therefore reported a minimum
    # feasible alpha of 0.24 while the floor table in the same artifact said
    # 0.087. Both were printed, and they disagreed. `tau_step` was already in
    # configs/project.yaml; the grid simply ignored it.
    grid = np.arange(TAU_STEP, 1.0, TAU_STEP)
    curves = {}
    for tag in ("A", "B", "P"):
        cal, test = matched.get(f"{tag}_india_cal"), matched.get(f"{tag}_india_test")
        if not cal or not test:
            continue
        rows = []
        for alpha in np.arange(0.02, 0.96, 0.02):
            tau = crc_threshold(cal, float(alpha), grid)
            rows.append({"alpha": round(float(alpha), 3),
                         "tau": None if tau is None else round(tau, 3),
                         "test_risk": None if tau is None else round(empirical_risk(test, tau), 4),
                         "feasible": tau is not None})
        curves[f"{tag}_india_cal_to_test"] = rows
        feas = [r for r in rows if r["feasible"]]
        # The curve steps alpha coarsely; resolve the boundary finely so the
        # reported range is the real one, not the first coarse step past it.
        fine = None
        for a in np.arange(0.01, 1.0, 0.002):
            if crc_threshold(cal, float(a), grid) is not None:
                fine = round(float(a), 3)
                break
        floor_alpha = report["sources"][f"{tag}_india_cal"]["min_certifiable_alpha"]
        report["sources"][f"{tag}_india_cal"]["feasible_from_alpha"] = fine
        print(f"\n{tag}: feasible from alpha {fine} (floor predicts {floor_alpha}); "
              f"{len(rows) - len(feas)}/{len(rows)} coarse alphas infeasible")

    # The violation: calibrate on non-India, deploy on India.
    non = matched["A_nonindia_val"]
    viol = []
    for alpha in (0.05, 0.10, 0.20, 0.30, 0.50):
        tau = crc_threshold(non, alpha, grid)
        viol.append({"alpha": alpha, "tau_from_nonindia": None if tau is None else round(tau, 3),
                     "risk_on_nonindia": None if tau is None
                     else round(empirical_risk(non, tau), 4),
                     "risk_on_india_test": None if tau is None else
                     round(empirical_risk(matched["A_india_test"], tau), 4)})
    report["risk_vs_alpha"] = curves
    report["transfer_violation_A"] = viol

    out = repo_root() / "results" / "T10"
    out.mkdir(parents=True, exist_ok=True)
    (out / "feasibility.json").write_text(json.dumps(report, indent=2))
    print("\n=== A calibrated on non-India, evaluated on india_test ===")
    for v in viol:
        print(f"  alpha {v['alpha']:.2f}  tau {v['tau_from_nonindia']}  "
              f"risk nonIN {v['risk_on_nonindia']}  risk India {v['risk_on_india_test']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
