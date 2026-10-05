# MuJoCo demo realism (look v2) implementation plan

**Goal:** Make the simulated road look more like a real road: 3D potholes, real-world surface
detail, and harsher light with shadows across the road. Today's simulator stays runnable,
unchanged, as `--look v1`.

**Architecture:** One config block per look in `configs/sim/mujoco.yaml`. `v1` is empty, so it
runs today's code paths exactly. `v2` switches on three additive features:
- a displaced road mesh (`sim/mujoco/relief.py`);
- surface detail in the baker;
- trees and harsher light in the scene.

The ground truth is identical across looks, so detection numbers compare directly.

**Tech stack:** MuJoCo 3.14 MjSpec meshes, NumPy, OpenCV.

## Global constraints

- Textures from `data/raw/trial_textures/` only; never RDD2022 or BharatPotHole crops.
  Procedural tints and plain-colour geometry are not textures.
- Real models, real survey code; the simulator reimplements none of it.
- `--look v1` must render byte-identical frames to the `demo-v1` tag.
- Same seed, same ground truth across looks.
- Realism is judged by eye and by physical measures (sizes, depths). Detection is measured
  **once**, after v2 is built, and reported; the scene is not adjusted toward a better score.
- Commit by explicit path; `check_repo.py` exits 0.

---

### Task 1: Looks, with v1 kept byte-identical

**Goal** `--look v1|v2` selects a config overlay; v1's frames hash identically to the
`demo-v1` tag's.

**Why** The current simulator is the fallback for the review if v2 fails.

**Files** `configs/sim/mujoco.yaml`, `sim/mujoco/road.py` (`load_config(look)`),
`sim/mujoco/demo.py` (`--look`), `tests/test_mujoco_road.py`

**Steps**
- [x] Test: `load_config("v1")` equals the base config; `load_config("v2")` differs only under
  `surface`, `scene` and `relief`, and generates the same road.
- [x] Implement the overlay, the CLI flag, and v2 run directories (`<preset>_seed<seed>_v2`).

**Done when** the test passes, and the frame hashes of poor and mixed, seed 0, at 99, 196,
300 and 409 m, under `--look v1`, equal those saved from `demo-v1`.

Record: identical, all 8 hashes. The renders are deterministic: two runs at `demo-v1` hashed
the same, and v1 was rechecked after every later task.

### Task 2: 3D potholes

**Goal** Each pothole is a depression 4–10 cm deep in the road mesh. Its outline is the same
irregular ellipse the texture shows, so the sun lights one wall, the other falls in shadow,
and the hole has depth seen from the camera.

**Why** Flat potholes with painted shading are the weakest part of the current look.

**Files** `sim/mujoco/relief.py`, `sim/mujoco/scene.py`, `tests/test_mujoco_relief.py`

**Steps**
- [x] Tests: depth is 0 outside every pothole and on its rim, reaches the drawn depth inside,
  and is never positive; the tile mesh's UVs map x and y exactly as the flat quad did.
- [x] Implement `depth_at(points)` from the baker's alpha shape, and a tile mesh that is fine
  only near potholes.

**Done when** the tests pass, and a v2 frame shows lit and shadowed pothole walls.

Record: 3 passed. The ground plane had to drop to -0.15 m in v2, or the holes showed it
through. The v2 road has 136,516 mesh vertices, and a live frame takes about 23 ms.

### Task 3: Surface detail

**Goal** Repair patches, oil stains, and dust along the kerbs, baked into the v2 tiles.

**Why** Real roads carry marks that are not damage; the detector must see them too.

**Files** `sim/mujoco/surface.py`, `configs/sim/mujoco.yaml`

**Steps**
- [x] Implement `_detail`, seeded by position like the rest of the baker, after the base
  asphalt and before the damage.

**Done when** a v2 frame shows them, and v1's tile hash is unchanged.

### Task 4: Light and shadows

**Goal** A harsher sun, and trees on both verges whose shadows fall across the road.

**Why** Hard shadow edges on asphalt are a real-world false-alarm source the current scene
lacks.

**Files** `sim/mujoco/scene.py`, `configs/sim/mujoco.yaml`

**Done when** a v2 frame shows tree shadows on the carriageway.

Record: two visual rounds. Ball-like canopies became 16–27 packed blobs leaning over the road,
and their shadows cross the driving lane.

### Task 5: Measure once, report

**Goal** All five presets under v2; recall and false alarms per km beside v1's; one v2 MP4;
and a judgement of the realism of five frames.

**Files** `docs/mujoco-demo.md`, `docs/DECISIONS.md` (D092)

**Done when** the table is in the docs, `check_repo.py` exits 0, and the work is committed by
path.

Record: all five exited 0 under v2; the table and the false-alarm check are in `docs/mujoco-demo.md` and D092.
`runs/mujoco/realism_grid_v2.png` holds the five frames, and `runs/mujoco/poor_seed0_v2.mp4` the recording.
