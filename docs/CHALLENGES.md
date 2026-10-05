# Challenges

Camera-Based Pothole and Crack Survey for Road Maintenance Planning · DA-2

Five problems from the decision log ([`DECISIONS.md`](DECISIONS.md)). Each gets three parts:
what broke, how it was found, and what changed. Numbers come from the result files named
in each section; where the log is the only record, the entry is named instead. Figure
numbers refer to [`results/figures/`](../results/figures/MANIFEST.md).

## 1. The same-scene leak (D061, D063)

**What broke.** India images were split per image by a salted hash (D059). Two frames of
one place, taken seconds apart, could land on opposite sides of the train/held-out
boundary. A detector trained on one has in effect seen the other, so a held-out score
over them is not held out (`results/T2/findings.md`).

**How it was found.** It took three passes.

1. D061's dHash audit (Hamming ≤ 6) flagged 1,321 India cross-split pairs, mostly
   look-alikes, because Indian dashcam frames share one layout. Ranking the flagged pairs by
   128×128 pixel correlation put true same-place pairs at the top, up to 0.9716 (figure
   02). A first check at correlation > 0.98 had found nothing: 0.98 tests for identical
   frames, and same-scene pairs top out near 0.97. The threshold was set at 0.93 by
   inspecting correlation bands (figure 03).
2. The audit hashed with PIL and the grouper with OpenCV, so after the first regrouping 19
   same-scene pairs still crossed the boundary. Both now share
   `src/certain_road/perception/dataset/dedupe.py`.
3. D061 then declared the split clean, because the audit found no same-scene pair among the
   pairs it had flagged. D063 showed that check was circular: it can only confirm the pairs
   its own prefilter selected. An exhaustive all-pairs correlation, one matrix multiply,
   found 1,373 pairs at or above 0.93 between `india_train` and held-out India (maximum
   0.9843), and 119 between India and `nonindia_train`.

**What changed.**

- Scene groups are built from every India–India pair, so the split is clean by
  construction. After the rebuild no pair reaches 0.93 across 14,254,248 India–India and
  188,858,648 India–non-India comparisons (`results/T2/exhaustive_leak.json`).
- Groups are placed so the pothole share is balanced: every split holds 46.61–46.67%
  (D063).
- 29 non-India training images were removed conservatively. D066 later showed they were
  look-alikes, not copies: their best India matches run from 0.9318 to 0.9562, and none
  reaches 0.98.
- Held-out India (2,312 images) is never uploaded to Kaggle, so no kernel can read it.
- Cross-country checks flag copies at 0.98; within India the same-scene threshold stays
  0.93 (D066). India against `nonindia_val`: 47,330,252 pairs, maximum 0.9516, 68 at or
  above 0.93, all inspected look-alikes and none a copy
  (`results/T2/exhaustive_india_vs_nonindia_val.json`, D065).
- A guard inside the Kaggle kernel refuses to train Model A if any India image appears in
  its lists (D065).

## 2. The drift alarm that caught 6 of 200 (D078)

**What broke.** The specification's drift alarm for T11 is a plain power martingale that
alarms at M ≥ 100. It missed a domain shift that arrived after 500 in-domain frames. It
detected 6 of 200 shifted streams: 193 never alarmed, 1 alarmed inside the null prefix,
and the 6 detections took a median of 1,248.5 frames (`results/T11/drift.json`, `plain`).
Its null side was fine, with a false-alarm rate of 0.005 against a budget of 0.01.

**How it was found.** `scripts/exp_drift.py` streams 500 non-India frames and then shuffled
India frames through Model A's frame scores. The signal is large: the median frame score is
0.7702 outside India and 0.9808 in India. D078 measured the cause rather than assume it.
Under the null, the martingale's log wealth falls by log ε + (1 − ε) = −0.193 nats per
frame without bound. After 500 frames it sat at −94.2 and had to repay that debt before it
could reach log 100 = 4.6 (figure 14). Varying only the prefix, on 40 streams each, gave 40
of 40 detected with no prefix, 39 of 40 after 100 frames and 0 of 40 after 500. A survey
vehicle runs in-domain for hours before it reaches new territory, and 500 frames is about
17 s of 30 fps video.

**What changed.**

- `DriftMartingale(cusum=True)` floors log M at zero, so no debt accumulates.
- The guarantee changes from Ville's P(ever alarm) ≤ 1/C to Lorden's E[frames to a false
  alarm] ≥ C, so C had to grow. A rule fixed in config before any shift stream ran picks
  the smallest of 10², 10³, 10⁴ and 10⁵ whose null false-alarm rate is within 0.01. The
  measured rates are 0.97, 0.29, 0.005 and 0.0, so C = 10,000 (`drift.json`, `cusum`).
- At the same null rate of 0.005 it detects 197 of 200 shifts: 3 alarm inside the null
  prefix and none never alarms. The median delay is 77 frames, with a range of 22–203
  (figure 15).
- The specification's statistic stays in the library and in the results, beside the
  CUSUM.
- One caveat is carried forward. C was chosen on the same null streams its 0.005 is
  measured on. The out-of-sample estimate is the 3 of 200 alarms inside the prefixes.

## 3. The Kaggle smoke failures

**What broke.** Four smoke runs of the Kaggle training kernel failed and produced no model
(D074). Each failed for a different reason:

1. `job.json` never arrived. Kaggle uploads only the file named by `code_file` and
   silently drops its siblings.
2. The kernel had no internet (`Temporary failure in name resolution`), so pip could not
   reach PyPI and ultralytics could not fetch its COCO weights. The cause was a Kaggle
   account that was not phone-verified.
3. The fallback for the second failure assumed Kaggle's image ships ultralytics. It does
   not.
4. In this ultralytics version under DDP, `train()` returns a dict rather than an object
   with `.save_dir`, so the script failed after training had already succeeded.

Model P's real runs then died twice on infrastructure. The first was pushed before the
dataset finished processing (`FileNotFoundError: p_train.txt`). The second ran on a dataset
version that landed 8,000 labels and 0 images: ultralytics marked all 9,689 pairs corrupt,
and the GPU session produced nothing.

**How it was found.** The kernel was smoke-tested before its full run, so each of the first
three failures cost 5–8 minutes rather than a four-hour run (`TASK_LOG.md`). Model P's
failures surfaced in the kernel logs. The readiness check added after the first one asked
Kaggle's `datasets files` endpoint. That endpoint paginates, so the check could pass a
dataset whose images had not arrived, which is exactly the second failure.

**What changed.**

- `scripts/kaggle_push.py` writes the job into the kernel script as an `EMBEDDED_JOB`
  literal before every push.
- `yolov8s.pt` and the ultralytics wheels travel as a private Kaggle dataset and install
  with `--no-index --no-deps`. A run no longer depends on network state, and pip can never
  replace Kaggle's CUDA-matched torch. The version that ran is recorded in `status.json`.
- The account was phone-verified, and the offline install was kept anyway.
- The results directory is read from the trainer, not from `train()`'s return value.
- `preflight_dataset` runs inside the kernel, on the mounted dataset, against the lists
  the trainer reads. Every image and label must exist, and ultralytics' own verification
  must report nothing missing or corrupt, before the optimiser sees an image.
  `tests/test_kaggle_guard.py` covers it without a GPU.

These failures have no decision entry of their own. D074 refers to D060 for them; they are
recorded in `TASK_LOG.md` (the 2026-09-22 entry), in the docstring of
`kaggle/train/train.py`, and in `docs/superpowers/plans/2026-09-22-kernel-preflight.md`.

## 4. The India gap, re-read (D069)

**What broke.** T6 measured Model A, trained on non-India roads only, at mAP50 0.5778 on
non-India validation and 0.1007 on India (`results/T6_A_nonindia_val/metrics.json`,
`results/LOCKED/A_india_full.json`; figures 04 and 05). The first write-up read that as
"Model A doesn't see Indian damage". That reading rested on IoU 0.5 matching at confidence
0.25, which cannot tell a model that finds nothing from one that finds the defect, scores
it low and draws it to a different extent.

**How it was found.** Localisation was measured again at confidence 0.001 and at IoU 0.1,
0.3 and 0.5 (`scripts/t6_localisation.py` → `results/T6/localisation.json`).

- At confidence 0.001, Model A localises 34.7% of India's 3,187 potholes at IoU 0.5 and
  54.1% at IoU 0.1.
- Between confidence 0.001 and 0.25, its recall at IoU 0.5 falls from 0.3467 to 0.0832.
  Three quarters of the potholes it localises are scored below the reporting threshold.
- India's pothole boxes are drawn larger. Their median relative area is 0.00869 against
  0.00382 outside India, and their median aspect is 1.724 against 1.457 (figure 06).

**What changed.**

- D069 rewrote the narrative: the gap is confidence collapse plus annotation extent, not
  blindness.
- That made a testable prediction: fine-tuning on Indian data should recover most of the
  gap. T7 confirmed it on `india_test` (`results/T7/A_vs_B_india_test.json`). Model B
  reaches mAP50 0.3885 against A's 0.1079. Its pothole recall at confidence 0.001 and IoU
  0.5 is 0.9007 against A's 0.3341.
- IoU 0.5 stays the primary metric, and 0.1 and 0.3 are a declared sensitivity analysis.
- Model A is never retuned because its India number looks low (D067).

## 5. The Bengaluru silence (D080)

**What broke.** On a public Bengaluru dashcam clip (`2DV-cYmIvT4`, RT Dashcam, CC BY, first
180 s), the road at about 100–110 s is broken, muddy and water-filled, and Model B is close
to silent there. Over the whole clip B confirms 9 pothole tracks. Model P, on the same frames
with the same settings, confirms 100 (`results/video/2DV-cYmIvT4/B/summary.json`,
`results/video/2DV-cYmIvT4/P/summary.json`). These counts are tracks, not potholes (D075). The proposed cause was
extent: damage too large to read as one object.

**How it was found.** The test was built so it could reject that cause (`scripts/exp_video_extent.py`
→ `results/video/2DV-cYmIvT4/extent.json`).

- Ten frames (t = 100–109 s) at confidence 0.05 were padded 1.5x, 2x and 3x, which makes the
  damage smaller, and zoomed 2x, which makes it larger. No condition, including the
  original frame, produced a single pothole box (figure 17).
- As a positive control, Model P on the same frames at the same confidence found 11
  pothole boxes in 6 of the 10.
- One water-filled pothole, drawn by eye on the t = 105 s frame, has a relative area of
  0.0045. That is the 31st percentile of India's training pothole boxes, an ordinary
  pothole size.
- The drift monitor (D078), run on B's frame scores, alarmed 1.03 s into the clip. That is
  about 100 s before the degraded stretch, so it is the footage itself that is outside B's
  domain (figure 18).

**What changed.**

- The recorded cause is B's training domain: its camera geometry and the look of wet,
  water-filled potholes. It is not scale.
- D080 records the scope limit that now frames the project. A detection count measures the
  discrete defects the detector recognises, not surface condition. Silence from a detector
  outside its domain is not evidence of a good road.
- D082 then took potholes from Model P and cracks from Model B, and never sums their pothole
  outputs. The DA-2 title, Camera-Based Pothole and Crack Survey for Road Maintenance
  Planning, describes the same scope.
- A 60 s window (120–180 s) has an annotation, done by an AI in one pass. It is not a hand
  count, and not blind in the strict sense. Against it B hits 4 of 17 potholes and P hits 10
  of 17, with P raising 20 false alarms per minute against B's 1
  (`results/video/2DV-cYmIvT4/gt_score.json`).
- Whether P transfers to such footage or only fires more stays open (D081).

---

The log records other problems in the same form, among them the external weights rejected
as unmeasurable (D053), the x86-only solver replaced by an exact DP (D062) and the τ grid
that never reached the measured floor (D076).
