# Bengaluru silence — scale, Model P, drift, and the scope record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explain, with measurements, why Model B is silent on the degraded stretch
of the Bengaluru clip (`2DV-cYmIvT4`, t≈100–110 s), compare Model P, test whether
the D078 drift monitor notices, and record the scope limit as a decision.

**Architecture:** `scripts/eval_video.py` gains `--model B|P`. A new
`scripts/exp_video_extent.py` runs the scale diagnostic and the drift stream,
writing `results/video/2DV-cYmIvT4/extent.json`, `scale.png`, `drift.png`; its
per-frame video scores are cached in `runs/video/2DV-cYmIvT4/frame_scores.npz`
(delete to force fresh inference, as in `t9_b_vs_p.py`).

**Tech stack:** ultralytics 8.4.115, `certain_road.assess.drift`, matplotlib.

## Global constraints

- Model B = `runs/kaggle/roadsight-train-b/export/model_b/best.pt` (3-class, pothole 2); Model P = `runs/kaggle/roadsight-train-p/export/model_p/best.pt` (1-class, pothole 0). Pothole index from `model.names`, never a literal.
- D074 stands: Part 2 reports, it does not re-select.
- Drift (user's choice 2026-09-28): **Model B scores, reference bag = B on `india_val`** from `results/T9/B_india_val_run/val/predictions.json`. Frame score = `frame_score(confs, topk=3)`, all classes, confidences rounded to 5 dp as in the reference JSON. Video predictions use the frozen eval block (conf 0.001, iou 0.7, max_det 300, imgsz 640, rect False) **and val's `multi_label=True` NMS**. D078 statistics: CUSUM at 10⁴ (headline), plain at 10², eps 0.5.
- The decision takes the **next free D-number** at write time — D079 was taken by T12 (`df7e5e6`). Never renumber.
- The record states what the evidence shows, even where it departs from "too large".
- Tunables in `configs/eval/video.yaml`. No commits. Another session is committing in this repo; touch only files listed here.

---

### Task 1: Model P on the same clip, B rerun beside it

- **Goal:** `results/video/2DV-cYmIvT4/{B,P}/summary.json` and matching MP4s exist, produced by one code version under identical settings.
- **Why:** P saw BharatPotHole (Indian dashcam potholes, reportedly water-filled); B did not. Without P's numbers, "the system can't see this road" can't be separated from "B can't".
- **Files:** modify `scripts/eval_video.py`, `configs/eval/video.yaml`; move the earlier B outputs into `B/`.
- **Steps:**
  - [x] Config `weights:` -> `models: {B: …, P: …}`; CLI `--model` (default B); `pothole = names.index("pothole")`; outputs under `<stem>/<model>/`; per-model contamination caveat.
  - [x] View 12 BharatPotHole training images with pothole labels — does it contain water-filled potholes? (premise check, reported either way)
  - [x] Run B, then P, sequentially, nothing else on the GPU.
- **Done when:** `jq '.model.name, .result.unique_confirmed_tracks, .result.raw_detections' results/video/2DV-cYmIvT4/{B,P}/summary.json` prints both; `uv run pytest tests/test_eval_video.py -q` -> 6 passed.

### Task 2: Scale diagnostic and GT extent

- **Goal:** detections vs padding factor (1.0, 1.5, 2.0, 3.0, plus a 2× zoom arm) on 10 frames t=100…109 s at conf 0.05 are tabulated and drawn, beside india_train GT relative-area stats and two hand-drawn extents.
- **Why:** "too large" predicts detections rise with padding; "too small" predicts they rise with zoom; "appearance" predicts neither. The record can only name one of these with this table.
- **Files:** create `scripts/exp_video_extent.py`; add `extent:` block to `configs/eval/video.yaml`.
- **Steps:**
  - [x] Hand-draw on t=105 s: the whole degraded stretch, and one discrete water-filled pothole; store as fractional boxes in config.
  - [x] Pad (grey 114, centred) / zoom crop; `predict` B at conf 0.05; count all-class and pothole boxes, max conf.
  - [x] GT: `w*h` from `data/yolo/labels` over `india_train.txt`, all classes and pothole; median, IQR, max; percentile of each hand box.
  - [x] Figure `scale.png`: t=105 s at 1.0 / 2.0 / 3.0 / zoom with boxes.
- **Done when:** `jq '.scale.by_factor' results/video/2DV-cYmIvT4/extent.json` prints 5 rows of counts; `jq '.gt_area' …` prints median/IQR/max; `scale.png` viewed.

### Task 3: Drift stream over the clip

- **Goal:** the D078 monitor's verdict on this video — alarm or not, and when — at 30 fps and at 1 fps, with a figure of zero-detection frames and the log-martingale traces.
- **Why:** if the detector is silent and the monitor alarms, the system knows it is blind; if the monitor is also silent, the blindness is invisible at runtime, which is worse and must be recorded.
- **Files:** `scripts/exp_video_extent.py`; `drift:` block in `configs/eval/video.yaml`.
- **Steps:**
  - [x] Equivalence check first: re-score 20 `india_val` images through the video path; `max |Δ frame_score|` vs the reference JSON must be < 1e-3, else stop.
  - [x] Score all 5,400 frames (cache); run `run_stream` CUSUM and plain, stride 1 and stride 30.
  - [x] Figure `drift.png`: top — per-frame detection count ≥ 0.05 with zero-detection frames marked; bottom — log M traces with log thresholds and alarm markers, x in seconds.
- **Done when:** script prints the equivalence Δ; `jq '.drift' …` gives alarm frame/second (or null) for 4 runs; `drift.png` viewed.

### Task 4: The scope record

- **Goal:** a new decision (next free number) states the scope limit with the Task 1–3 numbers and links D069's extent finding.
- **Why:** without it, the pothole count from `eval_video` reads as a survey of the road, and the silence reads as a clean road.
- **Files:** `docs/DECISIONS.md` (index row + section at the end).
- **Steps:**
  - [x] Re-read the log tail and index immediately before writing; take max+1.
  - [x] Write the entry from `extent.json` and the two summaries — numbers copied, not retyped from memory.
- **Done when:** `grep -c "^## D0NN" docs/DECISIONS.md` = 1 and `grep -c "^| D0NN" …` = 1 for the number used; `uv run pytest -q` passes; `uv run ruff check` clean on touched files.
