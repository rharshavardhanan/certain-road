"""T10 — conformal risk control on the pothole miss rate, from locked predictions.

Four calibration cases, one test set:

  * **A, calibrated on non-India** (`nonindia_val`, open) -> `india_test`. The
    shift case. The certificate is issued on one domain and spent on another,
    which is exactly where exchangeability fails and the bound should break.
  * **A, calibrated on `india_cal`** -> `india_test`. Exchangeable, but A barely
    finds Indian potholes: its floor is 0.64 (D070), so most alphas are
    infeasible and are reported as `None`, never as a failure of the method.
  * **B, calibrated on `india_cal`** -> `india_test`. The certified India result
    the spec names. Its floor is 0.087 (D076).
  * **P, calibrated on `india_cal`** -> `india_test`. Reported alongside because
    D074 carries P forward; it is not the headline.

Every number comes from predictions already locked or already open. Nothing is
re-run and no model decision is made here, so nothing can be tuned against the
result.

**The guarantee is marginal.** CRC promises that *expected* test risk is at most
alpha over the draw of calibration and test data. A single split may land above
alpha and still be consistent with it. So the check is the mean over 200
re-partitions of `india_cal U india_test`, and the re-partitions permute **scene
groups** rather than images (D064) — shuffling images would split near-duplicate
frames across the halves, make them more alike than independent samples, and
make the guarantee look slightly better than it is.

**The certificate says nothing about false alarms.** At tight alpha the
certified threshold is ~0.001, where D074 measured tens of false alarms per
image. So false alarms per image at tau-hat are reported next to every certified
risk. A threshold that meets its miss-rate promise while flagging thirty phantom
potholes a frame is certified and useless, and the table must say so.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from certain_road.assess.conformal import (  # noqa: E402
    crc_threshold,
    default_tau_grid,
    empirical_risk,
    instance_miss_rate,
    matched_confidences,
)
from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
C = CFG["conformal"]
ALPHAS = [float(a) for a in C["alphas"]]
IOU = float(C["iou"])
N_RESAMPLES = int(C["n_resamples"])
TAU_GRID = default_tau_grid(float(C["tau_step"]))
CURVE_ALPHAS = np.round(np.arange(C["curve_alpha_step"], 0.96 + 1e-9, C["curve_alpha_step"]), 3)
POTHOLE = int(CFG["pothole_class"])
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
LOCKED = repo_root() / "results" / "LOCKED"
GROUPS = repo_root() / "results" / "T2" / "india_scene_groups.json"
OUT = repo_root() / "results" / "T10"


def stems_of(split: str) -> list[str]:
    return [Path(x).stem for x in (YOLO_DIR / f"{split}.txt").read_text().split() if x.strip()]


def load_records(pred_json: Path, channel: int, stems: list[str]) -> dict[str, tuple]:
    """Per image: (matched confidence per GT pothole, sorted pothole-channel scores).

    `channel` is the model's own pothole index — 2 for the 3-class models, 0 for
    Model P. Ground truth is always the 3-class labels filtered to `POTHOLE`, so
    every model is measured against the same potholes.

    Keeping the sorted scores alongside the matches is what makes false alarms
    exact at any tau: greedy matching is prefix-consistent in confidence, so the
    GT matched at tau are precisely those with matched confidence >= tau, and
    everything else kept at tau is a false alarm.
    """
    preds: dict[str, list] = defaultdict(list)
    for r in json.loads(pred_json.read_text()):
        if int(r["category_id"]) - 1 == channel:
            preds[Path(str(r["image_id"])).stem].append((*r["bbox"], float(r["score"])))

    out = {}
    for s in stems:
        with Image.open(YOLO_DIR / "images" / f"{s}.jpg") as im:
            w, h = im.size
        gt = []
        for row in (YOLO_DIR / "labels" / f"{s}.txt").read_text().splitlines():
            parts = row.split()
            if parts and int(parts[0]) == POTHOLE:
                cx, cy, bw, bh = map(float, parts[1:])
                gt.append(
                    [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]
                )
        p = preds.get(s, [])
        pb = np.array([[x, y, x + bw, y + bh] for x, y, bw, bh, _ in p]) if p else np.zeros((0, 4))
        sc = np.array([r[4] for r in p]) if p else np.zeros(0)
        g = np.array(gt) if gt else np.zeros((0, 4))
        out[s] = (matched_confidences(g, pb, sc, iou_threshold=IOU), np.sort(sc))
    return out


def with_potholes(records: dict, stems) -> list[np.ndarray]:
    """The loss is defined per image with >= 1 GT pothole; others carry no risk."""
    return [records[s][0] for s in stems if len(records[s][0])]


def false_alarms_per_image(records: dict, stems, tau: float) -> float:
    total = 0
    for s in stems:
        matched, scores = records[s]
        kept = len(scores) - int(np.searchsorted(scores, tau, side="left"))
        total += kept - int(np.sum(matched >= tau))
    return total / len(stems) if stems else 0.0


def evaluate(cal_recs, cal_stems, test_recs, test_stems, alpha: float) -> dict:
    cal = with_potholes(cal_recs, cal_stems)
    test = with_potholes(test_recs, test_stems)
    tau = crc_threshold(cal, alpha, TAU_GRID)
    row = {"alpha": alpha, "n_cal": len(cal), "n_test": len(test), "feasible": tau is not None}
    if tau is None:
        return row | {
            "tau": None,
            "test_risk": None,
            "instance_miss_rate": None,
            "false_alarms_per_image": None,
        }
    return row | {
        "tau": round(tau, 4),
        "test_risk": round(empirical_risk(test, tau), 4),
        "instance_miss_rate": round(instance_miss_rate(test, tau), 4),
        "false_alarms_per_image": round(false_alarms_per_image(test_recs, test_stems, tau), 3),
    }


def scene_units(pool: list[str]) -> list[list[str]]:
    groups = json.loads(GROUPS.read_text())["groups"]
    keep, seen, units = set(pool), set(), []
    for members in groups.values():
        unit = [m for m in members if m in keep]
        if unit:
            units.append(unit)
            seen.update(unit)
    return units + [[s] for s in pool if s not in seen]


def repartition(units: list[list[str]], n_cal: int, rng: np.random.Generator):
    """Fill the calibration half with whole scene groups until it reaches n_cal."""
    cal, test = [], []
    for i in rng.permutation(len(units)):
        (cal if len(cal) < n_cal else test).extend(units[i])
    return cal, test


def main() -> int:
    cal_stems, test_stems = stems_of("india_cal"), stems_of("india_test")
    non_stems = stems_of("nonindia_val")
    pool = cal_stems + test_stems

    sources = {
        "A_nonindia": (
            repo_root() / "results/T6_A_nonindia_val/val/predictions.json",
            POTHOLE,
            non_stems,
        ),
        "A": (LOCKED / "A_india_full_run/val/predictions.json", POTHOLE, pool),
        "B": (LOCKED / "B_india_heldout_run/val/predictions.json", POTHOLE, pool),
        "P": (LOCKED / "P_india_heldout_run/val/predictions.json", 0, pool),
    }
    recs = {}
    for tag, (pj, channel, stems) in sources.items():
        print(f"matching {tag} ({len(stems)} images) ...", flush=True)
        recs[tag] = load_records(pj, channel, stems)

    units = scene_units(pool)
    where = {s: "cal" for s in cal_stems} | {s: "test" for s in test_stems}
    crossing = sum(1 for u in units if len({where[s] for s in u}) > 1)
    print(
        f"scene units over cal U test: {len(units)} "
        f"({sum(len(u) > 1 for u in units)} multi-image); "
        f"groups crossing the original cal/test split: {crossing}",
        flush=True,
    )

    # (label, calibration records, calibration stems, test records)
    cases = {
        "A_nonindia_to_test": (recs["A_nonindia"], non_stems, recs["A"]),
        "A_india_cal_to_test": (recs["A"], cal_stems, recs["A"]),
        "B_india_cal_to_test": (recs["B"], cal_stems, recs["B"]),
        "P_india_cal_to_test": (recs["P"], cal_stems, recs["P"]),
    }

    report: dict = {
        "iou": IOU,
        "tau_grid": [float(TAU_GRID[0]), float(TAU_GRID[-1]), float(C["tau_step"])],
        "alphas": ALPHAS,
        "n_resamples": N_RESAMPLES,
        "resampling_unit": "scene group (D064)",
        "scene_units": len(units),
        "groups_crossing_split": crossing,
        "cases": {},
    }

    for name, (cal_recs, cal_s, test_recs) in cases.items():
        table = [evaluate(cal_recs, cal_s, test_recs, test_stems, a) for a in ALPHAS]
        curve = [evaluate(cal_recs, cal_s, test_recs, test_stems, float(a)) for a in CURVE_ALPHAS]
        report["cases"][name] = {
            "table": table,
            "curve": [{k: r[k] for k in ("alpha", "tau", "test_risk")} for r in curve],
        }

    # --- 200 group-aware re-partitions ------------------------------------
    rng = np.random.default_rng(0)
    n_cal = len(cal_stems)
    # A's non-India threshold is fixed: its calibration set does not move.
    tau_non = {
        a: crc_threshold(with_potholes(recs["A_nonindia"], non_stems), a, TAU_GRID) for a in ALPHAS
    }
    draws: dict = {name: {a: [] for a in ALPHAS} for name in cases}
    sizes = []
    for _ in range(N_RESAMPLES):
        cal_d, test_d = repartition(units, n_cal, rng)
        sizes.append((len(cal_d), len(with_potholes(recs["B"], cal_d))))
        for a in ALPHAS:
            t = tau_non[a]
            draws["A_nonindia_to_test"][a].append(
                None if t is None else empirical_risk(with_potholes(recs["A"], test_d), t)
            )
            for tag in ("A", "B", "P"):
                cal = with_potholes(recs[tag], cal_d)
                tau = crc_threshold(cal, a, TAU_GRID)
                draws[f"{tag}_india_cal_to_test"][a].append(
                    None if tau is None else empirical_risk(with_potholes(recs[tag], test_d), tau)
                )

    report["resampling"] = {
        "cal_images_range": [min(s[0] for s in sizes), max(s[0] for s in sizes)],
        "cal_pothole_images_range": [min(s[1] for s in sizes), max(s[1] for s in sizes)],
        "cases": {},
    }
    for name in cases:
        rows = []
        for a in ALPHAS:
            vals = [v for v in draws[name][a] if v is not None]
            if not vals:
                rows.append({"alpha": a, "feasible_draws": 0})
                continue
            v = np.array(vals)
            rows.append(
                {
                    "alpha": a,
                    "feasible_draws": len(vals),
                    "mean_test_risk": round(float(v.mean()), 4),
                    "p95_test_risk": round(float(np.percentile(v, 95)), 4),
                    "share_of_draws_above_alpha": round(float((v > a).mean()), 4),
                    "mean_within_alpha": bool(v.mean() <= a),
                    "risks": [round(float(x), 4) for x in v],
                }
            )
        report["resampling"]["cases"][name] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "conformal.json").write_text(json.dumps(report, indent=2))
    write_markdown(report)
    plot(report)
    print_summary(report)
    return 0


# Entity -> fixed categorical slot, identical in every T10 figure.
SERIES = {
    "B_india_cal_to_test": ("B, calibrated on india_cal", 0),
    "A_nonindia_to_test": ("A, calibrated on non-India", 1),
    "P_india_cal_to_test": ("P, calibrated on india_cal", 2),
    "A_india_cal_to_test": ("A, calibrated on india_cal", 3),
}


def plot(report: dict) -> None:
    from plot_style import INK_2, MUTED, SLOTS, figure, save, title

    # 1. Test risk vs certified alpha, with the y = x promise drawn in.
    fig, ax = figure()
    ax.plot([0, 1], [0, 1], color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    # Rotated to lie along y = x at this figure's aspect, in the empty band above it.
    ax.text(0.47, 0.515, "risk = alpha (the promise)", color=MUTED, fontsize=8, rotation=28.5)
    # Direct labels placed by hand in clear space: B and P track within ~0.03 of
    # each other the whole way, and all four converge at the right edge.
    placed = {
        "A_nonindia_to_test": (0.30, 0.86),
        "A_india_cal_to_test": (0.62, 0.74),
        "B_india_cal_to_test": (0.53, 0.37),
        "P_india_cal_to_test": (0.15, 0.035),
    }
    short = {
        "A_nonindia_to_test": "A, non-India cal",
        "A_india_cal_to_test": "A, India cal",
        "B_india_cal_to_test": "B",
        "P_india_cal_to_test": "P",
    }
    for name, (label, slot) in SERIES.items():
        pts = [
            (r["alpha"], r["test_risk"])
            for r in report["cases"][name]["curve"]
            if r["test_risk"] is not None
        ]
        if not pts:
            continue
        xs, ys = zip(*pts, strict=True)
        ax.plot(xs, ys, color=SLOTS[slot], linewidth=2, label=label, zorder=3)
        ax.text(*placed[name], short[name], color=INK_2, fontsize=8, ha="center")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("certified alpha (promised pothole miss rate)")
    ax.set_ylabel("pothole miss rate on india_test")
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=INK_2)
    title(
        ax,
        "Calibrated in India the bound holds; calibrated elsewhere it breaks",
        "india_test, locked predictions, IoU 0.5. A line starts where its alpha "
        "first becomes feasible.",
    )
    save(fig, OUT / "risk_vs_alpha.png")

    # 2. The resampled distribution at one alpha both sources can certify.
    alpha = 0.20
    fig, ax = figure()
    bins = [i / 100 for i in range(0, 101, 1)]
    for name in ("B_india_cal_to_test", "A_nonindia_to_test"):
        label, slot = SERIES[name]
        row = next(r for r in report["resampling"]["cases"][name] if r["alpha"] == alpha)
        counts, _, _ = ax.hist(
            row["risks"],
            bins=bins,
            color=SLOTS[slot],
            label=label,
            edgecolor="#fcfcfb",
            linewidth=0.8,
        )
        ax.text(
            row["mean_test_risk"],
            max(counts) + 1.5,
            f"mean {row['mean_test_risk']:.2f}",
            color=INK_2,
            fontsize=8,
            ha="center",
        )
    ax.axvline(alpha, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    top = ax.get_ylim()[1]
    ax.set_ylim(0, top * 1.08)
    ax.text(alpha + 0.01, top * 0.72, f"alpha = {alpha}", color=MUTED, fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel("pothole miss rate on the resampled test half")
    ax.set_ylabel("re-partitions")
    ax.legend(frameon=False, fontsize=8, loc="upper center", labelcolor=INK_2)
    title(
        ax,
        f"200 group-aware re-partitions at alpha = {alpha}",
        "Same test halves for both. India calibration centres on alpha; "
        "non-India calibration never comes close.",
    )
    save(fig, OUT / "resampled_risk_hist.png")

    # 3. What the certificate costs: false alarms per image at tau-hat.
    fig, ax = figure()
    for name in ("B_india_cal_to_test", "P_india_cal_to_test"):
        label, slot = SERIES[name]
        pts = [
            (r["alpha"], r["false_alarms_per_image"])
            for r in report["cases"][name]["table"]
            if r["feasible"]
        ]
        xs, ys = zip(*pts, strict=True)
        ax.plot(
            xs, ys, color=SLOTS[slot], linewidth=2, marker="o", markersize=5, label=label, zorder=3
        )
        ax.text(xs[0], ys[0] * 1.25, f"{ys[0]:.1f}", color=INK_2, fontsize=8, ha="center")
    ax.axhline(1.0, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(0.71, 1.08, "one false alarm per image", color=MUTED, fontsize=8, ha="right")
    ax.set_yscale("log")
    ax.set_xlabel("certified alpha (promised pothole miss rate)")
    ax.set_ylabel("false alarms per image at tau-hat (log)")
    ax.legend(frameon=False, fontsize=8, loc="upper right", labelcolor=INK_2)
    title(
        ax,
        "The certificate controls misses, not false alarms",
        "india_test, pothole channel. Tight alpha is certified at tau ~ 0.001, "
        "where the detector flags everything.",
    )
    save(fig, OUT / "false_alarms_vs_alpha.png")


def write_markdown(report: dict) -> None:
    md = [
        "# T10 - conformal risk control on the pothole miss rate",
        "",
        f"Loss: image-level fraction of GT potholes missed at IoU {report['iou']}. "
        f"tau grid {report['tau_grid'][0]}-{report['tau_grid'][1]} step "
        f"{report['tau_grid'][2]}. Test set: `india_test`. Locked predictions only.",
        "",
    ]
    for name, case in report["cases"].items():
        md += [
            f"## {name}",
            "",
            "| alpha | tau-hat | n cal | test risk | instance miss | false alarms/img |",
            "|---|---|---|---|---|---|",
        ]
        for r in case["table"]:
            if not r["feasible"]:
                md.append(f"| {r['alpha']} | infeasible | {r['n_cal']} | - | - | - |")
            else:
                md.append(
                    f"| {r['alpha']} | {r['tau']} | {r['n_cal']} | {r['test_risk']} | "
                    f"{r['instance_miss_rate']} | {r['false_alarms_per_image']} |"
                )
        md.append("")
    rs = report["resampling"]
    md += [
        f"## {report['n_resamples']} re-partitions of india_cal U india_test "
        f"({report['resampling_unit']})",
        "",
        f"Calibration half: {rs['cal_images_range'][0]}-{rs['cal_images_range'][1]} "
        f"images, {rs['cal_pothole_images_range'][0]}-{rs['cal_pothole_images_range'][1]} "
        "with a pothole.",
        "",
        "| case | alpha | feasible draws | mean test risk | p95 | draws above alpha |",
        "|---|---|---|---|---|---|",
    ]
    for name, rows in rs["cases"].items():
        for r in rows:
            if not r["feasible_draws"]:
                md.append(f"| {name} | {r['alpha']} | 0 | - | - | - |")
            else:
                md.append(
                    f"| {name} | {r['alpha']} | {r['feasible_draws']} | "
                    f"{r['mean_test_risk']} | {r['p95_test_risk']} | "
                    f"{r['share_of_draws_above_alpha']:.1%} |"
                )
    md += [
        "",
        "Generated by `scripts/exp_conformal.py` and overwritten on every run. "
        "Interpretation lives in `docs/DECISIONS.md`.",
    ]
    (OUT / "conformal.md").write_text("\n".join(md) + "\n")


def print_summary(report: dict) -> None:
    for name, case in report["cases"].items():
        print(f"\n=== {name} ===")
        print(f"{'alpha':>6} {'tau':>7} {'n':>5} {'risk':>7} {'inst':>7} {'FA/img':>8}")
        for r in case["table"]:
            if not r["feasible"]:
                print(f"{r['alpha']:>6} {'--':>7} {r['n_cal']:>5}   infeasible")
            else:
                print(
                    f"{r['alpha']:>6} {r['tau']:>7} {r['n_cal']:>5} {r['test_risk']:>7} "
                    f"{r['instance_miss_rate']:>7} {r['false_alarms_per_image']:>8}"
                )
    rs = report["resampling"]
    print(
        f"\n=== {report['n_resamples']} group-aware re-partitions "
        f"(cal images {rs['cal_images_range']}) ==="
    )
    for name, rows in rs["cases"].items():
        for r in rows:
            if r["feasible_draws"]:
                flag = "OK " if r["mean_within_alpha"] else "EXCEEDS"
                print(
                    f"  {name:<22} alpha {r['alpha']:<5} mean risk "
                    f"{r['mean_test_risk']:<7} {flag} ({r['feasible_draws']} feasible, "
                    f"{r['share_of_draws_above_alpha']:.0%} of draws above alpha)"
                )
            else:
                print(f"  {name:<22} alpha {r['alpha']:<5} infeasible in every draw")


if __name__ == "__main__":
    raise SystemExit(main())
