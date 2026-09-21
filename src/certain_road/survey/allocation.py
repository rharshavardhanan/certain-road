"""T12 — which evaluation segments to repair under a fixed budget.

A binary knapsack: maximise total priority subject to total cost. Segments are
repaired whole or not at all, which is why this needs a real optimiser rather
than a sort — a greedy pass can be arbitrarily far from optimal when mobilisation
cost is a large fixed share, and mobilisation is a large fixed share here.

**Solved by exact dynamic programming, not PuLP (D062).** T12 specified a PuLP
ILP, but PuLP ships an x86_64 CBC binary and this is an arm64 Mac with no
Rosetta: `bad CPU type in executable`. Rather than make the optimiser depend on
a system-level install, the DP indexes over *priority* and stores the minimum
cost to reach it. That handles float costs and budgets of any magnitude exactly
— unlike the textbook budget-indexed DP, which would need a table the size of
the budget in rupees.

Priorities are quantised to `PRIORITY_QUANTUM` to index the table. The result is
exact for the quantised problem; at the default of 0.01 on a 0-100 scale that is
finer than the vision-estimated PCI feeding it is meaningful to.

Four policies exist so the optimiser has something to be measured against.
`random` and `greedy` are not strawmen: if the optimiser cannot beat worst-first
on the metric that matters, it is not earning its place.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

PRIORITY_QUANTUM = 0.01


@dataclass(frozen=True)
class Segment:
    segment_id: int
    vision_estimated_pci: float
    cost: float
    traffic_weight: float = 1.0

    @property
    def priority(self) -> float:
        """Worse condition and busier road both raise the case for repair."""
        return (100.0 - self.vision_estimated_pci) * self.traffic_weight


def allocate_optimal(
    segments: Sequence[Segment], budget: float, *, quantum: float = PRIORITY_QUANTUM
) -> list[int]:
    """Exact 0/1 knapsack over priority, subject to the budget.

    `best[p]` is the least cost achieving quantised priority exactly `p`. After
    every segment has been offered, the answer is the highest `p` still within
    budget. Indexing by priority rather than by budget is what keeps the table
    small when costs are large floats.
    """
    if not segments:
        return []

    weights = [max(0, int(round(s.priority / quantum))) for s in segments]
    total = sum(weights)
    best = np.full(total + 1, np.inf)
    best[0] = 0.0
    # take[i, p] records whether segment i was used to first reach priority p.
    take = np.zeros((len(segments), total + 1), dtype=bool)

    for i, (segment, w) in enumerate(zip(segments, weights, strict=True)):
        if w == 0:
            continue
        # Descending in p, so each segment is offered at most once.
        candidate = best[:-w or None] + segment.cost
        target = best[w:]
        improved = candidate < target
        take[i, w:][improved] = True
        best[w:][improved] = candidate[improved]

    affordable = np.where(best <= budget)[0]
    if affordable.size == 0:
        return []

    p = int(affordable[-1])
    chosen = []
    for i in range(len(segments) - 1, -1, -1):
        if take[i, p]:
            chosen.append(segments[i].segment_id)
            p -= weights[i]
    return sorted(chosen)


def allocate_greedy_worst_first(segments: Sequence[Segment], budget: float) -> list[int]:
    """Repair the worst segment that still fits, repeatedly. The obvious policy."""
    spent, chosen = 0.0, []
    for s in sorted(segments, key=lambda s: -s.priority):
        if spent + s.cost <= budget:
            chosen.append(s.segment_id)
            spent += s.cost
    return sorted(chosen)


def allocate_random(segments: Sequence[Segment], budget: float, seed: int = 0) -> list[int]:
    """Lower bound. A policy that cannot beat this is not a policy."""
    order = list(segments)
    random.Random(seed).shuffle(order)
    spent, chosen = 0.0, []
    for s in order:
        if spent + s.cost <= budget:
            chosen.append(s.segment_id)
            spent += s.cost
    return sorted(chosen)


def total_cost(segments: Sequence[Segment], chosen: Sequence[int]) -> float:
    picked = set(chosen)
    return sum(s.cost for s in segments if s.segment_id in picked)


def total_priority(segments: Sequence[Segment], chosen: Sequence[int]) -> float:
    picked = set(chosen)
    return sum(s.priority for s in segments if s.segment_id in picked)
