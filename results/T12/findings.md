# T12 — findings

Authored companion to `allocation.md`, which `scripts/exp_allocation.py`
regenerates on every run. Decision record: D079.

The previous version of this file described a scalar-damage simulation in which
detection error could not change any decision (D079). Its numbers are superseded.

## Setup in one paragraph

200 synthetic evaluation segments, 1,000 networks per traffic regime, every
policy scored on the *truth*. Distress is drawn per class and detected instance
by instance at **Model B's measured per-class recall** on locked `india_test`,
at the threshold T10 certified. Headline operating point: **alpha 0.50, tau-hat
0.117** — the tightest certified alpha at which B raises under one false alarm
per image (0.43). Recall there: linear crack 0.36, alligator 0.64, pothole 0.53.
Condition is scored through `vision_density -> deduct_value ->
vision_estimated_pci`, a monotone proxy following the structure of Ibragimov et
al. (Sensors 2024); **ASTM D6433 deduct curves are not used**. False alarms are
not modelled.

## 1. Conformal robustness changes decisions — and helps, modestly

At alpha 0.50, **robust and nominal choose different repair sets in 95–100% of
networks** under uniform traffic. The scalar design made that 0% by
construction.

| uniform traffic | 10% | 20% | 30% | 40% | 50% |
|---|---|---|---|---|---|
| nominal, share of oracle benefit | 95.2% | 95.6% | 96.0% | 96.4% | 96.7% |
| **robust**, share of oracle benefit | **95.7%** | **96.2%** | **96.6%** | **96.9%** | **97.2%** |
| robust − nominal, 95% CI (benefit units) | +3.8 [3.5, 4.2] | +8.2 [7.7, 8.7] | +12.6 [12.0, 13.2] | +15.1 [14.3, 15.8] | +15.7 [14.8, 16.5] |

Every interval clears zero, paired over 1,000 networks, and the same holds under
varying traffic. **Detection error at this operating point costs 3–5% of the
achievable benefit; the robust correction recovers about a tenth of that.** Real,
small, and bought for nothing — the correction is a division.

## 2. Robust repairs fewer of the worst roads — because it optimises better

The same pairs show robust repairing **fewer of the true worst 20**: −0.8 to
−3.4 percentage points under uniform traffic, every interval clear of zero.

The explanation is not a flaw in the correction. Under uniform traffic robust's
worst-20 coverage sits **between nominal's and the oracle's at every budget**:

| uniform traffic, worst-20 share | 10% | 20% | 30% | 40% | 50% |
|---|---|---|---|---|---|
| nominal | 2.2% | 7.9% | 17.5% | 30.6% | 45.9% |
| robust | 1.4% | 5.9% | 14.4% | 27.3% | 42.9% |
| oracle | 0.5% | 1.9% | 5.3% | 11.8% | 21.8% |

Robust is a better benefit-maximiser — closer to the oracle on both metrics —
and section 4 shows that a benefit-maximiser defers the worst roads. Nominal's
extra worst-20 coverage is noise from mis-estimated condition, not a virtue.
Sections 2 and 4 are one finding.

A tempting alternative explanation was checked and is false: the true worst 20
are *not* dominated by the classes the correction leaves alone. Alligator
cracking is 45% of their deduct against 48% across all segments, and potholes 40%
against 36% — the worst roads are, if anything, slightly pothole-enriched.

**The correction is pothole-only in scope.** T10 certifies a pothole miss rate,
so only pothole vision_density is divided by (1 − alpha); linear and alligator
cracking stay under-counted at 0.36× and 0.64× of the truth. That leaves bias the
certificate cannot touch. A per-class certificate would need a per-class CRC run,
which T10 did not do.

## 3. At tight alpha there is nothing to correct

| alpha | tau-hat | false alarms / img | same repair set, uniform, 30% | robust − nominal benefit |
|---|---|---|---|---|
| 0.10 | 0.001 | **31.2** | 55% | +0.4 [0.2, 0.5] |
| 0.30 | 0.029 | 2.3 | 7% | +4.4 [4.1, 4.8] |
| **0.50** | 0.117 | **0.43** | 0% | +12.6 [12.0, 13.2] |

At alpha 0.10 the certified threshold keeps every box, recall is already
0.87–0.96, and the correction factor is 1.11 — robust and nominal mostly agree.
**And this simulation flatters that operating point**, because at 31 false
alarms per image the observed pothole density would be dominated by phantoms
that are not modelled here. The tight-alpha rows are optimistic by construction.

## 4. The finding that outranks robustness: maximising benefit defers the worst roads

| uniform traffic, share of true worst 20 repaired | 10% | 20% | 30% | 50% |
|---|---|---|---|---|
| **oracle** (exact optimiser, on the truth) | **0.5%** | 1.9% | 5.3% | 21.8% |
| greedy worst-first (on observed) | 39.2% | 81.0% | 96.7% | 99.9% |

The *oracle* — perfect information, exact optimiser — repairs essentially none
of the worst roads at a tight budget. This is not a bug; checked directly:

| true benefit (100 − PCI) | p10 | p50 | p90 | p99 |
|---|---|---|---|---|
| benefit per 100k of cost | 9.8 | 31.2 | 31.4 | **20.5** |

**Benefit per unit cost is hump-shaped.** Light damage is poor value because
mobilisation dominates. Moderate damage is best value. The worst damage is
*worse* value again, because the log deduct saturates while repair cost keeps
rising linearly with area. The true worst 20 sit at an average value-rank of 117
out of 200. A benefit-maximiser therefore spends on fair and poor roads and
leaves the failed ones — which is the known "optimise versus worst-first" split
in pavement management, reproduced here from first principles.

The magnitude is a property of this cost model and this deduct shape, and would
move with either. The direction would not.

Greedy worst-first pays for its worst-20 coverage in total benefit: 68.5% of
oracle at a 10% budget, below even random (76.4%).

**Neither objective is simply right, and T16's dashboard must not report only
one.** Maximum total benefit is the utilitarian answer; "no severely damaged road
is left unrepaired" is usually the safety and political requirement. A dashboard
that shows only the optimiser's plan would recommend deferring every failed road
at a tight budget, and would not say so.

## 5. Traffic weight changes which regime you are in

Under varying traffic the worst-20 by *benefit* are busy roads, and busy roads
are good value however damaged, so the oracle covers 66% of them at a 10% budget
and every principled policy lands within a few points of it. Random collapses to
30% of oracle benefit. The conflict in section 4 is sharpest where traffic is
flat.

## Caveats

- **False alarms are not modelled.** Honest at alpha 0.50 (0.43 per image),
  optimistic at 0.30 (2.3), and not credible at 0.10 (31.2).
- Recall is Model B's on `india_test`, applied uniformly across segments.
  Real recall varies with lighting, surface and speed, which would add noise the
  simulation lacks.
- Generator parameters were fixed on the *true* condition distribution alone,
  against a target declared before adjusting, before any policy ran (config
  comments carry the three candidates tried).
- Budget fraction is of total true repair cost, which a real authority does not
  know; it is a scale, not a planning input.
