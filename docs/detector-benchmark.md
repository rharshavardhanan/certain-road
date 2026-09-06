# Detector benchmark — India test set

**2026-09-06** · 784 held-out India images (330 with objects, 454 empty)
· identical harness, identical ground truth, identical inference path for every model

## Result

| model | source | params | mAP50 | mAP50-95 | latency ms |
|---|---|---:|---:|---:|---:|
| `multicountry_v8s` | **ours**, provenance-controlled | 11.14 M | **0.3932** | 0.1662 | 8.4 |
| `yolo12s_RDD2022_best` | HuggingFace `rezzzq/…`, MIT | 9.26 M | **0.9765** | 0.7221 | 13.6 |

## The external model's score is not a performance result

**0.9765 mAP50 is not achievable on this task.** It indicates the model was evaluated on
images it had already been trained on.

Three independent lines of evidence:

**1. It contradicts a held-out measurement of the same architecture.** A separate published
benchmark measured YOLOv12s on RDD2022 India at **mAP50 0.2808** using its own held-out split.
The same architecture here scores **0.9765** — a 3.5× gap between "held out" and "our test
set". That gap is the signature of train/test overlap, not of a better checkpoint.

**2. The absolute value is outside what the task supports.** The CRDDC'2022 *winner* — an
ensemble with test-time augmentation — reached **F1 0.769** across all six countries. This
model reports recall **0.981** at conf 0.10 and per-class AP50 of 0.961 / 0.994 / 0.975 on the
hardest single-country subset. Road-damage detection does not look like that.

**3. The mechanism is known and expected.** Our `test` split is 784 images carved by salted
hash from RDD2022's India *training* data (D009). Any model trained on RDD2022 has seen them,
unless its author used our exact salt — which nobody else has.

**The harness is not at fault.** It reproduces ultralytics' own figure for our model to within
0.0005 (D045), and both models here ran the same ground truth, the same images and the same
inference path.

## Consequence

**The external weights are unusable — not because they are bad, but because they cannot be
measured.** Every number derived from them would be inflated by an unknown amount, with no way
to detect it from the numbers themselves.

This holds **even though conformal prediction is cut from the sprint** (D051). Contamination
was framed earlier as a conformal-calibration problem; it is more basic than that. It destroys
the ability to evaluate the detector at all.

## Honest limits of this claim

Overlap is inferred from strong circumstantial evidence, not proven: the author does not
publish their split, so it cannot be checked directly. The defensible phrasing is
**"performance inconsistent with a held-out evaluation, indicating probable train/test
overlap"** — not an accusation. Nobody did anything wrong; the weights simply are not usable
for this purpose.

## What our own numbers actually say

`multicountry_v8s` at mAP50 0.3932 is a modest detector, and the per-class breakdown says why:

| class | AP50 | note |
|---|---:|---|
| alligator_crack | 0.5761 | large, distinctive texture — easiest |
| pothole | 0.3432 | |
| linear_crack | 0.2603 | thin, low-contrast against noisy Indian surfaces — hardest |

The operating-point sweep shows the real trade: at conf 0.10 recall is 0.538 with **759 false
positives** across 784 images; at 0.25 recall falls to 0.332 with 180. That is what the
two-threshold rule in D051 exists to manage — a low bar to record evidence for the survey, a
high bar before steering the vehicle.

## Reproduce

```bash
uv run certain-road perception eval --weights <path> --split test --class-map <map>
```

Maps: `identity_3class` for our models, `rdd2022_4class` or `rdd2022_5class` for external
RDD2022 models. The 5-class map drops `Repair` explicitly — a repaired area is not distress,
and counting it as damage would penalise a road for having been maintained.
