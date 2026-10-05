# Deck figures

Camera-Based Pothole and Crack Survey for Road Maintenance Planning · DA-2 · copied 2026-10-04,
figures 21 and 22 captured 2026-10-05

Figures 01–20 are byte copies, numbered in the order a deck would show them. **Edit the
source, not the copy.** Each of their sources is a committed file at commit `0a9d02a` except
two: figure 19 comes from the gitignored `runs/`, and figure 20 was drawn for DA-2. Figures 21
and 22 are captures, not copies: 21 renders the committed `results/dashboard/index.html`,
and 22 is one frame of the gitignored `runs/video/2DV-cYmIvT4/P/annotated.mp4`.

PR-curve legends show ultralytics' own AP. The numbers this project reports come from
pycocotools and are named beside each curve.

| Copy | Copied from | Produced by | What it shows |
|---|---|---|---|
| `01-dataset-pool-B-samples.jpg` | `results/T2/qa_pool_B.jpg` | no committed script; added with the T2 pool build (commit `66204f9`) | Ground-truth boxes on five images each from `india_test`, `india_full`, `india_heldout` and `nonindia_replay`, and on five Norway images resized from 4040 to 1280 px. |
| `02-leak-same-scene-pairs.jpg` | `results/T2/qa_dup_top.jpg` | no committed script; added with D061 (commit `0ccef57`) | The four closest train/held-out India pairs by pixel correlation (0.9716 to 0.9679, dHash 3 to 6). Each pair is the same place seconds apart: the same-scene leak (D061). |
| `03-leak-threshold-bands.jpg` | `results/T2/qa_dup_calib.jpg` | no committed script; added with D061 (commit `0ccef57`) | Example pairs from four correlation bands (0.955–0.975, 19 pairs; 0.935–0.955, 94; 0.915–0.935, 177; 0.895–0.915, 196). This inspection set the same-scene threshold at 0.93 (`results/T2/findings.md`). |
| `04-modelA-nonindia-val-PR.png` | `results/T6_A_nonindia_val/val/BoxPR_curve.png` | `scripts/eval_open.py`, through ultralytics `model.val(plots=True)` | Model A's precision–recall curves on non-India validation, 6,142 images. Legend mAP@0.5 0.579; reported 0.5778 (`results/T6_A_nonindia_val/metrics.json`). |
| `05-modelA-india-PR.png` | `results/LOCKED/A_india_full_run/val/BoxPR_curve.png` | `scripts/eval_locked.py`, through ultralytics `model.val(plots=True)` | Model A on all 7,706 India images, locked. Legend mAP@0.5 0.097; reported 0.1007 (`results/LOCKED/A_india_full.json`). Against figure 04 this is the India gap (D067–D069). |
| `06-modelA-india-pothole-misses.jpg` | `results/T6/qa_india_pothole_misses.jpg` | no committed script; added with the T6 follow-up (commit `8abd0fd`) | Twelve India potholes Model A missed at IoU 0.5 (ground truth green, pothole predictions red with confidence). In the top two rows a prediction exists at IoU 0.1–0.5: the extent and confidence failure D069 describes, not blindness. |
| `07-modelB-india-heldout-PR.png` | `results/LOCKED/B_india_heldout_run/val/BoxPR_curve.png` | `scripts/eval_locked.py`, through ultralytics `model.val(plots=True)` | Model B on held-out India (2,312 images: `india_cal` and `india_test`), locked. Legend mAP@0.5 0.370 (linear 0.243, alligator 0.511, pothole 0.357); reported 0.3718 (`results/LOCKED/B_india_heldout.json`). |
| `08-modelB-india-heldout-labels.jpg` | `results/LOCKED/B_india_heldout_run/val/val_batch0_labels.jpg` | `scripts/eval_locked.py`, through ultralytics `model.val(plots=True)` | The first validation batch of held-out India images with their ground-truth boxes. |
| `09-modelB-india-heldout-predictions.jpg` | `results/LOCKED/B_india_heldout_run/val/val_batch0_pred.jpg` | `scripts/eval_locked.py`, through ultralytics `model.val(plots=True)` | The same 16 images with Model B's predicted boxes and confidences. Pair it with figure 08. |
| `10-modelP-india-heldout-PR.png` | `results/LOCKED/P_india_heldout_run/val/BoxPR_curve.png` | `scripts/eval_locked.py`, through ultralytics `model.val(plots=True)` | Model P (pothole only) on the same 2,312 held-out images. Legend AP 0.341; reported 0.3416 (`results/LOCKED/P_india_heldout.json`). |
| `11-crc-risk-vs-alpha.png` | `results/T10/risk_vs_alpha.png` | `scripts/exp_conformal.py` | Certified α against the pothole miss rate realised on `india_test`. B, P and A are calibrated on `india_cal`, and A again on non-India. The India-calibrated lines sit at or below risk = α; the non-India line sits far above it (D070, D076, D077). |
| `12-crc-false-alarms-vs-alpha.png` | `results/T10/false_alarms_vs_alpha.png` | `scripts/exp_conformal.py` | False alarms per image at the certified threshold, for B and P on a log scale: 31.2 for B at α 0.1, and under one only from α 0.5. The certificate controls misses, not false alarms (D077). |
| `13-crc-resampled-risk.png` | `results/T10/resampled_risk_hist.png` | `scripts/exp_conformal.py` | 200 scene-group re-partitions at α 0.2. B calibrated on `india_cal` centres on α (mean 0.19); A calibrated on non-India centres on 0.70 (D064, D077). |
| `14-drift-martingale-traces.png` | `results/T11/martingale_traces.png` | `scripts/exp_drift.py` | Ten streams of Model A frame scores, 500 non-India frames and then India. The spec's plain power martingale falls to about −100 in log wealth before the shift, and none of the ten reaches its alarm at M = 100 within 2,000 frames. The CUSUM reset (D078) stays near zero and crosses M = 10,000 soon after the shift. |
| `15-drift-cusum-delay.png` | `results/T11/delay_hist.png` | `scripts/exp_drift.py` | CUSUM detection delay over 200 shifted streams at threshold 10,000: median 77 India frames, 3 alarms inside the null prefix, none that never alarmed (D078). |
| `16-allocation-policies.png` | `results/T12/allocation.png` | `scripts/exp_allocation.py` | Repair allocation at certified α 0.5 (τ 0.117, Model B): share of oracle benefit (top) and share of the true worst 20 repaired (bottom) against budget, for oracle, nominal, robust, greedy and random, under uniform and varying traffic (D079). Simulated at Model B's recall for every class, potholes included (D082). |
| `17-video-scale-test.png` | `results/video/2DV-cYmIvT4/scale.png` | `scripts/exp_video_extent.py` | Model B at conf 0.05 on the degraded Bengaluru stretch (t = 100–109 s), padded 1x to 3x and zoomed 2x. No condition produces a pothole box (D080). |
| `18-video-drift-alarm.png` | `results/video/2DV-cYmIvT4/drift.png` | `scripts/exp_video_extent.py` | Model B's boxes per frame over the 180 s clip (none at conf ≥ 0.05 in 4,283 of 5,400 frames), and the drift statistics on it. The CUSUM alarms at 1.0 s on every frame and at 15.0 s at about 1 fps (D080). |
| `19-sim-centre-scenario.png` | `runs/sim/centre.png` (gitignored) | `uv run certain-road sim run --scenario centre`, rendered 2026-10-04 | The kinematic simulator (D050), scenario "centre": a pothole dead ahead with both sides clear. Left, the top-down path coloured by urgency; right, the camera frame with the pothole box inside the corridor. |
| `20-wiring-esp32p4.svg` | `docs/wiring-esp32p4.svg` | drawn by hand for DA-2, 2026-10-04 | ESP32-P4 sensor hub: NEO-6M GPS (VCC, GND, TX) and MPU6050 IMU (VCC, GND, SCL, SDA), with the 3.3 V-only rule and the USB link to the Jetson Orin Nano. A design for T14: not built or tested. |
| `21-dashboard-full-page.png` | `results/dashboard/index.html`, rendered (not copied) | headless Chrome 154.0.8037.93 over the DevTools protocol, 2026-10-05: 1,440 px wide, full page (10,127 px), `prefers-color-scheme: light`, its six lazy-loaded figures forced to load first | The offline dashboard (T16, D083) at its opening state, top to bottom: both repair plans side by side at a 10% budget, the true worst 20 road by road, the averages over 1,000 networks, the Map placeholder (T14 not run), the models, conformal risk control, the drift alarm, and the Simulation placeholder (T13 not run). |
| `22-video-P-confirmed-tracks.png` | `runs/video/2DV-cYmIvT4/P/annotated.mp4` (gitignored), frame 4727 | `scripts/eval_video.py --model P` wrote the video; `ffmpeg -vf "select=eq(n\,4727)"` extracted the frame, 2026-10-05 | Model P on the Bengaluru dashcam clip at t = 157.57 s. Two confirmed tracks (#670 and #675, thick green) sit on water-filled potholes that the ground truth counts as hits (`results/video/2DV-cYmIvT4/gt_score.json`); thin yellow boxes are raw detections, and the cyan line is the horizon gate. The frame is the one with the most live confirmed tracks that hit a ground-truth pothole, and no live false alarm. The overlay counts tracks, not potholes (D075). Video: YouTube `2DV-cYmIvT4`, RT Dashcam, Creative Commons Attribution. |

## Not copied, and why

- **Ultralytics' other plots** from each evaluation: the P, R and F1 curves, the batch 1–2
  mosaics and the confusion matrices. The confusion counts the project reports come from its
  own scorer at conf 0.25 (`results/T6/gap_analysis.json`, `results/T7/A_vs_B_india_test.json`),
  not from these matrices.
- **T2 audit montages outside the deck's story**: `qa_duplicates.jpg` (dHash flags by Hamming
  band), `qa_adjacent_pairs.jpg` (D059), `qa_biggest_group.jpg` (D063),
  `qa_india_vs_nonindia_val.jpg` (D065), `qa_removed29.jpg` (D066) and `qa_pool_A.jpg`.
- **`results/T1/qa/`**: gitignored renders, rebuilt by `scripts/qa_raw.py`.
- **The dashboard's figures**: they are figures 11–16, embedded in
  `results/dashboard/index.html`.

## Not available

- No photograph of hardware exists. T14 (edge hardware) has not run.
