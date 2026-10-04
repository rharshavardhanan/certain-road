"""T12 — does conformal robustness change which roads get repaired?

A synthetic network, because the real one does not exist yet and the question is
about *policy*, not about any particular road. The generative model is stated so
the result can be argued with, and every tunable lives in `configs/project.yaml`.

**Why the generator is per class (D079).** The first version reduced damage to
one scalar and applied one global recall: `observed = true_damage * recall`.
Scaling every segment by the same constant cannot change a ranking, and the
knapsack's choice is invariant to it too — so detection error had no effect on
any decision, and "robust" (another uniform constant) chose exactly what
"nominal" chose, by construction. Detection error only matters when it is uneven,
and in this project it is: Model B finds different shares of each class.

**The generator.** 200 evaluation segments of `segment_m` x `lane_width_m`.

  * Segment damage level ~ Gamma(shape, scale): right-skewed, most segments in
    fair condition, a minority bad.
  * Per class, distress instances ~ Poisson(rate_c x level); each instance's
    ground footprint ~ LogNormal(log median_c, sigma).
  * **Detection**: each instance is found independently with probability equal to
    Model B's recall *for that class*, measured on locked `india_test` at T10's
    certified threshold. Nothing is assumed about recall.
  * Condition is scored through the real pipeline — `vision_density` ->
    `deduct_value` -> `vision_estimated_pci` — for the truth, for what a survey
    would observe, and for the **robust** variant, which divides observed pothole
    vision_density by (1 - alpha) using T10's certified alpha.
  * Cost = mobilisation + per-m2 cost of the true distressed area. Mobilisation
    dominates light damage, which is what makes the problem a knapsack.

**The operating point.** T10 certifies a pothole miss rate at a threshold, and
the tighter the certificate the lower the threshold and the more false alarms
(D077: 31 per image at alpha 0.10). This simulation models misses and **not
false alarms** — so it is only honest where false alarms are rare. The headline
alpha is therefore the tightest one at which Model B raises fewer than
`max_false_alarms_per_image`; the tighter alphas run as declared sensitivities,
and their results are optimistic by construction.

**Policies**, all under the same budget: **oracle** (exact optimiser on the
truth — the ceiling, not a policy anyone can run), **nominal** (exact optimiser
on observed condition), **robust** (exact optimiser on robust condition), **greedy**
worst-first on observed condition, and **random**.

**Two metrics, because they disagree:** true benefit repaired (the utilitarian
total) and the share of the true worst 20 segments repaired (whether the roads
that most need work get it). **Two traffic regimes**, because with uniform traffic
priority and cost move together and greedy is already near-optimal (see
`findings.md`).
"""

import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from certain_road.assess.conformal import matched_confidences  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.survey.allocation import (  # noqa: E402
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
    allocate_random,
)
from certain_road.survey.scoring import (  # noqa: E402
    deduct_value,
    robust_vision_density,
    vision_density,
    vision_estimated_pci,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
A, S = CFG["allocation"], CFG["scoring"]
NAMES = {int(k): v for k, v in CFG["classes"].items()}
POTHOLE = NAMES[int(CFG["pothole_class"])]
CLASSES = list(S["deduct_weights"])
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
OUT = repo_root() / "results" / "T12"
POLICIES = ("oracle", "nominal", "robust", "greedy", "random")


# --- operating points from T10 --------------------------------------------


def operating_points() -> list[dict]:
    """Headline alpha by the stated rule, then the declared sensitivities."""
    table = json.loads((repo_root() / "results/T10/conformal.json").read_text())
    rows = [r for r in table["cases"]["B_india_cal_to_test"]["table"] if r["feasible"]]
    usable = [r for r in rows if r["false_alarms_per_image"] < A["max_false_alarms_per_image"]]
    if not usable:
        raise SystemExit("no certified alpha meets the false-alarm limit")
    head = min(usable, key=lambda r: r["alpha"])
    points = [head | {"role": "headline"}]
    for a in A["sensitivity_alphas"]:
        r = next((r for r in rows if abs(r["alpha"] - a) < 1e-9), None)
        if r is None:
            raise SystemExit(f"sensitivity alpha {a} is not certifiable for Model B")
        points.append(r | {"role": "sensitivity"})
    return points


def per_class_recall(taus: list[float]) -> dict[float, dict[str, float]]:
    """Model B's recall per class at each threshold, on locked india_test.

    Same greedy IoU-0.5 matching T10 certifies with, so the recall a segment's
    detection is drawn from is the one the certificate was issued against.
    """
    preds: dict = defaultdict(lambda: defaultdict(list))
    for r in json.loads(
        (repo_root() / "results/LOCKED/B_india_heldout_run/val/predictions.json").read_text()
    ):
        preds[Path(str(r["image_id"])).stem][int(r["category_id"]) - 1].append(
            (*r["bbox"], float(r["score"]))
        )
    matched: dict[int, list] = defaultdict(list)
    for s in (Path(x).stem for x in (YOLO_DIR / "india_test.txt").read_text().split()):
        with Image.open(YOLO_DIR / "images" / f"{s}.jpg") as im:
            w, h = im.size
        gt: dict[int, list] = defaultdict(list)
        for row in (YOLO_DIR / "labels" / f"{s}.txt").read_text().splitlines():
            p = row.split()
            if p:
                cx, cy, bw, bh = map(float, p[1:])
                gt[int(p[0])].append(
                    [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]
                )
        for c, boxes in gt.items():
            pp = preds[s][c]
            pb = (
                np.array([[x, y, x + a, y + b] for x, y, a, b, _ in pp]) if pp else np.zeros((0, 4))
            )
            sc = np.array([q[4] for q in pp]) if pp else np.zeros(0)
            matched[c].append(matched_confidences(np.array(boxes), pb, sc, iou_threshold=0.5))
    out = {}
    for tau in taus:
        out[tau] = {
            NAMES[c]: round(float(np.mean(np.concatenate(matched[c]) >= tau)), 4) for c in NAMES
        }
    return out


# --- the synthetic network ------------------------------------------------


def pci(areas: dict[str, float], robust_alpha: float | None = None) -> float:
    """Vision-estimated PCI for one segment, through the real scoring functions."""
    deducts = {}
    for c, area in areas.items():
        d = vision_density(area, segment_m=S["segment_m"], lane_width_m=S["lane_width_m"])
        if robust_alpha is not None and c == POTHOLE:
            d = robust_vision_density(d, robust_alpha)
        deducts[c] = deduct_value(d, S["deduct_weights"][c])
    return vision_estimated_pci(deducts)


def draw_truth(rng: np.random.Generator, vary_traffic: bool) -> dict:
    """True instances per class, drawn before any detection so every alpha is paired."""
    n = A["n_segments"]
    level = rng.gamma(A["severity_gamma"]["shape"], A["severity_gamma"]["scale"], n)
    inst = {}
    for c in CLASSES:
        counts = rng.poisson(A["instances_per_severity"][c] * level)
        seg = np.repeat(np.arange(n), counts)
        size = rng.lognormal(
            np.log(A["footprint_median_m2"][c]), A["footprint_log_sigma"], len(seg)
        )
        inst[c] = (seg, size, rng.random(len(seg)))  # uniform draw decides detection
    traffic = rng.lognormal(0.0, A["traffic_log_sigma"], n) if vary_traffic else np.ones(n)
    true_area = {c: np.bincount(inst[c][0], weights=inst[c][1], minlength=n) for c in CLASSES}
    true_pci = np.array([pci({c: true_area[c][i] for c in CLASSES}) for i in range(n)])
    cost = A["mobilisation_cost"] + A["cost_per_m2"] * sum(true_area.values())
    return {"inst": inst, "traffic": traffic, "true_pci": true_pci, "cost": cost}


def observe(truth: dict, recall: dict[str, float], alpha: float) -> tuple[np.ndarray, np.ndarray]:
    n = A["n_segments"]
    obs_area = {}
    for c in CLASSES:
        seg, size, u = truth["inst"][c]
        found = u < recall[c]
        obs_area[c] = np.bincount(seg[found], weights=size[found], minlength=n)
    nominal = np.array([pci({c: obs_area[c][i] for c in CLASSES}) for i in range(n)])
    robust = np.array(
        [pci({c: obs_area[c][i] for c in CLASSES}, robust_alpha=alpha) for i in range(n)]
    )
    return nominal, robust


def segments(condition: np.ndarray, truth: dict) -> list[Segment]:
    return [
        Segment(
            segment_id=i,
            vision_estimated_pci=float(condition[i]),
            cost=float(truth["cost"][i]),
            traffic_weight=float(truth["traffic"][i]),
        )
        for i in range(len(condition))
    ]


def run_trial(job: tuple) -> dict:
    """One network, every alpha and budget. Returns metrics keyed (alpha, budget)."""
    trial, vary, points, recalls = job
    rng = np.random.default_rng(trial)
    truth = draw_truth(rng, vary)
    benefit = (100.0 - truth["true_pci"]) * truth["traffic"]
    worst = set(np.argsort(-benefit)[: A["worst_k"]].tolist())
    true_segs = segments(truth["true_pci"], truth)
    total = float(truth["cost"].sum())

    def score(chosen):
        picked = set(chosen)
        return float(benefit[list(picked)].sum()) if picked else 0.0, len(picked & worst) / len(
            worst
        )

    oracle = {f: score(allocate_optimal(true_segs, total * f)) for f in A["budget_fractions"]}
    out = {}
    for p in points:
        nominal, robust = observe(truth, recalls[p["tau"]], p["alpha"])
        nom_s, rob_s = segments(nominal, truth), segments(robust, truth)
        for f in A["budget_fractions"]:
            budget = total * f
            pick_nom = allocate_optimal(nom_s, budget)
            pick_rob = allocate_optimal(rob_s, budget)
            out[(p["alpha"], f)] = {
                "oracle": oracle[f],
                "nominal": score(pick_nom),
                "robust": score(pick_rob),
                "greedy": score(allocate_greedy_worst_first(nom_s, budget)),
                "random": score(allocate_random(nom_s, budget, seed=trial)),
                "same_choice": sorted(pick_nom) == sorted(pick_rob),
            }
    return {"vary": vary, "trial": trial, "metrics": out}


# --- driver -----------------------------------------------------------------


def check_generator() -> None:
    """Print the TRUE condition distribution only. Run before any policy."""
    from collections import Counter

    from certain_road.survey.scoring import band

    vals = np.concatenate(
        [draw_truth(np.random.default_rng(t), False)["true_pci"] for t in range(50)]
    )
    print(
        f"true vision-estimated PCI over {len(vals)} segments: "
        f"median {np.median(vals):.1f}, p10 {np.percentile(vals, 10):.1f}, "
        f"p90 {np.percentile(vals, 90):.1f}"
    )
    counts = Counter(band(float(v)) for v in vals)
    for name in ("Good", "Satisfactory", "Fair", "Poor", "Very Poor", "Serious", "Failed"):
        print(f"  {name:<13} {counts.get(name, 0) / len(vals):6.1%}")


DEMO_SEED = 0  # fixed before the network was looked at; not a chosen example


def export_demo() -> None:
    """Write one T12 network, truth included, for the dashboard to read (T16).

    The dashboard runs the optimiser live but must not re-implement the generator,
    so it reads this file. Uniform traffic, because that is where D079 found the
    two objectives furthest apart. Detection uses Model B's per-class recall for
    every class, pothole included — exactly as T12 ran — and the file says so.
    """
    head = next(p for p in operating_points() if p["role"] == "headline")
    recall = per_class_recall([head["tau"]])[head["tau"]]
    truth = draw_truth(np.random.default_rng(DEMO_SEED), False)
    nominal, robust = observe(truth, recall, head["alpha"])
    out = {
        "source": "scripts/exp_allocation.py --export-demo",
        "seed": DEMO_SEED,
        "regime": "uniform_traffic",
        "note": "One network of T12's 1,000, seed fixed in advance. Averages over all "
        "1,000 are in results/T12/allocation.json.",
        "alpha": head["alpha"],
        "tau": head["tau"],
        "recall": recall,
        "detector": "Model B's per-class recall at tau-hat for every class, pothole "
        "included, as in T12. Under D082 the survey takes potholes from "
        "Model P; P's recall is not used in this simulation.",
        "segments": [
            {
                "id": i,
                "true_pci": round(float(truth["true_pci"][i]), 3),
                "observed_pci": round(float(nominal[i]), 3),
                "robust_pci": round(float(robust[i]), 3),
                "cost": round(float(truth["cost"][i]), 2),
                "traffic": round(float(truth["traffic"][i]), 4),
            }
            for i in range(A["n_segments"])
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "demo_network.json").write_text(json.dumps(out, indent=2))
    print(
        f"wrote {OUT / 'demo_network.json'} ({A['n_segments']} segments, "
        f"alpha {head['alpha']}, tau {head['tau']})"
    )


def main() -> int:
    if "--check-generator" in sys.argv:
        check_generator()
        return 0
    if "--export-demo" in sys.argv:
        export_demo()
        return 0

    if "--trials" in sys.argv:  # smoke runs only; overwrites the outputs, so rerun in full
        A["n_trials"] = int(sys.argv[sys.argv.index("--trials") + 1])
    points = operating_points()
    recalls = per_class_recall([p["tau"] for p in points])
    for p in points:
        print(
            f"{p['role']:<11} alpha {p['alpha']}: tau {p['tau']}, "
            f"FA/img {p['false_alarms_per_image']}, recall {recalls[p['tau']]}",
            flush=True,
        )

    jobs = [(t, vary, points, recalls) for vary in (False, True) for t in range(A["n_trials"])]
    results = []
    with ProcessPoolExecutor(max_workers=A["workers"]) as pool:
        for i, r in enumerate(pool.map(run_trial, jobs, chunksize=4)):
            results.append(r)
            if (i + 1) % 200 == 0:
                print(f"  {i + 1}/{len(jobs)} networks", flush=True)

    rows, paired = [], []
    for vary in (False, True):
        regime = "varying_traffic" if vary else "uniform_traffic"
        sub = [r["metrics"] for r in results if r["vary"] == vary]
        for p in points:
            for f in A["budget_fractions"]:
                cells = [m[(p["alpha"], f)] for m in sub]
                oracle = np.array([c["oracle"][0] for c in cells])
                for pol in POLICIES:
                    b = np.array([c[pol][0] for c in cells])
                    w = np.array([c[pol][1] for c in cells])
                    rows.append(
                        {
                            "regime": regime,
                            "alpha": p["alpha"],
                            "role": p["role"],
                            "budget_fraction": f,
                            "policy": pol,
                            "mean_benefit_repaired": round(float(b.mean()), 1),
                            "benefit_vs_oracle": round(float(b.sum() / oracle.sum()), 4),
                            "mean_worst20_share": round(float(w.mean()), 4),
                        }
                    )
                d_b = np.array([c["robust"][0] - c["nominal"][0] for c in cells])
                d_w = np.array([c["robust"][1] - c["nominal"][1] for c in cells])
                se_b, se_w = (
                    d_b.std(ddof=1) / np.sqrt(len(d_b)),
                    d_w.std(ddof=1) / np.sqrt(len(d_w)),
                )
                paired.append(
                    {
                        "regime": regime,
                        "alpha": p["alpha"],
                        "role": p["role"],
                        "budget_fraction": f,
                        "identical_choice_share": round(
                            float(np.mean([c["same_choice"] for c in cells])), 4
                        ),
                        "benefit_robust_minus_nominal": round(float(d_b.mean()), 2),
                        "benefit_ci95": [
                            round(float(d_b.mean() - 1.96 * se_b), 2),
                            round(float(d_b.mean() + 1.96 * se_b), 2),
                        ],
                        "worst20_robust_minus_nominal": round(float(d_w.mean()), 4),
                        "worst20_ci95": [
                            round(float(d_w.mean() - 1.96 * se_w), 4),
                            round(float(d_w.mean() + 1.96 * se_w), 4),
                        ],
                    }
                )

    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "generator": {
            k: A[k]
            for k in (
                "n_segments",
                "n_trials",
                "severity_gamma",
                "instances_per_severity",
                "footprint_median_m2",
                "footprint_log_sigma",
                "traffic_log_sigma",
                "mobilisation_cost",
                "cost_per_m2",
                "worst_k",
            )
        },
        "scoring": S,
        "operating_points": [p | {"recall": recalls[p["tau"]]} for p in points],
        "false_alarms_modelled": False,
        "rows": rows,
        "robust_vs_nominal": paired,
    }
    (OUT / "allocation.json").write_text(json.dumps(report, indent=2))
    write_markdown(report)
    plot(report)
    print_summary(report)
    return 0


def write_markdown(report: dict) -> None:
    head = next(p for p in report["operating_points"] if p["role"] == "headline")
    md = [
        "# T12 - repair allocation under budget",
        "",
        f"{report['generator']['n_segments']} synthetic evaluation segments, "
        f"{report['generator']['n_trials']} networks per traffic regime, paired across "
        "every alpha and budget. Detection per class at Model B's recall on locked "
        "india_test; condition through vision_density -> deduct_value -> "
        "vision_estimated_pci. **False alarms are not modelled.**",
        "",
        "| role | alpha | tau-hat | false alarms/img | recall (linear / alligator / pothole) |",
        "|---|---|---|---|---|",
    ]
    for p in report["operating_points"]:
        r = p["recall"]
        md.append(
            f"| {p['role']} | {p['alpha']} | {p['tau']} | {p['false_alarms_per_image']} | "
            f"{r['linear_crack']} / {r['alligator_crack']} / {r['pothole']} |"
        )
    md += [
        "",
        f"## Headline, alpha {head['alpha']}",
        "",
        "| regime | budget | policy | benefit vs oracle | worst-20 share |",
        "|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        if r["alpha"] == head["alpha"]:
            md.append(
                f"| {r['regime']} | {r['budget_fraction']:.0%} | {r['policy']} | "
                f"{r['benefit_vs_oracle']:.1%} | {r['mean_worst20_share']:.1%} |"
            )
    md += [
        "",
        "## Robust minus nominal, paired over networks",
        "",
        "| regime | alpha | budget | identical choice | benefit diff [95% CI] | "
        "worst-20 diff [95% CI] |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["robust_vs_nominal"]:
        md.append(
            f"| {r['regime']} | {r['alpha']} | {r['budget_fraction']:.0%} | "
            f"{r['identical_choice_share']:.1%} | {r['benefit_robust_minus_nominal']:+.1f} "
            f"[{r['benefit_ci95'][0]:+.1f}, {r['benefit_ci95'][1]:+.1f}] | "
            f"{r['worst20_robust_minus_nominal']:+.4f} [{r['worst20_ci95'][0]:+.4f}, "
            f"{r['worst20_ci95'][1]:+.4f}] |"
        )
    md += [
        "",
        "Generated by `scripts/exp_allocation.py` and overwritten on every run. "
        "`findings.md` is authored; decisions are in `docs/DECISIONS.md`.",
    ]
    (OUT / "allocation.md").write_text("\n".join(md) + "\n")


def plot(report: dict) -> None:
    import matplotlib.pyplot as plt
    from plot_style import INK_2, SLOTS, SURFACE, save, style_axes

    head = next(p for p in report["operating_points"] if p["role"] == "headline")
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), facecolor=SURFACE, sharex=True)
    metrics = (
        ("benefit_vs_oracle", "true benefit repaired, share of oracle"),
        ("mean_worst20_share", "share of the true worst 20 repaired"),
    )
    regimes = (("uniform_traffic", "uniform traffic"), ("varying_traffic", "varying traffic"))
    for i, (metric, ylabel) in enumerate(metrics):
        for j, (regime, rname) in enumerate(regimes):
            ax = axes[i][j]
            style_axes(ax)
            for k, pol in enumerate(POLICIES):
                pts = sorted(
                    (r["budget_fraction"], r[metric])
                    for r in report["rows"]
                    if r["alpha"] == head["alpha"] and r["regime"] == regime and r["policy"] == pol
                )
                xs, ys = zip(*pts, strict=True)
                ax.plot(
                    [x * 100 for x in xs],
                    ys,
                    color=SLOTS[k],
                    linewidth=2,
                    marker="o",
                    markersize=4,
                    label=pol,
                )
            ax.set_ylim(0, 1.05)
            if i == 0:
                ax.set_title(rname, loc="left", fontsize=10, color=INK_2)
            if j == 0:
                ax.set_ylabel(ylabel)
            if i == 1:
                ax.set_xlabel("budget, % of total repair cost")
    axes[0][0].legend(frameon=False, fontsize=8, loc="lower right", labelcolor=INK_2)
    fig.suptitle(
        f"Repair allocation at certified alpha {head['alpha']} (tau {head['tau']}, Model B)",
        x=0.01,
        ha="left",
        fontsize=12,
    )
    save(fig, OUT / "allocation.png")


def print_summary(report: dict) -> None:
    head = next(p for p in report["operating_points"] if p["role"] == "headline")
    print(f"\n=== headline alpha {head['alpha']}: benefit vs oracle / worst-20 ===")
    for regime in ("uniform_traffic", "varying_traffic"):
        print(regime)
        for f in A["budget_fractions"]:
            cells = {
                r["policy"]: r
                for r in report["rows"]
                if r["regime"] == regime
                and r["alpha"] == head["alpha"]
                and r["budget_fraction"] == f
            }
            print(
                f"  {f:.0%}: "
                + "  ".join(
                    f"{pol} {cells[pol]['benefit_vs_oracle']:.3f}"
                    f"/{cells[pol]['mean_worst20_share']:.3f}"
                    for pol in POLICIES
                )
            )
    print("\n=== robust - nominal (paired) ===")
    for r in report["robust_vs_nominal"]:
        print(
            f"  {r['regime']:<16} alpha {r['alpha']:<4} {r['budget_fraction']:.0%}: "
            f"same {r['identical_choice_share']:.0%}  benefit "
            f"{r['benefit_robust_minus_nominal']:+.1f} {r['benefit_ci95']}  worst20 "
            f"{r['worst20_robust_minus_nominal']:+.4f} {r['worst20_ci95']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
