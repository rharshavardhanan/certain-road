# MuJoCo live survey demo

2026-10-04 · for the DA-2 review · built in five steps, each reported before the next

> **For agentic workers:** executed inline with superpowers:executing-plans. TodoWrite is not
> available in this harness, so the checkboxes below are the running state.

**Goal:** a vehicle drives a seeded, randomly generated road in MuJoCo. It detects damage
with the real Model P (potholes) and Model B (cracks), and builds the survey live with the
real scoring and allocation code. It ends on a result screen an examiner can read from 3 m.

**Architecture:** `sim/mujoco/` is a composition root, like `cli.py`. It renders the road
and drives the camera, and everything it measures goes through the real code: the
detectors, `certain_road.core.geometry`, `certain_road.survey.scoring` and `.allocation`,
and `certain_road.assess.drift`. Damage is baked into the road texture tiles from the trial
photos. MuJoCo renders those tiles in perspective, so every instance is
perspective-correct on the road plane by construction.

**Tech:** MuJoCo 3 (new dependency) for rendering. NumPy, OpenCV and Pillow for textures and
the screen. Ultralytics for the two detectors.

## Decisions taken without asking (open to review at the step-1 checkpoint)

- **Texture source.** `data/raw/trial_textures/` did not exist. It is a copy of
  `indian_road_textures.zip` (verified with `unzip -t`). These are not the user's photos:
  QR4Change (Pune potholes, Mendeley 10.17632/zndzygc3p3.2) and BD-N6 (Bangladesh NH-N6
  cracks and asphalt, Zenodo 10.5281/zenodo.18072573 and .18114226), both CC BY 4.0, so
  the docs and the honesty caption credit them. A loose copy sits untracked in the repo
  root (`indian_road_textures/`); it is not used, and it is left for the user to delete.
- **No training images.** Every texture is checked for copies against the training pools:
  RDD2022 train for all countries (cached vectors) and BharatPotHole, at D066's 0.98. This
  catches copies of whole images, not crops. Provenance covers crops: both source datasets
  are separate from RDD2022 and BharatPotHole.
- **Curation.** The "linear" folder comes from BD-N6's alligator category. Each texture's
  class, crop and damage ellipse are set by eye and committed in
  `configs/sim/textures.yaml`, and the ground-truth class is the curated class.
- **Camera.** The numbers come from the `sim:` block of `configs/project.yaml`: 1.3 m high,
  10° down, HFOV 1.2 rad, 1280×720. `configs/sim/robot.yaml` describes the indoor robot
  (0.18 m, 15°, 640×640), so it is not used for this camera.
- **Lane.** Keep left, as in India: the vehicle drives the left lane of a two-lane road.
- **Sizes.** True footprints are lognormal around the project's design medians: 0.3 m²
  linear, 2.0 m² alligator, 0.25 m² pothole, log-σ 0.6 (`configs/project.yaml`,
  allocation).
- **Package name.** `sim/mujoco/`, as specified. Inside it, `import mujoco` is the library,
  because `sim/` itself is never put on `sys.path`.
- **Commit.** Nothing is committed until the step-1 look is approved. Then everything is
  committed by explicit path, with a decision entry for the new simulator and dependency.

## Files

| File | Responsibility |
|---|---|
| `configs/sim/mujoco.yaml` | every simulator tunable: road, presets, surface, light, camera effects |
| `configs/sim/textures.yaml` | curated textures: class, crop, damage ellipse, usable flag |
| `sim/__init__.py`, `sim/mujoco/__init__.py` | package markers |
| `sim/mujoco/textures.py` | load and prepare textures; the training-copy check |
| `sim/mujoco/road.py` | seeded road layout and clustered damage; ground truth to and from JSON |
| `sim/mujoco/surface.py` | bake road tiles: tiled asphalt, markings, composited damage |
| `sim/mujoco/scene.py` | MJCF: road tiles, kerbs, shoulders, sky, sun and shadows, roadside objects, camera |
| `sim/mujoco/camera.py` | camera pose with pitch and roll noise; motion blur, sensor effects, JPEG |
| `sim/mujoco/demo.py` | CLI: `--preset --seed`, `--screenshot`, later the live loop and `--record` |
| `tests/test_mujoco_road.py` | ground-truth round-trip; same seed gives identical ground truth |
| `tests/test_mujoco_camera.py` | the MuJoCo camera agrees with `core.geometry` IPM (analytic, no GL) |
| `pyproject.toml`, `uv.lock`, `requirements.txt` | add `mujoco`; requirements regenerated from the lock |

---

## Step 1 — scene generation with textures, and one screenshot

### Task 1.1 — textures in place, curated and leak-checked

**Goal** `data/raw/trial_textures/` holds the 49 photos. A committed manifest gives each
one's class, crop and damage ellipse, and no texture is a copy of a training image.

**Why** Without curation the ground truth carries wrong classes. Without the check, a
texture could be an image the models were trained on, and the sim would flatter them.

**Files** `configs/sim/textures.yaml`, `sim/mujoco/textures.py`

**Steps**
- [x] Unzip the verified zip into `data/raw/trial_textures/`.
- [x] Render a labelled contact grid per class with a 0–1 coordinate overlay, and choose a
  crop and ellipse per texture by eye. Drop the blurred and ambiguous ones, with reasons.
- [x] Copy check: compute `dedupe.norm_vec` for each texture, compare against the cached
  RDD2022 vectors and fresh BharatPotHole vectors, and report the maximum correlation.
- [x] Render a QA montage of every kept texture with its ellipse drawn on.

**Done when** `uv run python -m sim.mujoco.textures --check` prints the kept count per
class and `max correlation with any training image: <0.98`, and the QA montage shows every
ellipse on its damage.

### Task 1.2 — seeded road layout and ground truth

**Goal** Each of the 5 presets plus a seed gives a 400–600 m two-lane road with clustered
damage, written as ground truth. Each instance has a class, position, true extent and
texture, and the same seed reproduces it byte for byte.

**Why** Seeded reproducibility is a success criterion. The ground truth is what recall and
false alarms per km are scored against at step 4.

**Files** `sim/mujoco/road.py`, `configs/sim/mujoco.yaml`, `tests/test_mujoco_road.py`

**Steps**
- [x] Write the failing tests: a JSON round-trip that preserves every field, and two
  generations with the same seed that are equal.
- [x] Implement the generator. A smooth damage-intensity field along the road varies by
  preset (mixed is a step from good to poor). Parents are placed by intensity, and children
  form clusters around them (a Thomas process). Linear cracks sit in the wheel paths;
  potholes sit inside or beside alligator patches. Instances that overlap too much are
  rejected.
- [x] For the random preset, take class proportions and per-image rates from
  `results/T2/split_audit.json` (`india_train`).
- [x] Run the tests until they pass.

**Done when** `uv run pytest tests/test_mujoco_road.py -q` passes, and two calls of
`--preset poor --seed 0 --ground-truth` produce identical files (`cmp`).

### Task 1.3 — the scene, the camera and one screenshot

**Goal** The scene compiles in MuJoCo and renders a 1280×720 camera frame from the left lane
at 1.3 m and 10° down. The frame shows tiled asphalt, markings, kerbs, shoulders, sky, sun
shadows, roadside objects and composited damage, after pitch and roll noise, motion blur
and JPEG.

**Why** This is the step-1 deliverable, and how real it looks decides whether to continue.

**Files** `sim/mujoco/surface.py`, `sim/mujoco/scene.py`, `sim/mujoco/camera.py`,
`sim/mujoco/demo.py`, `tests/test_mujoco_camera.py`, `pyproject.toml`, `uv.lock`,
`requirements.txt`

**Steps**
- [x] `uv add mujoco`, then regenerate `requirements.txt` from the lock.
- [x] Write the failing camera test: a ground point projected through the MuJoCo camera's
  pose (`cam_xpos`, `cam_xmat`) and intrinsics (`fovy`) lands on the same pixel as
  `core.geometry.project`.
- [x] Bake the road tiles. Asphalt comes from the four plain photos, levelled to a common
  tone and tiled with random offsets, flips and feathered seams. Then lane and edge
  markings, then damage alpha-composited onto the asphalt and colour-matched to it.
- [x] Assemble the MJCF: tile meshes, kerbs, shoulders, a skybox gradient, a sun that
  follows the vehicle with a tight shadow box, haze, and poles, a wall and signs.
- [x] Render: sub-frame motion blur over the exposure, pitch and roll noise, sensor noise
  and vignette, then a JPEG round-trip.
- [x] Save the screenshot to `runs/mujoco/` and look at it. Fix what looks synthetic.
- [x] Probe, not step 2: run Model P and Model B once on the screenshot and record what
  they find.

**Done when** `uv run pytest tests/test_mujoco_camera.py tests/test_mujoco_road.py -q`
passes;
`uv run python -m sim.mujoco.demo --preset poor --seed 0 --screenshot runs/mujoco/step1.png`
writes a 1280×720 image; and `uv run python scripts/check_repo.py` exits 0.

**Stop here and show the screenshot.**

Step 1 record (2026-10-05): textures copied, curated (32 damage, 4 asphalt kept) and
audited clean (D086, `docs/texture-provenance.md`). 10 new tests pass and the full suite
gives 448 passed, exit 0. Two runs of `--preset poor --seed 0` give byte-identical ground
truth. `check_repo.py` was run as its steps (ruff, format, import-linter, pytest,
freshness), not as the script, so the shared REPO-MAP is not rewritten mid-session.
Damage first rendered as invisible smudges, for four reasons: potholes were too small,
the colour match averaged patches back to asphalt, MuJoCo's isotropic mipmaps erased thin
cracks at grazing angles, and water looked dry from above. The fixes are real sizes
(0.3-1.2 m), a percentile colour match, 3x supersampling, crack contrast and sun-aligned
pothole shading with sky sheen. Probe on the final frame: Model P finds the 10 m pothole
(0.62); Model B finds the 5.5 m alligator patch (0.79) but not the 10 m one.

---

## Step 2 — drive loop with live detection

### Task 2.1 — the drive loop

**Goal** The camera drives the road at 20 km/h, one frame every 5/9 m (10 fps of simulated
time), so every 9th frame is a 5 m survey sample (`edge.sample_every_m`, D006). On each
frame, Model P and Model B track with ByteTrack (`configs/eval/video.yaml`) under D082:
potholes from P only, cracks from B only, B's pothole channel discarded. A track is
confirmed by D075's `confirm_step` (3 of 5 frames). The gate is the row where
`edge.detect_range_m` (12 m) meets the road, computed with `core.geometry`, rather than the
hand-set 0.45 the video lane needs for footage with no camera model.

**Why** Step 3's survey and step 4's scoring consume these detections. A live view proves
the real models run in the loop.

**Files** `sim/mujoco/drive.py`, `sim/mujoco/demo.py`, `configs/sim/mujoco.yaml`,
`tests/test_mujoco_drive.py`

**Steps**
- [x] Tests first: the D082 channel rule, and the gate row agreeing with
  `core.geometry.project` at 12 m.
- [x] The loop yields one record per frame (position, sampled flag, detections with track,
  confirmed flag) and writes `runs/mujoco/<preset>_seed<seed>/detections.jsonl`.
- [x] Frames go to ultralytics as BGR. The step-1 probe passed RGB and its numbers are
  re-measured here.
- [x] A live window (class colours, confirmed tracks green), with `--headless` to skip it.
- [x] Time the frame budget and tune `drive` render settings to keep it near real time.

**Record (2026-10-05):** at 10 fps (one frame every 5/9 m) confirmation collapsed, so the
loop runs at 30 fps: 27 frames per 5 m sample (D088). The full poor road completes: 2,766
frames, 103 samples, 142.8 s, so 0.65× real time. The step-1 probe's RGB input was
re-measured as BGR; P scored 0.59/0.54/0.51 and B 0.76, against 0.62/0.55/0.50 and 0.79.

**Done when** `uv run python -m sim.mujoco.demo --preset poor --seed 0 --drive --headless`
completes and writes `detections.jsonl`; `uv run pytest tests/test_mujoco_drive.py -q`
passes.

## Step 3 — survey panel

**Goal** The four-panel live screen: camera, map with 50 m segments colouring by band,
counters, and the drift trace. The live scores come from `survey.scoring` and `segment.py`,
never a copy. **Done when** a test feeds the same detections through the sim path and
through `certain_road.survey` and gets identical scores.

## Step 4 — end screen

**Goal** The per-segment table, the optimiser plan beside worst-first at a chosen budget
with true-worst-N coverage for each (D079), per-class recall and false alarms per km
against ground truth, and the honesty caption. **Done when** two runs with the same seed
give identical end-screen numbers.

## Step 5 — the other presets, recording, docs

**Goal** All five presets run. `--record out.mp4` writes a backup. The docs say how to run
it and what is simulated and what is real. **Done when** all five complete and their recall
and false alarms per km are reported, one MP4 exists, and `check_repo.py` exits 0.
