# Dataset card — RDD2022 India subset

**Source:** RDD2022, DOI `10.6084/m9.figshare.21431547.v1`, CC BY 4.0
**Archive:** single 13.26 GB outer zip (13,264,172,619 bytes); no per-country download
exists. The outer zip is **nested two levels**: it contains exactly seven per-country
zips stored uncompressed, one of which is `RDD2022/India.zip` at 0.527 GB. Inside that
inner zip the root is `India/`, containing `India/train/{images,annotations/xmls}`
(7,706 files each) and `India/test/images` (1,959 files, unlabelled). See D036.
**sha256 of outer archive:** `5d230a2941e8f2ac5fbca1a0faddee393314368dd17f9304effc11ec532845b6`

## Contents used

| | Count |
|---|---|
| India train images shipped | 7,706 |
| India train annotations (VOC XML) | 7,706 |
| India test images (unlabelled, unused) | 1,959 |
| Label files after conversion | 7,706 |
| Boxes kept | 6,831 |
| Boxes dropped | 1,372 |

Train images and annotations are exactly **1:1** with zero orphans in either
direction — this was verified before the steps in this document were run. The
published RDD2022 **test split is unlabelled and is not used**. All four of our
splits are carved from the 7,706 annotated training images (D032, corrected by D036).

## Class census

Produced by `certain-road dataset census --country India` over all 7,706 annotation
files. No `PARSE_ERROR` rows occurred — every file parsed cleanly.

| Class | Boxes | Status |
|---|---|---|
| D40 (pothole) | 3,187 | keep |
| D20 (alligator crack) | 2,021 | keep |
| D00 (longitudinal crack) | 1,555 | keep |
| D44 | 1,062 | drop |
| D01 | 179 | drop |
| D10 (transverse crack) | 68 | keep |
| D43 | 57 | drop |
| D11 | 45 | drop |
| D50 | 28 | drop |
| D0w0 | 1 | drop |

**Total: 8,203 boxes. Kept 6,831 (D00/D10/D20/D40). Dropped 1,372.**

Six class strings beyond the four official CRDDC2022 classes appear in the India
annotations. `D44` alone (1,062 boxes) exceeds the kept count of the official `D10`
class (68 boxes) by more than 15x — this is a substantial second annotation scheme,
not annotator typos. Recorded as D037 in the decision log.

**D00 and D10 merge to one output class.** `D10` (transverse crack) has only 68
boxes total — 43 in `train`, 13 in `calib` — too few to learn on their own, and
ASTM D6433 defines longitudinal and transverse cracking as a single distress type
sharing one deduct curve for asphalt pavement, so RDD2022's split is finer than the
standard it is meant to support. `convert` therefore maps both source labels to
output class `0` (D038). The source census above is unchanged — D00 and D10 still
appear as distinct rows — but the **kept per-output-class** counts are:

| Output class | Source label(s) | Boxes kept |
|---|---|---|
| `linear_crack` (id 0) | D00 + D10 | 1,623 |
| `alligator_crack` (id 1) | D20 | 2,021 |
| `pothole` (id 2) | D40 | 3,187 |

Total kept is still **6,831** — the same boxes, relabelled, not a different sample.

**Reconciliation:** kept boxes (6,831) + dropped boxes (1,372) = 8,203 = census total
(8,203). The arithmetic closes exactly; there is no unexplained gap between the
annotation-level census and the conversion output.

The conversion rejection breakdown from `certain-road dataset convert --country India`
matches the drop side of the census exactly:

| Reason | Count |
|---|---|
| unknown_class:D44 | 1,062 |
| unknown_class:D01 | 179 |
| unknown_class:D43 | 57 |
| unknown_class:D11 | 45 |
| unknown_class:D50 | 28 |
| unknown_class:D0w0 | 1 |

No `degenerate_box` or `bad_image_size` rejections occurred against the real data.

## Splits

Assignment is by salted SHA-256 of the filename stem (salt `certain-road-v1`), not a
seeded shuffle, so adding files never reshuffles existing assignments (D009). A
salted-hash split lands *near* its target proportions, not exactly on them; the counts
below are what was actually produced from the real 7,706-stem dataset, not the
proportional projection in the plan.

| Split | Target share | Actual share | Count | Purpose |
|---|---|---|---|---|
| train | 60% | 59.9% | 4,617 | detector weights |
| val | 10% | 9.8% | 757 | early stopping, model selection |
| calib | 20% | 20.1% | 1,548 | conformal calibration only |
| test | 10% | 10.2% | 784 | final reported numbers |

Total: 4,617 + 757 + 1,548 + 784 = 7,706, matching the full annotated set exactly.

**`calib` is never exposed to training or model selection.** The generated
`configs/dataset/rdd2022_india.yaml` deliberately references only `train` and `val`,
so ultralytics cannot reach the other two — verified by grep to contain no `calib` or
`test` string.

**Calib firewall, verified on the real materialised split (not just the manifest):**
every stem in `data/processed/india/images/calib` was checked against every stem in
`images/train`, `images/val`, and `images/test`. No stem appears in more than one
split directory; `calib ∩ train = 0` and `calib ∩ val = 0` exactly. Every split's
image and label directories also contain identical stem sets (image/label counts
match in all four splits: train 4,617/4,617, val 757/757, calib 1,548/1,548, test
784/784). `materialise` reported `skipped_missing_image = 0` for all four splits, as
expected given the verified 1:1 image/annotation correspondence.

**Evaluation segments at `K = 15`:** 1,548 calib frames ÷ 15 ≈ **103 evaluation
segments**. This is the sample size the conformal calibration step (D026) actually
has to work with.

## Known limitations

- 4,617 training images is small, and India is the hardest RDD2022 subset. Published
  multi-country mAP figures are not a fair benchmark for this model and must not be
  cited as though they were (D032).
- No severity annotations exist, which is why `apparent_severity` is derived from
  area quantiles as a visual-prominence proxy (D014, D028).
- No GPS or route continuity, which is why calibration uses evaluation segments
  rather than physical road segments (D010).
- RDD2022 India carries six non-CRDDC2022 class strings (`D44`, `D01`, `D43`, `D11`,
  `D50`, `D0w0`); all are dropped during conversion and counted, never silently
  discarded. `D44` at 1,062 boxes is large enough that a future multi-class extension
  should evaluate it deliberately rather than assume it is noise (D037).
