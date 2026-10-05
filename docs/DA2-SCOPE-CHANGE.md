# Scope change, DA-1 to DA-2

Deck section · Camera-Based Pothole and Crack Survey for Road Maintenance Planning · DA-2

Four slides, ready to paste into the deck. Every number is read from `results/`, and each
slide lists the file and key it came from. "Review 1 deck" means `CERTAIN_ROAD.pdf`
(19 slides, Robot Perception BCSE425L, Review 1), which is not in this repo; its slide
titles are given so each promise can be found. A longer 27-slide version,
`CertainRoad_Review_One.pdf`, makes the same promises.

---

## Slide 1 · The title changed with the scope

**DA-1:** Certain Road — Edge-based Road Trustworthiness and Assessment
**DA-2:** Camera-Based Pothole and Crack Survey for Road Maintenance Planning

How it changed:

- **2026-09-05.** The project pivoted to an edge inspection unit with a driving pipeline
  (D049–D052). Conformal prediction was cut from that sprint (D051).
- **2026-09-22.** The RoadSight specification, adopted as T0 (commit `a23bf6a`), brought
  conformal prediction back as conformal risk control (CRC) on the pothole miss rate. It
  made that certificate the core claim (D085).
- **2026-09-28.** CRC, the drift alarm and the budget optimiser were measured (T10–T12,
  D077–D079).

> **Speaker notes.** The move from a segment-level interval to CRC came from the
> specification at T0, not from a result. The evidence on slide 3 then shaped how CRC was
> run. D004 had chosen the segment interval over CRC on false negatives. No later entry
> records why the specification reversed that, and D004 and D005 are still marked Accepted.

## Slide 2 · Promised against built

| DA-1 promised (Review 1 deck) | DA-2 |
|---|---|
| A split-conformal interval on each evaluation segment's vision-estimated PCI (*Objectives*, *Why Conformal Prediction?*) | **Not built.** Built instead: CRC on the image-level pothole miss rate, calibrated on `india_cal` and tested on `india_test` |
| An abstention gate: a wide interval sends the segment to human inspection (*Objectives*, *What Will the Final System Produce?*) | **Not built as promised.** CRC abstains when α is below the detector's miss floor, and a drift alarm flags input from outside the training domain |
| Remaining service life from the interval (*Abstract*, *What Will the Final System Produce?*) | **Not built.** No cited PCI→RSL relationship exists (D018 is Open) |
| Maintenance priority under a fixed budget (*Objectives*) | **Built.** An exact budget optimiser, run on the observed condition and on the conservative one, over 1,000 synthetic networks of 200 segments |
| Human validation of condition bands (*Timeline*, P2) | **Not run** |

The question DA-1 asked was whether uncertainty changes the repair list. In simulation it
does. At certified α 0.5 under uniform traffic, the robust and nominal optimisers choose the
same repair set in at most 5.3% of networks. Robust recovers 95.7–97.2% of the oracle's
benefit, against 95.2–96.7% for nominal. These runs use Model B's recall for every class.

*Sources:* `results/T12/allocation.json`: `robust_vs_nominal[].identical_choice_share`,
`rows[].benefit_vs_oracle` (`uniform_traffic`, α 0.5), `generator.n_trials`,
`generator.n_segments`.

## Slide 3 · What the evidence forced

1. **Model A cannot certify India.** Even keeping every box (τ = 0.001), A's pothole miss
   rate is 0.6390 on `india_cal` and 0.6227 on `india_test`, so no α below 0.6407 can be
   certified. B's floor is 0.0827 (α ≥ 0.0869) and P's is 0.1052 (α ≥ 0.1093). The α grid
   now comes from the measured floor (D070, D076). B and P carry the certificate, and A
   demonstrates the shift.
2. **Calibrate where you deploy.** Calibrated on non-India data, A promised a miss rate of
   0.2 and delivered 0.7317 on `india_test`. Over 200 scene-group re-partitions its mean
   was 0.7049, above α in every draw. Calibrated on `india_cal`, B's mean was 0.1918 (D077).
3. **A tight certificate floods false alarms.** At α 0.1, B's certified threshold is 0.001,
   and it raises 31.2 false alarms per image. False alarms fall below one per image only at
   α 0.5 (τ 0.117, 0.433 per image). T12 therefore runs at α 0.5, by a rule fixed in config,
   where B's pothole recall is 0.5254.
4. **The specified drift alarm went blind.** After 500 in-domain frames, the plain
   martingale detected 6 of 200 shifts. A CUSUM reset at the same null false-alarm rate
   (0.005) detects 197 of 200, with a median delay of 77 frames (D078).
5. **The optimiser defers the worst roads.** At a 10% budget the oracle (the exact optimiser
   with perfect information) repairs 0.46% of the true worst 20, while worst-first repairs
   39.2%. The dashboard therefore shows both plans side by side (D079, D083).
6. **A count measures discrete defects, not surface condition.** On a 180 s Bengaluru
   dashcam clip, B confirms 9 pothole tracks where P confirms 100 (D080). Potholes now come
   from P and cracks from B (D082), and the DA-2 title names that scope.

*Sources:* `results/T10/feasibility.json`: `sources.{A,B,P}_india_{cal,test}.miss_rate_floor`,
`.min_certifiable_alpha`. `results/T10/conformal.json`: `cases.A_nonindia_to_test.table`
(α 0.2), `cases.B_india_cal_to_test.table` (α 0.1, 0.5), `resampling.cases.*` (α 0.2).
`results/T12/allocation.json`: `operating_points[0]`, `rows[].mean_worst20_share`.
`results/T11/drift.json`: `plain.shift`, `cusum.shift`, `cusum.null_false_alarm_rate`.
`results/video/2DV-cYmIvT4/{B,P}/summary.json`: `result.unique_confirmed_tracks`. The α 0.5
rule is `allocation.max_false_alarms_per_image: 1.0` in `configs/project.yaml`.

## Slide 4 · Moved to the next phase

- **The segment-level interval and abstention.** A split-conformal interval on each
  evaluation segment's vision-estimated PCI, and the `inconclusive` flag built on it
  (D004, D005, D013). It needs a reference PCI (`pci_ref`) per evaluation segment.
- **Remaining service life.** It needs a published PCI→RSL relationship with its citation,
  or `mode: pci_only` (D018).
- **Validation against human raters.** The rating set is validation only, never a dev set.
- **A certificate for cracks.** CRC covers potholes only, so cracks stay under-counted in
  T12 (D079).
- **T12 on Model P's recall.** No T12 number reflects D082's pothole channel yet.
- **Model P on dashcam footage.** P's transfer stays open until it is scored against a hand
  count, which replaces the current one-pass AI annotation (D081).
- **Edge hardware and field data.** The Jetson pipeline and the ESP32-P4 sensor hub
  (`docs/wiring-esp32p4.svg`, T14), Chennai footage (T15) and the simulation trials (T13)
  have not run.

*Sources:* `docs/REPO-MAP.md` §10a (tasks not run) and §10b (open decisions).
