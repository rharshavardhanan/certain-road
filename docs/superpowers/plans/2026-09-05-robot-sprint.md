# CertainRoad Robot — 15-Day Sprint Plan

**2026-09-05 → 2026-09-20 · robot demo**
**2026-09-21 → 2026-10-05 · survey/thesis completion (D046 date survives)**

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or
> superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** a small autonomous robot that detects a pothole, decides whether it is in its
driving path, avoids it via commanded steering, and *simultaneously* records road-damage
data that feeds the existing CertainRoad survey pipeline.

**What changed:** the project gains **perception → action**. It was a passive camera
survey; it is now a robot. The survey half is unchanged and is reused, not rebuilt.

---

## 1. The one architectural rule

**Two pipelines from one detector. They never touch.**

```
                      CAMERA
                        │
                     PERCEPTION            (YOLO, one inference)
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
    DRIVE PIPELINE               SURVEY PIPELINE
    "what do I do NOW?"          "what do we know about this road?"
          │                           │
    pothole in path?             all defects
          │                           │
    state machine                segment aggregation
          │                           │
    serial / CAN                 vision-estimated PCI
          │                           │
    motor + steering             conformal interval
          │                           │
        ROBOT                    accept / HUMAN REVIEW
```

**Conformal prediction is never in the steering loop.** Real-time avoidance needs
immediate perception; CP applies to the slower condition assessment. Stated that way it
is a defensible design, not a compromise.

---

## 2. The decision that saves the schedule: transport-agnostic control

**No CAN hardware exists.** The Jetson Orin Nano has CAN controllers on the 40-pin header
but **no transceiver**; the robot side needs an MCU to translate to PWM. Both are
procurement items sitting on the critical path of a 15-day sprint.

**Therefore the control link is built transport-agnostic from Day 1.**

```
decision.py  ──►  Command(dataclass)  ──►  Transport (interface)
                                              ├── SerialTransport   (Day 1, works now)
                                              ├── CanTransport      (when parts arrive)
                                              └── NullTransport     (bench testing)
```

`decision.py` and `controller.py` **never know which transport is active.** CAN becomes a
swap of one module, not a rewrite. The robot moves on Day 2 regardless of shipping.

### 2b. The simulator is a fourth transport

**Robot for the demo, simulator for the numbers.** Both are built; neither replaces the other.

```
                                              └── SimTransport  ──► kinematic model ──► top-down view
```

`corridor.py` and `decision.py` **cannot tell simulation from hardware** — whatever avoids a
pothole in the simulator is the identical module that avoids one on the robot, not a
reimplementation. That is what makes this cheap.

**What it is:** recorded road video → **real** YOLO → **real** corridor test → **real** state
machine → `SimTransport` → a bicycle-model robot on a 2D top-down view. Genuine detections
driving genuine decisions; only the actuation is synthetic.

**What it is NOT:** Gazebo, Isaac Sim or CARLA. Those want a serious NVIDIA GPU, will not run
well on the MacBook, and would burn 3–5 days on setup with real failure risk.

**Why it earns its place — three reasons, in order:**

1. **It is the test harness Days 5–6 need anyway.** The corridor and state machine must be
   tested against *something*. The simulator is that something, so it costs hours rather than
   a day.
2. **It produces Day 14's measurements.** ≥20 obstacle presentations staged physically are
   slow, inconsistent and hard to reproduce. In simulation they are deterministic, instant,
   assertable in CI, and re-runnable after any code change.
3. **It unblocks Days 5–8 from hardware.** Avoidance logic is finished and proven on the
   MacBook while the Jetson is still being flashed and CAN parts are in transit.

**What it cannot test, and must not be claimed to:** motion blur, vibration, lighting change,
real command latency, real actuator dynamics. Those appear only on the robot.

**Framing for the demo — this matters.** The simulator is the *development and validation
environment*; the robot is the *deliverable*. Show the robot moving first, then show the
simulator as how 20+ scenarios were validated that could not be staged physically. In that
order it reads as rigour. Reversed, it reads as avoiding the hard part.

**Order the CAN parts on Day 1 regardless** — SN65HVD230 or TJA1050 transceivers ×2, and
an ESP32/STM32 with CAN if the lab robot has no CAN-native controller.

---

## 3. Repository restructure

### Before → after

| Now | Becomes | Action |
|---|---|---|
| `detect/` (1,138 lines) | `perception/` | **move, keep all code** — training, predict, eval, dataset all still needed |
| `ingest/` (stub) | `survey/recorder.py` | replace stub |
| `assess/` (stub) | `survey/assessment.py` | replace stub |
| `calibrate/` (stub) | `survey/conformal.py` | replace stub |
| `report/` (stub) | `dashboard/` | replace stub |
| `rsl/`, `optimize/` (stubs) | `survey/` | **keep — needed for Oct 5, not for Sep 20** |
| `artifacts/`, `core/` | unchanged | shared contract, untouched |
| — | `driving/` | **new** |
| — | `canbus/` | **new** |

### Target layout

```
src/certain_road/
├── artifacts/          schema.py  io.py            (unchanged)
├── core/               paths.py  config.py         (unchanged)
│
├── perception/         detector.py                 ← was detect/
│                       train.py  predict.py  evaluate.py  dataset/
│
├── driving/            corridor.py                 is the pothole in my path?
│                       decision.py                 the state machine
│                       controller.py               state → Command
│
├── canbus/             protocol.py                 Command ↔ bytes
│                       transport.py                Serial | CAN | Null
│
├── survey/             recorder.py                 every detection, geotagged
│                       segment.py                  detections → segments
│                       assessment.py               segment → vision-estimated PCI
│                       conformal.py                PCI → interval → accept/review
│                       rsl.py  optimize.py         (deferred to Oct 5)
│
├── dashboard/          report.py                   the one screen
│
└── sim/                model.py                    bicycle-model kinematics
                        scenario.py                 the repeatable trial matrix
                        view.py                     top-down render
```

**`canbus/` not `can/`** — `python-can` owns the top-level `can` module and shadowing it
would confuse every reader and some import paths.

### Files deleted

Nothing. Five stub packages are *replaced*, not deleted; `detect/` is *moved*. The three
superseded plan documents move to `docs/superpowers/plans/archive/` — the decision log
rule is append-never-delete, and the same logic applies to plans.

### `import-linter` contracts

Rewritten for the new module set. **The new rule that matters: `driving/` and `canbus/`
must never import `survey/`, and `survey/` must never import `driving/`.** That contract
is the architectural rule from §1 made mechanical — if CP ever creeps into the steering
loop, CI fails.

`sim/` is a **composition root**, like `cli.py`: it may import `driving/` and `canbus/`
because its job is to wire them together. It may **not** import `survey/`.

---

## 4. What runs where

**This split is not negotiable and is the source of most integration pain if ignored.**

| Work | MacBook Pro (M-series, MPS) | Jetson Orin Nano |
|---|---|---|
| Dataset prep, conversion, splits | ✅ all of it | ❌ never |
| **Model training / fine-tuning** | ✅ **only here** | ❌ Jetson is inference-only |
| Benchmarking candidates | ✅ | ❌ |
| ONNX export | ✅ produce the `.onnx` | — |
| **TensorRT engine build** | ❌ **impossible** | ✅ **only here** |
| Live camera capture | ❌ | ✅ |
| Real-time inference | ❌ | ✅ |
| Driving corridor / state machine | ✅ **develop + unit test here** | ✅ runs here |
| Serial / CAN transport | ❌ no bus | ✅ |
| Survey recording during a drive | ❌ | ✅ |
| PCI / conformal / dashboard | ✅ **all development** | ❌ runs offline after |
| Final demo | ❌ | ✅ |

**TensorRT engines are device- and version-specific and must be built on the Jetson
itself** (D048). The MacBook produces ONNX; the Jetson turns it into an engine. Never
attempt otherwise.

**Corollary that protects the sprint:** every `driving/` module is pure logic over a
`Detection` list. It is developed and unit-tested on the MacBook against synthetic
detections, exactly as the survey stages were. The Jetson is needed only to *run* it.

---

## 5. The 15 days

Each day carries: **Goal · Why · Where · Done when.**

### Day 0 (today) — restructure + unblock procurement

- **Goal:** repo matches the new architecture; parts ordered; lab robot identified.
- **Why:** every later day writes into this structure. Parts ordered today arrive mid-sprint; ordered on Day 5 they arrive after the demo.
- **Where:** MacBook.
- **Done when:** `uv run pytest` green after the move · `lint-imports` green with the new contracts · CAN parts ordered · lab robot model written into this file.

### Day 1 — Jetson bring-up + control link

- **Goal:** JetPack flashed, Python stack running, and the Jetson commands the robot to move over **USB serial**.
- **Why:** the single riskiest unknown. If the board or robot interface is wrong, everything changes and it must surface on Day 1.
- **Where:** Jetson (+ robot).
- **Done when:** `ssh` in, `python -c "import torch; print(torch.cuda.is_available())"` → `True` · robot drives forward and stops on command from a Jetson script.
- **⚠ Verify first (D048):** board is genuinely an **Orin** Nano, not a legacy 2019 Nano (EOL, JetPack 4.6, Python 3.6 — cannot carry this stack).

### Day 2 — command protocol + emergency stop

- **Goal:** `FORWARD / STOP / LEFT / RIGHT` over the transport interface, plus a hardware E-stop.
- **Why:** every subsequent day sends commands through this. Building it before autonomy means autonomy is a small change.
- **Where:** MacBook (protocol + tests) → Jetson (execution).
- **Done when:** all four commands drive the robot · **E-stop halts it mid-motion** · protocol unit-tested on the MacBook with `NullTransport`.

### Day 3 — camera on Jetson

- **Goal:** stable live frames with FPS and resolution logged.
- **Why:** the IMX708 (Pi Camera Module 3) is **not officially JetPack-supported** (D048). If it doesn't enumerate, an IMX219/IMX477 must be swapped in *now*.
- **Where:** Jetson.
- **Done when:** ≥15 FPS sustained for 60 s with no dropped-frame errors.

### Day 4 — YOLO on Jetson

- **Goal:** existing `multicountry_v8s` weights running live on camera frames.
- **Why:** proves the perception backbone survives the move to the edge.
- **Where:** MacBook exports ONNX → Jetson builds the TensorRT engine.
- **Done when:** live boxes on a real pothole · inference FPS recorded · **a pothole photo on a phone screen held to the camera is detected** (repeatable indoor test).

### Day 5 — driving corridor

- **Goal:** the robot knows whether a detection is *in its path*.
- **Why:** first genuinely robotic reasoning. Without it the robot avoids potholes it would never have hit.
- **Where:** MacBook (logic + tests + simulator) → Jetson (overlay).
- **Also today:** `sim/model.py` and `sim/view.py` — the bicycle model and top-down render. Built here because the corridor test needs something to be tested against, and the simulator is that something.
- **Done when:** corridor drawn on the live view · a pothole at frame edge → `IN_PATH = False` · centred → `True` · unit tests cover both plus the straddling case · **the simulator renders a robot driving past a pothole**.

### Day 6 — state machine

- **Goal:** `NORMAL / WARNING / AVOID_LEFT / AVOID_RIGHT / STOP` with correct transitions.
- **Why:** decisions must be provably right *before* they drive actuators. Debugging a state bug while the robot moves is dangerous and slow.
- **Where:** MacBook — **pure logic, fully unit-tested, no hardware.**
- **Also today:** `sim/scenario.py` — the trial matrix (left / right / centre / multiple / blocked-left / blocked-right / blocked-both), runnable headless.
- **Done when:** every transition covered by a test · **ambiguous/blocked-both-sides → `STOP`, never a guessed direction** · stale detections (>N frames old) → `STOP` · **every scenario in the matrix passes in simulation before any actuator moves**.

### Day 7 — autonomous avoidance ← **MVP**

- **Goal:** camera → YOLO → corridor → state machine → transport → robot avoids a pothole unaided.
- **Why:** this is the project. Everything before is scaffolding; everything after is reliability and reporting.
- **Where:** Jetson + robot.
- **Done when:** robot avoids a single centred obstacle **3 consecutive times** without intervention.

### Day 8 — make it reliable

- **Goal:** avoidance survives the awkward cases.
- **Why:** a demo that works once is not a product. The failure cases are what a mentor will probe.
- **Where:** Jetson + robot.
- **Done when:** the full scenario matrix passes **in simulation** *and* the four physically stageable cases (left / right / centre / blocked-both) pass **on the robot** · camera-loss, detector-crash and transport-loss each → STOP.
- **Note:** simulation carries the exhaustive matrix; the robot carries the cases that prove simulation matches reality. Neither alone is sufficient.

### Day 9 — survey recording

- **Goal:** every detection persisted while driving, with timestamp, GPS and the action taken.
- **Why:** the second output. Proves one perception pass serves both pipelines.
- **Where:** Jetson writes; MacBook reads.
- **Done when:** a drive produces a `detections.parquet` validating against `DetectionRow` · rows carry the drive action · GPS present (or a documented fallback if the module isn't wired).

### Day 10 — segmentation

- **Goal:** raw detections → fixed-distance road segments.
- **Why:** PCI is defined per segment, not per frame. Reuses D006's distance-sampling logic.
- **Where:** MacBook (offline over the recorded drive).
- **Done when:** a drive yields ≥3 segments with per-segment detection counts.

### Day 11 — vision-estimated PCI

- **Goal:** segment → vision density → apparent severity → deduct → CDV → **vision-estimated PCI**.
- **Why:** the survey pipeline's central quantity. Reconnects the existing CertainRoad design (spec §3).
- **Where:** MacBook.
- **Done when:** each segment carries a PCI in [0,100] spanning a usable range, not clustered.
- **⚠ Still blocked:** ASTM D6433 deduct curves have no source. `deduct_curves.yaml` carries a mandatory empty `source:` and the stage **refuses to run** until filled. **Resolve this by Day 9 or PCI slips.**

### Day 12 — conformal + human fallback

- **Goal:** `q̂` from the calibration set, an interval per segment, and `ACCEPT` vs `HUMAN REVIEW`.
- **Why:** the research contribution and the product's safety story.
- **Where:** MacBook.
- **Done when:** interval inside one PCI band → `ACCEPT` · spanning multiple bands → `HUMAN REVIEW` · empirical coverage reported against nominal.

### Day 13 — dashboard

- **Goal:** one screen: live view, detections, drive state, segment condition, interval, GPS.
- **Why:** it must look like a road-inspection product, not a YOLO demo.
- **Where:** MacBook builds; displayed alongside the Jetson at demo.
- **Done when:** the §14 layout renders from a real recorded drive, including an `ACCEPT` case *and* a `HUMAN REVIEW` case.

### Day 14 — full-system test + measurement

- **Goal:** the five scenarios run repeatedly, with numbers recorded.
- **Why:** the report needs measured results. **Numbers are measured, never invented.**
- **Where:** Jetson + robot.
- **Done when:** **≥20 simulated presentations** logged with detected / avoided / false-avoidance / collision counts · **≥5 physical presentations** logged the same way, to show simulation and reality agree · command latency and inference FPS measured **on the robot** · one run produces both a drive log *and* a survey report.
- **Report both columns separately.** Never present simulated trials as physical ones.

### Day 15 — rehearsed demo

- **Goal:** one clean run, rehearsed end to end.
- **Why:** a rehearsed simple demo beats an unrehearsed rich one.
- **Where:** Jetson + robot + dashboard.
- **Done when:** the full sequence runs **twice consecutively** without intervention: robot drives → detects → avoids → continues → survey report shown with an `ACCEPT` segment and a `HUMAN REVIEW` segment.

---

## 6. Priority order — do not reverse

```
1 CAN/serial + manual control      6 safety STOP
2 camera on Jetson                 7 survey recording
3 YOLO on Jetson                   8 PCI
4 pothole-in-path                  9 conformal
5 automatic avoidance             10 dashboard
                                  11 measurement
```

**A beautiful dashboard on a robot that cannot move is a failed robotics product.**

---

## 7. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| **CAN parts don't arrive** | Days 1–2 slip → cascade | **Serial transport from Day 1**; CAN is a one-module swap. Order Day 0. |
| **Lab robot interface unknown** | Day 1–2 blocked | Identify model Day 0. `Transport` interface absorbs whatever it speaks. |
| **Legacy Jetson Nano, not Orin** | P3 invalid | Verify board identity Day 1, first hour (D048). |
| **IMX708 not JetPack-supported** | No camera | Verify Day 1; swap to IMX219/IMX477 immediately if it fails. |
| **Deduct curves unsourced** | Day 11 blocked | Resolve by Day 9. Fallbacks: published coefficients by DOI, or a documented linear approximation labelled as such. |
| **TensorRT export fails** | Day 4 slips | Fall back to PyTorch inference on Jetson; slower but sufficient at ~1.4 fps. |
| **Robot damages itself** | Days lost | E-stop on Day 2, before any autonomy. Low speed throughout. **Every scenario passes in simulation before an actuator moves.** |
| **Robot/CAN/Jetson all fail** | No demo | The simulator demonstrates the full decision pipeline end to end. Weaker, but not nothing. |

**Contingency ladder if slipping:** dashboard polish → conformal (Day 12) → PCI (Day 11) →
segmentation (Day 10). **Never cut** avoidance, the safety STOP, or survey recording.

---

## 8. What is NOT cut

The Oct 5 date stands. Deferred to 2026-09-21 → 2026-10-05, not abandoned: RSL, budget
optimisation, the D027 three-rater validation study, the coverage table at full rigour,
and the thesis write-up.

---

## 9. Language discipline for the demo

| Never say | Say instead |
|---|---|
| "The robot knows the actual PCI" | "The system estimates a **vision-based** condition score" |
| "CP tells us detection is 90% correct" | "CP provides a **calibrated uncertainty interval** for the condition estimate" |
| "YOLO is our innovation" | "YOLO is the perception backbone; the contribution is **perception-to-action and uncertainty-aware decision-making**" |
| "The model is wrong" (on abstain) | "The automated system **lacks sufficient certainty** to decide safely" |

---

## 10. Open items blocking Day 1

1. **Lab robot exact model** — determines the control interface entirely.
2. **CAN parts ordered** — transceivers ×2, plus MCU if the robot has no CAN controller.
3. **Deduct curve source** — needed by Day 9; carried over unresolved from the previous plan.
