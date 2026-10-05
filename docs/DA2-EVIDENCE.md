# DA-2 evidence

**Camera-Based Pothole and Crack Survey for Road Maintenance Planning** · Robot Perception
(BCSE425L) · DA-2

One page per DA-2 deliverable. Each page names the exact files in this repo that satisfy
the deliverable and gives one of three statuses:

- **complete**: the named files cover the deliverable.
- **partial**: some of it is covered, and the page names the part that is absent.
- **missing**: nothing in the repo covers it. The page names the nearest work.

Paths are relative to the repo root. A path marked *gitignored* exists on the development
machine but is not in the repo or the submission archive. To check everything this page
relies on, run `uv run python scripts/check_repo.py`, which runs every check CI runs. Figure
numbers refer to [`results/figures/`](../results/figures/MANIFEST.md).

| # | Deliverable | Status | Main evidence |
|---|---|---|---|
| 1 | Architecture | complete | `README.md` (Architecture), `docs/REPO-MAP.md` §2, `.importlinter` |
| 2 | Algorithm | complete | `src/certain_road/assess/`, `src/certain_road/survey/`, each with its tests |
| 3 | Model | complete | `results/LOCKED/*.json`, `kaggle/train/train.py` |
| 4 | Source code | complete | `dist/certain-road-DA2-source.zip` (gitignored), `README-DA2.md` |
| 5 | Screenshots | complete | figures 21 and 22, with 08, 09 and 19 |
| 6 | Preliminary results | complete | `results/RESULTS.md` and the files it cites |
| 7 | Sensor selection | partial | `docs/design.md` (Appendix: Hardware), D048, D052 |
| 8 | Wiring | partial | `docs/wiring-esp32p4.svg` |
| 9 | Embedded setup | missing | nearest: `src/certain_road/runtime/pipeline.py` |
| 10 | Integration | partial | `scripts/eval_video.py`, `tests/test_runtime_pipeline.py` |
| 11 | Prototype | partial | the CLI, simulator, video pipeline and dashboard |
| 12 | Testing | partial | `tests/` (438 tests), `scripts/check_repo.py`, `results/LOCKED/` |
| 13 | Challenges | complete | `docs/CHALLENGES.md` |

The scope change since DA-1 is in [`DA2-SCOPE-CHANGE.md`](DA2-SCOPE-CHANGE.md).

<div style="page-break-after: always;"></div>

## 1. Architecture

**Status: complete**

**Evidence**

- `README.md`, section *Architecture*: the perception stage feeds two pipelines that never
  touch. The driving pipeline asks "what do I do right now?" and the survey pipeline asks
  "what do we know about this road?" (D049).
- `docs/REPO-MAP.md` §2: the survey pipeline as a diagram, stage by stage, with the
  artifact that carries each stage to the next. It is generated from the scripts' own reads
  and writes.
- `docs/design.md` §1: one `uv` project with staged artifacts, and the invariants it
  enforces.
- `.importlinter` and `tests/test_architecture.py`: stages never import each other. They
  meet only through typed artifacts on disk, and 8 import contracts fail the build on a
  cross-stage import (`uv run lint-imports`: 8 kept, 0 broken).

**What it shows.** The survey chain runs in this order:

1. Camera frames go to the detectors: Model P for potholes, Model B for cracks (D082).
2. A conformal risk control certificate bounds the pothole miss rate (T10), and a drift
   alarm watches the detector's frame scores (T11).
3. Each evaluation segment gets a condition score, and a budget optimiser plans repairs
   (T12).
4. An offline dashboard reports both (T16).

**Absent.** The hardware side exists only as a design (page 8).

**Show it.** Open `docs/REPO-MAP.md` §2. The diagram renders on GitHub and in VS Code.

<div style="page-break-after: always;"></div>

## 2. Algorithm

**Status: complete**

**Evidence**, each module with its test:

| Algorithm | Module | Test | Decision |
|---|---|---|---|
| Conformal risk control on the image-level pothole miss rate, with scene-group re-partitioning | `src/certain_road/assess/conformal.py` | `tests/test_conformal.py` | D064, D070, D076, D077 |
| Drift alarm: a power martingale over conformal p-values, with a CUSUM reset | `src/certain_road/assess/drift.py` | `tests/test_drift.py` | D078 |
| Budget optimiser: an exact priority-indexed DP for the 0/1 knapsack | `src/certain_road/survey/allocation.py` | `tests/test_scoring_allocation.py` | D062, D079 |
| Condition score: `vision_density` → deduct → vision-estimated PCI | `src/certain_road/survey/scoring.py` | `tests/test_scoring_allocation.py` | D015 |
| Evaluation segments: fixed blocks of consecutive frames | `src/certain_road/survey/segment.py` | `tests/test_survey_segment.py` | D010 |
| Same-scene grouping for leak-free splits | `src/certain_road/perception/dataset/dedupe.py` | `tests/test_splits.py` | D061, D063 |
| Temporal confirmation (N of M), corridor test, decision state machine | `src/certain_road/driving/confirm.py`, `corridor.py`, `decision.py` | `tests/test_driving_corridor.py`, `tests/test_driving_decision.py` | D051 |

**What it shows.** Every algorithm the built system runs has a module with a docstring that
states its limits, and a test that runs without a GPU.

**Absent.** DA-1's split-conformal interval on each evaluation segment's vision-estimated
PCI, and remaining service life, are not implemented (`docs/DA2-SCOPE-CHANGE.md`, slide 4).
The vision-estimated PCI is a proxy: it uses neither the ASTM D6433 deduct curves nor the
corrected-deduct step (docstring of `src/certain_road/survey/scoring.py`).

<div style="page-break-after: always;"></div>

## 3. Model

**Status: complete**

**Evidence**

- Training: one script for every Kaggle run, `kaggle/train/train.py`, pushed by
  `scripts/kaggle_push.py`. Data lists are in `configs/data/model_a.yaml` and
  `configs/data/model_b.yaml`. Run provenance is in
  `results/T5/roadsight-train-a_verification.json` and
  `results/T5/roadsight-train-b_verification.json`.
- Three YOLOv8s models. Model A is trained on non-India data only (D060). Model B is A
  fine-tuned on `india_train` with non-India replay. Model P is B fine-tuned for potholes
  only, with BharatPotHole added to its training data (D074).
- Locked evaluations, each run once and never rewritten, with the weights' sha256:
  - `results/LOCKED/A_india_full.json`: mAP50 0.1007 on 7,706 India images.
  - `results/LOCKED/B_india_heldout.json`: mAP50 0.3718 on 2,312 held-out images.
  - `results/LOCKED/P_india_heldout.json`: pothole AP50 0.3416 on the same 2,312.
- Selection and comparison: `results/T9/B_vs_P_india_val.json` (selection, D074),
  `results/T9/B_vs_P_india_test_LOCKED.json` and `results/T7/A_vs_B_india_test.json`.
- Deployed per class (D082): potholes from Model P, cracks from Model B (`docs/REPO-MAP.md`
  §8).

**Absent from the archive.** The weight files are gitignored:
`runs/kaggle/roadsight-train-b/export/model_b/best.pt` and
`runs/kaggle/roadsight-train-p/export/model_p/best.pt`. The locked JSON files record their
sha256.

**Show it.** Figures 04, 05, 07 and 10 are the precision–recall curves; figure 09 shows
predictions.

<div style="page-break-after: always;"></div>

## 4. Source code

**Status: complete**

**Evidence**

- `dist/certain-road-DA2-source.zip` (*gitignored*: a build output, not a source file). It
  is a `git archive` of the tracked files plus the DA-2 documents, with no `data/` or
  `runs/`.
- `README-DA2.md`, the archive's front page. It points to `docs/ONBOARDING.md` to start and
  to `scripts/check_repo.py` to check.
- 51 Python files in `src/certain_road/`, 35 in `scripts/`, 43 in `tests/` and 1 in
  `kaggle/`.
- `pyproject.toml` and `uv.lock` pin every dependency. `requirements.txt` is generated from
  the lock (D056).
- `.github/workflows/ci.yml` runs exactly `uv run python scripts/check_repo.py`.

**Show it.** `uv sync --all-extras --dev`, then `uv run python scripts/check_repo.py`.

<div style="page-break-after: always;"></div>

## 5. Screenshots

**Status: complete**

**Evidence**

- `results/figures/21-dashboard-full-page.png`: the offline dashboard (T16, D083), the
  committed `results/dashboard/index.html` captured full page in headless Chrome.
- `results/figures/22-video-P-confirmed-tracks.png`: frame 4727 (t = 157.57 s) of Model P's
  annotated dashcam video. Two confirmed pothole tracks, #670 and #675, sit on potholes the
  ground truth counts as hits (`results/video/2DV-cYmIvT4/gt_score.json`).
- `results/figures/19-sim-centre-scenario.png`: the simulator (D050) running the real
  corridor and decision code on a pothole dead ahead. It is a copy of `runs/sim/centre.png`
  (*gitignored*), written by `uv run certain-road sim run --scenario centre`.
- `results/figures/08-modelB-india-heldout-labels.jpg` and
  `results/figures/09-modelB-india-heldout-predictions.jpg`: one batch of held-out India
  images, with ground truth and Model B's predictions.
- `results/dashboard/index.html`: the offline dashboard (T16, D083), one self-contained HTML
  file that opens in any browser.
- `results/video/2DV-cYmIvT4/B/summary.json` and `results/video/2DV-cYmIvT4/P/summary.json`
  name the annotated videos at `runs/video/2DV-cYmIvT4/B/annotated.mp4` and
  `runs/video/2DV-cYmIvT4/P/annotated.mp4` (*gitignored*).

**Absent from the archive.** The annotated videos themselves (`runs/video/`, *gitignored*);
figure 22 is one frame of Model P's.

**Show it.** Figures 21 and 22, or open `results/dashboard/index.html` in a browser.

<div style="page-break-after: always;"></div>

## 6. Preliminary results

**Status: complete**

**Evidence**

- `results/RESULTS.md`: every result, each table naming the file it was read from. It is
  generated by `scripts/make_report.py`, and `scripts/check_repo.py` fails if it differs
  from a fresh rebuild.
- The files it reads: `results/LOCKED/`, `results/T7/A_vs_B_india_test.json`,
  `results/T9/B_vs_P_india_test_LOCKED.json`, `results/T10/conformal.json`,
  `results/T10/feasibility.json`, `results/T11/drift.json`, `results/T12/allocation.json`
  and `results/video/2DV-cYmIvT4/`.

**What it shows**, with numbers from those files:

- On locked `india_test`, Model B scores mAP50 0.3885 against Model A's 0.1079.
- For potholes, P and B cannot be told apart on locked `india_test`: pothole AP50 0.3559
  against 0.3582, with a 95% interval for P − B of [−0.0361, +0.0298] over 1,037 scene
  groups.
- Calibrated on `india_cal`, B's certified pothole miss rate holds: at α 0.2 the mean over
  200 scene-group re-partitions is 0.1918. Calibrated on non-India data, A's mean is 0.7049.
- The CUSUM drift alarm detects 197 of 200 shifts.
- In 1,000 simulated networks under uniform traffic at α 0.5, the conservative optimiser
  picks the same repair set as the nominal one in at most 5.3% of them.

**Show it.** `results/RESULTS.md`, and figures 11–18.

<div style="page-break-after: always;"></div>

## 7. Sensor selection

**Status: partial**

**Evidence**

- `docs/design.md`, *Appendix — Hardware*: a Jetson Orin Nano Dev Kit 8 GB for compute, a
  Raspberry Pi Camera Module 3 (IMX708), a 500 GB NVMe drive, a u-blox NEO-6M GPS, power,
  and an enclosure, each with its reason. The Review 1 deck (*System Architecture*) lists
  the same core: RGB camera, Jetson Orin Nano, GPS and NVMe.
- D048: the Jetson's identity and the camera-driver risk. The IMX708 is not officially
  supported by JetPack.
- D052: the camera is deferred in favour of recorded video, and the CAN transceiver is
  deferred in favour of `vcan0`.
- `configs/project.yaml` (`edge`): `imu_hz: 100`, `can_hz: 10`, `obd_bitrate: 500000`. An
  IMU at 100 Hz is configured, but no code refers to these keys yet.
- `docs/wiring-esp32p4.svg`: the DA-2 design, an ESP32-P4 sensor hub carrying a NEO-6M GPS
  and an MPU6050 IMU.

**Absent.** No decision records the choice of the ESP32-P4 or the MPU6050. There is no
record of any hardware being fitted or tested, because T14 has not run. The camera choice
is unresolved (D048, D052).

<div style="page-break-after: always;"></div>

## 8. Wiring

**Status: partial**

**Evidence**

- `docs/wiring-esp32p4.svg`, copied as `results/figures/20-wiring-esp32p4.svg`. It shows the
  ESP32-P4 wired to the NEO-6M (VCC, GND, TX) and to the MPU6050 (VCC, GND, SCL, SDA), the
  USB link to the Jetson Orin Nano, and the 3.3 V-only rule. The GPS runs NMEA at 9600 baud,
  and the IMU sits on I²C at address 0x68, sampled at 100 Hz.

**Absent.** This is a design. There is no photograph of a wired build and no firmware. The
GPIO numbers are unassigned, because the ESP32-P4 routes UART and I²C through its GPIO
matrix.

**Show it.** Open `docs/wiring-esp32p4.svg` in a browser.

<div style="page-break-after: always;"></div>

## 9. Embedded setup

**Status: missing**

**Nearest work**

- `src/certain_road/runtime/pipeline.py`, the loop written to run on the Jetson: frame
  source → detector → perception → state machine → command → transport. It is tested on the
  Mac with a stub detector (`tests/test_runtime_pipeline.py`).
- `src/certain_road/canbus/transport.py`: `CanTransport` (SocketCAN, `vcan0` on the Jetson)
  and `NullTransport`.
- D048 sets out the deployment surface. JetPack 6 ships Python 3.10, only `ingest` and
  `detect` ship to the edge, and TensorRT engines must be built on the device.

**Absent.** There is no JetPack install record, no ONNX or TensorRT export, no ESP32-P4
firmware, and no edge latency or FPS measurement: T14 has not run, and `results/T14` does
not exist (`docs/REPO-MAP.md` §10a). The video timings in `results/RESULTS.md` were measured
on a Mac with MPS, and they do not stand in for T14.

<div style="page-break-after: always;"></div>

## 10. Integration

**Status: partial**

**Evidence**

- Software, end to end on real footage: `scripts/eval_video.py` runs a detector, a tracker
  and per-track confirmation over a dashcam clip. Over 5,400 frames at 30 fps it processes
  84.5 fps with Model B and 77.8 fps with Model P on a Mac
  (`results/video/2DV-cYmIvT4/B/summary.json`, `results/video/2DV-cYmIvT4/P/summary.json`).
- The on-device loop, `src/certain_road/runtime/pipeline.py`, is integrated and tested with
  a stub detector (`tests/test_runtime_pipeline.py`).
- `tests/test_sim_model.py` proves the simulator drives the real corridor code, not a
  parallel copy of it.
- The survey chain: `results/T10/conformal.json` → `scripts/exp_allocation.py` →
  `results/T12/allocation.json` → `scripts/build_dashboard.py` →
  `results/dashboard/index.html` (`docs/REPO-MAP.md` §2).

**Absent.** Nothing is integrated on hardware: no camera, ESP32-P4 sensor hub or Jetson
(T14). The survey takes potholes from Model P (D082), but no T12 number uses P's recall
yet.

<div style="page-break-after: always;"></div>

## 11. Prototype

**Status: partial**

**Evidence.** A software prototype, runnable on a laptop with no hardware:

- the CLI: `uv run certain-road --help` (`src/certain_road/cli.py`);
- the simulator: `uv run certain-road sim run --scenario centre` (figure 19);
- the video pipeline: `scripts/eval_video.py` (`results/video/2DV-cYmIvT4/`);
- the offline dashboard: `results/dashboard/index.html`.

**Absent.** No hardware prototype exists. T13 (simulation trials), T14 (edge hardware) and
T15 (Chennai footage) have not run (`docs/REPO-MAP.md` §10a).

<div style="page-break-after: always;"></div>

## 12. Testing

**Status: partial**

**Evidence**

- `tests/`: 438 tests in 40 files. All 438 passed at commit `119a666` on 2026-10-05
  (`uv run pytest`). `docs/REPO-MAP.md` §9 maps each test file to what it covers.
- `scripts/check_repo.py` runs every CI check: lint, formatting, import contracts, the
  suite, the repo map and the freshness of every generated file
  (`.github/workflows/ci.yml`).
- Locked evaluation discipline: `results/LOCKED/` is run once and never rewritten (D058,
  D068).
- Statistical checks: 200 scene-group re-partitions (T10), 200 shifted streams (T11) and
  1,000 paired networks (T12).
- Data checks: `tests/test_splits.py` (no scene group spans splits),
  `tests/test_kaggle_guard.py` (the kernel refuses an incomplete dataset) and
  `tests/test_repo_hygiene.py` (no committed path depends on one machine).

**Absent.** There is no hardware or field test. The simulation trials (T13), the edge
measurements (T14) and the Chennai footage (T15) have not run.

<div style="page-break-after: always;"></div>

## 13. Challenges

**Status: complete**

**Evidence**

- `docs/CHALLENGES.md`: five challenges, each with what broke, how it was found and what
  changed. They are the same-scene leak (D061, D063), the drift alarm that caught 6 of 200
  (D078), the Kaggle smoke failures, the India gap re-read (D069) and the Bengaluru silence
  (D080).
- `docs/DECISIONS.md`: all 85 decisions, append-only. Superseded entries are kept, so each
  wrong turn stays visible.
