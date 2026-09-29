"""Both repair plans at one budget, side by side, scored on the truth (D079).

The exact optimiser maximises total benefit. With a log deduct and repair cost
linear in damaged area, benefit per rupee is hump-shaped in damage, so at a tight
budget the optimiser rationally defers the worst roads: in T12 it repaired 0.5% of
the true worst 20 at a 10% budget where worst-first repaired 39%. Neither
objective is simply right, and a budget slider that showed only the optimiser's
set would recommend deferring every failed road without saying so. This module
therefore never returns one plan without the other.

Both plans rank on *observed* condition — what a survey sees — and are scored on
the truth, which only a synthetic network has. The oracle (the optimiser run on
the truth) is the ceiling for "share of oracle", not a plan anyone can run.
"""

from certain_road.survey.allocation import (
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
)

DEFAULT_WORST_K = 20


def _segments(net: dict, field: str) -> list[Segment]:
    return [Segment(segment_id=s["id"], vision_estimated_pci=float(s[field]),
                    cost=float(s["cost"]), traffic_weight=float(s["traffic"]))
            for s in net["segments"]]


def two_plans(net: dict, budget_fraction: float, *, condition: str = "observed_pci",
              worst_k: int = DEFAULT_WORST_K) -> dict:
    """The optimiser's plan and the worst-first plan at `budget_fraction` of total cost.

    `condition` is the observed field the plans rank on ("observed_pci" or the
    conformal "robust_pci"). Each plan reports its cost, true benefit, share of
    the oracle's benefit, and how many of the true worst `worst_k` segments it
    repairs and which it defers.
    """
    segs = net["segments"]
    benefit = {s["id"]: (100.0 - float(s["true_pci"])) * float(s["traffic"]) for s in segs}
    cost = {s["id"]: float(s["cost"]) for s in segs}
    worst = sorted(benefit, key=lambda i: -benefit[i])[:worst_k]
    budget = sum(cost.values()) * budget_fraction

    observed = _segments(net, condition)
    oracle = allocate_optimal(_segments(net, "true_pci"), budget)
    oracle_benefit = sum(benefit[i] for i in oracle)

    def describe(chosen: list[int]) -> dict:
        picked = set(chosen)
        got = sum(benefit[i] for i in picked)
        return {"chosen": sorted(picked),
                "cost": sum(cost[i] for i in picked),
                "true_benefit": got,
                "share_of_oracle": got / oracle_benefit if oracle_benefit else 1.0,
                "worst_repaired": sum(1 for i in worst if i in picked),
                "worst_deferred": [i for i in worst if i not in picked]}

    return {"budget": budget, "budget_fraction": budget_fraction, "worst_k": len(worst),
            "worst": worst, "condition": condition,
            "optimiser": describe(allocate_optimal(observed, budget)),
            "worst_first": describe(allocate_greedy_worst_first(observed, budget))}
