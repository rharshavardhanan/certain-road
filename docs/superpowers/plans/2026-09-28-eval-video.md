# eval_video — per-track pothole confirmation on real dashcam video

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command turns a forward-facing road video into an annotated MP4 and a
`summary.json` that counts unique **confirmed tracks** of Model B's pothole channel,
with latency and honest caveats.

**Architecture:** `scripts/eval_video.py` reads frames with OpenCV, calls
`model.track(persist=True)` (ByteTrack) per frame, captures the raw pre-tracker
boxes through a predictor callback, applies the horizon gate, then D075 per-track
3-of-5 confirmation via one `certain_road.driving.confirm.Confirmer` per track ID.
Frames are piped to `ffmpeg` as H.264. The confirmation step is a pure function,
tested without a model.

**Tech stack:** ultralytics 8.4.115 (ByteTrack needs `lap`), OpenCV, ffmpeg,
yt-dlp (Homebrew), pytest.

## Global constraints

- Model B = `runs/kaggle/roadsight-train-b/export/model_b/best.pt`, 3-class; pothole is `pothole_class: 2` from `configs/project.yaml`.
- conf **0.25**, tracker `bytetrack.yaml`, `persist=True`.
- D075 confirmation: **same track ID present in >= 3 of the last 5 frames**.
- ROI gate: drop a box when its bottom edge is above the horizon (`y2 < horizon_frac * H`).
- Tunables live in `configs/eval/video.yaml`, never literals in code.
- The count is reported as **tracks, not potholes** (D075), everywhere it appears.
- Dependencies via `uv add` only; `requirements.txt` regenerated with `uv export --format requirements-txt --no-hashes`.
- No commits (user's global rule). Another session is committing in this repo — do not touch its files (`drift.py`, `test_drift.py`, `project.yaml`, `results/T11`, `exp_drift.py`).

## Decisions settled in brainstorming (2026-09-28)

- D075 did not exist (index gap D074 -> D076). **Write it**, including the user's
  addition: confirmed count is of TRACKS; ID switches bias it up, merges down;
  GT trials report tracks beside GT-matched potholes; real video reports tracks.
- Contamination caveat stated **accurately**: B never saw BharatPotHole (only P did).
- The design lives in this file; no separate spec doc.

---

### Task 1: D075 confirmation step, tested, and logged

- **Goal:** A pure `confirm_step` implements horizon gate + per-track 3-of-5, its
  behaviour (including the ID-switch double count) is pinned by tests, and D075
  records the rule.
- **Why:** The count is the headline number. A silent error in the window, the
  gate, or pooling across IDs changes it with nothing visibly wrong in the MP4; and
  the repo's CLAUDE.md makes a decision change without a log entry incomplete.
- **Files:** create `scripts/eval_video.py` (function only), `tests/test_eval_video.py`,
  `configs/eval/video.yaml`; modify `docs/DECISIONS.md` (index row + section between D074 and D076).
- **Steps:**
  - [ ] Write tests: 3 hits spread over 5 frames confirms on the 3rd hit and not before · a one-frame flash never confirms · 2-of-5 never confirms · a box above the horizon never confirms even at 5/5 · hits split over three IDs do not pool (the old D051 condition-confirmer would have fired) · one pothole re-acquired under a new ID confirms twice (the D075 upward bias, pinned).
  - [ ] Run `uv run pytest tests/test_eval_video.py` -> fails on import.
  - [ ] Implement:
    ```python
    def confirm_step(confirmers, tracks, horizon_y, required, window) -> set[int]:
        present = {tid for tid, y2 in tracks if y2 >= horizon_y}
        for tid in present - confirmers.keys():
            confirmers[tid] = Confirmer(required, window)
        return {tid for tid, c in confirmers.items() if c.update(tid in present)}
    ```
  - [ ] Write `configs/eval/video.yaml` and the D075 entry (re-read DECISIONS.md immediately before editing; another session writes to it).
- **Done when:** `uv run pytest tests/test_eval_video.py -q` -> `6 passed`, and
  `grep -c "^## D075" docs/DECISIONS.md` -> `1` and `grep -c "^| D075" docs/DECISIONS.md` -> `1`.

### Task 2: A licensed, forward-facing pothole video with provenance

- **Goal:** `data/video/<id>.mp4` (1-3 min, forward-facing, potholes visible) sits
  beside yt-dlp's `<id>.info.json`, and URL, channel and licence are known.
- **Why:** Without provenance the result cannot be cited or re-run; a non-CC video
  cannot be redistributed even as an annotated derivative.
- **Files:** `data/video/` (gitignored).
- **Steps:**
  - [ ] Search YouTube's Creative-Commons filter via yt-dlp; print id, duration, licence, channel.
  - [ ] Download best candidate at <= 720p with `--write-info-json`.
  - [ ] Extract 3 frames, view them: forward-facing? potholes? where is the horizon?
- **Done when:** `ffprobe` duration is 60-180 s and
  `jq '.license,.channel,.webpage_url' data/video/<id>.info.json` prints all three
  non-null (or the licence gap is reported, not hidden).

### Task 3: Runner — annotated MP4 and summary.json

- **Goal:** `uv run python scripts/eval_video.py data/video/<id>.mp4 --horizon <f>`
  writes `runs/video/<id>/annotated.mp4` (H.264) and `results/video/<id>/summary.json`.
- **Why:** This is the deliverable: the count, the per-track frames, FPS, latency
  p50/p95, provenance and caveats in one inspectable file plus a video a human can check.
- **Files:** modify `scripts/eval_video.py`; modify `pyproject.toml`, `uv.lock`,
  `requirements.txt` (`uv add lap`).
- **Steps:**
  - [ ] `uv add lap`; regenerate `requirements.txt`; `import ultralytics.trackers` succeeds.
  - [ ] Raw boxes: `model.add_callback("on_predict_postprocess_end", grab)` **before** the first `track()` call, so it runs ahead of the tracker's callback that replaces `result.boxes`.
  - [ ] Per frame: time `model.track(...)` with `perf_counter`; gate + confirm; draw raw thin (yellow below horizon, grey above), horizon line, confirmed tracks green thick with `#id`, running "unique confirmed tracks: N"; pipe to `ffmpeg -c:v libx264 -pix_fmt yuv420p`.
  - [ ] Summary: video + source provenance + sha256; model; settings; `unique_confirmed_tracks`, `tracks_seen`, per-confirmed-track `{frames_detected, first_frame, last_frame, confirmed_at}`; video/processing/end-to-end FPS; latency p50/p95 excluding `latency_warmup` frames; caveats.
  - [ ] Run on the Task 2 video; open the MP4; spot-check annotated frames by eye.
- **Done when:** `ffprobe -show_entries stream=codec_name` on the MP4 -> `h264`, frame
  count equals the source's; `jq '.result.unique_confirmed_tracks, .performance.latency_ms'`
  prints an integer and `{p50, p95}`; `uv run ruff check scripts/eval_video.py tests/test_eval_video.py` clean;
  `uv run pytest -q` passes.
