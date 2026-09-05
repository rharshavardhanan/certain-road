# Day 5 (hardware-free) — driving corridor + simulator core

**2026-09-05 · executes Day 5 of `2026-09-05-robot-sprint.md`, minus the Jetson overlay**

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans.

**Goal:** the robot can answer *"is this hazard in my path, and how near is it?"*, and a
simulator can drive a robot past a pothole on a top-down view — all on the MacBook, with no
Jetson, no camera, no robot.

**Deferred to when hardware exists:** drawing the corridor on the live camera view.

**Baseline:** `f461eac`, 74 tests, 6 import contracts kept.

## Global constraints

- Python 3.12, `uv` only. `lint-imports` must stay green — **`driving/` may not import `survey/`**.
- No magic numbers: corridor geometry and thresholds live in `configs/driving/`.
- Terminology unchanged (`vision_density`, `apparent_severity`, `pci_ref`, "vision-estimated PCI", "evaluation segment").
- **No hardware, no training, no `data/` writes.**
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## Three design decisions, made here

### 1. Proximity is the box's **bottom edge**, not its height

The sprint plan §1b said "bounding-box height is a usable distance proxy". **That is the
weaker choice and is corrected here.**

For an object resting on the ground plane under perspective projection, the **bottom edge's
image y-coordinate maps monotonically to ground distance** — lower in frame is nearer,
regardless of the object's real size. Box *height* confounds distance with size: a large
pothole far away and a small one close by can produce the same height.

```
proximity = y2 / img_h        0.0 = horizon,  1.0 = at the bumper
```

Monotone, size-independent, needs no depth sensor or calibration.

### 2. The driving corridor is **not** the survey ROI

They are different trapezoids with different configs and must never share one.

| | Purpose | Shape |
|---|---|---|
| Survey ROI | "what road surface can I see" — the `vision_density` denominator | **wide** |
| Driving corridor | "where will my wheels actually go" | **narrow** |

Sharing config would silently couple the two pipelines that D049 exists to keep apart.

### 3. `Detection` is a lightweight frozen dataclass, in `artifacts/`

`DetectionRow` is a pydantic model for Parquet rows — wrong shape for a per-frame real-time
list. `Detection` lives in `artifacts/schema.py` so **both** pipelines may use it while the
contract layer stays a leaf.

---

## Task A — `Detection` + corridor geometry

**Files:** `src/certain_road/artifacts/schema.py` (add), `src/certain_road/driving/corridor.py`, `configs/driving/corridor.yaml`, `tests/test_driving_corridor.py`

**Interfaces produced:**
- `Detection` — frozen dataclass: `class_name, score, x1, y1, x2, y2, img_w, img_h`
- `load_corridor(path) -> Corridor` — frozen dataclass of trapezoid fractions
- `corridor_polygon(corridor, img_w, img_h) -> np.ndarray` (4×2)
- `overlap_fraction(det, corridor) -> float` — fraction of the box inside the corridor
- `in_path(det, corridor, *, min_overlap) -> bool`

**Why:** without this the robot would avoid potholes it was never going to hit — the first genuinely robotic reasoning in the project.

**Steps (TDD):**

- [ ] **A1** Write `configs/driving/corridor.yaml` — trapezoid in image fractions (narrower than the survey ROI), plus `min_overlap`. Comment that it is deliberately separate from the survey ROI and why.
- [ ] **A2** Write the failing tests:
  - polygon has 4 vertices and widens toward the camera
  - a box centred low in frame → `in_path` True
  - a box at the frame edge → False
  - a box straddling the corridor edge → overlap strictly between 0 and 1
  - a box entirely above the corridor top (horizon) → False
  - `overlap_fraction` of a box fully inside == 1.0
- [ ] **A3** Run, watch fail. **A4** Implement — reuse the shoelace + Sutherland–Hodgman approach; no shapely. **A5** Run, pass. **A6** Commit.

**Done when:** all six tests pass; `lint-imports` green.

---

## Task B — proximity, lateral offset, and `Command`

**Files:** `src/certain_road/driving/corridor.py` (extend), `src/certain_road/canbus/protocol.py`, `configs/driving/corridor.yaml` (extend), `tests/test_driving_corridor.py`, `tests/test_canbus_protocol.py`

**Interfaces produced:**
- `proximity(det) -> float` — `y2 / img_h`, clamped to [0,1]
- `urgency(det, corridor) -> Urgency` — `FAR | NEAR | IMMINENT` from configured thresholds
- `lateral_offset(det, corridor) -> float` — −1.0 (far left) … +1.0 (far right)
- `Command` — frozen dataclass: `action, speed, steer, mode`; `to_bytes()` / `from_bytes()`

**Why:** proximity turns "a pothole exists" into "a pothole matters now" — the ADAS behaviour from §1b. `Command` is pure data pulled forward from Day 2 because the simulator needs it and it requires no hardware.

**Steps (TDD):**

- [ ] **B1** Failing tests: a box at the frame bottom has higher proximity than one near the horizon · proximity is size-independent (two boxes with the same `y2` but different heights score equally — **this is the test that proves the §1b correction**) · urgency rises monotonically with proximity · a box left of centre gives negative offset, right gives positive, centred gives ≈0 · `Command` round-trips through `to_bytes`/`from_bytes` · an out-of-range speed or steer is rejected.
- [ ] **B2** Run, watch fail. **B3** Implement. **B4** Run, pass. **B5** Commit.

**Done when:** all tests pass; **`canbus/protocol.py` imports nothing from `driving/`** — it is pure data.

---

## Task C — simulator: kinematics, render, first scenario

**Files:** `src/certain_road/sim/model.py`, `src/certain_road/sim/view.py`, `src/certain_road/sim/scenario.py`, `configs/sim/robot.yaml`, `tests/test_sim_model.py`, CLI `certain-road sim run`

**Interfaces produced:**
- `RobotState` — frozen dataclass `x, y, heading, speed`
- `step(state, command, dt, wheelbase) -> RobotState` — bicycle-model kinematics
- `Scenario` — potholes as ground-plane positions + a start state
- `render(states, scenario, path) -> Path` — top-down PNG or GIF
- CLI: `certain-road sim run --scenario centre --out runs/sim/`

**Why:** this is the test harness Days 6, 8 and 14 depend on, and the fallback demo if hardware fails.

**Steps (TDD):**

- [ ] **C1** Failing tests: zero steer → straight line (heading unchanged) · positive steer → heading increases · zero speed → position unchanged regardless of steer · **the same command sequence from the same start always yields the same trajectory** (determinism, which Day 14's measurements depend on).
- [ ] **C2** Run, watch fail. **C3** Implement `model.py`. **C4** Run, pass.
- [ ] **C5** Implement `view.py` — top-down: robot rectangle, heading arrow, corridor wedge, potholes as circles, trajectory trail.
- [ ] **C6** Implement `scenario.py` with one scenario (`centre`) and wire `certain-road sim run`.
- [ ] **C7** Produce a real rendered output and report its path.
- [ ] **C8** Commit.

**Done when:** `uv run certain-road sim run --scenario centre` writes an image showing a robot driving past a pothole; kinematics tests pass; suite green.

**Not in scope today:** the state machine consuming these (Day 6) and closing the loop so the robot actually *steers around* the pothole. Today it drives past on a fixed command sequence — enough to prove the model and render work.

---

## Definition of done

- [ ] `uv run pytest` green (74 + new)
- [ ] `uv run lint-imports` — 6 contracts kept
- [ ] `ruff check` / `ruff format --check` clean
- [ ] A rendered simulator output exists on disk
- [ ] No hardware touched, no training run, `data/` untouched
