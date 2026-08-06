# certain-road — Design Specification

**Date:** 2026-08-06
**Status:** Approved design, pending implementation plan
**Timeline:** 8 weeks
**Author:** Harshavardhanan R

---

## §0 — What this is

A pavement management decision-support system, not a pothole detector.

The question the system answers is **"which road segments should be repaired first,
given a fixed budget?"** — not "where is a pothole?". Detection is an input, not the
product.

### Three contributions

1. **Edge AI** — automated road distress detection from a vehicle-mounted camera.
2. **Trustworthy AI** — conformal prediction supplying calibrated uncertainty on the
   estimated pavement condition of a road segment.
3. **Decision support** — that uncertainty measurably changing maintenance
   prioritisation under a fixed budget.

The novelty is the **integration and the decision**, not the detector.

### Pipeline

```
Camera / video
      ↓
YOLOv8n                     → detections
      ↓
Segment aggregation         → distance-sampled frames grouped into segments
      ↓
Vision-estimated PCI        → ASTM-D6433-structured, vision-adapted
      ↓
Conformal interval on PCI   → [pci_lo, pci_hi] with coverage guarantee
      ↓
RSL interval                → monotone transform, guarantee preserved
      ↓
Budget optimiser            → worst-case-RSL-driven knapsack
      ↓
Offline HTML dashboard      → map, ranked list, Decision Replay
```

---

## §1 — Architecture

### Approach: single `uv` project, staged artifacts ("A+")

One project, one dependency file, one CLI. Stages communicate **only** through typed
artifacts on disk. No stage imports another stage.

Rejected alternatives:

- **`uv` workspace with six sub-packages** — six `pyproject.toml` files and
  cross-package version pinning; ceremony that buys nothing for a single author in
  eight weeks.
- **Flat package with `scripts/`** — fastest to start, and the exact mechanism by
  which the codebase becomes unmaintainable by week 6.

### Why this specifically

Because stages talk through files with a fixed schema, `assess`, `calibrate`,
`optimize` and `report` are buildable and fully testable **against synthetic
detections** — no model, no GPU, no camera, no Jetson. Hardware procurement can
never block the project, and detector training can run unattended for days while
downstream stages are developed. This parallelism is what makes 8 weeks feasible.

### Layout

```
certain-road/
├── pyproject.toml  uv.lock  .python-version  CLAUDE.md  README.md
│
├── configs/
│   ├── default.yaml
│   ├── dataset/rdd2022_india.yaml
│   ├── train/yolov8n.yaml
│   ├── assess/
│   │   ├── deduct_curves.yaml        # fitted coefficients
│   │   ├── curves/*.csv              # raw WebPlotDigitizer points (provenance)
│   │   └── severity_bands.yaml       # frozen train-split quantile cutpoints
│   ├── rsl/published_default.yaml    # MUST carry a `source:` citation
│   └── optimize/costs.yaml
│
├── src/certain_road/
│   ├── cli.py                        # single entrypoint, one subcommand per stage
│   │
│   ├── artifacts/                    # THE CONTRACT — schemas only, zero logic
│   │   ├── schema.py                 #   pydantic models, one per artifact
│   │   └── io.py                     #   read/write + schema_version enforcement
│   ├── core/                         # config, RunContext, logging
│   │
│   ├── ingest/    sources.py  track.py  sample.py
│   ├── detect/    dataset/  train.py  predict.py  export.py
│   ├── assess/    geometry.py  severity.py  pci.py
│   ├── calibrate/ segments.py  nonconformity.py  split_conformal.py  evaluate.py
│   ├── rsl/       curves.py
│   ├── optimize/  cost.py  knapsack.py
│   └── report/    build.py  network.py  templates/  vendor/
│
├── data/     raw/  processed/                                  [gitignored]
├── models/   yolo/  conformal/                                 [gitignored]
├── runs/     <run_id>/{artifacts,manifest.json,report.html}    [gitignored]
├── tests/    fixtures/     # synthetic parquet; downstream tests need no model
├── scripts/  # thin wrappers only, never logic
└── docs/superpowers/specs/
```

### Enforced invariants

Rules nothing enforces do not survive contact with a deadline. Each of these is a
mechanism, not an intention:

| Invariant | Enforcement |
|---|---|
| Stages never import each other | `import-linter` contract, run in CI — violation fails the build |
| Only `artifacts/` and `core/` are shared | same contract |
| Artifact schemas are versioned | `io.py` validates `schema_version` on every read |
| RSL coefficients are cited | RSL stage **refuses to run** if `configs/rsl/*.yaml` has an empty `source:` |
| Deduct curves are reproducible | raw digitized points committed as CSV beside the fit |
| Runs are reproducible | `manifest.json` records git SHA, config hash, model hash, per-artifact schema versions |

### Artifact chain

```
ingest → detect → assess → calibrate → rsl → optimize → report
```

Note the ordering: **`assess` runs before `calibrate`.** The nonconformity score is
defined on segment PCI, so PCI must exist before it can be calibrated.

| Stage | Writes | Key columns |
|---|---|---|
| `ingest` | `frames.parquet` | `frame_id, ts_utc, survey_date, lat, lon, speed_mps, cum_dist_m, segment_id, image_path` |
| | | *(sample spacing `L` metres and segment length are config, not constants)* |
| `detect` | `detections.parquet` | `frame_id, det_id, class_name, score, x1, y1, x2, y2, img_w, img_h` |
| `assess` | `segments_pci.parquet` | `segment_id, survey_date, n_frames, vision_density_by_class_sev, total_deduct, cdv, pci` |
| `calibrate` | `segments_pci_ci.parquet` | `segment_id, survey_date, pci, pci_lo, pci_hi, alpha, inconclusive` |
| `rsl` | `segments_rsl.parquet` | `segment_id, survey_date, rsl, rsl_lo, rsl_hi, condition_band` |
| `optimize` | `priority.parquet` | `segment_id, rank, treatment, cost_inr, benefit, selected, must_fix, rationale` |
| `report` | `report.html` | self-contained, fully offline |

`survey_date` appears on every segment-level artifact from the start, so
longitudinal extension (comparing surveys over time) needs no schema migration.

`calibrate` has two verbs:

- **`calibrate fit`** — offline, once, over held-out evaluation segments →
  `models/conformal/conformal_model.json` (the quantile `q̂`)
- **`calibrate apply`** — per run, attaches intervals to segment PCI

This forces `assess` to be a pure function over *any* detections table, since
calibration invokes it twice: on predicted boxes and on ground-truth boxes.

---

## §2 — The conformal layer

### Research question

Not "can YOLO detect potholes" and not "can conformal prediction be implemented",
but: **how uncertain is the final vision-estimated PCI, and does that uncertainty
change the repair decision?**

### Data splits

Conformal validity is void if the calibration set influenced detector fitting.
RDD2022 (India subset) therefore splits **four** ways:

| Split | Share | Purpose |
|---|---|---|
| `train` | 60% | YOLOv8n weights |
| `val` | 10% | early stopping, model selection |
| `calib` | 20% | conformal calibration **only** — detector must never see it |
| `test` | 10% | final reported numbers |

Calibration receives 20% deliberately: `q̂` is itself a noisy estimate and the
sample unit is the *segment*, so the effective sample size is far smaller than the
frame count suggests.

### Evaluation segments (pseudo-segments)

RDD2022 is an image dataset, not continuous drive footage. It has no GPS and no
route continuity, so real 100 m road segments cannot be constructed from it.

An **evaluation segment** is a **random disjoint partition** of the calibration pool
into blocks of `K` frames. Disjointness is required: overlapping blocks share frames,
scores become dependent, and exchangeability — the entire basis of the guarantee —
is lost.

The term "evaluation segment" is used throughout, in code, schemas and prose. These
are **not physical road segments** and must never be described as such. Calibration
artifacts are named `eval_segments_*` so the distinction is visible in filenames.

**Segment count is a first-order constraint, and the India-only cut (D025) tightened
it.** The India subset gives ~1.8–2.0k calibration frames. At `K = 30` that is only
~60 evaluation segments; realised coverage then has a standard deviation of roughly
4 percentage points, so a nominal 90% interval may empirically land anywhere from
~82% to ~98%. The guarantee still holds — it is marginal over draws — but a single
noisy coverage number is weak evidence in a thesis.

**Default is therefore `K = 15`, giving ~120 evaluation segments**, halving that
noise while keeping segments large enough to be meaningful. Report at `α = 0.1` and
`α = 0.2`; `α = 0.05` is not supportable at this sample size and should not be
claimed.

`K` is a config knob and the K-versus-segment-count trade-off must be swept and
reported as a figure — it is a genuine finding about deploying conformal prediction
on small survey datasets, not merely a tuning note. If counts still prove too low,
raise the calibration share to 30% before reducing `K` further.

Calibration frames may **not** be borrowed from other countries: `calib` must be
exchangeable with `test`, and if test is India, calibration is India.

### Procedure

Per evaluation segment, the nonconformity score is

```
sᵢ = | pci_pred,ᵢ − pci_ref,ᵢ |
```

where **`pci_ref` ("reference PCI")** is produced by running the *identical* `assess`
function on ground-truth annotations. It is deliberately **not** called `pci_true`:
it is derived from annotations and from this project's assessment algorithm, not from
a certified ASTM field survey.

Split conformal:

```
q̂ = the ⌈(n+1)(1−α)⌉-th smallest of {s₁ … sₙ}
interval = clip([pci_pred − q̂, pci_pred + q̂], 0, 100)
guarantee: P(pci_ref ∈ interval) ≥ 1 − α
```

### Stated limitation (belongs in the thesis, in bold)

> **The conformal interval covers detector-induced error only.** It does not cover
> error in the PCI model, the vision-density proxy, the severity proxy, or the RSL
> curve — because `pci_ref` is itself defined through those same models. The interval
> answers *"where would the estimate land if detection were perfect?"*, not *"what is
> this road's true ASTM PCI?"*

An examiner will ask this. Volunteering it converts the weakest point into evidence
of rigour.

### Inconclusive segments

Any segment whose interval spans more than one PCI condition band is flagged
`inconclusive`. `[42, 55]` sits within one band and is actionable; `[38, 71]`
straddles three and is not. The dashboard renders these as *"human inspection
required"* rather than a confident number.

This is a derived property of the interval already computed — no new model, no new
score. It preserves an honest abstention behaviour without reintroducing OOD
detection as a second research objective.

### Shift experiments

Under distribution shift, exchangeability breaks and **coverage should fall below
nominal**. Demonstrating that fall is the finding: it shows that naively deployed
conformal prediction produces *false assurance* — the same silent-failure disease,
now carrying a statistical guarantee.

**Primary — synthetic severity sweep.** Rain, glare, motion blur and low light
applied to held-out frames at graduated severity. Ground truth is preserved exactly,
yielding a *coverage-versus-shift-severity curve*. Controlled, and cannot be blocked
by an external dependency.

**Optional — water-filled potholes** (Mendeley `tp95cdvgm8`). Real shift, external
validity. **Verified in week 1.** If the annotation format or class set does not
convert within one day, it is dropped without regret. The centrepiece result does not
depend on it.

### Headline result

Coverage plots persuade statisticians. This persuades the panel:

> **How often does accounting for uncertainty change the repair list?**

The optimiser runs twice — once ranking on point RSL, once on worst-case `rsl_lo` —
and the funded sets are diffed. A reordering of 15–20% of a fixed budget quantifies
the contribution in rupees. This is a **core figure**, not an appendix.

### Explicitly out of scope (future work)

Image-level conformal p-values / OOD detection; weighted conformal for shift
correction; normalized or Mondrian conformal prediction; cross-country shift.

---

## §3 — Assessment, RSL, optimisation

### Vision-estimated PCI

Follows the structure of ASTM D6433 with three named adaptations.

**1. Vision density.** For each (class, severity):

```
vision_density = Σ box_area / Σ ROI_area × 100
```

summed over sampled frames in the segment, where ROI is a fixed trapezoid
approximating the road surface. This is **image-space density, not ASTM physical
density**, and is named `vision_density` everywhere in code and prose.

**2. Severity (proxy).** RDD2022 carries no severity annotations. Severity is banded
L/M/H from each detection's own area fraction, using **per-class quantile cutpoints
computed once on the train split and frozen into config**.

> Thesis wording: *"Severity is a vision-derived proxy based on apparent damaged area,
> because RDD2022 contains no severity annotations."*

Known weakness, stated rather than hidden: a long thin crack may have small area yet
high severity; a large patch may have large area yet low severity.

**3. Deduct values.**

```
DV = min(100, α + β · log₁₀(vision_density))
```

per (class, severity). Coefficients fitted to digitized ASTM deduct curves for the
corresponding asphalt distress types. Curves are digitized with **WebPlotDigitizer**,
never eyeballed, and the **raw `(density, DV)` points are committed** to
`configs/assess/curves/*.csv` so β has auditable provenance and the fit is
reproducible.

**Corrected Deduct Value.** The full iterative q-correction is implemented — not
simplified. It is roughly forty lines and is the difference between something a
pavement engineer recognises as PCI and something that is merely a weighted penalty
sum.

```
PCI = clip(100 − CDV, 0, 100)
```

Output is labelled **vision-estimated PCI** throughout. Never bare "PCI".

### PCI → RSL

Deterioration-curve inversion, fully config-driven:

```
age_now  = ((100 − PCI)   / a)^(1/b)
age_term = ((100 − PCI_t) / a)^(1/b)
RSL      = max(0, age_term − age_now)
```

**The functional form above is a placeholder and is not yet cited.** The config file
carries a mandatory `source:` field and the stage **refuses to run while it is
empty**. Before implementation of this stage (week 5), either a published PCI→RSL
relationship is located and its coefficients and citation entered, or the mentor
selects `mode: pci_only`, which short-circuits the stage and drives recommendations
directly from PCI bands. Either path is a one-line config change.

Because the relationship is **monotone increasing in PCI**, interval endpoints map
through directly:

```
[pci_lo, pci_hi] → [rsl(pci_lo), rsl(pci_hi)]
```

A monotone transform of a valid interval is a valid interval, so **conformal coverage
is preserved exactly** — no recalibration, no approximation.

### Optimiser

**Treatment** by PCI band — do-nothing / preventive seal / thin overlay /
mill-and-overlay / reconstruction. Config table.

**Cost** = `₹per_km × segment_length_km`. Config table.

**Benefit** = `length × traffic_weight × risk`, with `traffic_weight = 1` by default.
AADT-derived traffic weighting is named as future work; Chennai AADT data is not
available for this project.

**Policy** is deliberately risk-averse: urgency is driven by **`rsl_lo`, the worst
case**, and any segment with `rsl_lo < 1 year` enters as a **hard must-fix
constraint** ahead of discretionary spend. This mirrors how road agencies actually
budget.

**Solver:** exact 0/1 knapsack by dynamic programming over costs integerised to ₹1
lakh. A few million states for a few hundred segments — exact, instant, and removes
any need to defend a greedy approximation.

The stage runs **twice** (point RSL vs `rsl_lo`) and diffs the funded sets, producing
the §2 headline figure as a by-product rather than a bolted-on experiment.

### Demonstration network

RDD2022 has no geometry, so it supplies no map, no segment lengths and no costs.

**Default: a procedurally generated synthetic road network** with fictional names and
no real-world geography. Segment lengths and topology are realistic; the geography is
invented.

An OSM-derived mode exists but is **off by default** and gated behind a persistent
"Demonstration Only" banner. Real road names are never rendered. The rationale is
non-negotiable: a screenshot of "Anna Salai — PCI 34" would be read as a real
measurement of a real road that was never surveyed.

A useful consequence: **a synthetic network needs no basemap tiles.** Leaflet draws
polylines on a blank canvas, which deletes tile prefetching, CDN dependence and the
entire offline-tiles problem at once.

### Dashboard

One generated self-contained HTML file per run. Leaflet and Plotly **vendored inline**
— no CDN, since a CDN fails exactly like a tile server. Works with no network, no
server, no install: double-click and demo.

Contents: survey summary; network map coloured by PCI band; ranked priority table
with PCI and RSL intervals; budget slider; conformal coverage plots; the
point-vs-worst-case ranking diff; print stylesheet for PDF export.

**Decision Replay panel.** Clicking a segment expands the full reasoning chain:

```
Segment #42
  detections      6 potholes, 3 longitudinal cracks
  vision-est PCI  48   (90% interval: 42–55)
  RSL             0.8–1.4 years
  treatment       mill and overlay
  cost            ₹3.2 lakh
  rank            #2
  rationale       worst-case RSL below 1 year; moderate cost
```

This single panel exhibits the entire contribution — perception, through calibrated
uncertainty, to an engineering decision — and converts the ranking from a black box
into a visible audit chain.

---

## §4 — Eight-week plan

### Scope cuts made to reach 8 weeks

| Cut | Rationale |
|---|---|
| **India subset only** (~9–10k images, not 47k) | 4–6h training instead of 25–40h; same-day retraining. Tighter Tamil Nadu narrative. Loses cross-country shift. |
| Water-pothole dataset → optional | Verified week 1; dropped if it does not convert in a day |
| Normalized CP → future work | Stretch value only |
| Jetson deployment → export + benchmark only | Hardware not yet approved; will not arrive and integrate in 8 weeks |
| Basemap tiles → deleted | Falls out of the synthetic-network decision |

### Defended (these are the contribution)

Deduct-curve digitization (timeboxed: 3 days), full CDV correction, split conformal
with coverage table, dual-run ranking diff.

### Schedule

| Wk | Ships |
|---|---|
| 1 | Skeleton, CLI, schemas + versioned IO, import-linter, CI, synthetic fixtures; India subset converted and 4-way split; **training launched**; water-pothole dataset verified |
| 2 | Detector trained and evaluated *(unattended)*; concurrently ROI geometry, vision density, severity bands |
| 3 | Deduct curves digitized and fitted, CDV, vision-estimated PCI |
| 4 | Evaluation segments, split conformal, **coverage table** ← result 1 |
| 5 | RSL (sourced curve or `pci_only`), DP knapsack, must-fix, **ranking diff** ← core figure |
| 6 | Synthetic shift sweep ← result 2 |
| 7 | Dashboard: synthetic network, Leaflet, Plotly, Decision Replay, print stylesheet |
| 8 | ONNX export + latency benchmark, thesis writing, buffer |

Eight weeks is only feasible because of the §1 artifact contract: **detector training
runs unattended for days while `assess` and `calibrate` are built against synthetic
fixtures.** Those stages do not need the real model until week 4.

### Risk register

| Risk | Mitigation |
|---|---|
| MPS training slower than estimated | India subset already chosen; free Colab/Kaggle GPU as fallback for the final run |
| Water-pothole annotations incompatible | Verified week 1; synthetic sweep is primary and unblocked |
| Too few evaluation segments for tight `α` | `K = 15` default (~120 segments); report `α = 0.1` and `0.2` only; raise calib share to 30% before shrinking `K` further. **Aggravated by the India-only cut — watch this one.** |
| No published PCI→RSL source found | `mode: pci_only` fallback, decided with mentor by week 5 |
| Deduct-curve digitization overruns | Hard 3-day timebox; fall back to fewer severity levels (L/H only) |
| Jetson never arrives | Nothing upstream of `ingest` knows hardware exists; deployment chapter becomes export + benchmark + architecture design |
| Slipping past week 6 | **Cut the shift sweep before touching the dashboard.** A working demo with one solid result beats two results nobody sees. |

### Open questions for the mentor

1. **PCI→RSL:** use a published relationship (needs the citation) or stop at PCI
   bands (`mode: pci_only`)? Needed by week 5.
2. Does the lab already stock a Jetson-compatible CSI camera, before requesting a
   Raspberry Pi Camera Module 3?

---

## Appendix — Hardware (deferred, not on the 8-week critical path)

Requested but not yet approved; the software does not depend on it arriving.

| Component | Choice | Why |
|---|---|---|
| Compute | Jetson Orin Nano Dev Kit (8 GB) | Inference at the edge; not a training device |
| Camera | Raspberry Pi Camera Module 3, standard FOV (IMX708) | Autofocus, CSI, compact, better than IMX219 |
| Storage | 500 GB NVMe SSD | OS, models, logs |
| GPS | u-blox NEO-6M | Segment geotagging |
| Power | 19 V adapter; 12 V→19 V DC-DC for vehicle | Correct supply for the dev kit |
| Enclosure | Two 3D-printed PETG parts | Camera pod (~40×40×25 mm) behind windshield; compute box (~170×120×70 mm) under dash |

Splitting the camera pod from the compute box mirrors how commercial automotive
vision systems are actually packaged.
