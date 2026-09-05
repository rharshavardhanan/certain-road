# certain-road — Complete Project Overview

**Last updated:** 2026-08-15 · **Branch:** `week-1-foundation` · 27 commits · 59 tests · 43 logged decisions

This is the single document that explains what this project is, every component in it,
what has been tried, what remains, and how the remaining work reaches the goal.

For the authoritative design see
[`superpowers/specs/2026-08-06-certain-road-design.md`](superpowers/specs/2026-08-06-certain-road-design.md).
For why every choice was made see [`DECISIONS.md`](DECISIONS.md).

---

## 1. What this project actually is

**The question it answers:** *"Which road segments should be repaired first, given a fixed
budget?"*

**The question it does NOT answer:** *"Where is a pothole?"*

That distinction is the whole project. Pothole detection is a solved, crowded problem.
Turning detections into a **defensible, uncertainty-aware repair priority list a highways
department can act on** is not.

Imagine the Tamil Nadu Highways Department with ₹100 crore a year. They cannot repair
every road. A system that says "there is a pothole at these coordinates" does not help
them. A system that says *"Segment 42 has a vision-estimated PCI of 48, we are 90%
confident the true value lies in [42, 55], its remaining service life is 0.8–1.4 years,
and repairing it costs ₹3.2 lakh — fund it before Segment 17"* does.

### The three contributions

| # | Contribution | What it means |
|---|---|---|
| 1 | **Edge AI** | Automated road distress detection from a vehicle-mounted camera |
| 2 | **Trustworthy AI** | Conformal prediction giving *calibrated uncertainty* on the estimated pavement condition |
| 3 | **Decision support** | That uncertainty *measurably changing* which roads get funded |

**The novelty is the integration and the decision, not the detector.** A better YOLO is
not the contribution. Anyone can train YOLO.

---

## 2. The pipeline, end to end

```
Camera / recorded video
        ↓
   [ ingest ]        distance-sampled frames, grouped into segments
        ↓  frames.parquet
   [ detect ]        YOLOv8 → bounding boxes
        ↓  detections.parquet
   [ assess ]        boxes → vision-estimated PCI per segment
        ↓  segments_pci.parquet
   [ calibrate ]     attach a conformal interval to that PCI
        ↓  segments_pci_ci.parquet
   [ rsl ]           PCI interval → remaining-service-life interval
        ↓  segments_rsl.parquet
   [ optimize ]      budget-constrained repair selection
        ↓  priority.parquet
   [ report ]        self-contained offline HTML dashboard
        ↓  report.html
```

**Every stage talks only through typed Parquet files on disk. No stage imports another.**
`import-linter` enforces this in CI — a cross-stage import fails the build.

Why that matters practically: `assess`, `calibrate`, `optimize` and `report` are all
buildable and testable against **synthetic fixtures**, with no trained model, no GPU, no
camera and no Jetson. Hardware procurement and 12-hour training runs never block
development. This single architectural choice is what makes a 7-week timeline possible.

---

## 3. Every component explained

### 3.1 `ingest` — video/camera → frames

Reads a video file (or eventually a live camera) plus a GPS track, and emits sampled
frames grouped into segments.

**The key design decision (D006): distance-based sampling, not tracking.**

At 30 fps and 30 km/h, 100 m of road is ~360 frames, and one pothole appears in ~40
consecutive frames. Counting it 40 times would make every road look catastrophic.

Two ways to fix that:
- Run a tracker (ByteTrack) to give each physical defect one persistent ID
- **Sample one frame per ~L metres so camera footprints never overlap** ← chosen

The second makes double-counting **impossible by construction** rather than something a
fragile tracker might get wrong on shaky dashcam footage. It removed one of the two most
failure-prone components from the project.

### 3.2 `detect` — YOLOv8

Takes frames, emits bounding boxes with class and confidence. Nothing more. YOLO does not
know whether a road is good, whether it should be repaired, or what anything costs.

Covered in full in §5.

### 3.3 `assess` — the PCI computation

This is where detections become an engineering quantity. It follows the **structure** of
ASTM D6433 (the standard pavement condition index procedure) with three **named
adaptations**:

**Adaptation 1 — `vision_density`, not ASTM density.**
```
vision_density = Σ box_area_inside_ROI / Σ ROI_area × 100
```
ASTM density is *physical* area in m². This is *image-space* area fraction inside a fixed
trapezoid approximating the road surface. Calling it plain "density" would be wrong and a
civil engineer would rightly object, so it is named `vision_density` everywhere in the
code (D015).

The second failure-prone component removed: **no inverse perspective mapping**. Converting
pixels to real m² needs a homography from camera height and pitch — and RDD2022's camera
geometry varies by country and vehicle, so no single homography can be right. Skipping it
is valid because predicted and reference PCI pass through *identical* geometry, so the
error cancels in the comparison that matters.

**Adaptation 2 — `apparent_severity`, not structural severity.**
ASTM severity depends on crack width, spalling, depth and ride quality — none of which are
observable from one monocular frame. RDD2022 has no severity labels at all.

So `apparent_severity` is banded Low/Medium/High from each detection's **area fraction**, using
per-class quantile cutpoints computed once on the train split and **frozen into config**.
This measures *visual prominence*, not structural severity, and is named
`apparent_severity` so the distinction cannot be lost (D014, D028).

Known weakness, stated rather than hidden: a long thin crack may be structurally severe
yet visually small.

**Adaptation 3 — parametric deduct curves.**
```
DV = min(100, α + β · log₁₀(vision_density))     per (class, apparent_severity)
```
Then the **full iterative CDV correction** from ASTM D6433 — not a simplified sum. That
correction is ~40 lines and is the difference between something a pavement engineer
recognises as PCI and a weighted penalty sum (D017).

```
PCI = clip(100 − CDV, 0, 100)
```

Output is labelled **vision-estimated PCI** everywhere. Never bare "PCI".

### 3.4 `calibrate` — the conformal layer (the actual novelty)

**The research question:** *how uncertain is the final vision-estimated PCI, and does that
uncertainty change the repair decision?*

**Calibrated at the segment, not the frame (D005).** Governments repair road segments, not
bounding boxes. Attaching the guarantee to the engineering decision rather than to the
detector is both a stronger research story and statistically cleaner — the segment is the
exchangeable unit.

**The nonconformity score:**
```
sᵢ = | pci_pred,ᵢ − pci_ref,ᵢ |
```
where `pci_ref` ("reference PCI") comes from running the **identical** `assess` function on
ground-truth annotations. Deliberately not called `pci_true`: it is derived from
annotations and this project's own algorithm, not a certified ASTM field survey (D011).

**Split conformal:**
```
q̂ = the ⌈(n+1)(1−α)⌉-th smallest of {s₁ … sₙ}
interval = clip([pci_pred − q̂, pci_pred + q̂], 0, 100)
guarantee: P(pci_ref ∈ interval) ≥ 1 − α
```

**The limitation, which belongs in the thesis in bold:** the interval covers
**detector-induced error only**. It does not cover error in the PCI model, the
vision-density proxy, the apparent-severity proxy, or the RSL curve — because `pci_ref` is itself
defined through those same models. It answers *"where would the estimate land if detection
were perfect?"*, not *"what is this road's true ASTM PCI?"*

An examiner will ask this. Volunteering it converts the weakest point into evidence of
rigour.

**`inconclusive` segments (D013):** any interval spanning more than one PCI condition band
is flagged. `[42,55]` sits in one band and is actionable; `[38,71]` straddles three and is
not. The dashboard shows those as "human inspection required" rather than a confident
wrong number.

### 3.5 `rsl` — remaining service life

Deterioration-curve inversion, entirely in config:
```
age_now  = ((100 − PCI)   / a)^(1/b)
age_term = ((100 − PCI_t) / a)^(1/b)
RSL      = max(0, age_term − age_now)
```

**The relationship is monotone increasing in PCI**, so interval endpoints map straight
through: `[pci_lo, pci_hi] → [rsl(pci_lo), rsl(pci_hi)]`. A monotone transform of a valid
interval is a valid interval, so **conformal coverage is preserved exactly** — no
recalibration, no approximation. This is a genuinely elegant property and worth stating in
the thesis.

**⚠ BLOCKING (D018):** the coefficients `a`, `b` are **not yet cited**. The config carries
a mandatory `source:` field and **the stage refuses to run while it is empty**. Either a
published PCI→RSL relationship is entered with its citation, or the mentor selects
`mode: pci_only`, which skips the stage and drives recommendations from PCI bands
directly. One-line config change either way.

### 3.6 `optimize` — the budget decision

- **Treatment** by PCI band: do-nothing / preventive seal / thin overlay / mill-and-overlay
  / reconstruction
- **Cost** = ₹per_km × segment_length
- **Benefit** = length × traffic_weight × risk (traffic_weight = 1; AADT is future work)
- **Policy is risk-averse:** urgency driven by **`rsl_lo`, the worst case**, and any
  segment with `rsl_lo < 1 year` enters as a **hard must-fix** ahead of discretionary
  spend. This mirrors how road agencies actually budget.
- **Solver:** exact 0/1 knapsack by dynamic programming over costs integerised to ₹1 lakh.
  Exact and instant, so no greedy approximation to defend.

**The stage runs twice** — once ranking on point RSL, once on `rsl_lo` — and diffs the
funded sets. That diff is the headline result, produced as a by-product rather than a
bolted-on experiment.

### 3.7 `report` — the dashboard

One self-contained HTML file per run. Leaflet and Plotly **vendored inline** — no CDN,
because a CDN fails exactly like a tile server and a viva room's wifi cannot be trusted.
Double-click and demo.

**Demo network (D022):** RDD2022 has no geometry, so the map needs a road network. Default
is a **procedurally generated synthetic network** with fictional names and no real
geography. An OSM mode exists but is off by default behind a persistent "Demonstration
Only" banner. Rationale is non-negotiable: a screenshot of "Anna Salai — PCI 34" would be
read as a real measurement of a road that was never surveyed.

Useful consequence (D023): a synthetic network needs **no basemap tiles at all**, which
deletes tile prefetching, CDN dependence and the offline problem in one move.

**Decision Replay panel (D021):** clicking a segment expands the full chain — detections →
vision-estimated PCI with interval → RSL interval → treatment → cost → rank → rationale.
One panel exhibits the entire contribution and turns the ranking from a black box into a
visible audit chain.

---

## 4. Datasets — every one considered

### 4.1 RDD2022 — the backbone ✅ IN USE

**DOI** `10.6084/m9.figshare.21431547.v1` · CC BY 4.0 · **13.26 GB single zip**

Verified facts (D032, D036), several of which contradict the published documentation:

- **There is no per-country download.** The whole 13.26 GB must be fetched.
- **The archive is nested two levels**: an outer zip of seven per-country zips, stored
  uncompressed; the inner root is `India/`, not `RDD2022/India/`.
- **India is 527 MB of that 13.26 GB. Norway alone is 10.6 GB.** Because entries are
  stored uncompressed, a range-read of the central directory could have fetched India
  alone — a real missed optimisation, recorded so it is not repeated.
- Figshare throttles **per connection** (~0.75 MB/s); parallel connections via `aria2c -x16`
  reached 7.9 MB/s (D034).

| Country | Images | **Annotated** |
|---|---:|---:|
| India | 9,665 | **7,706** |
| Japan | 13,133 | 10,506 |
| Norway | 10,201 | 8,161 |
| United States | 6,005 | 4,805 |
| Czech | 3,538 | 2,829 |
| China MotorBike | 2,477 | 1,977 |
| China Drone | 2,401 | 2,401 |
| **Total** | | **38,385** |

**The published test splits are unlabelled** and cannot be used. India's four splits are
all carved from its 7,706 annotated training images.

### 4.2 RDD2020 — ❌ REJECTED

RDD2022 is the *extended version* of RDD2020, and RDD2020 is *part of* it. Both report
**7,706 India images**, same resolution, same collection locations.

Adding it would contribute **zero new images** while injecting **duplicates**. Duplicates
are uniquely destructive here: the split assigns by filename hash, so the same photograph
under a different filename lands in `train` *and* `calib`. The detector would then be
scored on images it memorised, `|pci_pred − pci_ref|` would be artificially small, and
**the conformal intervals would come out too narrow while looking perfectly valid** — the
exact silent failure this project exists to prevent, introduced into the calibration set.

### 4.3 Water-filled potholes (Mendeley `tp95cdvgm8`) — ❌ NO-GO (D039)

Intended as a real distribution-shift test. Investigated and rejected:
- 713 images, single undifferentiated `pothole` class (1,156 boxes, plus one stray `o`)
- **No water/dry distinction in the annotation vocabulary at all**
- The in-zip ReadMe says nothing about water content
- Against our three-class set it would restrict reference PCI to the pothole contribution
  alone

The **synthetic corruption sweep remains the sole shift experiment**, which D025 always
anticipated.

### 4.4 Road Anomaly Detection (RAD) — ❌ NOT PURSUED

Road-anomaly datasets typically label *Pothole, Drain Hole, Sewer Cover, Wet Surface,
Unpaved Road* — obstacles and surface states, not pavement distress types. Only `pothole`
maps onto our taxonomy. Partial fit at best.

### 4.5 Additional Indian datasets — ⏸ OPEN

Genuinely new Indian imagery would help, especially anything Chennai/Tamil Nadu specific.
Requires: perceptual-hash deduplication against RDD2022 (byte hashing misses re-encoded
copies), licence verification, and taxonomy mapping. Realistically 1–2 weeks, which comes
straight out of the conformal work.

---

## 5. The model — everything tried and what remains

### 5.1 Class taxonomy (D038)

RDD2022 ships four classes. The real census found **D10 (transverse crack) has only 68
boxes in India — 43 train, 13 calib.** Untrainable, and absent from most evaluation
segments.

**D00 and D10 were merged into one `linear_crack` class.** This is not a data-balance hack:
**ASTM D6433 already treats longitudinal and transverse cracking as a single distress type
sharing one deduct curve** for asphalt. The merge therefore *increases* fidelity, and cuts
deduct-curve digitisation from four curves to three.

Final three classes:

| Class | RDD2022 source | India boxes | All-country boxes |
|---|---|---:|---:|
| `linear_crack` | D00 + D10 | 1,623 | **37,846** |
| `alligator_crack` | D20 | 2,021 | 10,616 |
| `pothole` | D40 | 3,187 | 6,544 |
| **Total** | | **6,831** | **55,006** |

**Dropped** (counted, never silently discarded): D44 (1,062 in India), D01, D43, D11, D50,
`D0w0`, plus `Repair` (1,046, China) and `Block crack`.

Also worth knowing: **4,483 of India's 7,706 label files are empty** — genuine negative
frames. The effective positive set is 3,223 images, not 7,706.

### 5.2 Splits

Assignment is by **salted SHA-256 of the filename**, not a seeded shuffle. The reason is
stability: adding or removing files must never reshuffle existing assignments, or
calibration images would migrate into training between runs.

| Split | India | Multi-country | Purpose |
|---|---:|---:|---|
| `train` | 4,617 | **35,296** | detector weights |
| `val` | 757 | 757 | early stopping — India only |
| `calib` | **1,548** | 1,548 | conformal calibration **only** |
| `test` | 784 | 784 | final reported numbers |

**The `calib` firewall is the single most consequential thing in the codebase.** If `calib`
ever reaches training, every statistical guarantee in the project is silently void. It is
enforced four ways: the generated data yaml writes only literal `train`/`val` keys; the
train stage refuses any yaml containing `calib` or `test`; disjointness is asserted in
memory *and* on disk; and the training logs are checked for zero references.

Verified after the class merge: **split sizes identical, `multicountry/calib` byte-for-byte
identical to `india/calib`.**

### 5.3 Training runs — what was tried

| # | Model | Data | Epochs | Time | India **test** mAP50 | mAP50-95 |
|---|---|---|---:|---:|---:|---:|
| 1 | YOLOv8n (3.01 M) | India 4,617 | 100 | 5.3 h | **0.4081** | 0.1698 |
| 2 | YOLOv8s (11.1 M) | Multi 35,296 | 27 | 11.6 h | **0.4220** | 0.1857 |
| 3 | YOLOv8s continuation | Multi 35,296 | +23 | ~10 h | *running* | *running* |

Per-class mAP50 on the held-out India test set:

| Class | Run 1 (v8n India) | Run 2 (v8s multi) | Δ |
|---|---:|---:|---:|
| `linear_crack` | 0.3103 | 0.2855 | **−0.0248** |
| `alligator_crack` | 0.5810 | 0.6185 | +0.0375 |
| `pothole` | 0.3331 | 0.3621 | +0.0290 |

**The interesting result:** `linear_crack` got *worse* despite going from 1,623 to 37,846
training boxes. Two candidate explanations, and the current experiment cannot distinguish
them:

1. **Negative transfer** — Japanese/Norwegian pavement, crack morphology and camera
   geometry differ enough that foreign linear cracks taught a notion that doesn't match
   Indian roads. Potholes and alligator cracking look similar everywhere, which is why
   they improved.
2. **Undertraining** — run 2 was **cut short, not converged**: best mAP landed on the final
   epoch with the early-stop counter at 0/9, and mAP50-95 rose monotonically across all
   five final epochs.

Run 3 settles it. If `linear_crack` recovers as training continues, it was undertraining.
If it stays flat while the others improve, it is genuine domain mismatch. **Either answer
is a reportable finding.**

Honest framing (D042): run 2 changed **model capacity and training data simultaneously**,
so the comparison against run 1 is a **combined** before/after and must never be attributed
to either factor alone.

### 5.4 Options not yet tried

| Option | Expected gain | Cost | Verdict |
|---|---|---|---|
| **Fine-tune run 3 on India only** | Likely recovers `linear_crack` while keeping pothole/alligator gains — the standard fix for negative transfer | ~2 h | **Strongest remaining option** |
| Multi-country **v8n** run | Recovers the clean data-only ablation confounded by D042 | ~6 h | Good for the write-up |
| YOLOv8m / v8l | +2–4 mAP points | 25–40 h on MPS | Poor ratio; weakens edge story |
| Ensembling + TTA | How the CRDDC'2022 winner reached F1 0.769 | Large; breaks real-time inference | Contradicts the edge-AI framing |
| Hyperparameter sweep | Unknown, probably small | Many runs | Low priority |
| More Indian data | Best domain match | 1–2 weeks sourcing | Only if a genuinely independent source exists |

---

## 6. What "good" looks like — the numbers to aim for

### 6.1 Detector (secondary)

CRDDC'2022's winner reached **F1 0.769 across all six countries** — an ensemble of large
models with TTA, on a test set dominated by easier countries. India-only is harder.

| | India test mAP50 |
|---|---|
| Current | 0.4220 |
| Plausible with convergence + tuning | 0.48–0.55 |
| Needs ensembling/TTA/larger backbone | 0.60+ |
| Not reachable on this data | 0.75+ |

**Chasing 0.60 would cost weeks and is not the contribution.**

### 6.2 The numbers that actually matter (primary)

The thesis stands or falls on whether the conformal interval is **narrow enough to decide
with**. PCI condition bands are ~15 points wide, and D013 flags any interval spanning more
than one band as unusable.

| Target | Value | Why it is the number |
|---|---|---|
| **q̂ (interval half-width)** | **≤ 7.5 PCI pts** at α=0.1 | interval fits inside one band → segment actionable |
| **Empirical coverage** | 86–94% at α=0.1 | ±4 pp is sampling noise at ~101 evaluation segments |
| **`inconclusive` rate** | < 20% of segments | above that the dashboard mostly says "ask a human" |
| **Budget reallocation** | 10–20% | uncertainty visibly changes the decision |
| **Unfunded critical km** | reduced vs point policy | it changed things *for the better* |

**Nobody yet knows what mAP is needed to reach q̂ ≤ 7.5.** It depends on how detection
error propagates through vision-density → deduct curves → CDV, which is exactly what weeks
2–4 measure. That is the research question, not a gap in the plan.

**This is why building `assess` and `calibrate` beats more training.** If q̂ turns out to be
5, the detector is already good enough and further training is wasted. If q̂ is 20, you will
know precisely which class's error dominates instead of guessing.

---

## 7. Results to report

| # | Result | Status |
|---|---|---|
| 1 | **Coverage** — conformal intervals achieve nominal coverage on held-out data | week 3–4 |
| 2 | **Policy impact** — uncertainty changes the funded set *and* improves network condition | week 5 |
| 3 | **Validation** — vision-estimated PCI agrees with human condition assessment at band level, relative to the human-human ceiling | week 4 (D027) |
| 4 | **Shift** — coverage degrades under distribution shift, so a naive guarantee gives false assurance | week 6 |
| + | **Sensitivity** — how much PCI moves under ±20% ROI and severity-cutpoint perturbation | week 6 (D029) |

The **validation study (D027)** is the one that must never be cut: 50 stratified segments,
three raters assigning condition bands blind, reported with **Fleiss' κ between raters as
the ceiling**. A model at κ 0.45 where humans agree at κ 0.5 is performing near the limit
of the task; reporting the first number without the second understates the result.

---

## 8. Timeline and where we are

**≈7 weeks in four partitions: 2026-08-18 → 2026-10-05** — 48 days (D047, bringing Jetson
and GPS into scope; refines D046, which refined D025). Full schedule:
[`superpowers/plans/2026-08-16-seven-week-schedule.md`](superpowers/plans/2026-08-16-seven-week-schedule.md).

| # | Weeks | Dates | Partition | Status |
|---|---|---|---|---|
| P0 | — | — | Skeleton, artifact contract, dataset, split, training, eval harness | ✅ **done** |
| **P1** | 1–2 | Aug 18–31 | Research core: `assess`, conformal, **coverage table**, ⛔ detector freeze | ← result 1 |
| **P2** | 3–4 | Sep 1–14 | Decision layer + validation: raters, `rsl`, DP knapsack, **policy impact** | ← results 2, 3 |
| **P3** | 5–7 | Sep 15–Oct 5 | Edge deployment: Jetson, camera, GPS, `ingest`, ONNX/TensorRT, real capture | |
| **P4** | 1–7 | Aug 18–Oct 5 | Dashboard + thesis, written continuously · **submit Oct 5** | |

**Hardware is sequenced last on purpose:** all three results are frozen by Sep 14, so a
procurement slip costs the deployment chapter rather than the thesis. If hardware is not
in hand by **Sep 22**, P3 reverts to D025's degraded chapter (ONNX export, MPS latency,
simulated GPS track).

**Cut to fit:** the synthetic shift sweep (result 4) and the sensitivity analysis. **Never
cut the validation study** — it is the only evidence the central quantity is meaningful.

### Week 1, delivered

- `uv` project, Python 3.12, typer CLI, 59 tests, CI
- **`import-linter` contracts, proven to fire** by deliberately introducing a violation
- Versioned Parquet artifact IO that refuses stale-schema reads
- Synthetic fixtures for 102 evaluation segments — the thing that unblocks weeks 2–5
- RDD2022 acquired, converted, split, with the calib firewall enforced four ways
- Water-pothole spike: NO-GO with evidence
- Two detector runs complete, a third in flight
- 43 decisions logged

---

## 9. Blockers — what needs a human

| # | Blocker | Blocks | Options |
|---|---|---|---|
| 1 | **PCI→RSL citation** (D018) | week 5 | Published relationship with citation, **or** `mode: pci_only` using PCI bands directly |
| 2 | **ASTM D6433 deduct curves** | week 3 | Obtain D6433 + WebPlotDigitizer (preferred), **or** an open-access paper's published coefficients, **or** a documented linear approximation labelled as such |
| 3 | Manual raters (D027) | week 4 | Three people, ~1 hour each. Schedule in week 3 — the one thing that cannot be compressed by working harder |
| 4 | Jetson Orin Nano | week 8 | Never approved. Deployment chapter degrades gracefully to ONNX export + latency benchmark + architecture design |

Blockers 1 and 2 are the same conversation: *which published relationship do we stand on?*
Both are enforced in code — the stages **refuse to run** on an empty `source:` — so neither
can be silently fudged.

---

## 10. Hardware (deferred, not on the critical path)

Requested, never approved. The software does not depend on it arriving.

| Component | Choice | Why |
|---|---|---|
| Compute | Jetson Orin Nano Dev Kit (8 GB) | Inference at the edge; **not** a training device |
| Camera | Raspberry Pi Camera Module 3 (IMX708) | Autofocus, CSI, compact |
| Storage | 500 GB NVMe SSD | OS, models, logs |
| GPS | u-blox NEO-6M | Segment geotagging |
| Enclosure | Two 3D-printed PETG parts | Camera pod behind windshield; compute box under dash |

**Nothing upstream of `ingest` knows whether hardware exists**, so it can arrive at any
time — or never — without touching another stage.

---

## 11. Engineering principles that keep it honest

Every one of these is a **mechanism**, not an intention. Rules nothing enforces do not
survive a deadline.

| Principle | How it is enforced |
|---|---|
| Stages never import each other | `import-linter` in CI; a violation fails the build |
| Artifacts are versioned | `io.py` validates `schema_version` on every read; a stale artifact is unreadable, loudly |
| RSL coefficients are cited | The stage **refuses to run** on an empty `source:` |
| Deduct curves are reproducible | Raw digitized points committed as CSV beside the fit |
| `calib` never reaches training | Data yaml writes only `train`/`val`; train refuses a yaml naming `calib`/`test`; disjointness asserted on disk |
| Runs are reproducible | `manifest.json` records git SHA, config hash, model hash, schema versions |
| The rating set is validation, never a dev set | Stated in `CLAUDE.md`; poor agreement is a **result to report**, not a defect to fix |

**Terminology is load-bearing and enforced in review:** `vision_density` never bare
`density`; `apparent_severity` never bare `severity`; `pci_ref` never `pci_true`;
"vision-estimated PCI" never bare "PCI"; "evaluation segment" never "road segment". Each
one prevents a specific overclaim.

---

## 12. How to run it

```bash
cd ~/PROJECTS/certain-road

# tests and architecture contracts
uv run pytest -q
uv run lint-imports

# dataset (already done)
uv run certain-road dataset fetch   --country India
uv run certain-road dataset census  --country India
uv run certain-road dataset convert --country India
uv run certain-road dataset split   --country India

# training
uv run certain-road detect train --config configs/train/yolov8s.yaml --country multicountry
uv run python scripts/train_progress.py runs/detect/models/yolo/multicountry_v8s_ext2

# synthetic fixtures — how weeks 2-5 are built without a model
uv run python scripts/make_fixtures.py
```

⚠ **`dataset split` clears and re-links image directories. Running it while training is
live crashes the DataLoader mid-epoch.** That has already cost one run.

⚠ **Launch long training under `caffeinate -i`.** macOS idle sleep on battery killed a run
after one epoch.

---

## 13. The one-paragraph summary

A vehicle-mounted camera records road surface. YOLOv8 detects three distress types.
Detections are aggregated over distance-sampled frames into evaluation segments, and
converted into a **vision-estimated PCI** through an ASTM-D6433-structured computation with
three honestly-named adaptations. Split conformal prediction attaches a **calibrated
interval** to that PCI, which propagates exactly through a monotone PCI→RSL transform into
a remaining-service-life interval. A budget-constrained knapsack ranks segments by
**worst-case** remaining life, and the whole chain is presented in an offline HTML dashboard
where clicking any segment reveals its full reasoning. The contribution is not the
detector — it is that the uncertainty is *calibrated*, *propagated to the decision*, and
*measurably changes which roads get funded*.
