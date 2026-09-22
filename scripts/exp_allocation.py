"""T12 — does optimising the repair budget actually beat the obvious policies?

A synthetic network, because the real one does not exist yet and the question is
about *policy* rather than about any particular road. The generative model is
stated here so the result can be argued with:

  * 200 evaluation segments. True damage ~ Beta(2, 5) scaled to 0-100, which is
    right-skewed: most segments are in fair condition and a minority are bad.
    That shape is what makes allocation interesting — a uniform distribution
    would make every policy look similar.
  * Cost = fixed mobilisation + per-damage cost. Mobilisation dominates for light
    damage, which is exactly what defeats greedy-by-damage: two moderate segments
    can cost less together than one severe one.
  * Detection is imperfect. Observed damage is the true damage scaled by the
    detector's recall at T10's certified threshold, so the optimiser sees what a
    survey would see, not the truth.

Two metrics, because they disagree and the disagreement matters:
  * **true damage repaired** — the utilitarian total;
  * **share of the true worst 20 repaired** — whether the segments that most
    need work actually get it. A policy can score well on the first by fixing
    many mild segments cheaply while missing every severe one.

**Two traffic regimes, because the first one answers the question the wrong way.**
With uniform traffic, priority *is* damage and cost rises with damage, so
priority-per-rupee is nearly monotone and greedy-worst-first is already
near-optimal — the optimiser has nothing to find. That is a real result about
this cost model, not a bug, and it is reported.

The decision only becomes a knapsack when priority and cost decouple, which is
what traffic weight does: a busy road with moderate damage can outrank a quiet
road with severe damage, while costing less to repair. Both regimes are run so
the comparison shows *when* optimising is worth the trouble rather than asserting
that it always is.
"""

import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.survey.allocation import (  # noqa: E402
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
    allocate_random,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
N_SEGMENTS = 200
N_TRIALS = 1000
BUDGET_FRACTIONS = [0.10, 0.20, 0.30, 0.40, 0.50]
MOBILISATION_COST = 50_000.0
COST_PER_DAMAGE = 3_000.0
WORST_K = 20


def make_network(rng: np.random.Generator, recall: float, *, vary_traffic: bool):
    true_damage = rng.beta(2.0, 5.0, N_SEGMENTS) * 100.0
    # What a survey sees: the detector finds `recall` of what is there.
    observed = true_damage * recall
    cost = MOBILISATION_COST + COST_PER_DAMAGE * true_damage
    # Lognormal: most roads carry ordinary traffic, a few carry far more.
    traffic = rng.lognormal(0.0, 0.8, N_SEGMENTS) if vary_traffic else np.ones(N_SEGMENTS)
    segments = [Segment(segment_id=i, vision_estimated_pci=100.0 - observed[i],
                        cost=float(cost[i]), traffic_weight=float(traffic[i]))
                for i in range(N_SEGMENTS)]
    # Benefit is damage weighted by how many people meet it.
    return segments, true_damage * traffic, cost


def evaluate(chosen, true_damage, worst_set):
    picked = set(chosen)
    return (float(sum(true_damage[i] for i in picked)),
            len(picked & worst_set) / len(worst_set))


def main() -> int:
    recall = 0.75          # stand-in until T10 reports the certified operating point
    rows = []
    for regime, vary in (("uniform_traffic", False), ("varying_traffic", True)):
      print(f"\n=== {regime} ===", flush=True)
      for fraction in BUDGET_FRACTIONS:
        totals = {p: [] for p in ("optimal", "greedy", "random")}
        worst = {p: [] for p in totals}
        for trial in range(N_TRIALS):
            rng = np.random.default_rng(trial)
            segments, benefit, cost = make_network(rng, recall, vary_traffic=vary)
            budget = float(cost.sum()) * fraction
            worst_set = set(np.argsort(-benefit)[:WORST_K].tolist())
            picks = {
                "optimal": allocate_optimal(segments, budget),
                "greedy": allocate_greedy_worst_first(segments, budget),
                "random": allocate_random(segments, budget, seed=trial),
            }
            for name, chosen in picks.items():
                damage, share = evaluate(chosen, benefit, worst_set)
                totals[name].append(damage)
                worst[name].append(share)
        for name in totals:
            rows.append({"regime": regime, "budget_fraction": fraction, "policy": name,
                         "mean_benefit_repaired": round(float(np.mean(totals[name])), 1),
                         "mean_worst20_share": round(float(np.mean(worst[name])), 4)})
        print(f"budget {fraction:.0%}: " + "  ".join(
            f"{n} benefit={np.mean(totals[n]):,.0f} worst20={np.mean(worst[n]):.1%}"
            for n in ("optimal", "greedy", "random")), flush=True)

    out = repo_root() / "results" / "T12"
    out.mkdir(parents=True, exist_ok=True)
    (out / "allocation.json").write_text(json.dumps({
        "n_segments": N_SEGMENTS, "n_trials": N_TRIALS, "detector_recall": recall,
        "mobilisation_cost": MOBILISATION_COST, "cost_per_damage": COST_PER_DAMAGE,
        "damage_distribution": "Beta(2,5) x 100", "worst_k": WORST_K, "rows": rows,
    }, indent=2))

    md = ["# T12 - repair allocation under budget", "",
          f"{N_SEGMENTS} synthetic evaluation segments, {N_TRIALS} trials per budget. "
          f"True damage ~ Beta(2,5)x100; cost = {MOBILISATION_COST:,.0f} mobilisation + "
          f"{COST_PER_DAMAGE:,.0f} per damage unit; detector recall {recall}.", "",
          "| regime | budget | policy | benefit repaired | worst-20 share |",
          "|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['regime']} | {r['budget_fraction']:.0%} | {r['policy']} | "
                  f"{r['mean_benefit_repaired']:,.1f} | {r['mean_worst20_share']:.1%} |")
    md += ["", "---", "",
           "Interpretation is in `findings.md` alongside this file. This file is",
           "generated by `scripts/exp_allocation.py` and overwritten on every run;",
           "`findings.md` is authored and is not."]
    (out / "allocation.md").write_text("\n".join(md) + "\n")
    print(f"\nwrote {out}/allocation.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
