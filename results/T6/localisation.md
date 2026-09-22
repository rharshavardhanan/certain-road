# T6 follow-up — localisation vs blindness

**The T6 narrative said Model A "doesn't see" Indian damage. That was wrong, and
this analysis is what shows it.** The claim rested on IoU-0.5 matching at
conf 0.25, which cannot distinguish a model that finds nothing from one that
finds the defect, rates it below threshold, and draws it to a different extent.

## Recall under progressively looser matching

| set · class | conf 0.25, IoU.5 | conf 0.001, IoU.5 | conf 0.001, IoU.1 | conf 0.001, centre |
|---|---|---|---|---|
| nonIN linear | 0.546 | 0.912 | 0.982 | 0.977 |
| nonIN alligator | 0.613 | 0.969 | 0.991 | 0.988 |
| nonIN pothole | 0.463 | 0.845 | 0.939 | 0.927 |
| **India linear** | 0.046 | 0.558 | 0.770 | 0.748 |
| **India alligator** | 0.103 | 0.410 | 0.625 | 0.634 |
| **India pothole** | 0.083 | 0.347 | 0.541 | 0.594 |

## Decomposition of the India pothole gap

Of 3,187 India potholes, at maximum permissiveness (conf 0.001):

| outcome | share |
|---|---|
| matched at IoU >= 0.5 | **34.7%** |
| matched only at IoU 0.1-0.5 — right place, wrong extent | **19.5%** (620 boxes) |
| centre inside GT but IoU < 0.1 | 5.3% |
| nothing predicted nearby | **~40.6%** (1,462 boxes) |

And **confidence is the largest single loss**: recall falls 0.347 → 0.083 moving
from conf 0.001 to 0.25, so **76% of correctly localised potholes are rated below
the reporting threshold**.

## Three distinct failures, not one

1. **Confidence collapse (largest).** The model finds a third of India's
   potholes at IoU 0.5 but scores them so low they vanish at any usable
   threshold. This is miscalibration under domain shift, not an inability to
   detect. It is also the most recoverable: it is what fine-tuning on India data
   directly addresses.
2. **Extent disagreement (~20% of potholes).** India GT boxes are **2.3x larger
   in relative area** than non-India (median 0.0087 vs 0.0038) and more elongated
   (aspect 1.72 vs 1.46), and 5.3% of India images carry 3+ potholes against 0.9%
   of non-India. The inspected near-misses show the pattern directly:
   `India_000580` has a prediction at **0.46 confidence** sitting on the pothole
   inside a GT box roughly three times its size — IoU 0.29, scored as a miss.
   India annotates damaged *stretches*; the model was trained to mark discrete
   defects.
3. **Genuine blindness (~41%).** 1,462 potholes have nothing predicted near them
   at any confidence. The viewed examples are faint, hazy, low-contrast patches
   on dusty unpaved surfaces — the part of the domain gap that is real.

## Corrected narrative

> Model A's India mAP50 of 0.0972 is not principally a failure to detect damage.
> At its own operating threshold it recovers only 8% of potholes, but at
> conf 0.001 it localises **35% at IoU 0.5 and 54% at IoU 0.1** — so more than
> half of India's potholes produce a prediction in roughly the right place. The
> headline number is dominated by **confidence collapse** (76% of correct
> localisations fall below threshold) and by **annotation-extent mismatch** (~20%
> land at IoU 0.1-0.5 because India labels damaged stretches rather than discrete
> defects). Roughly **41% is genuine blindness** on faint, dusty, low-contrast
> surfaces.

This matters for what comes next. A blindness-dominated gap would argue the
architecture or the training data volume is wrong. A confidence-and-convention
dominated gap argues that **Model B's India fine-tuning should recover a large
share of it**, which is a testable prediction rather than a hope.

## Threshold note

IoU 0.5 remains the primary matching threshold for every reported metric. The
0.1 and 0.3 figures here are a declared sensitivity analysis to locate the
failure, not an alternative headline.
