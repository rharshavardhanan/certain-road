# Decision log

The running history of this repo. Every design decision, why it was made, and what
superseded it.

**Rules:**

- **Append, never rewrite.** A decision that turns out wrong is marked `Superseded`
  and a new entry explains why. The wrong turn stays visible — that history is the
  point of this file.
- **One decision per entry.** Numbered `Dnnn`, never renumbered.
- **Update on the same commit as the change.** A code change that alters a decision
  and does not touch this file is an incomplete change.
- Status is one of: `Accepted`, `Superseded by Dnnn`, `Refined by Dnnn`, `Rejected`,
  `Open`.

Current design spec: [`design.md`](design.md)

---

## Index

| # | Decision | Status |
|---|---|---|
| D001 | Product is a prioritisation system, not a pothole detector | Accepted |
| D002 | Single `uv` project with staged artifacts ("A+") | Accepted |
| D003 | Stage isolation enforced by `import-linter` in CI | Accepted |
| D004 | Conformal layer targets PCI, not detections | Refined by D005 |
| D005 | Calibration unit is the segment, not the frame | Accepted |
| D006 | Distance-sampled frames + ROI area fraction; no tracker, no homography | Accepted |
| D007 | `assess` runs before `calibrate` | Accepted |
| D008 | `rsl` is its own stage | Accepted |
| D009 | Four-way data split | Accepted |
| D010 | Evaluation segments: disjoint random partition, within-country | Accepted |
| D011 | `pci_true` renamed `pci_ref` (reference PCI) | Accepted |
| D012 | OOD detection / conformal p-values cut to future work | Accepted |
| D013 | Band-spanning intervals flagged `inconclusive` | Accepted |
| D014 | Severity is an area-quantile proxy, declared as such | Accepted |
| D015 | `density` renamed `vision_density` | Accepted |
| D016 | Deduct curves digitized; raw points committed | Accepted |
| D017 | Full iterative CDV correction, not simplified | Accepted |
| D018 | PCI→RSL curve requires a mandatory `source:` citation | Open |
| D019 | Optimiser ranks on worst-case RSL with must-fix constraint | Accepted |
| D020 | Dashboard is a self-contained offline HTML file | Accepted |
| D021 | Decision Replay panel | Accepted |
| D022 | Synthetic demo network by default; OSM gated and bannered | Accepted |
| D023 | No basemap tiles at all | Accepted |
| D024 | `survey_date` on every segment artifact | Accepted |
| D025 | Timeline cut 16 → 8 weeks; India subset only | Accepted |
| D026 | Evaluation segment size `K = 15`; `α = 0.05` not claimed | Accepted |
| D027 | Band-level validation study against manual assessment | Accepted |
| D028 | `severity` renamed `apparent_severity`; visual prominence, not structural | Accepted |
| D029 | Sensitivity analysis over ROI geometry and severity cutpoints | Accepted |
| D030 | Policy impact reported on two axes, not ranking churn alone | Accepted |
| D031 | Shift sweep narrowed to 2–3 corruptions to pay for D027–D030 | Accepted |
| D032 | Verified dataset facts; Python pinned to 3.12 | Accepted |
| D033 | Synthetic fixtures vary detection count, not defect character | Accepted |
| D034 | `aria2c` preferred over `curl` for the RDD2022 download, with curl fallback | Accepted |
| D035 | `convert`/`split` fail loud-but-not-fatal on real-data defects; `materialise` reports and self-cleans | Accepted |
| D036 | RDD2022 archive is nested two levels; corrects D032's flat-layout assumption and image/annotation counts | Accepted |
| D037 | Real census: RDD2022 India carries six non-CRDDC2022 class strings; `D44` dominates the drop set | Accepted |
| D038 | D00/D10 merged to one class; three-class set, refines D016 | Accepted |
| D039 | Water-pothole dataset: NO-GO as secondary shift experiment | Accepted |
| D040 | Ultralytics resolves a relative data-yaml `path` against its own `datasets_dir`, not cwd; `detect train` resolves against `repo_root()` at runtime | Accepted |
| D041 | Multi-country training, India-only calibration; refines D025 | Accepted |
| D042 | YOLOv8s over v8n for the multi-country run; combined before/after vs. india_v1 | Accepted |
| D043 | multicountry_v8s continued 23 epochs from existing weights, low-LR, no resume | Accepted |
| D044 | Detector eval harness: predictions remapped onto our taxonomy, not labels; D00+D10 merge extended to predictions | Accepted |
| D045 | Detector eval harness metrics: reuse `ultralytics.utils.metrics`, not `torchmetrics`; Task-4 validation diverges 0.029 mAP50 from `model.val()`'s `rect=True` default, cause identified | Accepted |
| D046 | Timeline fixed to 7 dated weeks (2026-08-17 → 2026-10-05); shift sweep cut; detector freezes 2026-08-30; refines D025 | Refined by D047 |
| D047 | Jetson + GPS brought into scope as a 3-week partition sequenced last; 4-partition schedule 2026-08-18 → 2026-10-05; sensitivity analysis cut | Refined by D048 |
| D048 | Jetson arrives 2026-08-18: risky bring-up pulled into a bounded weeks-1–4 parallel track; only `ingest`+`detect` ship to the edge | Accepted |
| D049 | Project pivots to an autonomous road-inspection robot; perception feeds two independent pipelines; control transport is abstract | Accepted |
| D050 | Simulator is a fourth `Transport`; robot for the demo, simulation for the trial matrix | Refined by D096 |
| D051 | CP cut from the sprint; survey ends at vision-estimated PCI; ADAS-inspired behaviours added; calibration split preserved | Superseded by D085 |
| D052 | Deliverable is a vehicle-agnostic control unit demoed on the Jetson: recorded video → real YOLO → real CAN on vcan0; no robot, camera or transceiver required | Accepted |
| D053 | External RDD2022 weights rejected: 0.9765 mAP50 on our test set indicates train/test overlap, so they cannot be measured | Accepted |
| D054 | Workspace cleaned and repo reorganised; redundant weights and data deleted, keepers named explicitly | Accepted |
| D055 | RoadSight spec amended to the frozen three-class merge; `pothole_class` replaces every hard-coded class 3 | Accepted |
| D056 | `uv` and Python 3.12 retained over the spec's pip/3.11; `requirements.txt` is generated, Kaggle installs only ultralytics | Accepted |
| D057 | Package stays `certain_road`; spec modules are audited and extended, never rewritten | Accepted |
| D058 | Local commit at the end of each task and before every `eval_locked` run; never push | Accepted |
| D059 | India block split rejected on evidence: adjacent IDs are uncorrelated, so a per-image salted-hash split at the spec's fractions is used | Accepted |
| D060 | Model A trains on Kaggle only; the Mac is a fallback for Model B alone, and never for A | Accepted |
| D061 | Near-duplicate audit by dHash before T3 bakes the splits into an upload | Accepted |
| D062 | Allocation solved by exact priority-indexed DP, not PuLP: the bundled CBC binary is x86_64 and cannot run here | Accepted |
| D063 | Leak verification is exhaustive, not hash-prefiltered; held-out India is never uploaded | Accepted |
| D064 | T10 resampling permutes scene groups, not images | Accepted |
| D065 | India x nonindia_val checked (68 false positives, 0 copies); kernel-side India guard added; NaN val loss shown to be inert | Accepted |
| D066 | Cross-country checks test for copies at 0.98, not the within-India same-scene 0.93; amends D063 | Accepted |
| D067 | The India generalization gap is the finding; Model A is never retuned because that number looks low | Accepted |
| D068 | Model A accepted; evaluation settings frozen and stamped so every reported number is like-for-like | Accepted |
| D069 | The India gap is confidence collapse and annotation extent, not blindness; corrects the T6 narrative | Accepted |
| D070 | T10 alphas come from the measured miss-rate floor, not a fixed list; Model A cannot certify India | Accepted |
| D072 | Overall 3-class mAP is not the target; pothole AP and per-pothole video detection are | Accepted |
| D073 | BharatPotHole is 162 drives, not 7,074 images; neither its val nor its test split is held out, so neither is used for evaluation | Accepted |
| D074 | Model P selected over Model B on india_val; the advantage survives scene-group resampling there but does not transfer to locked india_test, where the two are indistinguishable | Accepted |
| D075 | Video evaluation confirms per track (same ID, 3 of the last 5 frames, behind a horizon gate) and reports tracks, not potholes; qualifies D006 and D051 for evaluation only | Accepted |
| D076 | The T10 tau grid never reached the measured floor, so D070's feasible-alpha prose contradicted its own table; fixed, and Model P's floors measured | Accepted |
| D077 | T10 complete: Model B's certificate holds over 200 group-aware re-partitions, non-India calibration fails in every one, and every tight certificate costs a flood of false alarms | Accepted |
| D078 | T11: the spec's plain martingale is blind to a shift after 500 in-domain frames; a CUSUM reset at matched null false-alarm rate detects 197/200 with median delay 77 frames | Accepted |
| D079 | T12: conformal robustness changes repair decisions and helps modestly; maximising benefit defers the worst roads, so the dashboard must report both objectives | Accepted |
| D080 | Scope: a detection count measures discrete defects the detector recognises, not surface condition, and silence is not a good road; Model B's near-silence on degraded Bengaluru road is its training domain, not scale | Accepted |
| D081 | On dashcam video P fires where B does not (100 vs 9 tracks) while on india_test they are indistinguishable; whether P transfers or only fires more is Open until GT scoring; run both on Chennai footage and report both | Accepted · transfer claim Open |
| D082 | Potholes come from Model P and cracks from Model B, and their pothole outputs are never summed; settles the channel D081 left open; no T12 number reflects it yet; D081's transfer claim stays Open | Accepted · T12 re-run Open |
| D083 | T16: the dashboard stays one offline HTML file (D020 over the spec); the optimiser's and worst-first's plans always side by side; T12 numbers carry the Model B recall caveat | Accepted |
| D084 | The locked Model P run's 2,312 absolute symlinks stay as committed (results/LOCKED is never rewritten); eval_locked.py now links relatively; a test pins every escaping link and home-directory path, and configs/data stays absolute by decision | Accepted |
| D085 | Conformal prediction, cut by D051 under sprint pressure, was reinstated by the RoadSight spec adopted at T0 (a23bf6a), which made the certified miss rate the core claim; no separate decision recorded the reversal | Accepted |
| D086 | Simulator textures are QR4Change and BD-N6 photos (CC BY 4.0), never used in training; audited clean by norm_vec (max 0.8887) and ORB crop matching (max 8 inliers) | Accepted |
| D087 | A MuJoCo demo simulator for the DA-2 review (`sim/mujoco/`): synthetic road from the D086 photos, real detectors and survey code, design camera; not T13 | Accepted |
| D088 | The MuJoCo demo detects at 30 fps, the rate D075's 3-of-5 rule was set on; at 10 fps confirmation collapsed. Gate at the design detect range; the survey still scores 5 m samples (D006) | Accepted |
| D089 | The demo's survey counts D006's ROI, the 5 m strip of the driving lane 3–8 m ahead, scored by certain_road.survey; the reference PCI takes the same path. The real drift monitor fires on clean road, not on the mixed preset's bad stretch, so that moment is captioned as a band drop | Accepted |
| D090 | The demo's end screen scores confirmed tracks against ground truth (IoU > 0.1, both lanes) and runs both real allocators on D079's pricing, scored on D079's two objectives. Same seed, same result | Accepted |
| D091 | Only damaged segments can be among the end screen's true worst N; all five presets run, and the drift alarm fires at 65–150 m on every road | Accepted |
| D092 | The demo's look v2 adds 3D potholes, surface marks and harsher light with tree shadows, and is the default; v1 stays byte-identical as the fallback. Measured once: detection barely moves, and no false alarm comes from the new marks | Accepted |
| D093 | A ROS 2 Jazzy demo on the Jetson wraps the 2D simulator in three nodes; ROS is one more `Transport`; the camera frame is rendered from the projection; no Gazebo (D050 stands) | Accepted |
| D094 | The review demo runs on the Jetson: the MuJoCo survey demo and a live real-road viewer on CUDA; `mps` resolves to the machine's accelerator; textures rebuilt from their public sources | Accepted |
| D095 | The ROS graph takes any camera: the real road clip streams in as a camera (open loop), every Command also leaves as a CAN frame on vcan0, and the 2D sim defaults to projection | Accepted |
| D096 | A Gazebo Harmonic world, converted geom by geom from the MuJoCo look-v2 road, with a sprung Ackermann car; reverses D050's rejection of Gazebo for the demo | Accepted |
| D097 | The Gazebo closed loop (car profile, car corridor, stand-in lane keeper) is built but not yet measured | Open |
| D098 | The survey simulation report and RSL from Sharaf et al. (1987), pending mentor approval; built in part, not yet run on three roads | Open |

---

## D001 — Product is a prioritisation system, not a pothole detector

**2026-08-06 · Accepted**

The question is "which segments do we repair first on a fixed budget", not "where is
a pothole". Detection, YOLO and the Jetson are inputs and tooling, not the product.
Contributions are edge detection, calibrated uncertainty, and uncertainty changing
the budget decision — the novelty is the integration.

## D002 — Single `uv` project with staged artifacts ("A+")

**2026-08-06 · Accepted**

One project, one dependency file, one CLI. Stages communicate only through typed
artifacts on disk.

Rejected: a `uv` workspace of six sub-packages (configuration ceremony with no payoff
for one author in eight weeks); a flat package with `scripts/` (how the codebase
becomes unmaintainable by week 6).

Consequence — and the reason for the choice: downstream stages are testable against
synthetic detections, so hardware procurement and long training runs never block
development.

## D003 — Stage isolation enforced by `import-linter` in CI

**2026-08-06 · Accepted**

Stages may import `artifacts/` and `core/` only, never each other. A rule nothing
enforces does not survive a deadline, so a cross-stage import fails the build.

## D004 — Conformal layer targets PCI, not detections

**2026-08-06 · Refined by D005**

Chosen over conformal risk control on false negatives, OOD-only, and box-level
conformal detection. Nonconformity is `|PCI(predicted) − PCI(reference)|`, which
needs no PCI ground truth that does not exist, and quantifies the error the detector
injects into the decision.

## D005 — Calibration unit is the segment, not the frame

**2026-08-06 · Accepted · refines D004**

Governments repair road segments, not frames or bounding boxes. Attaching the
guarantee to the engineering decision rather than to the detector is both a stronger
research story and statistically cleaner — the segment is the exchangeable unit.
Guarantees are reported as `PCI [41,56]`, `RSL [0.8,1.6] years`.

## D006 — Distance-sampled frames + ROI area fraction; no tracker, no homography

**2026-08-06 · Accepted**

One frame per ~L metres of travel, so camera footprints never overlap and
double-counting is impossible by construction. Density is damaged pixel area over a
fixed trapezoid ROI.

Rejected: ByteTrack dedup (fragile on dashcam video, ID switches corrupt counts);
inverse perspective mapping (RDD2022 camera geometry varies by country, so one
homography cannot be right). Removes the two most failure-prone components from the
project. Valid because predicted and reference PCI pass through identical geometry.

## D007 — `assess` runs before `calibrate`

**2026-08-06 · Accepted**

Corrects an earlier sketch of `detect → calibrate → assess`. The nonconformity score
is defined on segment PCI, so PCI must exist before it can be calibrated. Chain is
`ingest → detect → assess → calibrate → rsl → optimize → report`.

Consequence: `calibrate` splits into `fit` (offline, once) and `apply` (per run), and
`assess` must be pure over any detections table since calibration calls it on both
predicted and ground-truth boxes.

## D008 — `rsl` is its own stage

**2026-08-06 · Accepted**

Separated from `assess` so the PCI→RSL relationship can be swapped, or skipped
entirely via `mode: pci_only`, without touching PCI computation.

## D009 — Four-way data split

**2026-08-06 · Accepted**

`train` 60 / `val` 10 / `calib` 20 / `test` 10. Conformal validity is void if the
calibration set influenced detector fitting, so `calib` is disjoint from both `train`
and `val`. Calibration gets 20% because `q̂` is noisy and the sample unit is the
segment, not the frame.

## D010 — Evaluation segments: disjoint random partition, within-country

**2026-08-06 · Accepted**

RDD2022 has no GPS or route continuity, so real 100 m segments cannot be built from
it. An evaluation segment is a random **disjoint** partition of the calibration pool
into `K`-frame blocks — disjoint because overlapping blocks break exchangeability.
Partitioned within country; a segment mixing Norwegian and Japanese frames is not a
road.

Named "evaluation segment" in code, schemas and prose. These are **not** physical
road segments and must never be described as such.

## D011 — `pci_true` renamed `pci_ref` (reference PCI)

**2026-08-06 · Accepted**

`pci_true` implies a certified ASTM field survey. The quantity is derived from
annotations and from this project's own assessment algorithm. Renaming is a one-word
change that removes a whole line of attack.

## D012 — OOD detection / conformal p-values cut to future work

**2026-08-06 · Accepted**

Image-level conformal p-values over backbone embeddings were specified, then cut:
they constitute a second research objective (distribution-shift detection) bolted
onto the first (certified PCI). Implementation cost without strengthening the central
contribution.

## D013 — Band-spanning intervals flagged `inconclusive`

**2026-08-06 · Accepted · consequence of D012**

D012 removed the abstention mechanism, so the dashboard had nothing to say when it
should not be trusted. Any interval spanning more than one PCI condition band is
flagged `inconclusive` and rendered as "human inspection required". `[42,55]` is
actionable; `[38,71]` is not. Derived from the interval already computed — no new
model, no second thesis.

## D014 — Severity is an area-quantile proxy, declared as such

**2026-08-06 · Accepted**

RDD2022 has no severity annotations. Severity is banded L/M/H from each detection's
area fraction, using per-class quantile cutpoints computed once on the train split
and frozen into config.

Known weakness, stated rather than hidden: a long thin crack may have small area but
high severity. Thesis must carry the sentence "severity is a vision-derived proxy
based on apparent damaged area, because RDD2022 contains no severity annotations."

## D015 — `density` renamed `vision_density`

**2026-08-06 · Accepted**

ASTM density is physical area. This is image-space area fraction. A civil engineer
would correctly object to the unqualified term. Renamed everywhere in code and prose.

## D016 — Deduct curves digitized; raw points committed

**2026-08-06 · Accepted**

`DV = min(100, α + β·log₁₀(vision_density))` per (class, severity), fitted to ASTM
curves digitized with WebPlotDigitizer — never eyeballed. Raw `(density, DV)` points
committed to `configs/assess/curves/*.csv` beside the fitted coefficients, so β has
provenance and the fit is reproducible.

## D017 — Full iterative CDV correction, not simplified

**2026-08-06 · Accepted**

~40 lines, and the difference between something a pavement engineer recognises as PCI
and something that is merely a weighted penalty sum.

## D018 — PCI→RSL curve requires a mandatory `source:` citation

**2026-08-06 · Open**

The form `age = ((100 − PCI)/a)^(1/b)` was proposed without a citation — a standard
deterioration *shape*, but presented as if settled. It is not.

`configs/rsl/*.yaml` carries a mandatory `source:` field and the stage **refuses to
run while it is empty**. Resolve by week 5: either enter a published relationship
with its citation, or the mentor selects `mode: pci_only`. One-line config change
either way.

Note: the relationship is monotone increasing, so interval endpoints map through
directly and conformal coverage is preserved exactly.

## D019 — Optimiser ranks on worst-case RSL with must-fix constraint

**2026-08-06 · Accepted**

Urgency driven by `rsl_lo`, not point RSL. Any segment with `rsl_lo < 1 year` is a
hard must-fix ahead of discretionary spend, mirroring how road agencies budget.
Benefit is `length × traffic_weight × risk` with `traffic_weight = 1` (AADT is future
work; Chennai data unavailable). Solver is an exact 0/1 knapsack by DP over costs
integerised to ₹1 lakh — exact and instant, so no greedy approximation to defend.

The stage runs twice (point RSL vs `rsl_lo`) and diffs the funded sets, producing the
headline "how often does uncertainty change the repair list" figure as a by-product.

## D020 — Dashboard is a self-contained offline HTML file

**2026-08-06 · Accepted**

One generated HTML per run. Leaflet and Plotly vendored inline — no CDN, because a
CDN fails exactly like a tile server and a viva room's wifi cannot be trusted. No
server, no install, no database. PDF export is a print stylesheet, not a library.

Rejected: Streamlit (looks like a research notebook, needs a process running);
React + FastAPI + DB (6–8 weeks for zero research contribution); CSV only (loses the
demo, which is what a panel remembers).

## D021 — Decision Replay panel

**2026-08-06 · Accepted**

Clicking a segment expands the full chain: detections → vision-estimated PCI with
interval → RSL interval → treatment → cost → rank → rationale. Converts the ranking
from a black box into a visible audit chain, and exhibits the entire contribution in
one panel.

## D022 — Synthetic demo network by default; OSM gated and bannered

**2026-08-06 · Accepted**

RDD2022 has no geometry, so the map and cost model need a network. Default is a
procedurally generated synthetic network with fictional names and no real geography.
An OSM mode exists but is off by default and gated behind a persistent "Demonstration
Only" banner; real road names are never rendered.

Rationale: a screenshot of "Anna Salai — PCI 34" would be read as a real measurement
of a road that was never surveyed. The safe option is the default option.

## D023 — No basemap tiles at all

**2026-08-06 · Accepted · consequence of D022**

A synthetic network needs no satellite imagery. Leaflet draws polylines on a blank
canvas, deleting tile prefetching, CDN dependence and the offline-tiles problem in
one move.

## D024 — `survey_date` on every segment artifact

**2026-08-06 · Accepted**

Without it the optimiser treats a segment surveyed today and one surveyed six months
ago identically, and longitudinal extension later requires a schema migration.
Present from the first schema even though all current runs share one date.

## D025 — Timeline cut 16 → 8 weeks; India subset only

**2026-08-06 · Accepted**

Cut: RDD2022 India subset only (~9–10k images, 4–6h training instead of 25–40h,
same-day retraining, tighter Tamil Nadu narrative, loses cross-country shift);
water-pothole dataset optional and verified in week 1; normalized CP to future work;
Jetson deployment reduced to ONNX export plus latency benchmark; basemap tiles
deleted per D023.

Defended as the actual contribution: deduct-curve digitization (3-day timebox), full
CDV correction, split conformal with coverage table, dual-run ranking diff.

Feasible only because of D002 — training runs unattended for days while `assess` and
`calibrate` are built against synthetic fixtures.

If slipping past week 6: **cut the shift sweep before touching the dashboard.**

## D026 — Evaluation segment size `K = 15`; `α = 0.05` not claimed

**2026-08-06 · Accepted · consequence of D025**

Found during spec self-review. D025 cut the dataset to India only, which shrank the
calibration pool to ~1.8–2.0k frames. At the previously assumed `K = 30` that yields
only ~60 evaluation segments, giving realised coverage a standard deviation of ~4
percentage points — a nominal 90% interval could land empirically between ~82% and
~98%. The guarantee holds (it is marginal over draws) but one noisy number is weak
thesis evidence.

Default `K = 15` (~120 segments) halves that noise while keeping segments meaningful.
Report `α = 0.1` and `α = 0.2` only; **`α = 0.05` is not supportable at this sample
size and must not be claimed.** Raise the calibration share to 30% before shrinking
`K` further.

Calibration frames may not be borrowed from other countries — `calib` must be
exchangeable with `test`.

The `K` sweep becomes a reportable figure: a genuine finding about deploying
conformal prediction on small survey datasets, not a tuning note.

## D027 — Band-level validation study against manual assessment

**2026-08-06 · Accepted**

Without it the project demonstrates a pipeline that runs but never shows its central
quantity means anything.

50 stratified evaluation segments; three raters independently assign a condition band
from a contact sheet of each segment's frames, blind to model output (~1h per rater).
Reported as a confusion matrix, exact and within-one-band agreement, quadratic-weighted
Cohen's κ against the modal human band, and **Fleiss' κ between raters as the ceiling**
— a model at κ = 0.45 where humans agree at κ = 0.5 is performing near the limit of the
task, and omitting that context understates the result.

Scope boundary, stated wherever reported: raters judge the same monocular images the
model consumes, so this validates agreement with *human visual judgement*, not with a
certified ASTM field survey.

Why it matters: D004/§2's limitation states the conformal interval covers
detector-induced error and **not** PCI-model error. This study is direct evidence about
that uncovered term. It does not close the gap; it bounds it.

**The rating set is validation, never a dev set.** The model is not tuned against it.
Poor agreement is a result to report and analyse, not a failure to fix.

## D028 — `severity` renamed `apparent_severity`; visual prominence, not structural

**2026-08-06 · Accepted · refines D014**

ASTM severity is a structural judgement depending on crack width, spalling, depth and
ride quality — none observable from a single monocular frame. What the area-quantile
proxy actually measures is **visual prominence**. Renamed `apparent_severity` in code
and schemas so the distinction cannot be lost in a later reading of the thesis.

## D029 — Sensitivity analysis over ROI geometry and severity cutpoints

**2026-08-06 · Accepted**

Two arbitrary choices sit upstream of every reported number. If PCI swings with
either, the pipeline is measuring its own configuration.

Sweep ROI trapezoid ±20% on height and width, and severity quantile splits at
(25/75), (33/67), (40/60), one at a time. Report change in mean PCI, in coverage and
interval width, and — the metric that matters — **in the funded segment set**.

Cheap only because of D002 and D003: every value is config, no stage imports another,
so a sweep is a loop over config files rather than a code change. Instability found is
a result to report, not a defect to conceal.

## D030 — Policy impact reported on two axes, not ranking churn alone

**2026-08-06 · Accepted · refines D019**

Ranking churn alone is a weak claim: swapping two equally-bad segments is noise, not
improvement.

**Axis 1, decision change:** Jaccard distance between funded sets; segments
entering/leaving; Spearman ρ over the full ordering; ₹ reallocated.

**Axis 2, aggregate network condition:** length-weighted network mean PCI after
treatment; RSL-years gained per ₹ crore; **km of `rsl_lo < 1 yr` left unfunded
(residual risk)**; `inconclusive` segments funded vs deferred.

The defensible claim is conjunctive: *uncertainty reallocated X% of the budget **and**
reduced unfunded critical length by Y km.* Axis 1 shows the answer changed; Axis 2
shows it changed for the better.

## D031 — Shift sweep narrowed to pay for D027–D030

**2026-08-06 · Accepted · consequence of D027–D030**

The four validation additions cost ~4 days against a schedule with little slack.
Funded by narrowing the synthetic shift sweep from four corruption types to two or
three; the coverage-versus-severity curve keeps its shape and its finding.

Rater collection is scheduled in week 4 because it depends on other people's
calendars — the one item in the plan that cannot be compressed by working harder.

Revised cut order if slipping past week 6: shift sweep → sensitivity sweep → policy
Axis 2. **The validation study (D027) is never cut** — it is the only evidence the
central quantity is meaningful.

## D032 — Verified dataset facts; Python pinned to 3.12

**2026-08-06 · Accepted**

Established against the Figshare and Mendeley APIs before planning, replacing
estimates used in D025 and D026.

**RDD2022** (DOI `10.6084/m9.figshare.21431547.v1`, CC BY 4.0). Ships as **one
13.26 GB zip** — *there is no per-country download.* "India subset only" therefore
means downloading 13.26 GB and selectively extracting `RDD2022/India/*`. Structure is
`RDD2022/<Country>/train/{images,annotations/xmls}` and `<Country>/test/images`.
Annotations are PASCAL VOC XML; `label_map.pbtxt` declares four classes — D00, D10,
D20, D40.

Per-country annotated counts (from the published file list):

| Country | Images | Annotated |
|---|---|---|
| India | 9,665 | **7,706** |
| Japan | 13,133 | 10,506 |
| Norway | 10,201 | 8,161 |
| United States | 6,005 | 4,805 |
| Czech | 3,538 | 2,829 |
| China MotorBike | 2,477 | 1,977 |
| China Drone | 2,401 | 2,401 |

**The test split is unlabelled** and cannot serve as our `test`. All four splits are
carved from the 7,706 annotated training images: `train` 4,624 / `val` 771 / `calib`
1,541 / `test` 770. This corrects D026 (see spec §2).

Consequence to expect: **~4,624 training images is small**, and India is the hardest
RDD2022 subset. Published multi-country mAP figures are not a fair benchmark for this
model, and the thesis should not compare against them as though they were.

**Water-filled potholes** (Mendeley `tp95cdvgm8`) is **lower risk than D025 assumed**.
`Potholes.zip` is 290 MB and the ReadMe confirms it ships `IMG/`, `XML/` (PASCAL VOC)
**and** `TXT/` (YOLO) — the same format family as RDD2022. The week-1 spike should
cost hours, not the budgeted day. The open question narrows to class set and whether
the potholes are genuinely water-filled.

**Python pinned to 3.12.** The machine's system Python is 3.14. torch 2.13 publishes
macOS arm64 wheels through cp314, but ultralytics 8.4.115 declares support only
through 3.13. 3.12 is the well-supported intersection and matches the machine's
existing convention.

## D033 — Synthetic fixtures vary detection count, not defect character

**2026-08-06 · Accepted**

`tests/fixtures/synthetic.py` draws a per-segment `apparent_severity` multiplier
that scales the Poisson detection rate, so segments genuinely differ in how many
defects they contain. Box size and `class_name`, however, are drawn independently
of that multiplier — uniform across every segment regardless of its severity.

Downstream, vision-estimated PCI is computed per (class × apparent_severity) with a
separate deduct curve for each combination, so the fixtures exercise only one axis
of that machinery: quantity varies, but the class mix and box-size distribution that
drive which deduct curve applies do not. A test built against these fixtures cannot
show PCI responding correctly to a shift in defect character, only to a shift in
defect count.

Deliberately deferred to week 2, once `assess` exists and can reveal what
variation the deduct curves actually need from the fixtures — building that
coupling now would be guessing at a shape the real computation hasn't specified
yet.

## D034 — `aria2c` preferred over `curl` for the RDD2022 download, with curl fallback

**2026-08-06 · Accepted**

`download_rdd2022` used a single-connection `curl -L -C -` to fetch the 13.26 GB
RDD2022 archive. Measured on 2026-08-06: Figshare redirects to
`s3-eu-west-1.amazonaws.com`, which **throttles per connection** at ~0.75 MB/s,
well under the machine's link speed of 12.8 MB/s. S3 honours HTTP byte-range
requests (206 Partial Content), so parallel connections multiply observed
throughput rather than sharing one throttled pipe. Switching to `aria2c -x16`
measured 7.4 MB/s — the same 13.26 GB drops from a ~4.4-hour download to ~28
minutes.

`download_rdd2022` now uses `aria2c` when it is present on `PATH`
(`shutil.which("aria2c")`), with the original single-connection `curl` invocation
kept unchanged as a fallback for machines without it. The early-return for an
already-complete file (checked against `expected_zip_size()` from the Figshare
API) and the post-download size check are both unchanged. `ARIA2_CONNECTIONS = 16`
is a named constant rather than a literal in the `aria2c` invocation.

Consequence to record: **aria2c cannot resume a partial file that curl started.**
`aria2c` splits a download using its own `.aria2` control file to track which
byte ranges have landed; a partial file left behind by `curl` has no such control
file, so `aria2c` treats it as an ordinary partial and silently falls back to a
single connection, losing the whole speedup. Switching downloaders mid-transfer
therefore means discarding the in-flight partial and restarting, not resuming it
in place.

## D035 — `convert`/`split` fail loud-but-not-fatal on real-data defects; `materialise` reports and self-cleans

**2026-08-06 · Accepted**

Pre-real-data review found four failures that only manifest against the actual
9,665-image / ~7,706-annotation RDD2022 India set, not the synthetic fixtures used
so far:

1. `convert_directory` called `parse_voc` bare, so a single malformed XML among
   ~7,706 real annotations raised `ET.ParseError`/`ValueError` and aborted the
   whole conversion with zero labels written — defeating the stated design intent
   that the gap between annotation count and label count is always explainable.
   `convert_directory` now catches the same two exception types `class_census`
   already does, counts them under the same `PARSE_ERROR:<Type>` key, skips that
   file (no label file is written for it), and continues.
2. `materialise` silently `continue`d past a missing source image. RDD2022 ships
   more images than annotations, so some skipping is expected — but the printed
   split sizes and `splits.json` gave no way to tell how much, or whether a
   skip meant "expected annotation gap" vs. "someone pointed this at the wrong
   directory." `materialise` now returns `dict[str, SplitMaterialiseReport]`
   (`requested`, `linked`, `skipped_missing_image` per split) instead of `None`;
   this is a breaking signature change for the one caller, `cli.dataset_split`,
   which now prints it and flags any non-zero skip count.
3. `materialise` never removed files from a prior run, so a stem dropped from
   `labels_all` (re-conversion, corrected annotations) left a stale symlink and
   label behind that silently diverged from the current `build_splits()` output.
   `materialise` now clears each split's `images/<split>` and `labels/<split>`
   directory contents before repopulating — but only files it manages (`*.jpg`
   symlinks, `*.txt` labels, matched by the new `IMAGE_SUFFIX`/`LABEL_SUFFIX`
   constants), never the directory tree itself. A `rm -rf` on a path built from
   config is exactly the kind of thing that eats someone's data when the path is
   wrong.
4. `materialise` and `write_manifest` had no test coverage, so the calib/train/val
   disjointness the whole conformal layer depends on (D009) was proven only in
   memory (`build_splits`), never verified in its physical, on-disk form.
   `tests/test_dataset_split.py` now builds a small fake dataset under `tmp_path`
   and checks matching image/label counts per split, no stem's image file
   appearing under more than one split directory, a missing image being skipped
   with no orphan label, no stale file surviving a re-run after a stem is
   removed, and `write_manifest`'s `counts` matching actual split sizes.

`SALT` and `SPLIT_BOUNDS` are unchanged (settled, D009); the ultralytics data
yaml still references only `train`/`val`.

## D036 — RDD2022 archive is nested two levels; corrects D032's flat-layout assumption and image/annotation counts

**2026-08-06 · Accepted · Corrects D032**

D032 described RDD2022's layout as flat: `RDD2022/<Country>/train/{images,annotations/xmls}`
directly inside the 13.26 GB outer zip. Inspecting the real, fully-downloaded archive
(13,264,172,619 bytes, matching the Figshare API) shows that's wrong — **the archive is
nested two levels.** The outer zip contains exactly seven entries, each a per-country zip
stored **uncompressed**:

| Entry | Size |
|---|---|
| `RDD2022/China_Drone.zip` | 0.160 GB |
| `RDD2022/China_MotorBike.zip` | 0.192 GB |
| `RDD2022/Czech.zip` | 0.257 GB |
| `RDD2022/India.zip` | 0.527 GB |
| `RDD2022/Japan.zip` | 1.073 GB |
| `RDD2022/Norway.zip` | 10.611 GB |
| `RDD2022/United_States.zip` | 0.444 GB |

Inside `RDD2022/India.zip`, the root is `India/` — **not** `RDD2022/India/` — with 17,377
entries: `India/train/images/*.jpg` (7,706 files), `India/train/annotations/xmls/*.xml`
(7,706 files, matched 1:1 with the train images), and `India/test/images/*.jpg` (1,959
files, unlabelled). 7,706 + 1,959 = 9,665.

`extract_country` assumed the flat layout and raised `ValueError: no entries under
'RDD2022/India/'` against the real archive — a real-data defect no synthetic fixture could
catch, since the fixture itself encoded the same wrong assumption. Fixed by having
`extract_country` open the outer zip, locate `RDD2022/<country>.zip` (raising a clear,
country-named error if absent), stream that member to a temporary file — never reading it
fully into memory, since Norway's inner zip alone is 10.6 GB — and extract *that* into
`dest / "RDD2022" / <country>`, preserving the flat on-disk contract the rest of the
codebase (`cli.py`, `convert.py`, `split.py`) already expects. `tests/test_dataset_fetch.py`'s
fixture now builds the same two-level nesting instead of a flat fake zip.

**This corrects D032's stated counts.** D032 listed India as "9,665 images, 7,706
annotated," which conflated the *combined* train+test image count (9,665) with the
*train-only* annotation count (7,706), implying a mismatch. There is no mismatch: India
has exactly 7,706 train images and 7,706 train annotations (1:1), plus 1,959 separate,
unlabelled test images, and 7,706 + 1,959 = 9,665. The per-country table in D032 for the
other six countries is unverified by this entry and should be treated the same way until
each is checked against its own inner zip.

**Concrete improvement logged for future work, not implemented here:** entries in the
outer zip are stored uncompressed, which means the ZIP central directory records each
member's exact byte range within the outer file. A future fetch could read only the
outer archive's central directory over HTTP (a small, fixed-size read from the end of
the file) to find `RDD2022/India.zip`'s offset and length, then issue a single HTTP
range request for just that span — pulling roughly **0.6 GB instead of the full 13.26
GB** for an India-only fetch. This is not a hypothetical: S3 already honours byte-range
requests (D034), so the same mechanism that makes `aria2c -x16` viable would carry a
range-restricted single-country fetch. Out of scope for this fix, which only corrects
extraction against the archive already on disk.

## D037 — Real census: RDD2022 India carries six non-CRDDC2022 class strings; `D44` dominates the drop set

**2026-08-06 · Accepted**

`certain-road dataset census --country India` over all 7,706 annotated training images
found six class strings beyond the four `label_map.pbtxt` classes {D00, D10, D20, D40}:

| Class | Boxes | Status |
|---|---|---|
| D44 | 1,062 | DROP |
| D01 | 179 | DROP |
| D43 | 57 | DROP |
| D11 | 45 | DROP |
| D50 | 28 | DROP |
| D0w0 | 1 | DROP |

Total census: 8,203 boxes; kept (D00/D10/D20/D40) 6,831; dropped 1,372. No
`PARSE_ERROR` rows occurred — every one of the 7,706 XML files parsed cleanly.

`D44` alone (1,062 boxes) is not noise: it exceeds the kept count of the official
`D10` class (68 boxes) by more than 15x, making it a substantial second-tier
annotation scheme India's RDD2022 contributors used alongside the official four,
not a scattering of typos. `conversion` already counts every rejection under
`unknown_class:<name>` (D035), so the gap between the census total and kept boxes
is fully explained and reconciles exactly: 6,831 kept + 1,372 dropped = 8,203
census total.

No code change results from this entry — the existing drop-and-count behaviour in
`to_yolo_lines` is correct as designed. Recorded because a future multi-class
extension (widening `CLASS_TO_ID` beyond the four CRDDC2022 damage types) would
need to weigh whether `D44` is a distinct, learnable damage type worth adding or
an annotation artifact specific to this contributor, before spending a training
run on it.

## D038 — `D00`/`D10` merged to one class id; three-class set; refines D016

**2026-08-07 · Accepted · refines D016 · amended by D055**

D037's census showed RDD2022 India's official `D10` (transverse crack) has only
**68 boxes total — 43 in `train`, 13 in `calib`.** Too few to learn: a YOLOv8n head
trained on 43 examples would score near-zero mAP on the class, and most of the
~103 evaluation segments (D026) contain no `D10` box at all, so the class would
contribute nothing to vision-estimated PCI while still adding a fourth deduct
curve to digitize and defend.

This is not a data-balance hack. **ASTM D6433 defines longitudinal and transverse
cracking as a single distress type for asphalt pavement, sharing one deduct
curve** — RDD2022 splits them into `D00`/`D10`, but the standard this project
targets does not. Merging `D00` and `D10` into one class is therefore *more*
faithful to ASTM, not less: it treats a split that only exists because of RDD2022's
labeling scheme as what it actually is downstream.

`SOURCE_TO_ID` in `certain_road/detect/dataset/convert.py` now maps `{"D00": 0,
"D10": 0, "D20": 1, "D40": 2}`. Output classes are renamed for readability:
`linear_crack` (0, was D00+D10), `alligator_crack` (1, was D20), `pothole` (2, was
D40). The merge changes only labels, not the underlying boxes: kept count is
unchanged at 6,831, split sizes are unchanged (train 4,617 / val 757 / calib 1,548
/ test 784 — verified stable under the same salted-hash assignment, D009), and the
new per-class kept counts are `linear_crack` 1,623 (1,555 D00 + 68 D10),
`alligator_crack` 2,021, `pothole` 3,187 — total 6,831, unchanged.

Consequence for D016: deduct-curve digitization drops from **four curves to
three** — one fewer curve to digitize from WebPlotDigitizer, fit, and commit to
`configs/assess/curves/`.

**Cost:** comparability with RDD2022's own four-class benchmark is given up — a
model trained on this three-class set cannot be scored against published
four-class mAP figures class-for-class. D032 already established that those
published multi-country figures were not a fair yardstick for an India-only model
in the first place, so this gives up a comparison that was already flagged as
unreliable, not one this project was relying on.

## D039 — Water-pothole dataset: NO-GO as secondary shift experiment

**2026-08-07 · Accepted**

Timeboxed spike per D025/D032 (see `docs/datasets/water-pothole-viability.md` for full
evidence). Downloaded and extracted Mendeley `tp95cdvgm8`'s `Potholes.zip`
(290,505,592 bytes): 713 images, 713 PASCAL VOC XML annotations, 713 YOLO TXT
annotations, plus a `ReadMe.txt` and two dashcam videos not anticipated in D032.

`class_census` over `XML/` found a single annotated class, `pothole` (1,156
boxes), plus one apparent mislabel (`o`, 1 box). Images are geometrically
heterogeneous — 66 distinct `(width, height)` pairs across 713 files, no
dominant size — consistent with images drawn from varied sources rather than one
capture rig.

**Decision: NO-GO.** Two independent reasons, neither alone decisive but
compounding:

1. The dataset's premise — a genuine water-filled vs. dry distribution shift —
   is unverifiable within this timebox. The bundled `ReadMe.txt` says nothing
   about water content; only the Mendeley page's own title ("An Annotated
   Water-Filled, and Dry Potholes Dataset...") asserts it, and the annotation
   vocabulary has no class or attribute that could confirm it computationally.
   A single undifferentiated `pothole` class is exactly what an incidentally
   wet collection would also produce — the data cannot distinguish the two
   without a human opening all 713 images by hand, which this spike's timebox
   does not cover.
2. The dataset is single-class (`pothole` only) against our three-class set
   (`linear_crack`, `alligator_crack`, `pothole`, D038). Any use would compute
   reference PCI and vision-estimated PCI restricted to the pothole
   contribution only, narrowing the comparison relative to the primary
   RDD2022-based results.

Consequence: the synthetic corruption sweep (D031) remains the sole
distribution-shift experiment for the thesis — exactly the fallback D025 and
D031 already planned around. No other week-1/week-2 work is blocked or delayed
by this verdict.

## D040 — Ultralytics relative `path` resolves against `datasets_dir`, not cwd

**2026-08-07 · Accepted**

D039's sibling commit (`configs/dataset/rdd2022_india.yaml` no longer baking in
an absolute machine path) assumed a relative data-yaml `path` resolves against
the process working directory, or against the yaml's own location. Measured
directly, neither is true: ultralytics resolves a relative `path` against its
own `datasets_dir` setting (`~/PROJECTS/datasets` on this machine, set once by
the library and unrelated to this repo), so `path: data/processed/india`
resolved to `~/PROJECTS/datasets/data/processed/india/...` — a directory that
does not exist — and training would have failed at the first batch. This
slipped through because the pre-launch smoke run was skipped to protect the
then-live training run, which is exactly the situation a smoke run exists to
catch.

**Decision:** keep the committed yaml's `path` relative (still required for
portability — it must not embed a machine-specific absolute path), but resolve
it ourselves before ultralytics ever sees it. `certain_road.detect.train`:

1. Loads the data yaml and runs the `calib`/`test` firewall check (D009) against
   the *original* loaded config, unconditionally, before any path resolution.
2. If `path` is relative, resolves it against `certain_road.core.paths.repo_root()`.
3. Confirms the resolved `images/train` and `images/val` directories exist,
   raising `FileNotFoundError` naming the resolved path (not just the relative
   one) if not — a missing-data error must say where it actually looked.
4. Writes an absolute-path copy to a temporary yaml and hands only that copy to
   `YOLO().train()`. The committed config is never mutated.

This keeps the config portable across machines while making the actual
resolution behavior explicit and tested, rather than relying on an assumption
about ultralytics internals that turned out to be wrong. Anyone tempted to
"simplify" this back to a bare relative `path` should read this entry first —
it will train against the wrong directory, or against nothing, with no error
until the trainer already claims a GPU/MPS device and starts scanning for
images.

## D041 — Multi-country training, India-only calibration; refines D025

**2026-08-07 · Accepted · refines D025**

D025 cut the dataset to India only, for time reasons: multi-country meant 13.26 GB
extracted six more times and 25–40h of training instead of 4–6h, against an 8-week
timeline. The India-only baseline has now actually finished (mAP50 0.4238, mAP50-95
0.1791 at epoch 84, weights at `runs/detect/models/yolo/india_v1/weights/best.pt`),
so per-epoch cost is measured rather than estimated, and the time constraint that
justified restricting training data no longer binds — extending the detector's
training set to all six additional RDD2022 countries costs known, bounded wall-clock
time, not an open-ended risk.

**Decision:** the detector trains on all seven RDD2022 countries. Conformal
calibration and testing stay India-only — `calib` and `test` are **unchanged** from
the India-only split (train 4,617 / val 757 / calib 1,548 / test 784). Concretely:

- `train` = India's existing train stems + every annotated non-India image
- `val` = India's existing val stems only (early stopping tracks Indian performance,
  since that is what deployment cares about)
- `calib` = India's existing calib stems, unchanged
- `test` = India's existing test stems, unchanged

**Why the guarantee must stay anchored to a describable population:** a conformal
interval is only meaningful relative to the exchangeable population it was
calibrated against. Calibrating on a blend of six countries' images would produce
intervals valid for an artificial mixture that exists nowhere as a deployment
target. Deployment is Indian roads, so the calibration and test populations must
stay Indian even though the detector itself benefits from more and more varied
training data. This is the same reasoning D010 already applied to evaluation
segments (partitioned within-country, never mixed) — D041 extends it to the
train/calib boundary rather than only the segment boundary.

**India's four-way split assignment is unchanged.** `build_splits` assigns by
salted SHA-256 hash of the filename stem (D009), which is a pure function of the
stem and the fixed salt `certain-road-v1` — independent of what else is in the
training set. Extraction and conversion of the six new countries (this task) added
zero new India stems and touched no existing `data/processed/india` files, so
India's split cannot have changed; the split-redesign work that actually re-runs
`build_splits` against the combined stem set is separate follow-on work, not part
of this task, and must re-verify the same India counts (train 4,617 / val 757 /
calib 1,548 / test 784) before proceeding — if any differ, that is a bug to stop
and report, not an expected consequence of adding countries.

**Ablation reference:** the India-only baseline (mAP50 0.4238, mAP50-95 0.1791,
epoch 84) is preserved at `runs/detect/models/yolo/india_v1/` specifically so the
multi-country run can be compared against it later. That directory is not touched
by this decision or by the extraction/conversion work that accompanies it.

**Scope of this entry:** records the design decision and the now-extracted,
converted, seven-country label corpus (`docs/datasets/multicountry-summary.md`).
It does not itself change `configs/dataset/rdd2022_india.yaml`, does not run
`dataset split` against the combined stem set, and does not launch training —
those are separate, later steps.

## D042 — YOLOv8s over v8n for the multi-country run; combined before/after vs. india_v1

**2026-08-14 · Accepted**

D041 extended the detector's training set to all seven RDD2022 countries but kept
`india_v1`'s YOLOv8n model. Two facts argue for moving to YOLOv8s at the same time:
the merged train set is 7.6x larger (35,296 vs 4,617 images, D041), so a
higher-capacity backbone has enough data to actually use; and v8n's original
justification — edge deployment on a Jetson (D001) — has weakened, since the
Jetson was never approved and no procurement is scheduled. A model sized for a
board that does not exist is optimizing for the wrong constraint.

**Decision:** the multi-country run trains YOLOv8s (11.1M params, 28.6 GFLOPs at
`imgsz=640`), not YOLOv8n (3.01M params). `configs/train/yolov8s.yaml` carries the
new hyperparameter set; `configs/train/yolov8n.yaml` (india_v1's config) is
untouched.

**This is a combined change, and must be reported as one.** Model capacity and
training data both change at once — v8s instead of v8n, and 7.6x the training
images. Any comparison against `india_v1` (mAP50 0.4238, mAP50-95 0.1791, epoch
84) is therefore a combined before/after of *both* factors together. It must never
be attributed to "more data" alone or "a bigger model" alone — no ablation isolates
the two (a v8s-on-India-only or v8n-on-multi-country run was not budgeted), so any
delta reported against `india_v1` is scoped as "capacity + data, combined" in the
thesis and in the dashboard, not decomposed into a per-factor contribution that
this experiment design cannot support.

**Epoch sizing, measured not guessed.** A 2-epoch smoke test
(`uv run certain-road detect train --config configs/train/yolov8s.yaml --country
multicountry --smoke`) ran to completion against the real 35,296-image merged
train set on MPS, batch 16: epoch 1 took 1661.73s, epoch 2 took 1529.24s, mean
1595.48s = 26.591 min/epoch. Target wall-clock for the full run is ~12h (this
machine's other constraints — see D025 — still favour same-day-or-next-day
turnaround over an open-ended multi-day run):

```
720 min / 26.591 min/epoch = 27.08 epochs -> epochs = 27
27 * 26.591 min = 717.9 min ≈ 11.97 h
```

27 sits inside the mandated floor-20/ceiling-40 bound. `patience = round(27 / 3) =
9`. `close_mosaic: 5` (unchanged from the initial config). At batch 16 the merged
set is 2,206 steps/epoch (35,296/16) against India's 289 (4,617/16, rounded up);
27 epochs here is `27*2,206 = 59,562` total gradient steps versus `india_v1`'s
`100*289 = 28,900` — **~2.06x**, above the ~1.5x/20-epoch floor because the
measured per-epoch cost allows more, per the instruction to prefer more epochs
when the measurement supports it rather than stopping at the floor.

**Full run launched:** `runs/detect/models/yolo/multicountry_v8s/`, log at
`runs/logs/train_multicountry_v8s.log`. Full arithmetic and verbatim launch output
in `.superpowers/sdd/2026-08-06-week-1-foundation/v8s-launch-report.md`.

**india_v1 is preserved, untouched, as the reference point** (D041) — this
decision does not retrain or overwrite it.

## D043 — multicountry_v8s continued 23 epochs from existing weights, low-LR, no resume

**2026-08-15 · Accepted**

The 27-epoch `multicountry_v8s` run (D042) completed its full 11.6h wall-clock
budget, but it was **truncated by a time-budget-sized epoch count, not
converged**: mAP50-95 landed on the final epoch (27/27) with the early-stop
counter at 0/9, and it rose monotonically across the last five epochs (0.1979 ->
0.2025 -> 0.2065 -> 0.2090 -> 0.2105). D042's epoch count was sized to a ~12h
wall-clock target, not to convergence — the right lesson going forward is that
epochs should be sized generously and `patience` should decide the stopping
point, not a clock. This run puts that into effect: it continues training toward
an effective 50 epochs total (27 already done + 23 more) with `patience: 15`
generous enough that the run is expected to actually converge and stop on its
own before exhausting 23 epochs, rather than being cut off again.

**A true resume was impossible.** `resume=True` requires optimizer state, an
epoch counter, and LR-schedule position from the checkpoint. Both `best.pt` and
`last.pt` from the finished run have `epoch: -1` and stripped optimizer state
(ultralytics strips it on normal completion), and `save_period: -1` meant no
per-epoch checkpoints were kept along the way. There is nothing to resume from.

**Decision:** `configs/train/yolov8s_continue.yaml` starts a **new** training run
that loads `runs/detect/models/yolo/multicountry_v8s/weights/last.pt` as plain
pretrained weights (`last.pt`, not `best.pt` — `last.pt` is the true end state of
the finished optimisation trajectory; this run's own best/last are epoch 27's
best anyway) and trains it 23 further epochs, writing to a **new** directory,
`runs/detect/models/yolo/multicountry_v8s_ext/`, so the original run's
`weights/` are never touched.

**The low-LR continuation, and why.** The finished run used ultralytics' default
linear LR decay from `lr0=0.01` down to `lr0*lrf=0.0001` over its 27 epochs. A
fresh run started at the config default `lr0=0.01` would re-warm the model to
full learning rate and knock it backwards, destroying most of the 11.6h already
invested chasing a lower loss. `yolov8s_continue.yaml` instead sets `lr0: 0.001`
and `warmup_epochs: 0`, picking the schedule up near where the prior run ended
rather than restarting it — an order of magnitude above the prior run's terminal
~0.0001 (headroom to keep making progress against the still-rising mAP50-95),
and two orders of magnitude below the original `lr0=0.01` (no backslide). All
other hyperparameters (`device: mps`, `imgsz: 640`, `batch: 16`, `seed: 0`,
augmentation) are unchanged from `configs/train/yolov8s.yaml`.

**`optimizer` must be pinned explicitly, or the low-LR config is silently
void.** The first launch attempt of this run was killed within its first
epoch: ultralytics' default `optimizer: auto` unconditionally *discards*
whatever `lr0`/`momentum` the config sets and substitutes its own heuristic —
logged as `'optimizer=auto' found, ignoring 'lr0=0.001' and 'momentum=0.937'`,
resolving to `MuSGD(lr=0.01, momentum=0.9)` — which is exactly the
full-LR restart this entire config exists to prevent. `optimizer: MuSGD` (the
same optimizer class the finished run's own `optimizer=auto` had resolved to,
since `iterations > 10000` at this train-set size) and `momentum: 0.9` are now
pinned explicitly in `yolov8s_continue.yaml` so the configured `lr0=0.001`
actually takes effect. Caught by reading the launch log before letting the
run proceed, per this task's own instruction to confirm the reported LR is
~0.001 rather than ~0.01 — recorded here because it is a real trap in any
future continue-from-weights config, not specific to this run.

**`detect train`'s `model:` config value now accepts a filesystem checkpoint
path, not just a bare ultralytics model name.** Ultralytics resolves a relative
model path against the process cwd (`check_file`), never the repo root — the
same class of bug D040 already fixed for the data yaml's `path:`.
`certain_road.detect.train.resolve_model_path` now resolves a `model:` value
containing a path separator against `repo_root()`, and leaves a bare name (e.g.
`yolov8s.pt`) untouched so ultralytics can still resolve or download it itself.
Covered by three new cases in `tests/test_train_config.py`.

**Starting point, measured before continuing.** Before launching the extended
run, `last.pt` was verified as the intended checkpoint (fused: 130->73 layers,
**11,126,745 parameters**, `nc=3`) and evaluated on the India **test** split
(784 images, `calib`/`test` never seen by training, D009): **mAP50 = 0.4220,
mAP50-95 = 0.1857** — matches the pre-registered expectation (~0.4220 /
~0.1857). This is the definite before-number the extended run is measured
against.

**Honest scope: this is a continuation, not a clean 50-epoch run.** Because the
LR schedule was restarted at a low value rather than continuing ultralytics'
own decay curve exactly, and because the optimizer momentum/state was lost at
the boundary, the resulting model is **not identical to a single run trained 50
epochs from scratch** — there is a discontinuity in the LR trajectory and a
reset of optimizer state at epoch 27. Any report of the final numbers must
describe this as "27 epochs + a 23-epoch low-LR continuation, ~50 effective
epochs," never as "a 50-epoch run," and must not assume the two are
interchangeable.

**Full run launched:** `runs/detect/models/yolo/multicountry_v8s_ext/`, log at
`runs/logs/train_v8s_continue.log`. `runs/detect/models/yolo/multicountry_v8s/`
is untouched and preserved as the pre-continuation reference point.

## D044 — Detector eval harness: predictions remapped onto our taxonomy, not labels; D00+D10 merge extended to predictions

**2026-08-15 · Accepted**

The project cannot yet compare its own detector against external RDD2022
models: there is no inference path, and external models use CRDDC2022's
four-class taxonomy (`D00` longitudinal, `D10` transverse, `D20` alligator,
`D40` pothole) while ours is the frozen three-class set from D038
(`linear_crack`, `alligator_crack`, `pothole`). The indices do not align —
external class `2` is alligator crack, ours is pothole — so scoring an
external model's raw output against our labels would silently score potholes
against alligator cracks and produce plausible-looking, wrong numbers.

**Decision:** remap happens on **predictions**, not labels, and it is a pure
relabel — boxes are never combined, deduplicated, or NMS'd across the merge.
`configs/eval/class_maps.yaml` defines two named maps: `identity_3class` (a
no-op, for our own models) and `rdd2022_4class`, which sends `D00 -> 0`,
`D10 -> 0`, `D20 -> 1`, `D40 -> 2`. `D00` and `D10` both collapsing onto
`linear_crack` **extends D038's label-side merge to predictions**, for the
same ASTM D6433 reason: longitudinal and transverse cracking share one deduct
curve, so evaluating them as separate classes would penalise a correct
call as a misclassification. `certain_road.detect.predict.remap_class_ids`
raises `ValueError` naming the offending id if a prediction's class is absent
from the map — silently dropping an unmapped class is exactly the failure
this decision exists to prevent.

**`certain_road.detect.predict.predict_to_detections`** is the first
inference path the project has had: weights + an image directory in,
a `DetectionRow`-conformant frame out, with the class map applied before
return. The ultralytics-calling code (`_raw_predictions`) is kept separate
from the remap/schema logic so the latter can be unit-tested without a
trained model — the automated suite never invokes a real detector. Wired onto
the existing stage as `certain-road detect predict`, not a parallel app.

**Confidence floor is a separate config from the operating-point sweep.**
`configs/eval/thresholds.yaml` sets `map_conf_floor: 0.001` (mAP integrates
the whole precision-recall curve; raising the threshold truncates it and
depresses mAP artificially, it does not "tune" it) and
`operating_thresholds: [0.10, 0.15, 0.20, 0.25]` for precision/recall/F1
sweeps at evaluation time (Task 3, not yet implemented). `detect predict`
defaults its own `--conf` to `map_conf_floor` so one prediction pass at the
low floor serves both purposes; the operating sweep filters scores after the
fact rather than re-running inference at each threshold.

**Scope: Tasks 1–2 of the harness only.** `detect eval` (mAP/operating
metrics), the harness-validation check against the known 0.4220 mAP50, the
current-model benchmark, and the candidate registry are follow-on tasks in
the same plan (`docs/superpowers/plans/2026-08-15-detector-evaluation-harness.md`)
and are not part of this decision. No training was run and no candidate
weights were downloaded to implement this.

## D045 — Detector eval harness metrics: `ultralytics.utils.metrics`, not `torchmetrics`; Task-4 divergence traced to `model.val()`'s `rect=True` default

**2026-08-15 · Accepted**

**Metric-implementation decision.** The plan's Task 3 suggested `torchmetrics.
detection.MeanAveragePrecision`; that suggestion was not binding, and the
plan's own Task 4 constraint — the harness must reproduce
`model.val()`'s pre-registered mAP50 ≈ 0.4220 / mAP50-95 ≈ 0.1857 for
`multicountry_v8s` within ±0.01 — made `torchmetrics` the wrong choice.
`torchmetrics`'s detection metric is backed by `pycocotools` (or
`faster_coco_eval`), an independently-coded implementation with its own IoU-
matching, IoU-threshold sweep, and IoU-envelope-interpolation conventions. A
correct implementation from a different codebase can legitimately differ from
ultralytics' own number by more than ±0.01 purely from those conventions,
which would make a harness bug indistinguishable from an implementation
difference — precisely the ambiguity Task 4 exists to rule out. Comparability
to the pre-registered number, and later to published ultralytics-based
RDD2022 benchmarks, requires reusing ultralytics' own machinery.

`certain_road.detect.evaluate.compute_map` therefore imports
`ultralytics.utils.metrics.box_iou` and `ap_per_class` unmodified — the same
two functions `model.val()` calls internally to build its PR curve and
integrate AP. The one piece that could not be imported directly,
`BaseValidator.match_predictions`'s greedy IoU matching, is an instance
method requiring a live validator; `_match_predictions` in `evaluate.py` is a
standalone re-implementation of that same algorithm, not a new one, so it can
run over a plain DataFrame pair instead of a dataloader. No third-party
mAP dependency was added.

**Task 4 result: the harness does not reproduce 0.4220 within ±0.01, and the
harness was not tuned to force it to.** Running `certain-road detect eval`
on `multicountry_v8s/weights/best.pt` over the India test split (784 images,
330 positive, 454 empty, `identity_3class`) measured **mAP50 = 0.3932,
mAP50-95 = 0.1662** — a divergence of **-0.0288 mAP50 / -0.0195 mAP50-95**
from the pre-registered 0.4220 / 0.1857, outside tolerance.

**Root cause, isolated and confirmed, not assumed.** Four diagnostics ruled
candidates in or out in order:

1. **Checkpoint identity.** `best.pt` and `last.pt` were suspected first,
   since D043's 0.4220 number was measured against `last.pt` and Task 4 asks
   for `best.pt`. Running ultralytics' own `model.val()` directly on
   `best.pt` reproduced **0.4220305393408599 / 0.18573762572421756** exactly
   — bit-for-bit the same as D043's `last.pt` number. The checkpoint choice
   is not the cause.
2. **`multi_label` NMS default.** `DetectionValidator.postprocess` (used by
   `model.val()`) calls `non_max_suppression(..., multi_label=True)`
   explicitly; `DetectionPredictor.postprocess` (used by `model.predict()`,
   which `predict_to_detections` calls) does not pass `multi_label`, so it
   defaults to `False`. Monkeypatching `predict_to_detections`'s underlying
   NMS call to force `multi_label=True` changed raw detection count
   (41,595 → 46,484) but moved mAP50 by only +0.0009 (0.3932 → 0.3941).
   Ruled out as the dominant cause.
3. **Per-image coordinate comparison.** Capturing the top-10 boxes for one
   positive image (`India_000027`) from both pipelines showed `model.val()`'s
   top box measurably offset (~20-50px on a 720px image) from both the
   ground-truth box and `model.predict()`'s corresponding box, despite
   near-identical confidence and class.
4. **Preprocessed tensor shape — the actual cause.** Hooking both
   pipelines' `preprocess` methods for that image showed `model.val()`
   feeds the model a **(16, 3, 672, 672)** batch tensor (`ratio_pad =
   (0.888…, 0.888…)`, `pad = (16, 16)`), while `model.predict()` feeds a
   **(1, 3, 640, 640)** tensor for the same `imgsz=640` request. `model.val()`
   defaults to **`rect=True`** (rectangular/stride-rounded batch inference);
   `model.predict()` always uses a plain square letterbox. Confirmed
   conclusively by re-running `model.val()` with `rect` forced both ways on
   the same weights/data: **`rect=True` → mAP50 0.4220 / mAP50-95 0.1857**
   (the reference); **`rect=False` → mAP50 0.3937 / mAP50-95 0.1661** —
   matching the harness's independently-measured 0.3932 / 0.1662 to within
   0.0005, i.e. within the residual noise already explained by (2).

**Conclusion.** `compute_map` correctly reproduces ultralytics' own AP
algorithm — proven by matching `model.val(rect=False)` almost exactly, and by
independently reproducing a non-obvious quirk of `ap_per_class` (a perfect
detector saturates at AP 0.995, not 1.0, under 101-point interpolation;
verified directly against `ultralytics.utils.metrics.compute_ap`). The 0.029
mAP50 gap is entirely attributable to `predict_to_detections` (D044, Task 2)
calling `model.predict()`, whose square-letterbox preprocessing at
`imgsz=640` is not equivalent to `model.val()`'s default rectangular-batch
preprocessing at the same nominal `imgsz`. This is a real, understood
divergence in inference preprocessing, not a bug in the metric computation,
and per the plan's explicit instruction it is reported as such rather than
closed by tuning the harness (e.g. by switching to `model.val()` internally,
which would silently reintroduce the exact per-model-source coupling D044
was written to avoid) until the number matched. Whether `predict_to_detections`
should adopt rect-style preprocessing to raise fidelity to `model.val()` is
left as an open question for whoever picks up Task 5/6 or a future revision
of D044 — not resolved unilaterally here.

## D046 — Timeline fixed to 7 dated weeks (2026-08-17 → 2026-10-05); shift sweep cut; detector freezes 2026-08-30

**2026-08-16 · Accepted · Refines D025**

D025 cut the timeline from 16 weeks to 8 but never anchored it to dates. The real
window is **2026-08-17 to 2026-10-05 — 49 days, exactly 7.0 weeks.** Week 1 of the
8-week plan is complete, so seven weeks of planned work remain against seven weeks of
calendar, with **zero buffer** and with the detector work added after D025 (the
evaluation harness, D044/D045, plus candidate benchmarking) not accounted for at all.

**Three structural facts resolve the shortfall.**

1. **Detector work is GPU-bound, not developer-bound.** Runs 3 and 4 are unattended
   overnight compute; only ~2.5 days of remaining detector work is attended. Training
   therefore runs in parallel with pipeline development rather than consuming a week.
   This is the sole reason the scope fits.
2. **Blockers 1–3 close on day 1 or not at all.** Deduct curves block `assess` in week
   1; the PCI→RSL citation blocks `rsl`; the three raters must be booked on 2026-08-17
   for a week-3 session. The rating session is the one deliverable that more effort
   cannot compress.
3. **The detector freezes 2026-08-30, end of week 2.** Changing weights after that
   invalidates `q̂`, the coverage table and the band-agreement analysis simultaneously.
   Candidate selection and benchmarking must therefore complete inside weeks 1–2.

**Cut: the synthetic distribution-shift sweep**, and with it Result 4. This is D025's
own designated first cut and D031 had already narrowed it to 2–3 corruptions. Results
1 (coverage), 2 (policy impact) and 3 (validation) all survive.

**Contingency ladder, in order:** sensitivity sweep → policy Axis 2 → Decision Replay
panel → the dashboard map. **Never cut** the validation study (D027) or the coverage
table — the first is the only evidence the central quantity is meaningful, the second
is Result 1.

Full dated schedule with per-week done-when conditions and the hard-date table:
[`superpowers/plans/2026-08-16-seven-week-schedule.md`](superpowers/plans/archive/2026-08-16-seven-week-schedule.md).

D025 is **not** superseded: its scope cuts (India subset, ONNX-instead-of-Jetson,
normalized CP to future work) all stand. Only its week count and undated framing are
replaced.

## D047 — Jetson + GPS brought into scope as a 3-week partition sequenced last; 4-partition schedule 2026-08-18 → 2026-10-05

**2026-08-17 · Accepted · Refines D046, reverses D025's hardware reduction**

D025 reduced Jetson deployment to "ONNX export plus latency benchmark" because the
hardware was never approved, and D046's 7-week schedule contained no hardware work at
all. The project owner has now asked for edge deployment — Jetson Orin Nano, CSI camera,
u-blox GPS — planned as real work with roughly three weeks allocated.

**Schedule: four partitions over 48 days (≈7 weeks), 2026-08-18 → 2026-10-05.**

| Partition | Weeks | Dates | Content |
|---|---|---|---|
| P1 | 1–2 | Aug 18–31 | Research core: `assess`, conformal, coverage table, detector freeze |
| P2 | 3–4 | Sep 1–14 | Decision layer + validation: raters, `rsl`, knapsack, policy impact |
| P3 | 5–7 | Sep 15–Oct 5 | Edge deployment: Jetson, camera, GPS, `ingest`, ONNX/TensorRT, real capture |
| P4 | 1–7 | Aug 18–Oct 5 | Dashboard + thesis, written continuously rather than terminally |

**The load-bearing decision is the ordering: hardware is sequenced LAST.** All three
thesis results are complete and frozen by Sep 14, before the Jetson is touched. Hardware
slip, DOA units, customs delay or non-approval then cost the *deployment chapter* only,
never the thesis. Sequencing hardware earlier would put a procurement risk on the
critical path of the degree, which is not an acceptable trade for a demonstration.

**`ingest` becomes real work.** It was unscheduled in D046 because a photo dataset has no
video to ingest. A camera and GPS track make it a genuine component — video + NMEA fixes
→ distance-sampled frames → evaluation segments — so it holds a full week inside P3
rather than being absorbed into hardware bring-up.

**Paid for by:** the sensitivity analysis (D029) is **cut**, joining the already-cut shift
sweep (D031); the dedicated dashboard week and dedicated write-up week are dissolved into
the continuous P4. **Not cut:** the validation study (D027) and the coverage table.

**Procurement gate.** Nothing in P3 is achievable without hardware in hand by Sep 15, so
the order must be placed 2026-08-18 with approval secured at that day's mentor meeting.
If hardware is not present by **Sep 22**, P3 reverts to D025's original degraded chapter —
ONNX export, MPS latency benchmark, a simulated GPS track over recorded dashcam video,
architecture documented rather than demonstrated. That call is made on Sep 22, not in
October.

Full schedule with per-week done-when conditions and the hard-date table:
[`superpowers/plans/2026-08-16-seven-week-schedule.md`](superpowers/plans/archive/2026-08-16-seven-week-schedule.md).

## D048 — Jetson arrives 2026-08-18: risky bring-up pulled into a bounded weeks-1–4 parallel track; only `ingest`+`detect` ship to the edge

**2026-08-17 · Accepted · Refines D047**

D047 sequenced hardware last because the dominant risk was **procurement**. The board now
arrives 2026-08-18, which closes that risk and replaces it with **integration** risk —
the opposite kind, since integration failures are cheap to find early and unrecoverable
to find late.

**P3's dates do not move.** Its deliverables genuinely need a frozen detector (Aug 31) and
a finished pipeline (Sep 14), so the demonstration stays in weeks 5–7. What moves earlier
is everything that can fail *independently* of the pipeline: flashing, on-device runtime,
camera driver, GPS/NMEA, and the ONNX→TensorRT export path — pulled into a **bounded
parallel track across weeks 1–4, timeboxed to one half-day per week plus unattended
downloads, which never displaces P1 or P2.** A task exceeding its box is parked and
carried into P3. The failure mode being guarded against is hardware stealing focus from
the coverage table.

**The export path is proven in week 2 against the *current* `multicountry_v8s` weights**,
so that the Aug 31 freeze is followed by re-running a known-good path rather than
debugging one under deadline. A **pilot capture drive in week 3** then yields the real
video and GPS track that `ingest` is built against in weeks 3–4, surfacing mounting,
vibration, exposure and time-sync problems while there is still time to fix them.

**Three day-1 verifications can invalidate P3 and are therefore done first:** board
identity (a legacy 2019 Jetson Nano is EOL at JetPack 4.6 / Python 3.6 / 4 GB and cannot
carry this stack, unlike the assumed Orin Nano); camera driver enumeration (JetPack
officially supports IMX219/IMX477 — the Pi Camera Module 3's IMX708 is **not** officially
supported, so an unsupported sensor must be swapped in week 1, not September); and the
fact that **TensorRT engines are device- and version-specific and must be built on the
Jetson**, never exported from the Mac.

**Deployment surface, and why the architecture already permits it.** JetPack ships Python
3.10 (JetPack 6 / Ubuntu 22.04), not the 3.12 this project pins, so `uv sync` of the whole
project on-device is explicitly *not* the deployment path. It is unnecessary: stage
isolation (D003) means the edge device need only emit the two artifacts the rest of the
pipeline consumes, so **only `ingest` and `detect` run on the Jetson** — against a
TensorRT engine and a Parquet writer, a dependency surface small enough to tolerate Python
3.10 without touching the pin. `assess` onward stay on the Mac, reading the two copied
Parquet files. This is the stage-isolation contract paying for itself rather than a
workaround.

**The fallback becomes an integration gate, decided by Sep 7** (legacy board, no camera
driver obtainable within a week, or runtime not working), reverting to D025's degraded
chapter. Deciding on Sep 7 rather than Sep 22 is possible precisely because the parallel
track has already answered the question by then.

## D049 — Project pivots to an autonomous road-inspection robot; perception feeds two independent pipelines; control transport is abstract

**2026-09-05 · Accepted · Refines D001, supersedes the passive-survey framing**

The deliverable changes from a passive camera survey to a **mobile robot that acts on what
it sees**: it detects a pothole, decides whether the pothole lies in its own driving path,
avoids it through commanded steering, and *simultaneously* records road-damage data for the
existing condition-assessment pipeline. Demo date **2026-09-20**; the 2026-10-05 date from
D046 survives for the survey and thesis work, so nothing is cut — only resequenced.

**The architectural rule.** One detector feeds **two pipelines that never touch**:

- **Drive** — "what should the robot do right now?" — corridor test, state machine, motor command.
- **Survey** — "what do we know about this road, and how certain are we?" — segment, vision-estimated PCI, conformal interval, human review.

**Conformal prediction is never in the steering loop.** Real-time avoidance needs immediate
perception; CP applies to the slower condition estimate. `import-linter` enforces it:
`driving/` and `canbus/` may not import `survey/`, and `survey/` may not import `driving/`.
If CP ever creeps into the steering path, CI fails.

**The control transport is abstract, and this is what saves the schedule.** No CAN hardware
exists — the Orin Nano has CAN controllers on its 40-pin header but no transceiver, and the
robot side needs an MCU to translate CAN to PWM. Both are procurement items on the critical
path of a 15-day sprint. So `decision.py` emits a `Command` to a `Transport` interface with
three implementations: `SerialTransport` (works day 1, no new hardware), `CanTransport`
(when parts arrive), `NullTransport` (bench tests). **CAN becomes a one-module swap rather
than a rewrite**, and the robot moves on day 2 regardless of shipping.

**Repository restructure.** `detect/` → `perception/` (all 1,138 lines reused unchanged);
the five empty stage stubs become `survey/` modules; `driving/` and `canbus/` are new.
Named `canbus/` and not `can/` because `python-can` owns the top-level `can` module.
Nothing is deleted — superseded plans move to `plans/archive/`, matching the decision log's
append-never-delete rule.

**Where work runs, restated because ignoring it causes most integration pain.** All
training, dataset work, PCI, conformal and dashboard development happen on the MacBook;
the Jetson does camera, live inference, control and recording. **TensorRT engines are
device-specific and must be built on the Jetson** (D048). Every `driving/` module is pure
logic over a `Detection` list, so it is developed and unit-tested on the MacBook against
synthetic detections — the Jetson is needed only to run it.

**Priority order, not to be reversed:** control link → camera → YOLO on device →
pothole-in-path → avoidance → safety STOP → survey recording → PCI → conformal → dashboard
→ measurement. A dashboard on a robot that cannot move is a failed robotics product.

Full day-by-day plan, per-task done-when conditions, the MacBook/Jetson split table and the
risk register: [`superpowers/plans/2026-09-05-robot-sprint.md`](superpowers/plans/2026-09-05-robot-sprint.md).

## D050 — Simulator is a fourth `Transport`; robot for the demo, simulation for the trial matrix

**2026-09-05 · Accepted · Refines D049 · Refined by D096 (Gazebo)**

Both are built and neither replaces the other: the **robot demonstrates the concept live**,
the **simulator produces the repeatable trials and the measurement table**.

This costs very little because D049 already made the control transport abstract. The
simulator is a fourth implementation alongside `SerialTransport`, `CanTransport` and
`NullTransport`, so `corridor.py` and `decision.py` **cannot tell simulation from hardware**.
Whatever avoids a pothole in simulation is the identical module that avoids one on the robot
— not a reimplementation.

**Design:** recorded road video → real YOLO → real corridor test → real state machine →
`SimTransport` → bicycle-model robot on a 2D top-down view. Genuine detections driving
genuine decisions; only actuation is synthetic.

**Rejected: Gazebo, Isaac Sim, CARLA.** All want a serious NVIDIA GPU, none run well on the
MacBook, and setup alone would consume 3–5 of 15 days with real failure risk.

**Three reasons it earns its place.** It is the test harness Days 5–6 need anyway, so it
costs hours rather than a day. It produces Day 14's ≥20 presentations, which staged
physically are slow, inconsistent and unrepeatable — in simulation they are deterministic and
assertable in CI. And it unblocks Days 5–8 from hardware entirely while the Jetson is being
flashed and CAN parts are in transit.

**What it cannot test, and must not be claimed to:** motion blur, vibration, lighting change,
real command latency, real actuator dynamics.

**Reporting rule:** simulated and physical trials are reported in **separate columns**.
Simulated trials are never presented as physical ones. Day 8 requires the exhaustive matrix
in simulation *and* the four stageable cases on the robot — simulation proves coverage,
hardware proves the simulation matches reality, and neither alone is sufficient.

**Demo framing:** robot first, simulator second, presented as how scenarios that could not be
staged physically were validated. In that order it reads as rigour; reversed it reads as
avoiding the hard part.

`sim/` is a composition root like `cli.py`: it may import `driving/` and `canbus/`, never
`survey/`.

## D051 — CP cut from the sprint; survey ends at vision-estimated PCI; ADAS-inspired behaviours added

**2026-09-05 · Superseded by D085 · Refines D049, D050**

The Sep 20 sprint focuses on **autonomous pothole avoidance plus road surveying**. Conformal
prediction is **cut from the 15-day scope**.

**What this costs, stated plainly.** CP was the research novelty (D004, D005). Without it the
project is *a robot that avoids potholes and estimates road condition* — good engineering,
thin as research. The abstain path degrades from a **calibrated coverage guarantee** to a
**confidence heuristic**: honest, still a genuine safety behaviour, but a materially weaker
claim that must never be described as conformal coverage.

**What is preserved so the cut is reversible.** The four-way split, the calibration firewall
and `pci_ref` all stand. `calib` stays untouched and unused. CP can return in the
**Sep 21 → Oct 5** window without touching the robot, because D049 already forbids CP from the
steering loop — the drive pipeline never depended on it.

**Detector consequence.** With CP out of sprint scope, a pretrained RDD2022 model becomes
technically viable for the sprint, since calibration contamination only matters for CP.
**We keep `multicountry_v8s` anyway**: it is already trained (zero additional cost), its
taxonomy matches the pipeline, and swapping detectors would spend sprint days for an unmeasured
gain. Candidate benchmarking moves to the Oct 5 window, where it belongs if CP returns.

**ADAS framing — bounded deliberately.** Parity with production ADAS is **not claimable**:
ISO 26262 / ASIL certification, multi-sensor fusion, million-kilometre validation, redundancy
and hard sub-100 ms timing are all absent. What *is* claimable is an **ADAS-inspired decision
architecture** at prototype scale. Three behaviours are added to make that real rather than
rhetorical:

1. **Temporal confirmation (N-of-M)** — a detection must persist across frames before it can
   trigger a manoeuvre. The highest-value reliability addition in the sprint: without it a
   single-frame false positive makes the robot swerve at shadows during the live demo.
2. **Confidence gate** — a high threshold to *intervene*, a lower one to *record for the
   survey*. Two thresholds, one detector.
3. **Proximity-based urgency** — trigger on how near the hazard is, not merely that it exists,
   using bounding-box height as a distance proxy. Far → `WARNING`; near → `AVOID`.

All three are pure logic, developed on the MacBook and exercised in the simulator, and are
**excluded from the contingency ladder** — they cost hours and they are what stop the demo
misbehaving.

## D052 — Deliverable is a vehicle-agnostic control unit, demonstrated on the Jetson

**2026-09-06 · Accepted · Refines D049, D050, D051**

The demonstration is no longer a specific robot driving. It is the **Jetson Orin Nano running
the full chain end to end**: recorded road video → real YOLO → real corridor and state machine
→ **real CAN frames** — with the decision core designed to drop onto any vehicle.

**Why this is better, not a retreat.** It removes every uncertain hardware dependency from the
critical path at once:

| Was blocking | Status for the Sep 20 demo | If it returns |
|---|---|---|
| Lab robot ("beetle bot", availability uncertain) | **deferred** | new `Transport` subclass, or reuse `CanTransport` if it speaks CAN |
| Pi Camera Module 3 / IMX708 not JetPack-supported (D048) | **deferred** — video playback instead | swap the frame source; everything downstream is unchanged |
| CAN transceiver not ordered | **deferred** — `vcan0` instead | one config line, `vcan0` → `can0` |

**Deferred, not eliminated.** Each of these is expected to return, and the architecture is
shaped so that each returns as a *swap* rather than a rewrite — that is the whole reason the
frame source and the transport are abstractions. What changes is which implementation is
configured, never the decision logic between them.

The only hardware that must work **for this demo** is the Jetson itself.

**Real CAN with no transceiver.** Linux ships SocketCAN with a virtual interface. On the
Jetson, `modprobe vcan` plus two `ip link` commands creates `vcan0`, and `CanTransport` writes
**genuine CAN frames** to it — observable live with `candump vcan0` during the demo. These are
real frames on a real socket, not a mock. When a transceiver arrives, `vcan0` → `can0` is a
**configuration change, not a code change**, which is precisely what D049's transport
abstraction was built for.

**The claim, bounded.** "Runs on any vehicle" is too strong and invites one question that
collapses it. What is generic is the **decision core** and the command semantics
(`action / speed / steer / mode`). What is vehicle-specific is the **CAN message layout** —
arbitration ID, byte packing, scaling — which differs per vehicle and is described by that
vehicle's DBC. The defensible claim is therefore:

> a **vehicle-agnostic decision core plus a thin per-vehicle CAN adapter**

not "works on any vehicle unmodified". That is how real automotive middleware is structured,
so it is a strength rather than a hedge.

**Development constraint.** SocketCAN is Linux-only, so `CanTransport` **cannot be tested on
the MacBook at all** — only on the Jetson. Everything else (corridor, confirmation, state
machine, simulator) stays fully testable on the Mac, which is why those were built first.

**The honest cost.** Nothing physically moves *at this demo*. The robotics claim shifts from
"an autonomous vehicle" to "an edge-deployed, vehicle-agnostic control unit" — accurate,
defensible, and narrower. The physical vehicle, the live camera and the transceiver are all
expected back; each is a configured implementation swap, which is the point of the
abstraction and should be stated that way rather than as scope that was dropped.

## D053 — External RDD2022 weights rejected: they cannot be measured

**2026-09-06 · Accepted**

`rezzzq/yolo12s-road-damage-rdd2022` (MIT, 9.26 M params) was benchmarked against
`multicountry_v8s` on the 784-image held-out India test set, through the identical harness.

| model | mAP50 | mAP50-95 |
|---|---:|---:|
| ours | 0.3932 | 0.1662 |
| external v12s | **0.9765** | 0.7221 |

**0.9765 is not a performance result.** It indicates evaluation on training data. A separate
published benchmark measured the same architecture on RDD2022 India at **0.2808** using a
held-out split; the CRDDC'2022 winning *ensemble* reached F1 0.769 across all six countries.
Our `test` split is carved by salted hash from RDD2022's India training data (D009), so any
model trained on RDD2022 has seen it.

**The weights are rejected — not for being bad, but for being unmeasurable.** Every derived
number would be inflated by an unknown amount with no way to detect it.

**This corrects an understatement in my earlier reasoning.** Contamination was framed as a
conformal-calibration problem, which implied it stopped mattering when CP left the sprint
(D051). It is more basic: it destroys the ability to evaluate the detector at all, regardless
of whether a conformal layer exists.

**Claim it carefully.** Overlap is inferred, not proven — the author publishes no split. The
defensible phrasing is *"performance inconsistent with a held-out evaluation, indicating
probable train/test overlap"*.

**The finding is worth more than the comparison.** This is an empirical instance of exactly
the failure the project exists to prevent: a system that looks excellent, reports confident
numbers, and is silently wrong — caught only because a provenance-controlled test set existed
to check it against. Full write-up:
[`detector-benchmark.md`](detector-benchmark.md).

**Also established:** the model loads on mainline ultralytics 8.4.115 with no YOLOv12 fork,
contrary to its model card; and `rdd2022_5class` drops `Repair` explicitly, since a repaired
area is not distress and counting it as damage would penalise a road for having been
maintained.

## D054 — Workspace cleaned and repo reorganised; redundant weights and data deleted, keepers named explicitly

**2026-09-22 · Accepted**

The working tree had reached 28 GB and the repository's most-read file, `README.md`, was
0 bytes. Both are fixed here. **No decision in this entry changes what the system does** —
it changes what is on disk and what a reader sees first.

### Deleted, each following from an existing decision

| Removed | Size | Follows from |
|---|---|---|
| `data/raw/RDD2022_released_through_CRDDC2022.zip` | 12 GB | already extracted; sha256 recorded in `CHECKSUMS.txt`, re-fetchable via `dataset fetch` |
| `data/raw/water_potholes/`, `data/processed/water_potholes/` | 564 MB | **D039** — NO-GO; the evidence survives in `datasets/water-pothole-viability.md` |
| `runs/…/multicountry_v8s_ext/` | 130 MB | **D043** — killed after one epoch by the LR bug; `_ext2` superseded it |
| `runs/…/multicountry_v8s_smoke/`, `runs/…/india_v1_smoke/` | 66 MB | smoke tests, throwaway by construction |
| `models/candidates/yolo12s_RDD2022_best.pt` | 18 MB | **D053** — rejected as unmeasurable; the *finding* is the artifact worth keeping, not the weights |
| `runs/detect/val*/` (21 dirs, 14 of them empty) | 25 MB | unnamed ultralytics dumps, mutually indistinguishable |
| `yolov8n.pt`, `yolov8s.pt` at repo root | 28 MB | ultralytics re-fetches bare-name checkpoints on demand |
| `runs/…/india_v1/weights/last.pt` | 6 MB | run completed; `best.pt` at epoch 84 is the **D042** baseline |
| `runs/…/india_v8s/` | 1.4 MB | halted before epoch 1, produced no weights |

`runs/logs/*.log` compressed 18 MB → 1.6 MB. Per-epoch metrics already live in each run's
`results.csv`; the logs are console output. `train_v8s_continue_attempt1_lr_bug.log.gz` is
the evidence behind D043 and remains readable via `gzip -dc`.

**28 GB → 15 GB.**

### Preserved deliberately, verified by sha256 before and after

- `multicountry_v8s/weights/best.pt` — the benchmarked model (D042, D043, D053).
- `multicountry_v8s/weights/last.pt` — **must not be removed**: it is the continuation start
  point named in `configs/train/yolov8s_continue.yaml`.
- `multicountry_v8s_ext2/weights/{best,last}.pt` — the paused 12/23-epoch continuation, kept
  whole by owner decision even though it was never measured.
- `india_v1/weights/best.pt` — the D042 baseline, preserved so the v8n→v8s comparison stands.

**`data/raw/RDD2022/` is load-bearing, not a duplicate of the zip.** Every image under
`data/processed/*/images/` is a symlink into it — 46,091 of them, all verified resolving
after the cleanup. Deleting the extraction would silently destroy every processed split.

### Not done, and why

**Weights stay out of git.** Git LFS was considered for shipping `multicountry_v8s/best.pt`
so a fresh clone could run inference without training, and declined: 395 MB of checkpoints in
history is unrecoverable, and `models/`, `runs/` and `data/` remain gitignored.

**`torchvision` and `tqdm` stay in `pyproject.toml`** despite zero direct imports. Ultralytics
pins both, and the explicit torchvision pin guards the torch pairing. Two lines saved is not
worth the breakage risk.

**`docs/superpowers/plans/` stays where it is.** The authoring workflow writes every plan to
exactly that path; relocating it would break the documented pipeline to save nothing at
repository root.

### Documentation

`PROJECT-OVERVIEW.md` is **merged into `MENTOR-WALKTHROUGH.md` and deleted.** It duplicated
the walkthrough on 11 of its 13 sections — its §6.1 mAP ladder appears verbatim as the
walkthrough's §12, and the walkthrough's §15 carries a fuller blockers table. Its two
genuinely unique sections (§6.2 conformal targets, §7 results to report) are built entirely on
the conformal layer that **D051 cut**, so they are dropped rather than ported: carrying
superseded targets forward would be worse than losing them.

Its enforcement-mechanism table was the one thing worth keeping, and moves into §15 **with a
status column added** — three of its seven rows described mechanisms that do not exist
(`configs/assess/curves/`, the `rsl` stage's empty-`source:` refusal, and a run manifest
recording a git SHA). The original table stated all seven as though built.

The design spec is surfaced from `docs/superpowers/specs/2026-08-06-certain-road-design.md` to
**`docs/design.md`**, and the three dataset cards grouped under `docs/datasets/`. Inbound
links in `CLAUDE.md` and in this file were repaired. **Path references inside earlier entries
were updated rather than left broken** — the append-never-rewrite rule protects the *reasoning*
in an entry, not a stale file path within it; no decision text was altered. Three pre-existing
dangling links to the archived seven-week schedule were also fixed.

`README.md` written from empty: what the system decides, the current two-pipeline architecture
(D049/D050/D051) rather than the superseded seven-stage chain, the honest 0.3932 mAP50 with
D053's rejection of the external 0.9765, and a quickstart whose every command was executed to
confirm it exits 0.

Finally, `pyproject.toml`'s description was still uv's `"Add your description here"`
placeholder, and `.gitignore` carried a `!configs/assess/curves/` negation that was doubly
dead — the directory was never created, and `configs/` is not ignored, so it could never have
matched anything.

## D055 — RoadSight spec amended to the frozen three-class merge

**2026-09-22 · Accepted · amends D038**

The RoadSight task specification (T0–T17) sets `classes: {0: D00, 1: D10, 2: D20,
3: D40}` and hard-codes class index `3` as the pothole class in four places. This
repo's taxonomy has been frozen since D038 at the three-class merge. **D038 stands;
the spec is amended to it, not the other way round.**

The spec's own reasoning already points this way: T6 asks for a "3-class mAP
(D00, D20, D40)" and marks any class under 100 GT instances `unreliable`. It
splits `D10` out and then reports around it. D038 merged it for a stronger reason
— **ASTM D6433 treats longitudinal and transverse cracking as one distress type
sharing one deduct curve**, so the merge is more faithful to the standard this
project targets, not a data-balance convenience.

**`pothole_class` replaces every hard-coded `3`.** `configs/project.yaml` carries
`classes: {0: linear_crack, 1: alligator_crack, 2: pothole}` and
`pothole_class: 2`. The four sites that must read it rather than a literal:
`eval_locked`'s pothole-only external evaluation (T9), the BharatPotHole class
remap (T9), the simulation's detection class filter (T13), and conformal
matching (T10). A literal `3` in any of these silently scores potholes against
nothing, since index 3 does not exist in this taxonomy.

**Reference facts for T1, restated merged.** Per country, `linear_crack /
alligator_crack / pothole`:

| Country | linear | alligator | pothole |
|---|---|---|---|
| Japan | 8,028 | 6,199 | 2,243 |
| India | 1,623 | 2,021 | 3,187 |
| Czech | 1,387 | 161 | 197 |
| Norway | 10,300 | 468 | 461 |
| United_States | 10,045 | 834 | 135 |
| China_MotorBike | 3,774 | 641 | 235 |
| China_Drone | 2,689 | 293 | 86 |

Six of the seven match this repo's converted labels exactly. **Japan's
`alligator_crack` converts to 6,198, not 6,199** — one instance, 0.016%, inside
T1's 1% tolerance. The likely cause is a degenerate or out-of-bounds box dropped
during VOC→YOLO conversion; T1's raw audit is the task that identifies it, and
the discrepancy is recorded here rather than resolved by picking a number.

T1's **raw** four-class check is unchanged. It audits the source XML before any
merge, so it must keep counting `D00`, `D10`, `D20` and `D40` separately — that
is what makes the merge auditable rather than assumed.

**Primary metric is 3-class mAP over the merged classes**, and this is *not* the
spec's 3-class mAP. The spec excludes `D10` from a four-class set; this averages
`linear_crack` (D00+D10), `alligator_crack` and `pothole`. The two numbers are
not interchangeable and the report must define which it is at the point of use.

The spec's "D10 unreliable, under 100 GT instances" note is replaced by: **"D00
and D10 are merged into `linear_crack`; India has only 68 D10 instances"** —
which is the fact that motivated the merge (D037's census), not a caveat on a
class this taxonomy contains.

`scoring.deduct_weights` becomes `{linear_crack: 8, alligator_crack: 20,
pothole: 30}`. The spec's `D00: 8, D10: 8` collapse to a single weight of 8,
which is consistent: the two classes shared a weight precisely because they
share an ASTM deduct curve.

**Existing weights are not reusable on trust.** Before any checkpoint is adopted
as Model A, its `args.yaml` and training data lists must show it was trained from
COCO `yolov8s.pt` on the **non-India split only**, with the fixed hyperparameters.
If they do not, that is reported and Model A is treated as untrained. This
matters because D053 already caught external weights whose apparent 0.9765 mAP50
came from train/test overlap — an unverified checkpoint is worth less than no
checkpoint, because it produces numbers that look valid.

## D056 — `uv` and Python 3.12 retained; `requirements.txt` generated, not authored

**2026-09-22 · Accepted**

Spec T0.2 calls for a Python 3.11 `.venv` populated with `pip` and an authored
`requirements.txt`. This project's `CLAUDE.md` mandates `uv` with a committed
`uv.lock`, and the working environment is Python 3.12.13 with `pyproject.toml`
pinning `>=3.12,<3.13`. **`uv` wins; `CLAUDE.md`'s environment line is updated to
state the version explicitly rather than leaving it implied.**

Switching to pip on 3.11 would re-resolve every dependency, reinstall torch, and
invalidate the environment that produced every result to date — a large,
uncompensated risk to satisfy a tooling preference the project had already
settled.

`requirements.txt` is **generated, never hand-edited**:

```
uv export --format requirements-txt --no-hashes > requirements.txt
```

regenerated whenever `uv.lock` changes. It exists so external runners can pin
exact versions; `uv.lock` remains the source of truth.

**Kaggle kernels install only `ultralytics==<pin>` plus `pycocotools`.** Never
the full requirements file. Kaggle images already carry torch built against
their own CUDA, and installing a full requirements set on top of that replaces a
working GPU stack with a generic one — the identical failure mode that made
`pip install -e .` unsafe on Colab, where `torch>=2.13.0` would have displaced
the pre-installed `2.11.0+cu128` build.

**T13 opens with a version gate.** Before any simulation work, a trivial Webots
Python controller must be shown to run under the 3.12 venv. Webots ships its own
Python discovery and may not accept 3.12; finding that out after the world
generator and controller are written would waste the whole task.

## D057 — Package stays `certain_road`; spec modules are audited and extended, never rewritten

**2026-09-22 · Accepted**

The RoadSight spec names its package `roadsight` and gives module paths like
`src/roadsight/voc.py`. This repo's package is `certain_road`, with 10
subpackages, 21 test files and 7 `import-linter` contracts built on that name.

**The spec is amended to the repo.** Every `roadsight` path or import reads
`certain_road`; T0's done-when becomes `import certain_road`. A rename would
touch every module and contract for no functional gain, and a parallel
`roadsight` package would be worse: it would duplicate `parse_voc` and
`SOURCE_TO_ID`, which are already written, already implement D038's merge, and
are already under test.

**Reuse-and-audit precedes writing.** Before any spec module is created, the
repo is checked for an existing implementation. Where one exists it is audited
against the spec and fixed or extended — never rewritten — because a rewrite
discards the decisions already encoded in it. The audit targets are the four
places where the spec states an exact formula:

- **CRC threshold:** the largest τ on the grid satisfying `(Σ_i L_i(τ) + 1) / (n + 1) ≤ α`.
- **Greedy-prefix equivalence:** predictions at or above τ form a prefix of the
  confidence-sorted list and yield the same matches, so
  `L_i(τ) = #{GT with matched_conf < τ} / #GT`. Unit-tested against brute-force
  re-matching at several τ.
- **Drift p-values:** an online *growing* bag — compute p against the current
  bag, *then* insert the score.
- **IPM:** `den = sin θ + y·cos θ`, `t = cam_h/den`, `X = t(cos θ − y·sin θ)`, `Y = −t·x`.

**Spec module → existing code.**

| spec module | exists in repo | action |
|---|---|---|
| `voc.py` | `perception/dataset/voc.py` — `parse_voc(xml_path) -> VocAnnotation` | **extend**: real-image-size fallback, clipping, `min_box_px` |
| `metrics.py` | `perception/evaluate.py` (369 lines) | **extend**: add a pycocotools path *alongside* |
| `geometry.py` | `sim/project.py` — world→image only | **extend**: add the inverse (image→ground), `haversine_m`, `interp_track` |
| `scoring.py` | `survey/segment.py` — segmentation only | **extend**: density, deduct proxy, PCI bands |
| `conformal.py` | — | **write new** |
| `drift.py` | — | **write new** |
| `allocation.py` | — | **write new** |

`conformal`, `drift` and `allocation` genuinely do not exist. A keyword sweep
appeared to find all three, but every hit was a comment: `allocation` matched
aria2c's `--file-allocation=none` flag, and `conformal` matched docstrings
warning against contaminating the calibration split. **The sweep was rerun with
context before this table was written** — matching a word is not finding an
implementation.

**`evaluate.py`'s choice of metric backend is deliberate and is preserved.** It
uses `ultralytics.utils.metrics.ap_per_class`, not pycocotools, because the
numbers must stay comparable to ultralytics-based RDD2022 benchmarks; its own
comment records that an independently correct pycocotools implementation can
differ by more than ±0.01 through IoU-matching and interpolation conventions
alone. This is not an oversight to correct. T6 step 4 asks for exactly this
cross-check — pycocotools against ultralytics, stop if they diverge by more
than 0.03 — so both implementations must coexist for that task to be meaningful.

## D058 — Local commit at the end of each task and before every `eval_locked` run; never push

**2026-09-22 · Accepted**

`eval_locked.py` stamps the git commit into every file it writes to
`results/LOCKED/`. With uncommitted work in the tree that stamp points at a
commit which does not contain the code that produced the number, which silently
breaks the audit trail on the India result — the one claim that most needs to be
reproducible.

**Policy:**
- Commit locally at the end of each task, once its tests pass, as `T<id>: summary`.
- **Always commit before any `eval_locked` run**, so the recorded hash matches
  the code that ran.
- **Never push.** Publication stays an explicit, separate decision.

This narrows `CLAUDE.md`'s "don't commit unless asked" for this spec's duration:
the commits *are* asked for, because the audit trail depends on them. Pushing is
not.

## D059 — India block split rejected on evidence; per-image salted-hash split at the spec's fractions

**2026-09-22 · Accepted**

T2 step 3 specifies a **block split** for India — chunk the filename-sorted list
into blocks of 50, shuffle the blocks, assign greedily — and asks for the
justification to be checked first: *"Open 5 pairs of adjacent-ID images and log
whether they look like consecutive frames from the same drive; this justifies the
block split."*

**They are not consecutive frames.** All five sampled pairs show unrelated
scenes, and one pair is `India_009354 → India_009357`, so the IDs are not even
dense. Five pairs is a thin basis for overturning a spec assumption, so it was
measured over 400 pairs using 32×32 grayscale correlation:

| | mean corr | median | corr > 0.9 |
|---|---|---|---|
| adjacent-ID pairs | **+0.487** | +0.535 | 1 / 400 |
| random pairs | **+0.483** | +0.520 | 0 / 400 |

A difference of **+0.004** is nil. Adjacent IDs are no more similar than randomly
chosen ones. IDs span 0–9,891 across 7,706 train images, and only 6,011 of 7,705
consecutive gaps are 1.

**Decision: per-image split at the spec's `india_fracs` (60/10/15/15)**, using the
existing salted-hash assignment (D009's `assign_split`) with a RoadSight-specific
salt. Blocking would buy nothing measurable while making the fraction targets
lumpier, since a block of 50 is an indivisible unit.

The block split is not *wrong* — it is simply solving a leak this dataset does
not have. Had the correlation been real, blocking would have been essential, and
that is why it was measured rather than assumed.

**Conformal consequence** (required by the project's standing constraint that no
split changes without one). This replaces D009's India assignment
(train 4,617 / val 757 / calib 1,548 / test 784 = 59.9 / 9.8 / 20.1 / 10.2) with
60 / 10 / 15 / 15:

- `india_cal` **shrinks** from ~1,548 to ~1,156. CRC's guarantee is
  `(Σ L_i + 1)/(n + 1) ≤ α` over calibration images holding at least one GT
  pothole, so a smaller *n* makes the bound slightly more conservative — the
  `+1` numerator term carries more weight. The guarantee stays valid; it costs a
  little tightness.
- `india_test` **grows** from ~784 to ~1,156, which lowers the variance of the
  measured test risk. That directly offsets the above: the number being reported
  becomes more stable.
- **No existing result is invalidated**, because no existing checkpoint survived
  D055's Model A gate. `multicountry_v8s` trained on India and validated on
  India, so it could never have supported an India claim under either split.
  Model A is retrained on non-India only, so India images cannot leak into it
  regardless of how India is partitioned.
- Salted hashing is kept rather than a seeded shuffle for the reason D009 chose
  it: assignment is stable when the file set changes, so adding or removing
  images never silently reshuffles an image from train into test.

## D060 — Model A trains on Kaggle only; the Mac is a fallback for Model B alone

**2026-09-22 · Accepted**

**Model A never trains on MPS.** It is the model every India claim rests on: it
must be trained on non-India only, from COCO `yolov8s.pt`, with the fixed
`train_A` hyperparameters, and its result has to be reproducible by someone else.
A T4 GPU on Kaggle is the reproducible environment; this particular MacBook is
not, and MPS has op-level gaps that can shift results in ways nobody would catch
from a loss curve.

**Model B defaults to Kaggle too**, but may fall back to the Mac if *both* hold:

1. **T4 passes** — MPS and CPU training losses agree within 25%, so the backend
   is not silently computing something different.
2. **The projected B run fits the schedule**, measured rather than guessed: train
   time at `fraction=0.02` divided by 0.02, plus one full validation pass.

B is the weaker claim of the two — it initialises from A's weights, trains on
~9.6k images (india_train + nonindia_replay) for 25 epochs, and is the
deployment model rather than the generalization measurement. A backend
discrepancy there is recoverable; in A it would poison everything downstream.

This is the same principle as D055's Model A gate: the constraint is not "use
the fastest machine available" but "make the number that matters defensible".

## D061 — Near-duplicate audit by dHash before T3

**2026-09-22 · Accepted**

T3 uploads the pool to Kaggle and **bakes the splits in**. Any leak found after
that costs a re-upload and invalidates every result trained against it, so the
audit happens first.

D059 established that *adjacent filenames* are uncorrelated in India. That is a
different question from whether **near-duplicate images exist anywhere in the
set** — two frames of the same pothole captured seconds apart need not have
adjacent IDs, and a salted hash scatters them independently across splits. D059
ruled out one leak mechanism; this rules out the other.

**Method.** 64-bit dHash per image — grayscale, resize to 9×8, compare adjacent
columns row-wise. PIL already ships; no new dependency. Pairs within **Hamming
distance ≤ 6** are flagged, then a sample is viewed, because a distance
threshold alone cannot distinguish a true duplicate from two genuinely similar
stretches of road.

**Comparisons:**
- `india_train` against `india_cal ∪ india_test` — this is the one that matters.
- `nonindia_train` against `nonindia_val`.

**If India cross-split duplicates exist:** group them with union-find, re-split
India keeping each group intact, at the same salt and fractions; rerun the
leakage tests; and add a permanent test that no flagged group spans India splits.
Grouping is necessary because duplicates are transitive — A≈B and B≈C must land
together even when A and C are themselves far apart.

**Non-India duplicates are reported as a count only.** They inflate validation
optimism and therefore affect early stopping, but Model A's India result is
measured on a set non-India duplicates cannot reach. Re-splitting non-India to
chase them would be churn against the wrong risk.

## D062 — Allocation solved by exact DP, not PuLP

**2026-09-22 · Accepted**

T12 specifies a PuLP binary ILP for the repair allocation. **PuLP cannot solve
anything on this machine.** It ships its own CBC binary, and the macOS build is
x86_64:

```
$ .../pulp/solverdir/cbc/osx/i64/cbc -quit
bad CPU type in executable
```

This is an arm64 Mac with no Rosetta (`oahd` is not running), and `brew install
cbc` is blocked behind an unaccepted Xcode licence needing `sudo`. Both fixes are
system-level changes outside the task.

**Replaced with an exact dynamic program indexed by priority.** `best[p]` holds
the least cost that achieves quantised priority exactly `p`; after every segment
is offered, the answer is the largest `p` still within budget.

Indexing by priority rather than by budget is the point. The textbook
budget-indexed knapsack DP needs a table the size of the budget, which for rupee
costs in the millions is unusable, and it cannot take float costs at all.
Priorities are bounded by construction — `(100 − vision-estimated PCI) ×
traffic_weight` — so the table stays small while costs remain exact floats.

Priorities are quantised at 0.01 to index the table. The solution is exact for
the quantised problem, and 0.01 on a 0–100 scale is finer than the
vision-estimated PCI feeding it is meaningful to, so the quantisation is not the
binding approximation — the PCI proxy is.

**This is not a downgrade.** Both solve the same 0/1 knapsack to optimality;
the DP simply has no binary dependency, which also means T16's dashboard can
re-run allocation live and Kaggle needs no solver install. `test_optimal_beats_
greedy_on_the_knapsack_trap` pins that it genuinely optimises: on a case where
worst-first takes one expensive segment, the DP takes two cheaper ones for more
total priority.

`pulp` stays in the dependency set — it is in T0's specified list and works on
Linux, so it remains available for cross-checking where CBC runs — but
`survey/allocation.py` does not import it.

## D063 — Leak verification is exhaustive; held-out India never leaves this machine

**2026-09-22 · Accepted · supersedes D061's verification method**

D061 verified the India split by re-running the dHash audit and finding no
same-scene pairs among the pairs it flagged. **That reasoning is circular.** The
audit can only ever confirm that the pairs *it selected* are clean; two frames of
one location a few metres apart can differ by more than Hamming 12, in which case
neither the grouper nor the audit ever compares them, and the leak survives
precisely because the prefilter missed it.

No prefilter is necessary. Every image is already a unit-norm 128x128 vector, so
all-pairs correlation is one matrix multiply — 4,623 x 2,312 over 16,384
dimensions is ~1.7e11 multiply-adds, seconds in BLAS.

**The exhaustive check found the leak D061 declared closed:**

| | dHash-filtered claim | exhaustive reality |
|---|---|---|
| india_train x held-out | 0 same-scene pairs | **1,373 pairs >= 0.93**, max 0.9843 |
| India x nonindia_train | never checked | **119 pairs >= 0.93**, max 0.9562 |

Scene groups are therefore built from **every** India-India pair rather than from
hash candidates, so the split is clean by construction instead of by iteration.
After rebuilding: **0 pairs >= 0.93 in both directions** over 14.3M and 188.9M
comparisons.

**The cross-country leak is fixed on the non-India side.** 29 non-India training
images duplicate an India image. Model A trains on non-India and is measured on
India, so such a pair leaks straight into the headline claim. Dropping the
*non-India* copy keeps the India evaluation sets whole and costs 0.1% of training
data; dropping the India copy would have shrunk the very set being defended.

**Held-out India is not uploaded.** `india_cal` and `india_test` — 2,312 images —
stay on this machine. Locked evaluation runs locally on CPU, so they have no
reason to travel, and if the bytes are absent then no Kaggle kernel can read them
through a misconfiguration or a copy-pasted data yaml. The calibration firewall
stops being a convention the code must honour and becomes a fact about where the
bytes are.

**Group assignment is now pothole-balanced.** Filling purely by count let
`india_val` drift to 51.6% pothole against 46% elsewhere, because whole scene
groups carry correlated class mixes and a small split absorbs one badly. Since
the India pothole share is the headline domain-shift number, a val split five
points richer in potholes would report a different problem than the one being
solved. Balanced placement brings the spread to **0.06 points** (46.61-46.67%).

**The largest group is not one scene, and that is fine.** Its 1,312 members have
mean within-group correlation 0.766, a minimum of 0.013, and only 1% of internal
pairs reach 0.93 — a transitive chain through low-information "hub" frames, not a
place. Twelve random members are visibly unrelated scenes. Over-grouping is the
conservative error: it can only reduce leakage, it costs a little split
flexibility, and with balance now enforced it costs nothing measurable. The group
sits entirely in `india_train`.

## D064 — T10 resampling permutes scene groups, not images

**2026-09-22 · Accepted**

T10's conformal experiments re-partition `india_cal ∪ india_test` 200 times to
check that mean test risk stays at or below alpha. **The exchangeable unit is now
a scene group, not an image** (D061/D063).

Shuffling individual images would split a group across the calibration and test
halves, making the two halves more alike than two genuinely independent samples
would be. The measured test risk would come out slightly low and the guarantee
would look slightly better than it is — a quiet overstatement of exactly the
property conformal prediction exists to establish honestly.

Resampling therefore permutes groups, with singleton images as groups of one.

## D065 — The third exhaustive comparison, a kernel-side guard, and the NaN val loss

**2026-09-22 · Accepted · completes D063**

Three gaps, found by review after T5b had already launched.

### India x nonindia_val was never compared

D063 ran two exhaustive checks — `india_train` x held-out, and India x
`nonindia_train`. It did **not** compare India against `nonindia_val`, which is
the set Model A's early stopping and best-epoch selection read. A duplicate there
would bias model *selection* toward the India domain without ever putting an
India image in training.

Run now, exhaustively: 7,706 x 6,142 = **47,330,252 pairs**, max correlation
**0.9516**, **68 pairs at or above 0.93**.

**All 68 are false positives; none is a copy.** The top ten were viewed. Every
one pairs a hazy, washed-out Indian road against a Japanese urban street, and
`Japan__Japan_008910` alone accounts for six of the ten — the same low-information
hub-frame effect seen within India. A dusty Indian highway and a Japanese car
park are not the same scene under any reading.

**This exposes a limit of the 0.93 threshold worth recording.** It was calibrated
on within-India pairs, where both images share a dashcam domain, lighting and
aspect. Across countries the discriminating power is lower: two low-texture
frames from different continents can exceed it while being obviously unrelated.
The threshold remains right for its calibrated purpose — grouping India scenes —
and cross-country figures must be read with inspection, not taken as counts.

**No retrain.** Zero copies means nothing to remove, so T5b continues.

### The kernel had no India guard

`test_splits.py` asserts the lists *in this repo* are clean. Nothing asserted the
list the **kernel actually reads** after an upload, a dataset version bump or a
hand-edited yaml. `assert_no_forbidden_prefix` now runs inside the kernel before
the optimiser sees an image, and refuses to train if any forbidden prefix appears
in any training list. It is job-configured (`forbid_prefixes: ["India__"]` for
Model A) because Model B legitimately trains on `india_train`.

**T5b launched without it**, so that run was verified another way: its
`nonindia_train.txt` has 0 `India__` entries and its local SHA256
`8a18dba1431e...` matches the uploaded manifest exactly. The guard protects
T7 and any resume.

### NaN `val/cls_loss` is inert

Traced in ultralytics 8.4.115:

| file:line | finding |
|---|---|
| `utils/metrics.py:1007-1010` | `fitness()` = `[P, R, mAP50, mAP50-95]` weighted `[0, 0, 0, 1]` — mAP50-95 alone, and wrapped in `np.nan_to_num` |
| `engine/trainer.py:596` | `self.metrics, self.fitness = self.validate()` |
| `engine/trainer.py:605` | `self.stop \|= self.stopper(epoch + 1, self.fitness)` — early stopping consumes fitness |
| `engine/trainer.py:766-767` | `if self.best_fitness == self.fitness: ... save best.pt` — checkpoint selection consumes fitness |

**Neither early stopping nor best.pt selection reads any validation loss.** The
NaN is written to `results.csv` and never consulted, so it cannot affect which
epoch is chosen or when training stops.

It is treated as real only if a **training** loss goes NaN, or if val mAP50
stalls — both of which would indicate divergence rather than a logging artifact.
The diagnosis if so: re-run validation locally on `best.pt` with `half=False`,
since fp16 underflow in an empty-prediction batch is the likeliest cause.

## D066 — Cross-country checks use a duplicate threshold, not the same-scene one

**2026-09-22 · Accepted · amends D063 and D065**

D063 applied one threshold, 0.93, to every comparison. That conflates two
different questions.

**Within India**, the question is *same scene*: two frames of one location
seconds apart, which contaminate a holdout even though they are different files.
0.93 was calibrated for exactly that, by inspecting correlation bands.

**Across countries, same-scene is impossible.** An Indian road and a Japanese
one are never the same place. The only cross-country failure that matters is a
**curation duplicate** — the identical file appearing in two country folders —
and that scores ~0.99, not 0.93. Applying the same-scene threshold across
countries measures nothing but shared composition: a hazy road centred in frame
under a blown-out sky, which is most of this dataset.

**Rule: cross-country comparisons flag at >= 0.98. Within-India stays at 0.93.**

### What this means for the figures already recorded

**India x `nonindia_val` (D065): 0 copies, confirmed.** 47,330,252 pairs, max
correlation **0.9516** — comfortably below the duplicate level. The 68 pairs
D065 reported at >= 0.93 were never evidence of copying, and the top ten were
viewed: all hazy Indian roads against Japanese urban streets.

**The 29 removed `nonindia_train` images were not copies either.** Their best
India match runs from **0.9562 down to 0.9318**, median 0.9357, and **none
reaches 0.98**. Six were viewed: Japanese, US and Norwegian roads against Indian
ones, distinguishable by signage, the Street View watermark and kerb striping.
They share only a layout.

They are therefore relabelled **"removed conservatively; not copies"** rather
than "duplicates of an India image" as D063 described them.

**They are not restored.** T5b is training on the list without them, and the
cost of their absence is 29 images out of 24,537 — 0.12% of Model A's training
data, with no measurable effect. Reverting would mean discarding a run in
progress to recover a tenth of a percent, and would invalidate the manifest
SHA256 that currently pins what the kernel is reading. The conservative removal
stands; only its justification is corrected.

**The general lesson.** A threshold is calibrated against a specific question on
specific data. Carrying it to a different question is how a measurement starts
reporting something other than what it names — here, "duplicates" that were
really "two pictures of a road".

## D067 — The India gap is the result; Model A is never retuned against it

**2026-09-22 · Accepted**

Model A's India number will be **clearly lower** than its non-India validation
number. That is the expected outcome and the point of the experiment, not a
defect to close.

Two reasons it must be low:

- **The class mix inverts.** Potholes are ~7% of the instances Model A trains on
  and ~47% of India's (T2). The detector is optimised for a distribution India
  does not have.
- **RDD2022's own authors report cross-country degradation.** A model trained on
  one country loses accuracy applied to another; this reproduces a known result
  on a split built to measure it honestly.

**The gap is what makes the rest of the project mean anything.** Without it,
T10's conformal violation under shift has nothing to violate, T11's drift alarm
has no shift to detect, and T7's Model B has nothing to recover.

**The prohibition.** Model A is **never** retrained, retuned, or reselected
because its India number looks low. Not a different checkpoint, not a different
confidence threshold chosen after seeing the result, not "one more run with
better augmentation". Any of those turns a measurement into a search, and a
number arrived at by searching against the test set is not a held-out number —
which is the entire property `india_cal`/`india_test` were built, firewalled and
withheld from Kaggle to protect. `eval_locked`'s one-shot lock enforces this
mechanically; this entry states why so the lock is never worked around.

**The one result that would indicate a bug rather than a finding:** India
**pothole** AP near zero while non-India validation is healthy. Low is expected;
near-zero on the class India has most of would point at a class-mapping error,
not domain shift. `test_metrics_coco.py` makes that unlikely — it proves a
mis-shifted class id scores under 0.4 where the correct shift scores 1.0 — but
if it appears, the response is to debug the mapping, never to retrain.

## D068 — Model A accepted; evaluation settings frozen

**2026-09-22 · Accepted**

Model A is the first checkpoint in this project that can support a held-out India
claim. D055's gate disqualified all three predecessors; this one was trained from
COCO `yolov8s.pt` on non-India only, with the fixed `train_A` hyperparameters.

**Accepted on evidence, not on completion.** `scripts/verify_run.py` reads the
kernel's own log rather than this repo:

| check | result |
|---|---|
| train scanned | **24,508** = `nonindia_train.txt` |
| val scanned | **6,142** = `nonindia_val.txt` |
| `India__` in either list | **0** |
| training losses, all 40 epochs | finite |
| non-India val mAP50 (training log) | 0.5912 |
| `val/cls_loss` NaN | none |
| ultralytics requested / used | 8.4.115 / **8.4.115** |
| `best.pt` sha256 | `4c169bc3f965582ceb6c38ca4811d65b133f0de09da8dd57fef3789961f7b904` |

The scan counts are the run-level evidence standing in for the kernel guard,
which landed after this run had already launched (D065).

The NaN validation loss seen in the smoke run never recurred across 40 epochs,
consistent with D065's reading that it was an artefact of having no positive
matches in a single epoch on 5% of the data.

### Evaluation settings are frozen and stamped

Comparing two models under different settings compares the settings. Every
reported number — `eval_open`, `eval_locked`, Model A and Model B alike — reads
one block in `configs/project.yaml`, and the lock metadata records it.

Values confirmed in the installed ultralytics 8.4.115 source:

| setting | value | source |
|---|---|---|
| NMS `iou` | 0.7 | `cfg/default.yaml:56` |
| `conf` | 0.001 | `cfg/default.yaml:55` (val default; predict is 0.25) |
| `max_det` | 300 | `cfg/default.yaml:57` |
| `imgsz` | 640 | `cfg/default.yaml:16` |
| `rect` | **false** | `cfg/default.yaml:32`; `detect/val.py` passes no `rect` kwarg to `build_yolo_dataset`, which resolves `rect=cfg.rect or rect` |
| `half` | false | fp32, so CPU and GPU agree |
| `device` | cpu | MPS lacks deterministic kernels for several ops used here (T4) |

`rect` is pinned explicitly although it already resolves false, because
`rect=True` letterboxes to 672 and this project has measured that shifting mAP50
by ~0.03.

### 0.5912 is a training-log number and is not used in the gap

It came from a GPU, fp16, and ultralytics' own aggregation. Subtracting an India
number computed on CPU, fp32 and pycocotools from it would measure the pipelines
as much as the domains.

**Recomputed through the pipeline India will use**, Model A on `nonindia_val`:

| scorer | mAP50 | mAP50-95 |
|---|---|---|
| ultralytics | **0.5787** | 0.2998 |
| pycocotools | **0.5778** | 0.3015 |

Cross-check delta **0.0009**, far inside T6's 0.03 tolerance — two independent
implementations agreeing to a thousandth, which is the check that would have
caught a ground-truth conversion error. Per-class AP50: `linear_crack` 0.5790,
`alligator_crack` 0.6663, `pothole` 0.4909.

**0.5787 is the baseline the generalization gap is measured against.**

## D069 — The India gap is confidence collapse and extent, not blindness

**2026-09-22 · Accepted · corrects D068's narrative**

T6 reported that Model A "doesn't see" Indian damage. **That was wrong.** It
rested on IoU-0.5 matching at conf 0.25, which cannot distinguish a model that
finds nothing from one that finds the defect, rates it below threshold, and draws
it to a different extent.

At conf 0.001, Model A localises **34.7% of India potholes at IoU 0.5 and 54.1%
at IoU 0.1**. More than half produce a prediction in roughly the right place.

| failure | share of India potholes |
|---|---|
| matched at IoU >= 0.5 | 34.7% |
| right place, wrong extent (IoU 0.1-0.5) | 19.5% |
| centre inside GT but IoU < 0.1 | 5.3% |
| nothing predicted nearby | ~40.6% |

**Confidence collapse is the largest single loss:** recall falls 0.347 -> 0.083
between conf 0.001 and 0.25, so **76% of correctly localised potholes are rated
below the reporting threshold**.

**Extent disagreement is real and measurable.** India GT boxes are 2.3x larger in
relative area than non-India (0.0087 vs 0.0038) and more elongated (aspect 1.72
vs 1.46). `India_000580` shows it: a prediction at **0.46 confidence** on the
pothole, inside a GT box three times its size — IoU 0.29, scored as a miss. India
labels damaged *stretches*; the model marks discrete defects.

**This made a testable prediction, and T7 confirmed it.** A blindness-dominated
gap would implicate the architecture or data volume. A confidence-and-convention
gap predicts fine-tuning recovers most of it. Model B on `india_test`:

| | A | B | delta |
|---|---|---|---|
| mAP50 | 0.1079 | **0.3885** | +0.2806 |
| pothole AP50 | 0.1009 | **0.3582** | +0.2573 |
| recall @0.25 | 0.0858 | **0.3431** | +0.2573 |
| pothole recall @0.001, IoU 0.5 | 0.334 | **0.901** | +0.567 |

Model B finds 90% of India potholes at IoU 0.5 where A found 33%. Misclassification
stayed under 3.3% for both — the axis that moved was detection and confidence,
exactly as predicted.

IoU 0.5 remains primary for every reported metric; 0.1 and 0.3 are a declared
sensitivity analysis used to locate the failure.

## D070 — T10 alphas come from the measured floor; Model A cannot certify India

**2026-09-22 · Accepted · one number corrected by D076**

CRC returns the largest tau whose bound holds. If even `tau = 0.001` — keeping
every prediction the detector emits — misses more than alpha of the potholes,
**no tau satisfies the bound and the procedure correctly returns nothing**. That
floor is a property of the detector on that domain, not of the conformal
machinery.

Measured (image-level loss, IoU 0.5, over images containing a pothole):

| model · set | n | miss-rate floor | min certifiable alpha |
|---|---|---|---|
| A · nonindia_val | 432 | 0.1485 | 0.1505 |
| **A · india_cal** | 217 | **0.6390** | **0.6407** |
| **A · india_test** | 219 | **0.6227** | **0.6244** |
| B · india_cal | 217 | 0.0827 | 0.0869 |
| B · india_test | 219 | 0.0867 | 0.0908 |

**The configured alphas (0.05, 0.10, 0.20) are all infeasible for Model A on
India**, and would previously have been reported as "CRC failed". They are
replaced by a **risk-vs-alpha curve across the full range with the infeasible
region shaded**, which states the finding directly: *no procedure can certify a
pothole miss rate below ~0.62 using Model A on Indian roads, because the detector
does not find them at any threshold.*

**Roles are now explicit:**
- **Model A demonstrates the violation and the infeasibility.** Calibrated on
  non-India and deployed on India, the guarantee breaks:

  | alpha | tau from non-India | risk on non-India | risk on india_test |
  |---|---|---|---|
  | 0.30 | 0.02 | 0.2816 ✓ | **0.7928** |
  | 0.50 | 0.18 | 0.4963 ✓ | **0.8777** |

  The bound holds in-domain and is exceeded by **2.6x** out-of-domain — the
  exchangeability assumption failing exactly where the theory says it must.

- **Model B carries the certified India result.** Its floor of 0.087 makes alphas
  from ~0.09 upward feasible, an order of magnitude better than A.

Primary loss stays IoU 0.5. IoU 0.3 may appear only as a declared secondary
sensitivity analysis, never as the headline.

## D072 — Pothole AP is the target, not overall 3-class mAP

**2026-09-22 · Accepted**

The deliverable is a vehicle that avoids potholes. **Overall 3-class mAP is not
chased**, and its ceiling is roughly the in-domain 0.58 Model A reached on
non-India — pushing India's aggregate toward that would mostly be gains on crack
classes the avoidance loop never acts on.

The targets are **pothole AP** and **per-pothole detection in video**.

### Model B is converged; more epochs is not the lever

From B's own `results.csv`, `india_val` mAP50 over the last epochs:

| window | slope |
|---|---|
| last 5 epochs | **+0.00072** mAP50/epoch (+0.007 per 10) |
| last 10 epochs | +0.00263/epoch |

Best 0.4381 at epoch 24, final 0.4378. The step at epoch 21 (0.4212 -> 0.4358) is
`close_mosaic` firing at epoch 20, not learning. Extending B would buy roughly
+0.007 per ten further epochs, which does not justify the GPU time.

### Model P — pothole-only

One class, so the detector spends none of its capacity separating crack types it
will never act on, and cracks appear as background it learns to reject.

**Data.** `india_train` with pothole -> 0 and every other class dropped, plus
BharatPotHole's own train split. Validation is `india_val` under the same remap.
Separate label tree, images shared by hard link.

| source | images | pothole boxes |
|---|---|---|
| india_train | 4,622 | 2,025 |
| BharatPotHole train | 5,067 | **8,795** |
| **p_train** | **9,689** | **10,820** |
| india_val | 772 | 342 |
| BharatPotHole valid | 1,345 | 2,276 |

**BharatPotHole contributes 4.3x more pothole boxes than india_train**, so it
dominates the annotation style. That is a real risk to India performance and is
precisely why selection is on `india_val` alone — if BharatPotHole's convention
hurts Indian roads, `india_val` shows it and Model P loses.

**BharatPotHole is CC BY 4.0** (Roboflow `dashcam-mg6en` v14) and must be
credited wherever Model P results appear.

### BharatPotHole does not overlap the India holdout

Checked before training, exhaustively, at the **cross-dataset duplicate
threshold of 0.98** (D066 — "same file", not "same scene", since two Indian
dashcam datasets sharing a road is not contamination while sharing a file is):

| split | images | pairs vs india_cal+test | max corr | duplicates |
|---|---|---|---|---|
| train | 5,067 | 11,714,904 | 0.9246 | **0** |
| valid | 1,345 | 3,109,640 | 0.9207 | **0** |
| test | 662 | 1,530,544 | 0.9187 | **0** |

`india_cal` and `india_test` are absent from the pothole pool by construction and
are not uploaded, exactly as in the main pool.

### Selection and locking

**Selection uses `india_val` only.** Held-out sets play no part in choosing
between B, P or any learning-curve variant. Finalists receive **one**
`eval_locked` run each under a new lock name, and **every model tried is
reported**, including those that lose — a comparison that lists only the winner
is a selection effect, not a result.

## D073 — BharatPotHole's val and test splits are not held out; its diversity is 162 drives

**2026-09-22 · Accepted · qualifies D072**

Roboflow exports name files `<videoID>_frame_<index>_jpg.rf.<hash>.jpg`, so the
source video and frame index survive in the filename and the splits can be
audited directly.

| | train | valid | test |
|---|---|---|---|
| frames | 5,067 | 1,345 | 662 |
| distinct videos | 153 | 112 | 93 |
| videos also present in train | — | **107 of 112** | **89 of 93** |
| **frames from videos seen in train** | — | **1,337 / 1,345 = 99.4%** | **658 / 662 = 99.4%** |
| near-adjacent pairs vs train (\|delta frame\| <= 10) | — | **17,572** | **9,013** |

Across all three splits the dataset holds **162 distinct videos** sampled into
**7,074 frames** — 43.7 frames per drive.

**Both of BharatPotHole's evaluation splits are the same footage as its training
split**, frequently adjacent frames of the same drive. A model trained on it
scores highly on either while having learned nothing transferable.

### Effective diversity

**BharatPotHole contributes 153 training videos, not 5,067 independent images.**
The whole dataset — train, valid and test together — is **162 distinct drives**
sampled into 7,074 frames, roughly 44 frames per drive. Frames from one drive
share vehicle, camera, mounting, weather, time of day, road surface and often the
same physical potholes from slightly different distances.

This is the number that belongs in any statement about what the pothole pool
consists of. `p_train.txt` is 9,689 images — 4,622 India frames and 5,067
BharatPotHole frames — but counted in independent scenes the BharatPotHole
contribution is roughly two orders of magnitude smaller than its image count
suggests. Any later claim of the form "BharatPotHole is the bulk of the pothole
data" is true by box count (8,795 vs 2,025) and misleading by scene count.

**Consequences:**

- **Neither BPH val nor BPH test is used for any evaluation**, reported or
  internal, and neither appears in a selection or acceptance decision. They are
  not "optimistic numbers to be discounted"; they are not measurements. The
  `p_bph_val.txt` list stays in the pool only as the training-time val hook
  ultralytics requires, and no number computed on it is reported.
- **BharatPotHole remains valid training data.** Nothing here says its images or
  its labels are wrong.
- **This is not evidence about annotation convention.** The audit reads frame
  indices out of filenames; it is silent on whether BharatPotHole boxes are drawn
  to the same convention as RDD2022 — how tight, what counts as one pothole
  versus a cluster, what minimum size is annotated. That risk is real and
  separate, and it is judged where the two conventions actually compete: on
  `india_val`. A filename result must not be allowed to stand in for a labelling
  result.
- **Nothing touches `india_val`, `india_cal` or `india_test`.** D072 already
  showed zero duplicate-level overlap between any BharatPotHole split and the
  India holdout (max correlation 0.9246 against a 0.98 threshold), so the India
  numbers are unaffected.
- **Selection remains on `india_val` alone**, which this makes more important
  rather than less: the BharatPotHole numbers that would have looked impressive
  are precisely the ones that mean least.

This is the same failure D059 tested for in India and did not find there.
Adjacent RDD2022 India filenames proved uncorrelated (+0.004 over random);
BharatPotHole's are 99.4% same-video. Two datasets, opposite answers, and the
only reason we know either is that both were measured.

## D074 — Model P is selected over Model B for pothole detection

**2026-09-22 · Accepted · settles D072 · selection set: `india_val` only**

Model P is Model B fine-tuned on a pothole-only pool: `india_train` (4,622
images, 2,025 pothole boxes) plus BharatPotHole train (5,067 frames from 153
drives, 8,795 boxes). 40 epochs requested, **36 run, early-stopped** on patience
10. Both models scored on `india_val` — 772 images, 342 pothole boxes — against
pothole-only ground truth, through one pycocotools path under the frozen eval
block. B runs NMS as the 3-class model it is and is then filtered to its pothole
channel; its crack detections are discarded rather than charged as false alarms,
which is the generous reading for B.

| | B | P | delta |
|---|---|---|---|
| pothole AP50 | 0.4010 | **0.4279** | +0.0269 |
| pothole AP50-95 | 0.1514 | **0.1574** | +0.0060 |
| recall @ conf 0.25 | 0.3567 | **0.4561** | +0.0994 |
| false alarms/image @ conf 0.25 | **0.1671** | 0.1878 | +0.0207 |

### The headline number does not survive resampling; the operating points do

342 pothole boxes is not many, so every difference was put through a **paired
bootstrap over images**, 2,000 draws — both models scored on the same resampled
`india_val` each draw, so the shared difficulty of a hard image cancels.

| quantity (P − B) | mean | 95% CI | separates from 0 |
|---|---|---|---|
| pothole AP50 | +0.0309 | [−0.0125, +0.0757] | **no** |
| false alarms/image @ recall 0.3 | −0.055 | [−0.101, −0.014] | **yes, P** |
| false alarms/image @ recall 0.4 | −0.104 | [−0.175, −0.035] | **yes, P** |
| false alarms/image @ recall 0.5 | −0.162 | [−0.271, −0.058] | **yes, P** |
| false alarms/image @ recall 0.6 | −0.217 | [−0.479, +0.043] | no |
| false alarms/image @ recall 0.8 | +0.754 | [−0.564, +2.244] | no |

**The +0.027 AP50 win is not a measured difference.** P is ahead in 91.4% of
draws, which is suggestive and nothing more; reporting it as a result would be
reporting noise with a decimal point on it. What does survive is narrower and
more useful: at every recall from 0.3 to 0.5, P pays **strictly fewer false
alarms for the same number of potholes found**, and the interval clears zero.
At recall 0.5, P emits 0.262 false alarms per image against B's 0.396 — **34%
fewer** — and is ahead in 99.9% of draws.

### The recall-0.8 comparison is the one point where B wins, and it is not real

| matched recall | B | P |
|---|---|---|
| 0.3 | 0.114 | **0.053** |
| 0.4 | 0.231 | **0.130** |
| 0.5 | 0.396 | **0.262** |
| 0.6 | 0.789 | **0.554** |
| 0.7 | 1.528 | **1.326** |
| **0.8** | **2.956** | 3.982 |
| 0.9 | 11.978 | **12.119** |
| 0.944 | 35.308 | **24.048** |

D072 asked for recall 0.8 specifically, and B is better there: 2.96 false alarms
per image against P's 3.98. Two things stop that from deciding anything. Its
bootstrap interval is [−0.564, +2.244], so **B's advantage at 0.8 does not
separate from zero either** — it is a single crossing in an otherwise consistent
pattern. And at 3–4 false alarms per image **nobody operates there**: a survey
vehicle would be flagging three phantom potholes per frame. The range a crew
could actually use is recall 0.3–0.6, at well under one false alarm per image,
and P is better across all of it.

This is why the grid is recorded and not just the requested point. A single
matched recall can flatter either model when the curves cross, and here they do.

**Selected: Model P.** The contingency in D072 — P2, `india_train` oversampled
3×, otherwise identical — is **not triggered**, because P did not lose.

### Re-run over scene groups (D064): the india_val advantage holds

The first bootstrap resampled images. `india_val` holds near-duplicate frames of
the same location, so image-level resampling treats two frames of one pothole as
two independent observations and the intervals come out too narrow. Redone over
**662 scene groups** covering the 772 images (largest group 17, 134 images
grouped), same grouping as D064:

| P − B on india_val | group-level 95% CI | separates | (image-level was) |
|---|---|---|---|
| pothole AP50 | +0.0307 [−0.0097, +0.0735] | no | [−0.0125, +0.0757] |
| FA/img @ recall 0.3 | −0.063 [−0.118, −0.015] | **yes, P** | [−0.101, −0.014] |
| FA/img @ recall 0.4 | −0.119 [−0.201, −0.042] | **yes, P** | [−0.175, −0.035] |
| FA/img @ recall 0.5 | −0.182 [−0.317, −0.063] | **yes, P** | [−0.271, −0.058] |

The intervals widened, as they should, and **the 0.3–0.5 advantage still clears
zero**. The "tie on india_val" amendment is therefore not triggered. The widening
is modest because `india_val` turns out to be mostly singletons — 662 groups for
772 images — so the correction matters less here than it will for T10, where the
same grouping governs re-partitioning.

### Held-out verification on india_test: the advantage does not transfer

One locked run each, no re-runs, pothole-only ground truth derived inside the run
directory, same scorer. `P_india_heldout`: pothole AP50 **0.3416** over 2,312
images and 820 instances, cross-check delta 0.0009. Sliced to `india_test`
(1,156 images, 413 pothole boxes) and compared against B's existing locked
predictions filtered to its pothole channel:

| | B | P | delta |
|---|---|---|---|
| pothole AP50 | **0.3582** | 0.3559 | −0.0023 |
| pothole AP50-95 | **0.1437** | 0.1375 | −0.0062 |
| recall @ conf 0.25 | 0.3462 | **0.3753** | +0.0291 |
| false alarms/image @ conf 0.25 | **0.1315** | 0.1678 | +0.0363 |

| matched recall | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 |
|---|---|---|---|---|---|---|---|
| B | 0.087 | 0.196 | **0.340** | **0.894** | **1.906** | **5.872** | 30.368 |
| P | 0.097 | 0.195 | 0.411 | 1.041 | 2.471 | 6.996 | **28.941** |

**Nothing separates from zero**, in either direction, at any operating point
(group-level bootstrap over 1,037 scene groups, 2,000 draws; AP50 delta −0.0031,
95% CI [−0.0361, +0.0298]). On the held-out set **B and P are indistinguishable**,
and every point estimate in the usable range now leans very slightly to B.

**This is what the declared selection bias predicts.** P's advantage lived on
`india_val`, which is the set P's checkpoint was selected against, and it does not
appear on a set neither model was selected against. The honest summary is that
**adding BharatPotHole did not measurably improve pothole detection on held-out
Indian roads** — 153 drives of extra footage, 8,795 extra boxes, and no
transferable gain.

**The selection is not re-decided.** D074 chose P on `india_val` before this run
existed, and re-deciding on the held-out number would spend the one thing a
held-out set is for. P remains the model carried forward; what changes is the
claim made about it, which is now "no worse than B on held-out India" rather than
"better". T10's certified result will be reported for P on that basis.

### The comparison is biased toward P, by construction

**P's `best.pt` was chosen on `india_val` pothole fitness. B's was chosen on
`india_val` 3-class fitness.** Ultralytics selects the best epoch by `fitness()`,
which is mAP50-95 averaged over whatever classes the run declares
(`metrics.py:1007`). P's job declared one class, so its checkpoint is the epoch
that maximised *pothole* mAP50-95 on the very set — and the very metric — the
D074 comparison then scored. B's job declared three, so its checkpoint is the
epoch that maximised the mean over `linear_crack`, `alligator_crack` and
`pothole`; the epoch best at potholes alone may have been discarded.

This is a real advantage to P and it is not small. It is also not removable
without retraining B under a pothole-only val, which would change B into a
different model. So it is declared rather than corrected, and it is one more
reason the AP50 gap failing to separate from zero is the honest reading.

**The locked `india_test` comparison is the unbiased referee.** Neither
checkpoint was selected against it, neither model has seen it, and it is run once.
D074's selection stands on `india_val` regardless of what that run returns —
selection and verification are different jobs, and re-deciding on the held-out
number would spend the one thing it is for.

### Models tried, all of them

| model | provenance | outcome |
|---|---|---|
| `multicountry_v8s` + 2 other pre-existing checkpoints | inherited | **disqualified** at the weights gate: trained on 4,617 India images and validated on 757 more |
| **A** | non-India only, from scratch | accepted (D068). nonindia_val mAP50 0.5787; india_full 0.0972 LOCKED; india_test pothole AP50 0.1009 |
| **B** | A + india_train + non-India replay | india_test mAP50 0.3885, pothole AP50 0.3582 (D069). india_val pothole AP50 0.4010 |
| **P** | B + BharatPotHole, pothole-only, 36 epochs | india_val pothole AP50 **0.4279**. **Selected** |

Four smoke runs failed on Kaggle infrastructure and produced no model; they are
recorded in D060 and in the `train.py` docstring, not here.

### What this does not say

- **Nothing about BharatPotHole's annotation convention.** P is better on
  `india_val`, which is evidence that the extra data helped on Indian roads. It
  is not evidence that BharatPotHole's boxes are drawn like RDD2022's, and the
  reverse would not have been evidence that they are not.
- **Nothing about held-out performance.** `india_val` is the selection set.
  P's held-out number comes from one `eval_locked` run and does not exist yet.
- **Nothing that licenses re-tuning A** (D067 stands).

## D075 — Video evaluation confirms per track, and counts tracks, not potholes

**2026-09-28 · Accepted · Qualifies D006 and D051 for video evaluation only**

*Written after D076 and D077, into a number that had been left unused.*

D072 made per-pothole detection in video a target. Counting potholes needs
objects, not a condition: D051's confirmer answers "is a hazard in my path",
which is right for steering and silent on how many potholes a drive contains.
`scripts/eval_video.py` therefore tracks.

### The rule

- Model B's pothole channel at conf 0.25, ByteTrack (`bytetrack.yaml` as shipped),
  tracker state persisted across frames.
- **ROI gate:** a box whose bottom edge lies above the horizon line is dropped
  before confirmation. Downloaded video has no camera model, so the horizon is a
  hand-set fraction of frame height, recorded in every run's summary.
- **Confirmation:** a track is confirmed once **the same track ID** is present in
  at least 3 of the last 5 frames. Hits on different IDs never pool — the
  difference from D051, where any 3 of 5 frames containing a hazard confirm.
- Settings in `configs/eval/video.yaml`; the rule is `confirm_step`, pinned by
  `tests/test_eval_video.py`.

**Stated cost of conf 0.25.** ByteTrack's second association stage matches
low-score boxes (0.1 to 0.25) to lost tracks. At conf 0.25 nothing below 0.25
reaches it, so that recovery path is off, and a pothole whose score dips for a
frame or two is more likely to come back under a new ID.

### The count is of tracks, not physical potholes

It is biased in both directions, and on video without ground truth neither bias
can be measured:

- **Upward by ID switches.** A pothole lost for longer than the tracker's buffer
  — occlusion, a run of missed detections, camera shake — and re-acquired under a
  new ID confirms twice. `test_one_pothole_reacquired_under_a_new_id_confirms_twice`
  pins this on purpose: it is the behaviour, not a defect to be fixed quietly.
- **Downward by merges.** Two potholes held by one ID — overlapping boxes, or an
  ID that jumps to a neighbour — confirm once.

This is D006's objection ("ID switches corrupt counts"), and D006 stands: **the
survey still uses no tracker.** D075 permits a tracker only where the output is
labelled as a track count.

### Reporting

- **Where ground truth exists** — the MuJoCo trial — report the confirmed track
  count **beside** the GT-matched per-pothole count, so the size of the bias is
  shown rather than assumed. (No MuJoCo trial exists in this repo yet; D050's
  simulator is a kinematic model. Whichever trial first has per-pothole ground
  truth inherits this rule.)
- **On real video with no ground truth**, report tracks and label them as tracks:
  `unique_confirmed_tracks` in `summary.json` and on the video overlay. Never
  "potholes found".

## D076 — The tau grid never reached the floor; Model P's feasible alphas

**2026-09-24 · Accepted · corrects one number in D070**

### The bug

D070 established that the alpha grid must come from the measured miss-rate floor
rather than habit. The floor was measured at `tau = 0.001`. **The risk-vs-alpha
curve searched `np.arange(0.01, 0.99, 0.01)`** — it could never consider a
threshold looser than 0.01, and risk climbs steeply below that:

| tau | B risk on india_cal | P risk on india_cal |
|---|---|---|
| **0.001** | **0.0827** | **0.1052** |
| 0.002 | 0.1113 | 0.1446 |
| 0.005 | 0.1627 | 0.1882 |
| **0.010** | **0.2198** | **0.2398** |

So D070's table said Model B is certifiable from alpha 0.087, while the curve in
the same artifact marked every alpha below **0.24** infeasible. Both numbers were
printed, from the same run, and they disagreed by a factor of nearly three. The
prose — "its floor of 0.087 makes alphas from ~0.09 upward feasible" — described
the table, not the curve, and the curve was what any plot would have shown.

`tau_step: 0.001` was already in `configs/project.yaml`. The grid ignored it and
hardcoded its own, which is also the magic-number rule this project set itself.

### The fix, and the check that it is a fix

The grid is now `np.arange(TAU_STEP, 1.0, TAU_STEP)` with `FLOOR_TAU = TAU_STEP`,
so the loosest threshold the search may consider **is** the one the floor is
measured at. The boundary alpha is then resolved on a fine grid rather than read
off the first coarse step past it.

Floor and curve now agree for all three models, which is what makes this a fix
rather than a different arbitrary choice:

| model | floor predicts | curve gives |
|---|---|---|
| A | 0.6407 | 0.642 |
| B | 0.0869 | 0.088 |
| P | 0.1093 | 0.110 |

### Model P's floors

| model · set | n | miss-rate floor | min certifiable alpha |
|---|---|---|---|
| **P · india_cal** | 217 | **0.1052** | **0.1093** |
| **P · india_test** | 219 | **0.0789** | **0.0830** |
| B · india_cal | 217 | 0.0827 | 0.0869 |
| B · india_test | 219 | 0.0867 | 0.0908 |

**Calibration happens on `india_cal`, so the binding number is P's 0.1093 and
P's feasible range is alpha >= 0.11.** B's is alpha >= 0.088.

**B can certify a tighter pothole miss rate than P.** P is worse on `india_cal`
(0.1052 vs 0.0827) and better on `india_test` (0.0789 vs 0.0867); the two halves
are 217 and 219 images and the disagreement is the size one would expect from
that. It is one more reading consistent with D074's held-out finding that the two
models are not distinguishable.

### P's certified curve holds

Calibrated on `india_cal`, evaluated on `india_test`, **test risk stays at or
below alpha at every feasible alpha**:

| alpha | 0.12 | 0.16 | 0.20 | 0.26 | 0.30 | 0.40 |
|---|---|---|---|---|---|---|
| tau | 0.001 | 0.002 | 0.005 | 0.013 | 0.023 | 0.069 |
| risk on india_test | 0.0789 | 0.1216 | 0.1595 | 0.2243 | 0.2686 | 0.3917 |

Both halves are India and the split is group-aware, so exchangeability holds and
the bound does too — which is the point of also having a case where it does not.

### The transfer violation is now sharper

With the grid reaching 0.001, Model A calibrated on non-India becomes feasible at
alpha 0.20, which it previously was not:

| alpha | tau from non-India | risk on non-India | risk on india_test |
|---|---|---|---|
| **0.20** | 0.004 | 0.1905 | **0.7317** |
| 0.30 | 0.024 | 0.2980 | **0.8100** |
| 0.50 | 0.183 | 0.4975 | **0.8777** |

The bound holds in-domain and is exceeded by **3.8x** at alpha 0.20 — a stronger
statement of the same failure than D070 could make, because the tighter alpha is
now reachable.

Primary loss stays IoU 0.5 (D070 unchanged).

## D077 — T10: the certificate holds, breaks under shift, and is not free

**2026-09-28 · Accepted · completes T10 · D075 is reserved for the video metric**

`scripts/exp_conformal.py`, locked predictions only, loss = image-level fraction
of GT potholes missed at IoU 0.5, tau grid 0.001-0.990 step 0.001 (D076).
Test set `india_test`. Outputs `results/T10/{conformal.json, conformal.md, *.png}`.

### Model B carries the certified India result

| alpha | tau-hat | test risk | instance miss | **false alarms / image** |
|---|---|---|---|---|
| 0.05 | infeasible (floor 0.087) | - | - | - |
| 0.10 | 0.001 | 0.0867 | 0.0993 | **31.2** |
| 0.20 | 0.008 | 0.1499 | 0.1646 | **7.5** |
| 0.30 | 0.029 | 0.2572 | 0.2833 | **2.3** |
| 0.50 | 0.117 | 0.4260 | 0.4746 | 0.43 |
| 0.70 | 0.298 | 0.6584 | 0.7046 | 0.09 |

### The guarantee is checked where it lives: in expectation, over re-partitions

CRC promises *expected* risk <= alpha; one split can land above it legitimately.
So `india_cal U india_test` was re-partitioned 200 times by **scene group**
(D064; 2,017 units, 196 multi-image, zero groups crossing the original split;
realised calibration halves 1,156-1,161 images):

| case | alpha 0.10 | 0.20 | 0.30 | 0.50 | 0.70 |
|---|---|---|---|---|---|
| **B, india_cal** | 0.0941 (168/200 feasible) | 0.1918 | 0.2961 | 0.4962 | 0.6960 |
| P, india_cal | 0.0993 (128/200) | 0.1930 | 0.2984 | 0.4968 | 0.6963 |
| A, india_cal | infeasible | infeasible | infeasible | infeasible | 0.6818 |
| **A, non-India** | infeasible | **0.7049** | **0.7962** | **0.8748** | **0.9500** |

**Every India-calibrated mean sits at or below alpha, at every feasible alpha.**
About half of individual draws land above alpha, which is what a tight marginal
bound looks like — not a failure.

**Non-India calibration exceeds alpha in all 200 draws at every alpha**: promised
0.20, delivered 0.70. The shift violation D070 found on one split is not a split
artefact.

Near the floor, feasibility is itself random: at alpha 0.10 B abstains in 32 of
200 draws and P in 72. Those means are over the draws where the procedure issued
a threshold, which is conditioning, and is stated as such.

### The certificate controls misses and nothing else

At alpha 0.10 the certified threshold is **0.001** — keep every box the detector
emits — and B flags **31 phantom potholes per image**. False alarms fall below one
per image only at alpha 0.50, i.e. once the system is allowed to miss half the
potholes. **This detector can certify a low miss rate or a usable false-alarm
rate on Indian roads, not both.** That is a property of the detector (D069's
confidence problem), not of CRC, and it is the most decision-relevant number in
T10: any downstream use that consumes tau-hat inherits its false alarms.

`false_alarms_vs_alpha.png` draws this. It is one figure beyond the spec's two,
added because the trade-off is the finding.

## D078 — T11: the drift alarm needs a CUSUM reset to see a late shift

**2026-09-28 · Accepted · amends the T11 statistic; the spec's is kept beside it**

`scripts/exp_drift.py`, Model A predictions (nonindia_val open, india_full
locked). Frame score 1 − mean(top-3 confidences), eps 0.5. `nonindia_val` split
50/50 into a 3,071-frame reference bag and a 3,071-frame null pool; shift streams
are 500 null frames then shuffled India frames. Median frame score is 0.770
non-India vs **0.981** India, so the signal is large.

### As specified, the alarm misses the shift

| | null false-alarm rate | detected after shift | never | median delay |
|---|---|---|---|---|
| **plain power martingale (spec), M >= 100** | 0.005 | **6/200** | 193 | 1,248 frames |

The null side is fine — 1 in 200 against Ville's 0.010. The shift side is not.

**Cause, measured rather than assumed.** Under the null the plain martingale's
log-wealth drifts by `log eps + (1 - eps)` = **−0.193 nats per frame**, without
bound. After the 500-frame prefix it sat at **−94.2** (predicted −96.5), so a
shift must first repay ~94 nats before it can reach log 100 = 4.6, while the
growing bag absorbs India frames and dilutes each new p-value. Varying only the
prefix, on 40 streams each:

| null frames before the shift | 0 | 100 | 500 |
|---|---|---|---|
| detected | 40/40 | 39/40 | **0/40** |
| median delay | 42 | 245 | — |

**Why it matters.** The plain martingale tests exchangeability *from the start of
the stream*. Its sensitivity decays linearly with uptime. A survey vehicle runs
in-domain for hours before it crosses into new territory, and 500 frames is
~17 s of 30 fps video — as specified, the alarm is blind after the first minute.

### The fix, and what it costs

`DriftMartingale(cusum=True)` floors log M at zero, so no debt accumulates. The
guarantee changes: Ville's *P(ever alarms) <= 1/C* becomes Lorden's *E[frames to
a false alarm] >= C*. That is a much weaker promise per unit of C — at C = 100
the CUSUM null false-alarm rate over a 3,071-frame stream is **0.970** — so the
threshold must be far larger.

**Threshold chosen by a rule fixed in config before any shift stream ran**: the
smallest value in {10², 10³, 10⁴, 10⁵} whose null false-alarm rate is within the
spec's own budget 1/100.

| C | 100 | 1,000 | **10,000** | 100,000 |
|---|---|---|---|---|
| null false-alarm rate | 0.970 | 0.290 | **0.005** | 0.000 |

### At matched null false-alarm rate

| | null false-alarm rate | detected after shift | early | never | median delay | p90 |
|---|---|---|---|---|---|---|
| plain (spec), M >= 100 | 0.005 | 6/200 | 1 | 193 | 1,248 | 1,538 |
| **CUSUM reset, M >= 10⁴** | 0.005 | **197/200** | 3 | **0** | **77** | 121 |

**Every shifted stream alarms, median 77 India frames after the shift** (range
22–203). At 30 fps that is ~2.6 s; at a survey's one frame per ~5 m, ~400 m.

**One caveat carried forward.** C was selected on the same null streams its 0.005
is measured on, so that number is mildly optimistic. The out-of-sample check is
the 500-frame null prefixes of the shift streams, independently drawn: CUSUM
alarmed inside them in **3 of 200**. That is the better estimate of its
false-alarm rate on short runs, and it is above the in-sample figure. Three
events cannot pin it down; they are reported, not smoothed.

The spec's statistic is kept in the library and in the results because it is
what T11 asked for and what the comparison is against.

## D079 — T12: robustness changes decisions; maximising benefit defers the worst roads

**2026-09-28 · Accepted · completes T12 · supersedes the scalar T12 simulation**

### The simulation could not answer its own question

The first T12 reduced damage to one scalar and applied one global stand-in
recall of 0.75: `observed = true_damage * recall`. Scaling every segment by the
same constant cannot change a ranking, and the knapsack's choice is invariant to
it — so detection error changed no decision, and the robust variant (divide by
1 − alpha, another uniform constant) chose exactly what nominal chose, by
construction. Rebuilt per class: distress instances drawn per class, each found
at **Model B's measured recall for that class** at T10's certified threshold,
condition scored through the real `vision_density -> deduct_value ->
vision_estimated_pci` pipeline. Generator fixed on the true condition
distribution alone, against a target declared before adjusting (median in
Satisfactory, 10–20% Poor or worse; 16/4/8 instances per unit level gives 71.1
and 20.7%). Exact optimiser parallelised over 14 workers; 2,000 networks.

### Operating point: alpha 0.50, by a rule, because false alarms are not modelled

T10 (D077) showed tight certificates flood false alarms: 31 per image at alpha
0.10. This simulation models misses only, so it is honest only where false alarms
are rare. **Headline alpha = the tightest certified alpha at which B raises under
one false alarm per image: 0.50** (tau 0.117, 0.43 per image; recall linear
0.36, alligator 0.64, pothole 0.53). Alphas 0.10 and 0.30 run as declared
sensitivities and are optimistic by construction.

### Results (1,000 paired networks per regime; full tables in `results/T12/`)

- **Robust changes decisions.** At alpha 0.50 it picks a different repair set in
  95–100% of networks under uniform traffic (the scalar design: 0%).
- **Robust helps, modestly.** Share of oracle benefit, uniform traffic: nominal
  95.2–96.7%, robust 95.7–97.2%; every paired interval clears zero. Detection
  error costs 3–5% of achievable benefit; the correction recovers about a tenth.
- **At alpha 0.10 there is nothing to correct**: recall is already 0.87–0.96 and
  the factor is 1.11; robust and nominal agree on 53–91% of networks.
- **Robust repairs fewer of the true worst 20 (−0.8 to −3.4 pp), because it
  optimises better.** Its worst-20 coverage sits between nominal's and the
  oracle's at every uniform budget. A tempting alternative — that the worst roads
  are dominated by the crack classes the pothole-only correction ignores — was
  measured and is false (worst-20 deduct: alligator 45% vs 48% overall, pothole
  40% vs 36%).

### The finding that outranks robustness

**The oracle — exact optimiser, perfect information — repairs 0.5% of the true
worst 20 at a 10% budget under uniform traffic; greedy worst-first repairs 39%.**
Benefit per unit cost is hump-shaped in damage: light damage is poor value
(mobilisation dominates, 9.8 per 100k), moderate damage is best (~31), and the
worst damage is worse value again (20.5 at p99) because the log deduct saturates
while cost rises linearly with area. The true worst 20 average a value-rank of
117 of 200. Maximising network benefit therefore defers the worst roads — the
optimise-versus-worst-first split, reproduced from the scoring design. Magnitude
depends on the cost model and deduct shape; direction does not. Greedy pays for
its coverage: 68.5% of oracle benefit at 10%, below random's 76.4%.

**Consequence for T16:** the dashboard must report both objectives. Showing only
the optimiser's plan would recommend deferring every failed road at a tight
budget, silently.

### Scope and caveats

- The correction is pothole-only because the certificate is: cracks stay
  under-counted (0.36×, 0.64×). A per-class certificate needs a per-class CRC run.
- `band()` now assigns a continuous score to the band whose lower edge it has
  reached; the spec's integer edges left one-point gaps (commit 800f7c7).
- `segment_distress()` implements the spec's counts-per-100 m fallback, which the
  scoring docstring had promised and nothing implemented, and carries the unit
  with the value.
- Scoring remains a monotone proxy after Ibragimov et al. (Sensors 2024); ASTM
  D6433 deduct curves are not used.

## D080 — Scope: a detection count is discrete defects, not surface condition; B's Bengaluru silence is domain, not scale

**2026-09-28 · Accepted · extends D069 · uses D075 and D078 · D074 stands**

On the Bengaluru dashcam clip (`2DV-cYmIvT4`, CC BY, RT Dashcam; first 180 s) the
road at t≈100–110 s is broken, muddy and water-filled, and Model B is close to
silent there. That was proposed as an **extent** failure: damage too large to read
as one object. The measurements below do not support that cause. They support a
narrower scope statement and a different cause.

Evidence: `scripts/exp_video_extent.py` -> `results/video/2DV-cYmIvT4/extent.json`,
`scale.png`, `drift.png`; `scripts/eval_video.py --model B|P` ->
`results/video/2DV-cYmIvT4/{B,P}/summary.json`.

### Scale does not explain it

Ten frames, t = 100…109 s, Model B at conf 0.05. Padding shrinks the damage
relative to the image; the zoom arm (lower-centre half-frame, ~2x) enlarges it.

| condition | frames with any box | boxes | **pothole boxes** | max conf |
|---|---|---|---|---|
| pad 1x | 2/10 | 4 | **0** | 0.282 |
| pad 1.5x | 3/10 | 10 | **0** | 0.220 |
| pad 2x | 1/10 | 1 | **0** | 0.110 |
| pad 3x | 0/10 | 0 | **0** | — |
| zoom 2x | 3/10 | 6 | **0** | 0.290 |
| *control: Model P, pad 1x* | *6/10* | *11* | ***11*** | *0.375* |

"Too large" predicts pothole boxes rise with padding; "too small" predicts they
rise with the zoom. **Neither happens.** On the same frames at the same conf, Model
P finds 11 pothole boxes in 6 of 10.

**GT extent.** india_train relative box area (w·h): all classes median 0.0208
(IQR 0.0070–0.0687, max 0.668, n 4,340); pothole median 0.0085 (IQR 0.0036–0.0210,
max 0.307, n 2,025). Drawn by eye on the t=105 s frame:

| extent | relative area | percentile, pothole GT | percentile, all GT |
|---|---|---|---|
| the whole degraded stretch | 0.1265 | 97.0 | 86.1 |
| **one discrete water-filled pothole** | **0.0045** | **31.0** | 16.5 |

The stretch is larger than almost every pothole label, but **the individual
potholes on it are ordinary pothole-sized objects**, and B misses those too. Where
D069 found India labels damaged stretches while the model marks discrete defects,
here discrete defects of a typical size are present and still unseen. The binding
failure is not the size of the damage.

**B is near-silent, not silent.** "Nothing even at conf 0.05" holds for the frames
at whole seconds. Across all 300 frames of the window, B emits a pothole box at
>= 0.05 in 37 frames, >= 0.25 in 5 (max 0.341), and never on the same track in 3
of 5 frames, so D075 confirms none.

### Model P sees this road; B does not

Identical settings (conf 0.25, ByteTrack, horizon 0.66, D075 3-of-5), whole 180 s:

| | confirmed tracks | tracks seen | raw boxes | gated above horizon | tracks in t=100–110 s |
|---|---|---|---|---|---|
| B | 9 | 14 | 206 | 0 | 0 |
| P | **100** | 133 | 2,191 | 36 | 3 (3–5 frames each) |

Tracks, not potholes (D075), and no ground truth, so neither count is scored.
**Report only: D074 stands** — this clip is not a selection set. Twelve
BharatPotHole training images, sampled at seed 0, show what P learned from:
forward-facing wide-angle dashcams pitched up like this one, wet roads, and
water-filled potholes labelled as small discrete boxes. Eight `india_train`
images at seed 0 show what B learned from: square 720x720 phone frames through the
windscreen, a narrower field of view, and dry, dusty, sunlit road, with no standing
water in any of the eight. **B's
silence is a training-domain limit** — camera geometry and the appearance of wet,
muddy potholes — **not a limit of what a detector can do on this road.** P also
misses most of the stretch by eye, so no model here makes the stretch well
covered.

### The drift monitor does alarm — on the footage, not the stretch

D078's monitor, Model B's frame scores against **B's own `india_val` bag** (772
frames; B's scores need B's bag), scored through the frozen eval block with
`model.val`'s multi-label NMS. Re-scoring 20 `india_val` images through the video
path reproduced the bag to max |delta| 3.3e-6.

| statistic | every frame (30 fps) | every 30th frame (~1 fps) |
|---|---|---|
| **CUSUM, M >= 10⁴ (D078)** | alarm **1.0 s** | alarm **15.0 s** |
| plain, M >= 100 (spec) | alarm 0.9 s | alarm 6.0 s |

Median frame score: video **0.996**, `india_val` 0.952 — 0.745 on its 304 frames
with GT, 0.988 on its 468 without. The video scores above even undamaged Indian
road, and 4,283 of 5,400 frames carry no box of any class at >= 0.05. So the
monitor flags that B is out of its domain **from the first second**, about 100 s
before the degraded stretch. It is a verdict on the footage and camera, not on the
broken road.

Two limits on that alarm, carried forward:

- **At 30 fps the monitor forgets.** Every frame joins the bag, the bag becomes
  mostly this video, and the CUSUM falls back to 0 at 74.3 s. Through t=100–110 s
  it is above threshold **0%** of the time. At ~1 fps it never returns to 0 and is
  above threshold 100% of the window. **An alarm must be latched by whatever
  consumes it**; the running statistic is not a state.
- **Video frames are not exchangeable.** D078's false-alarm guarantee assumes
  exchangeable frames; consecutive frames of one drive are strongly correlated even
  at 1 fps. No in-domain Indian video exists here to measure the null on video, so
  this alarm's false-alarm rate is unmeasured. It is consistent with the domain
  finding above; it does not prove it on its own.

### The scope limit

1. **A detection count measures discrete defects the detector recognises. It is
   not a measure of surface condition.** On continuously degraded surface there is
   no discrete-defect count that represents the road, and D075's track count is
   biased in both directions on top of that.
2. **A low count, or silence, is not evidence of a good road.** Silence from a
   detector outside its domain looks exactly like a clean road in the count. The
   D078 monitor is the only runtime signal that separates them, and only when its
   alarm is latched.
3. **B's per-pothole video results are claimed for RDD-like imagery only.** On
   forward-facing wide-angle dashcam footage of wet, water-filled potholes, B is
   near-silent, and a model trained on similar footage (P) is not. That is a
   property of B's training data, not of the task.

## D081 — Dashcam video: P fires where B does not; whether that is transfer is Open; run both on Chennai

**2026-09-28 · Accepted (the counts and the deployment rule) · the transfer claim is
Open until GT scoring · D074 stands**

### Two results that pull in different directions

**Forward-facing wide-angle dashcam video** (`2DV-cYmIvT4`, 180 s, D080; identical
settings: conf 0.25, ByteTrack, horizon 0.66, D075 3-of-5):

| | confirmed tracks | raw boxes | tracks seen |
|---|---|---|---|
| B | 9 | 206 | 14 |
| P | **100** | **2,191** | 133 |

**RDD-style `india_test`** (D074, locked, 1,156 images, 413 pothole boxes): pothole
AP50 B 0.3582 vs P 0.3559, delta −0.0031 with 95% CI [−0.0361, +0.0298] over 1,037
scene groups. **Indistinguishable.**

### The hypothesis, not yet a result

**"On dashcam video P transfers and B does not."** Evidence for it: on ten frames at
conf 0.05, P finds 11 pothole boxes and B none under any padding or zoom (D080),
and BharatPotHole, which P was trained on, looks like this footage.

**Why it is not accepted yet: part of P's advantage may be firing rate, not skill.**
P emits **10.6x** B's raw boxes and 11.1x its tracks. A model that fires more will
confirm more tracks whether or not they are potholes. D074 shows the same
direction on held-out Indian roads: at conf 0.25, P's recall is higher by +0.029
(0.3753 vs 0.3462) but its false alarms per image are higher by +28%
(0.1678 vs 0.1315). Neither track count is scored, and tracks are not potholes
(D075).

**What decides it:** `scripts/score_video_gt.py` against a hand-counted 60 s
window of the same clip. It reports, per model, potholes hit of those present,
duplicate tracks, false alarms per minute and median frames per hit. A new entry
records the outcome. **Until then, no report may state that P transfers to dashcam
video.** The permitted statement is "P fires on this footage and B does not".

### Deployment rule: run both on Chennai footage, report both

The Chennai rig (U5, T15) is dashcam-like by the user's description (2026-09-28);
no Chennai footage has arrived, so that is not yet verified here.

- **B for 3-class scoring.** P is pothole-only. The vision-estimated PCI needs
  cracks, and only B sees them.
- **P for potholes.** It fires on dashcam footage where B is near-silent.
- **Report both side by side, never one alone.** If P and B disagree on Chennai,
  the disagreement is the finding.

Costs and open points:

- **Two detectors per frame.** On this Mac, B runs at p50 11.3 ms and P at 12.2 ms
  (D080 runs), so running both roughly halves throughput. The Jetson cost is
  unmeasured (U6).
- **Two pothole channels now exist**: B's pothole class and P. They must not be
  summed into one `vision_density`, or every pothole seen by both counts twice.
  Which one feeds the PCI proxy is **not decided here**.
- If Chennai footage turns out RDD-like rather than dashcam-like, D074 applies and
  P is expected to add nothing measurable. Reporting both makes that visible
  rather than assumed.

## D082 — Potholes from Model P, cracks from Model B, never summed

**2026-09-29 · Accepted · the T12 re-run under it is Open · settles the channel
D081 left open · builds on D074 · D081's transfer claim stays Open**

*Written 2026-10-03, after D083, which cites it. The decision is the user's,
recorded in the T16 plan on 2026-09-29; the entry itself was never written.*

D081 left two pothole channels, B's pothole class and P, with a rule (never sum
them) and a gap: "Which one feeds the PCI proxy is **not decided here**." This
entry fills the gap.

### The rule

- **The pothole term of `vision_density` comes from Model P.** D074 selected P
  for pothole detection and carried it forward as "no worse than B on held-out
  India"; on dashcam video it fires where B is near-silent (D080, D081).
- **The crack terms (`linear_crack`, `alligator_crack`) come from Model B.** P is
  pothole-only.
- **Never summed.** B's pothole class does not enter `vision_density`, or every
  pothole both models see counts twice. B runs anyway for cracks, so its pothole
  output is still reported beside P's under D081's run-both rule; it does not
  score.

### The evidence does not yet reflect the rule

**Every T12 number was simulated at Model B's recall for every class, potholes
included.** That covers the allocation results, the T16 dashboard (D083) and the
Allocation section of `results/RESULTS.md`. None of them is a D082 number.

- The dashboard, RESULTS.md and the `detector` field of
  `results/T12/demo_network.json` say so wherever a T12 number appears.
  `results/T12/allocation.json` predates this entry: it holds B's per-class recall
  without naming the model.
- **Re-running T12 with P's pothole recall is Open, not done.** Until it runs, no
  repair plan, share of oracle benefit or true-worst-20 count in this project
  follows D082.
- What D082 already changes is wording, not numbers. The dashboard header and
  RESULTS.md state the attribution, and both name P's T10 rows as the operative
  pothole certificate; B's rows are shown because T12 ran on B.

### Nothing enforces it

`survey/scoring.py` scores detections by class and has no notion of which model
produced a detection. **The rule is applied by what the pipeline feeds it, not by
a check.** Hand it B's pothole boxes beside P's and it sums them without
complaint. No code yet runs both detectors into one survey. When one does, a test
that B's pothole detections leave `vision_density` unchanged turns the rule into
a check.

### Cost: P's false alarms, which T10 does not bound

- **Held-out India.** On locked `india_test` at conf 0.25 (D074), P raises 0.1678
  false alarms per image against B's 0.1315 (+28%), for recall 0.3753 against
  0.3462.
- **Dashcam video, one AI-annotated window.** On t = 120–180 s of `2DV-cYmIvT4`
  (17 potholes; `results/video/2DV-cYmIvT4/gt_score.json`), P's confirmed tracks
  hit 10 and B's 4. P's false alarms run at 20 per minute against B's 1, and P
  adds 7 duplicate tracks to B's none. The caveats:
  - It is a single 60 s window.
  - It was annotated by Claude (AI) in one pass, not the hand count D081
    anticipated. It is not strictly blind: the CSV header records that the
    annotator had seen some model output for this range.
  - Matching is interval-only, with no spatial check, so hits are an upper bound.

  **This is not a verdict on D081's transfer claim.**
- **The certificate controls misses only.** T10 certifies P's pothole miss rate,
  not its false alarms. A false alarm in the pothole term lowers an evaluation
  segment's vision-estimated PCI exactly as a real pothole does, and no certified
  bound limits how far.

### What this does not decide

**Whether P transfers to dashcam video.** D081's claim stays Open. The video
numbers above are the cost of this choice. The video-GT plan reserves the
settling entry for after the user's go-ahead, and none is recorded. Until then
the permitted statement is still "P fires on this footage and B does not".

## D083 — T16: the dashboard stays one offline HTML file; both plans, always

**2026-10-03 · Accepted · reaffirms D020 over the RoadSight T16 spec · applies D079 and D082 on the page**

### The spec and the log disagreed

RoadSight's T16 specified a Streamlit app. **D020 (Accepted) makes the dashboard one
self-contained offline HTML file and rejects Streamlit by name** ("looks like a
research notebook, needs a process running"). D055–D058 amended other spec items
but never this one. Asked directly, the user kept D020.

### What was built

`scripts/build_dashboard.py` writes `results/dashboard/index.html`: one file,
~1.2 MB, figures embedded, no external URL, no server. Rendering lives in
`certain_road.dashboard` (`results`, `plans`, `render`, `template.html`), so
import-linter governs it; the only cross-package import is `survey` (allowed).

- **The slider never shows one plan (D079).** It selects among plans the real T12
  optimiser computed at every 1% from 5% to 60%, for observed and conformal robust
  ranking. At every position the optimiser and worst-first sit side by side with
  true-worst-20 coverage and share of oracle benefit, a 200-segment strip ordered
  by true condition, a road-by-road table of the worst 20, and a live sentence the
  slider rewrites. On the demo network at 10%: optimiser 95% of oracle and 0 of
  the worst 20; worst-first 65% and 7.
- **"True worst 20" needs truth**, which only a synthetic network has. The view
  reads one T12 network (`exp_allocation.py --export-demo`, seed 0 fixed in
  advance, uniform traffic); the dashboard never re-implements the generator.
- **Attribution (D082).** The header states that potholes come from Model P and
  cracks from Model B, never summed. Every number from T12 says, where it
  appears, that the simulation detected every class — potholes included — at
  Model B's recall, not P's.
- **Not run is visible.** Map (T14 produced no edge database) and Simulation (T13
  has no results) render "not run" naming the path looked for. Paths print
  relative; an absolute path would leak a home directory into a shared file.
- **Light only**, from the use scene: a projector in a lit room, and every
  embedded figure is a light plate. A departure from the chart guidance's
  dark-mode default, made on purpose.
- **Figure alt text is generated from the result files.** Hand-written alt text
  once overstated T11 ("every shifted stream alarms within a few hundred India
  frames" counted the 3 streams that alarmed before India began); a test pins the
  generated text to `drift.json`.

### Departures from the spec, stated

- No folium map and no edge-database picker: there is no database to pick or
  draw. When T14 produces one, Leaflet is vendored inline per D020, never loaded
  from a CDN.
- No `DESIGN.md`/`PRODUCT.md`: the user did not ask for new root files, and
  `docs/design.md` is this project's design spec, which a generated DESIGN.md
  would collide with.

### Review

An independent fresh-context design review (impeccable finish review) returned
**fix** twice. Round one: the T12 caveat sat below the projector fold, the
worst-first column vanished at 390 px, the T12 figure sat 7,000 px from its
table, and dark mode would glare. Round two: two hand-written alt texts
contradicted `drift.json`, the brand broke at 390 px, and one lede ran into a
Source line. All were fixed; the last three were verified by screenshot and test
rather than re-scored by the reviewer.

## D084 — The locked run's absolute symlinks stay; a test pins them and every home-directory path

**2026-10-04 · Accepted · release cleanup · `results/LOCKED/` is never rewritten · uses D040**

### What is committed

`results/LOCKED/P_india_heldout_run/gt_root/images/` holds 2,312 symlinks, committed
in `ac77039` (D074). `scripts/eval_locked.py` built them for the 1-class case with
`symlink_to(....resolve())`, so every target is an absolute path into this
machine's `data/yolo/images/`. On any other clone they point at nothing.

### Options

| | Touches LOCKED | On a fresh clone |
|---|---|---|
| **A. Leave as committed** | no | dangle, as now |
| B. Rewrite as relative links into `data/yolo/images/` | 2,312 blobs | still dangle (`data/` is gitignored), but inside the repo |
| C. Untrack and gitignore | 2,312 deletions | nothing to dangle |

**Chosen: A** (the user, 2026-10-04). The rule that `results/LOCKED/` is never
modified outranks tidiness, and none of the three makes the images available on a
clone, because they live in gitignored `data/`. The links carry nothing the run
lacks without them:

- `gt_root/india_heldout.txt` lists the same 2,312 images;
- the 2,312 derived labels are committed as regular files;
- the scores are in `P_india_heldout.json` and `val/predictions.json`.

The images were inputs to a one-shot evaluation, never its outputs.

### The guard

`tests/test_repo_hygiene.py` fails if either of these holds:

- a committed symlink has an absolute target or climbs out of the repository, other
  than exactly these 2,312;
- a committed file contains a home-directory path (one under `/Users` or `/home`),
  other than 19 pinned files.

Of the 19, 10 are provenance under `results/`: 4 in LOCKED, including the run's
`labels.cache`, and 6 verification and open-evaluation records. The other 9 are the
`configs/data/*.yaml` that `scripts/build_pool.py` writes with an absolute `path:`.
Those 9 stay absolute because `scripts/mps_sanity.py` passes `model_a.yaml` to
ultralytics unresolved, and ultralytics resolves a relative `path` against its own
`datasets_dir` (D040). Making them relative first needs that consumer to resolve the
path itself, as `certain_road.perception.train` does. That change is not made here.

Changing a pin, including fixing one, means editing the test, so the change shows in
review.

### Open when written (resolved in the update below)

- **`eval_locked.py` still writes absolute links.** A future 1-class locked run would
  add more and fail the guard. Linking relatively is a small change to the
  evaluation script. It is recorded here so the next locked run doesn't discover it
  by failing CI.
- **`configs/data/*.yaml`** become relative only after `mps_sanity.py` resolves them
  (above).

### Update, 2026-10-04: the links are fixed at the source; `configs/data` stays absolute

- **`eval_locked.py` now writes relative links** (`d8d1b2c`): each link is relative
  to its own directory, so it resolves on any clone that has `data/`.
  - `tests/test_eval_locked_links.py` runs the link-building step on a tiny temporary
    fixture and fails on any absolute or escaping link.
  - Run once on the real Model P held-out split in a scratch directory under the
    gitignored `runs/`: 2,312 relative links, all resolving inside the repository.
    Ultralytics' own dataset loader found 2,312 images and 820 pothole boxes through
    them, as the locked run reports. No model was loaded. The scratch directory was
    deleted.
  - The 2,312 existing links stay as committed; `results/LOCKED/` is not rewritten.
- **`configs/data/*.yaml` stay absolute, by the user's decision (2026-10-04).** The D040
  reason above stands. The release cleanup's criterion "no home-directory path outside
  `results/`" is therefore **not met for these 9 files, deliberately**. They stay
  pinned.
- **A future locked run still writes two files that hold home paths:**
  - its `data.yaml`, whose absolute `path:` is what ultralytics needs (D040);
  - ultralytics' `gt_root/labels.cache`.

  Committing such a run means adding those two files to the test's pins, as the
  existing runs' are. Neither file is changed here, because that would alter what
  ultralytics reads during a one-shot run.

Nothing in this entry is open.

## D085 — The RoadSight spec reinstated conformal prediction; no decision recorded it

**2026-10-04 · Accepted · supersedes D051 · records a reversal made at T0 (`a23bf6a`)**

D051 (2026-09-05) cut conformal prediction from the 15-day sprint under schedule
pressure, and said what that cost: CP was the research novelty (D004, D005), and
without it the abstain path falls back to a confidence heuristic.

**The RoadSight specification reversed the cut.** Adopting it as T0 (`a23bf6a`,
2026-09-22) brought in T10, conformal risk control on the pothole miss rate, and made
the certified miss rate the project's core claim. T10 was then built and measured:
D064, D070, D076, D077 and `results/T10/`.

**No separate decision reinstated it.** Of the entries between D051 and T10's own:

- D057's module table lists `conformal.py` as "write new";
- D055 retargets T10's class index;
- D054, written the same day the spec was adopted, still dropped documentation built
  on "the conformal layer that D051 cut".

None of them reverses D051, which stayed Accepted while T10 was built over the cut it
records. This entry closes that gap. D051 is marked superseded, and its text is left
intact.

**What of D051 still stands.** Its ADAS-inspired driving behaviours. This entry
reverses only the cut.

## D086 — Simulator textures: provenance and leak audit

**2026-10-05 · Accepted**

The MuJoCo demo's road textures are 49 photos in `data/raw/trial_textures/` (gitignored),
listed with their sources in `docs/texture-provenance.md`. They are not the user's
own photos. The 18 potholes come from QR4Change (Pune, Mendeley doi:10.17632/zndzygc3p3.2).
The 31 crack and asphalt photos come from BD-N6 (Bangladesh NH-N6, Zenodo
doi:10.5281/zenodo.18072573 and .18114226). Both are CC BY 4.0, so both must be credited
wherever a render is shown.

**No model ever trained on either dataset.** Neither appears in any config, split, job,
upload manifest, script or earlier decision. No QR4Change image exists under `data/` outside
the texture folder. The only Mendeley dataset in this log is `tp95cdvgm8` (D039, NO-GO).

**The audit**, with the method unchanged:

- Copies (D063/D066 `norm_vec`, threshold 0.93), against `india_train`, `nonindia_train` and
  BharatPotHole `train`: no pair at or above 0.93; the maximum is 0.8887.
- Crops (ORB with a RANSAC homography, flag at 30 inliers, against each texture's 20 nearest
  training images): at most 8 inliers; nothing flagged.

All 49 are clean. The crop check's positive control caught 9 of 10 real crops. It is
therefore evidence against crops, not proof, and provenance carries the rest.

Which textures the simulator uses is a separate curation choice (blur, glare, class): it is
recorded in `configs/sim/textures.yaml`, not here.

## D087 — A MuJoCo demo simulator: synthetic road, real models and survey code

**2026-10-05 · Accepted · for the DA-2 review · not T13**

`sim/mujoco/` renders a seeded two-lane road, 400–600 m long, in five presets (good,
moderate, poor, mixed, random). The road is built from the trial photos audited in D086.
It is seen through the design camera from the `sim:` block of `configs/project.yaml`: 1.3 m
high, 10° down, HFOV 1.2 rad, 1280×720. `configs/sim/robot.yaml` describes the indoor robot
and is not used. Each road writes its ground truth (class, centre, true extent, texture) as
JSON, and the same preset and seed give byte-identical ground truth
(`tests/test_mujoco_road.py`).

**What is real and what is simulated.** Real: the detectors (Model P for potholes, Model B for
cracks, never summed, per D082), the `core.geometry` IPM, and `survey` scoring and
allocation. The simulator calls them and reimplements none of them. Simulated: the road, its
damage layout, the light, and the camera's motion and sensor. Every number the demo shows is
a measurement on a synthetic road. It is never reported beside real-data results without
that label, and nothing is written to `results/`.

**How the damage is drawn, and the limits of each choice.**

- **Baked into the road texture tiles.** MuJoCo has no decals. Baking makes each instance
  perspective-correct on the road plane by construction, lit by the scene's sun.
- **Real sizes.** Potholes are 0.3–1.2 m across. Crack photos keep their photographed scale,
  about 2,000 px/m, estimated from the size of the aggregate. Linear cracks are enlarged
  1.0–1.6× and alligator areas 1.4–2.2×, because real alligator areas run 1.5–3 m.
- **Visibility fixes.** At step 1 the damage first rendered as invisible smudges.
  - A mean colour match averaged each patch back to plain asphalt, so the match now uses the
    clean surface between the cracks (a percentile).
  - MuJoCo's isotropic mipmaps erase thin cracks at grazing angles, so frames are rendered 3×
    and downsampled, and crack lines are deepened.
  - Potholes are shaded as depressions, aligned to the sun. Standing water gets a sky sheen.
    That sheen is right only for grazing views, which are the only views this camera has.
- **Keep left**, as in India. The vehicle drives the left lane.
- **`mujoco` is a main dependency**, so the documented command works after a plain
  `uv sync`.

**Not T13.** T13 is the Webots detect-and-avoid trial matrix. This demo makes no claim about
avoidance, and T13 stays not run.

**Step-1 probe** on the showcase frame, at conf 0.25: Model P found all three driving-lane
potholes (0.50–0.62), the one at 10.8 m included. Model B found the 5.5 m alligator patch
(0.79) but not the one at 9.8 m.

## D088 — The demo's drive loop runs at 30 fps

**2026-10-05 · Accepted · extends D087 · applies D075 and D082 · keeps D006 for the survey**

`sim/mujoco/drive.py` drives the design camera at 20 km/h. On every frame, Model P and Model
B each track with ByteTrack under `configs/eval/video.yaml`, with D082's channel rule:
potholes come from P only, cracks from B only, and B's pothole channel is discarded. A track
is confirmed by D075's `confirm_step`, imported from `scripts/eval_video.py` rather than
copied.

**The frame rate is 30 fps, because confirmation depends on it.** D075's rule (the same ID in
3 of the last 5 frames) was set on 30 fps video. A first loop ran at 10 fps, which is real
time on this Mac. There, near damage moves far between frames, ByteTrack loses the ID, and
almost nothing confirms. Over the same 150 m of the poor preset, seed 0:

| | linear crack | alligator crack | pothole |
|---|---|---|---|
| 10 fps, confirmed | 0/3 | 2/7 | 0/8 |
| 30 fps, confirmed | 1/3 | 6/7 | 4/8 |
| detected in any frame (both rates) | 2/3 | 6–7/7 | 5/8 |

30 fps costs real time. The two models take about 24 ms a frame, so the full 512 m road runs
at 0.65× real time (142.8 s against 92.1 s). The drive is still simulated at 20 km/h, and
only the playback is slower.

**The gate is geometric.** The video lane gates at a hand-set fraction of frame height,
because downloaded footage has no camera model. The simulator has the design camera, so its
gate is the row where `edge.detect_range_m` (12 m) meets the road, from
`core.geometry.project`.

**The survey keeps D006.** Every 27th frame is a survey sample, one every
`edge.sample_every_m`. Step 3 scores only those, with no tracker involved. Tracks feed the
live view and step 4's recall against ground truth.

**Full poor road, seed 0, at 30 fps.** These are rough per-instance figures; step 4 scores them
properly. A hit is a confirmed track of the right class overlapping the instance's projected
box (IoU above 0.1).

- Linear cracks: 13 of 27 hit.
- Alligator cracks: 21 of 24.
- Potholes: 18 of 27.
- Confirmed tracks that never matched an instance of their own class: 1 linear, 11
  alligator, 14 pothole. Most of the pothole ones are Model P firing on alligator patches.

## D089 — The demo's live survey, drift panel and screen

**2026-10-05 · Accepted · extends D088 · applies D006, D078, D080 and D082**

Every 5 m survey sample is detected again with plain `predict`, by copies of P and B that
hold no tracker state, and `sim/mujoco/survey.py` scores it through `certain_road.survey`.
`sim/mujoco/screen.py` shows the drive on one 1920×1080 screen with four panels: camera,
survey map, counters and drift.

**D006's ROI is the 5 m strip of the driving lane, 3–8 m ahead.** D006 counts a fixed ROI on
each sample and spaces the samples so that footprints never overlap. This camera sees the road
from about 2.2 m to 12 m, so counting whole frames would count most damage twice. A box counts
on a sample when its base centre lies 3–8 m ahead and within half a lane width of the camera,
with the base centre found by `core.geometry.ground_point`. Samples are 5 m apart, so the
strips tile the road. A test checks that every drive-lane instance is counted by exactly one
sample. The strip starts at 3 m to clear the frame bottom (2.2 m), so a box cut off by the
frame edge never counts.

**The reference PCI takes the same path.** Each ground-truth instance is projected into the
sample as the box a perfect detector would draw, then counted and scored like a detection.
A test feeds those boxes back in as detections and gets the reference PCI exactly, for every
segment. `segment_drive` groups the samples, 10 to a segment.

**The drift panel shows the real monitor, and it does not fire where the brief expected.** On
each sample, B scores the frame exactly as `model.val` scored india_val, using
`exp_video_extent.val_mode_scorer`. D078's CUSUM (threshold 10⁴) runs against B's india_val
bag, as in D080. The scorer patches NMS for the whole process, so the patch is held to its
own calls, where it cannot change what the trackers see. Measured on the 103 samples of each
seed-0 road:

| Road | Mean frame score | CUSUM alarm |
|---|---|---|
| good | 0.992 | 55 m |
| poor | 0.897 | 295 m |
| mixed | 0.982 in the good stretch, 0.891 in the bad | 55 m, in the good stretch |

97% of india_val frames contain damage, and the bag's mean score is 0.879. On a clean road B
sees almost nothing, which looks unlike that bag. The monitor is one-sided and fires on low
confidence. On the mixed preset the bad stretch pulls the CUSUM down, not up. A road getting
worse is a change in condition, which the PCI reports, not a shift in domain. So the mixed
preset's moment is the band drop instead: the caption marks a segment that falls two bands or
more below the one before it. The reference bag was not changed to make the alarm fire where
it was expected.

**Detector confusion lowers the vision estimate, and is reported as found.** Over the first
110 m of the poor road, segment 2 scores 86.9 against a reference of 93.2. Model P marks an
alligator patch as a pothole. On one linear crack, B fires both linear (0.52) and alligator
(0.39), and P calls the same crack a pothole (0.31). Nothing is tuned against this.

*Correction, D090: in the drive itself the poor road's alarm comes at 150 m, not 295 m.*

## D090 — The demo's end screen: detection against ground truth, and both repair plans

**2026-10-05 · Accepted · extends D089 · applies D079**

`sim/mujoco/evaluate.py` scores a run from its logs and writes `end.json`, and
`screen.render_end` draws the result screen. `--end-only` redraws it without driving again.

**Detection is scored on confirmed tracks, in both lanes.** A confirmed track hits an
instance when, in some frame, its box overlaps the instance's projected box with IoU above
0.1 and the classes agree, as D088's rough figures did. Recall's denominator is every
instance that came into view nearer than the 12 m gate. A false alarm is a confirmed track
that never hit an instance of its own class, counted per km driven. Both lanes count, because
the camera sees both.

**The plans are the real allocators', on D079's pricing.** Each segment is an
`allocation.Segment` with its vision-estimated PCI. Its cost is D079's: mobilisation plus
`cost_per_m2` times the reference distressed area. `allocate_optimal` and
`allocate_greedy_worst_first` spend the same budget, by default 30% of the cost of repairing
every segment. Each plan is scored on D079's two objectives, both against the reference PCI:
the true benefit repaired, and how many of the true worst 3 segments it repairs. D079 counts
the worst 20 of 200 segments; a 500 m road has about 11.

**Poor road, seed 0:**

| Class | Recall | False alarms per km |
|---|---|---|
| pothole | 16 of 28 (57%) | 35.2 (18 tracks) |
| alligator crack | 22 of 24 (92%) | 7.8 (4 tracks) |
| linear crack | 14 of 27 (52%) | 0.0 |

At the 30% budget, worst-first repairs segments 7 and 8, for a true benefit of 58, and gets
2 of the true worst 3. The optimiser repairs segments 3, 5 and 8, for a true benefit of 50,
and gets 1 of 3. It maximises benefit as the vision estimate sees it, and that estimate puts
segment 3 at 86 when its reference is 97. Under uniform traffic D079 also found worst-first
close to optimal. This is one road; it is reported as found and nothing was tuned.

**The same seed gives the same result.** Two runs of poor, seed 0, gave byte-identical
`ground_truth.json`, `survey.json` (segments and drift trace) and `end.json`. Their frame
records were identical apart from timings.

**Correction to D089's drift table.** D089's alarm positions came from a probe that rendered
only the sample positions, so its sensor-noise draws differ from the drive's. On the poor
road the CUSUM hovers near the threshold, so the alarm position moves with the noise. The
drive alarms at 150 m, not 295 m. Step 5 records the drive's alarm position for every preset.
D089's conclusion stands.

## D091 — The demo's true worst N are damaged segments; all five presets run

**2026-10-05 · Accepted · refines D090**

**Only damaged segments can be among the true worst N.** On the good road every segment's
reference PCI is 100. D090's rule then made the "true worst 3" three tied, undamaged
segments, and gave worst-first 3 of 3 for spending budget on road that needs nothing.
`allocate_greedy_worst_first` does fill a leftover budget with zero-priority segments; that is
the real code's behaviour and is shown as it is. But covering undamaged road is not covering
the worst road. So the worst N are now drawn from segments with reference PCI below 100,
and a road with none shows "no damaged segment".

**All five presets, seed 0.** The table is in `docs/mujoco-demo.md`. As D090 promised, it
records the drift alarm position for every preset, measured in the drive itself: 65 m on
good, moderate and mixed, 145 m on random and 150 m on poor. Every alarm comes before any bad
stretch, which is D089's finding on every road.

## D092 — The demo's look v2: 3D potholes, surface marks and harsher light; v1 kept

**2026-10-05 · Accepted · extends D087**

The user asked for a road as close to a real one as possible, with today's simulator kept
as the fallback. `--look v1|v2` picks an overlay from `looks:` in `configs/sim/mujoco.yaml`.
v1 is the simulator at the `demo-v1` tag. Hashes of poor and mixed frames at four positions
are byte-identical to the tag's, rechecked after each change. v2 is now the default.

**v2 changes how the road is drawn, never the road.** A test checks that the ground truth is
the same in both looks.

- **3D potholes** (`sim/mujoco/relief.py`). Each road tile is a grid mesh, sunk 4–10 cm under
  each pothole and shaped by the baker's own outline. The scene's sun therefore lights and
  shadows real walls. The painted wall shadow is off and the painted depth darkening reduced,
  because the geometry now does that work. The ground plane drops to −15 cm; at −1 cm the
  holes showed it through.
- **Surface marks.** Repair patches, oil stains and dust off the verges, drawn from their own
  random stream. They are not damage and are not in the ground truth.
- **Light.** A harsher sun (diffuse 1.0, ambient 0.30), and trees, mostly on the left verge,
  whose hard shadows cross the driving lane.

These use plain geometry, procedural tints and the existing photos. There is no new texture
source.

**Measured once, after v2 was built, and not adjusted.** The table is in
`docs/mujoco-demo.md`. Pooled over the four damaged presets, pothole recall is 27/60 under v1
and 29/60 under v2. Alligator is 52/56 and 51/56, and linear 25/69 and 28/69. Pothole false
alarms per km fall on two roads and rise on two. At one run per preset, realism did not make
the damage easier to find.

**The pothole false alarms are crack confusion, not the new marks.** On poor and mixed, in
both looks, every confirmed pothole track that matched no pothole sits on an alligator patch
or a linear crack. None sits on a tree shadow, a repair patch, an oil stain or bare road.

**Drift.** v2 moves the alarm to 80 m on good, moderate and mixed, and to 150 m on random,
and removes it on poor. The clean opening stretch still sets it off, so D089 stands.

## D093 — A ROS 2 Jazzy demo on the Jetson: three nodes around the 2D simulator; ROS is one more `Transport`

**2026-10-06 · Accepted · extends D050; D050's rejection of Gazebo stands**

The user asked for a ROS 2 demo running on the Jetson the same day. JetPack 7.2 ships
Ubuntu 24.04, so the distribution is Jazzy. A Gazebo world, models and nodes is not a
one-day build on a freshly installed stack, and D050's reasons for rejecting Gazebo still
hold, so the existing 2D simulator is wrapped instead. `ros/certain_road_ros` holds three
nodes, a launch file and an RViz layout; every tunable is in `configs/ros/demo.yaml`.

- **`sim_node`** steps the bicycle model with the latest `/cmd_vel` and publishes the
  camera frame, the ground-truth boxes for that frame, pose, path and TF. It runs the trial
  matrix in turn, each scenario for its own frame count, as `run_scenario` does.
- **`perception_node`** runs Model P for potholes and Model B for cracks (D082) on CUDA, or,
  when torch, ultralytics or either weights file is missing, passes on the simulator's
  projected boxes. That fallback says PROJECTION-ONLY in the log, on `/perception/source`
  and on every annotated frame, so a recording cannot pass ground truth off as model output.
- **`planner_node`** runs `build_perception`, `next_state` and `command_for` unchanged.
  Only potholes steer (D049: cracks are survey material). A stale detection stream goes
  through the same `next_state` failsafe and stops the robot.

**ROS is one more `Transport` (D049, D050).** `RosTransport` implements
`canbus.transport.Transport` and publishes each `Command` as a Twist in physical units,
from `sim.model.command_velocity`; the vehicle reads it back with `command_from_velocity`.
The conversion drops `Mode`, which a Twist cannot carry. A test pins that the round trip
drives `step` identically. `driving/` cannot tell ROS from CAN.

**The simulator gets a camera frame.** `sim/project.py` turns a pothole straight into a box,
so there was no image to publish. `sim/camera_image.py` runs that projection backwards per
pixel, and a test pins that a rendered pothole fills its projected box. Building it exposed
that `project_pothole` under-reports a near pothole's width: it takes the width at the
disc's centre distance, short by 1–2 % at the ~0.9 m decision distance and 7 % at 0.5 m.
It is left unchanged because the trial matrix is asserted on it. The frames are flat-shaded,
far from the RDD2022 photos the detectors learnt from, so a detector missing these potholes
says nothing about real roads; `sim/mujoco` is the photographic renderer (D087).

**Evidence, per episode.** `planner_node` writes each episode to
`runs/ros/<UTC stamp>/episodes.jsonl`: whether it reached its `expect`, and whether its
drive-state sequence matches `run_scenario` on the same scenario offline. Measured on the
Jetson, 2026-10-06, projection-only: over two cycles of all eight scenarios, 17 complete
episodes all reached their expected state and 16 matched frame for frame. The 17th lost its
first frame, published before ROS discovery finished. `sim_node` now waits for every link
of the loop before starting its clock; a re-run then gave episode 0 all 60 frames, matching.
The loop runs at 9.97 Hz against a 10 Hz target.

**Environment.** The nodes run on the project's own uv venv, built on the system Python
3.12 with system site packages so that ROS's `rclpy` loads into it. The locked PyPI
torch 2.13.0 is a CUDA 13 build on aarch64. The Orin (sm_87) is outside its build list, but
its sm_80 kernels run: conv output matches the CPU to 6.6e-7 and NMS is identical.
CLAUDE.md's "MPS, not CUDA" describes the MacBook; on the Jetson torch runs on CUDA. Jazzy's
message libraries, built against numpy 1.26, were checked to work with the venv's numpy 2.5.

**What it cannot show.** The weights are not on the Jetson yet, so every run so far is
projection-only. D050's list stands: no motion blur, vibration, lighting, real command
latency or actuator dynamics.

## D094 — The review demo runs on the Jetson: MuJoCo survey demo and a live real-road viewer, on CUDA

**2026-10-08 · Accepted · extends D087 and D093**

The user asked for the mentor demo to show Model P and Model B detecting potholes live, as
realistically as the Jetson allows. Three parts, in `ros/MENTOR-DEMO.md`: the MuJoCo survey
demo (D087–D092) as the main simulation, because it has real photo textures and exact
ground truth; a live viewer on the real RT Dashcam clip, because only real footage answers
"does it work on a real road"; and D093's ROS loop, the only part where a decision moves
the vehicle. Recorded footage cannot be steered, and the MuJoCo road is driven straight, so
parts 1 and 2 show detection, not control.

**`mps` resolves to the machine's accelerator.** The configs name the MacBook's `mps`.
`core/device.available_device` returns the configured device where it exists, else `cuda`,
else `mps`, else `cpu`; `cpu` is honoured as asked, since bit-reproducible evaluation needs
it. `sim/mujoco/drive.py`, `scripts/eval_video.py` and `scripts/exp_video_extent.py` use it,
so the same config runs on both machines and the recorded device is the one that ran. The
screen's fonts became a list, the Mac's first and DejaVu second.

**`scripts/live_video.py`.** Both models track every frame with ByteTrack, potholes from P
and cracks from B (D082), confirmed by `eval_video.confirm_step` (D075) behind the horizon
gate, and Model P's tracks are scored with `score_video_gt.score_tracks`, the rule the
offline numbers use. No frame is skipped (D088), so the live window runs slower than real
time; `--record` writes at the clip's rate. A run stopped early is scored on the stretch it
played.

**Inputs rebuilt on the Jetson, none copied from the Mac.** The weights came from the Kaggle
kernel outputs; their SHA-256 match `results/LOCKED`. The clip came from YouTube again,
1280x720, 30 fps, 290.9 s, as recorded. The 49 textures were rebuilt from QR4Change
(Mendeley, SHA-256 checked) and BD-N6 (Zenodo, read by range request) with
`scripts/fetch_trial_textures.py`, using `docs/texture-provenance.md`'s file map. The
curated set had been downscaled to a 3000 px long side with the aspect kept, and the script
resizes to the map's sizes, so geometry and `natural_px_per_m` hold. The pixels are not
the zip's, so D092's byte-identical v1 check does not carry over to these textures. The
drift reference needs the india_val image list; the committed `splits/india_val.txt` is
that list (all 752 images with predictions are among its 772).

**Measured on the Jetson, 2026-10-08, once.** MuJoCo poor seed 0, look v2: potholes 16/28 at
44.9 false alarms/km, alligator 21/24, linear 14/27, drift alarm at 345 m. The Mac's run was
15/28, 21/24, 15/27, no alarm. The textures differ in their pixels and the arithmetic in its
device, and the results are close but not identical. The drive runs at 0.20x real time
(per frame: render 49 ms, P 32 ms, B 31 ms) after a scene build of about 220 s. On the real
clip, 120–180 s, Model P caught 12 of 17 counted potholes with 21 false alarms per minute
(the Mac's eval_video run: 10 of 17, 20 per minute), at 12 fps, 0.4x real time. Nothing was
tuned on these runs.

## D095 — The ROS graph takes any camera: real road video in, decisions out as CAN frames

**2026-10-08 · Accepted · extends D052 and D093**

`perception_node` pairs frames with ground truth only when `/sim/ground_truth` is published,
and reads each image's own size; the planner takes image size from `/camera/camera_info`.
`video_node` streams the RT Dashcam clip as `/camera/image_raw`, in lockstep by default (each
frame waits for its detections, so D075's 3-of-5 rule keeps its 30 fps premise, D088) or in
real time with frames dropped and labelled. The clip is open loop: a recording cannot be
steered, so it scores decisions, not avoidance, and the overlay says so on every frame.

Every Command also leaves as a CAN frame: a composite transport sends it to `RosTransport` and
`CanTransport` (D049), on socketcan/vcan0 by a ROS-side override in `configs/ros/demo.yaml`;
`configs/canbus/transport.yaml` keeps the Mac's `virtual` default and owns the 0x101 ID and the
provisional 4-byte layout. `can_monitor_node` decodes vcan0 onto `/can/decoded`.

With the weights present, `auto` picked the detector for the 2D sim, which never fires on its
flat-shaded frames, and every episode stayed NORMAL; the 2D sim now defaults to projection
(`sim.perception_source`). The staleness failsafe is off for lockstep video only.

Measured on the Jetson, 120–180 s of the clip: 1800 of 1800 frames at 9.9 fps (0.33x real
time); 1800 decisions, 1800 CAN frames on candump, 1800 decoded, byte-identical. The planner
left NORMAL during 12 of the 17 counted potholes, always with a manoeuvre; 27 of 53 manoeuvre
onsets had no counted pothole in view, and the median manoeuvre lasts 2 frames. Perception
stalls of 1–3 s occur on this shared machine and change speed, not decisions. The 2D sim:
31 of 31 episodes reached their expected state and matched `run_scenario`, 60 frames each.

## D096 — A Gazebo world converted from the MuJoCo road, with a sprung Ackermann car

**2026-10-08 · Accepted · refines D050 (its rejection of Gazebo, for the demo); D050's other
reasons stand**

The user asked for a Gazebo world on the Jetson realistic enough that the models detect from
pixels. `sim/gazebo/export.py` builds the MuJoCo look-v2 scene with the unchanged
`sim.mujoco.scene.build` and converts it geom by geom: baked photo textures, pothole relief
4–10 cm deep in visual and collision geometry, kerbs, markings, poles and trees. The ground
truth is byte-identical to D092/D094's. `ros/certain_road_gz` holds a 950 kg car (2.45 m
wheelbase, gz-sim AckermannSteering, four spring-damper legs at 1.4 Hz, the design camera at
1.3 m and 10° down), the ros_gz bridge and a launch whose paths are all relative, so the world
folder runs on another machine. Light was calibrated once to MuJoCo's brightness, never against
detections; gz's jerk limiter was removed after it made the speed hunt.

Measured on the Jetson, poor seed 0: Model P boxed 23 of the 28 ground-truth potholes that came
into view in at least one frame, and confirmed tracks hit 16–20 of 28 (MuJoCo: 16/28); pothole
false alarms 23.8–25.7 per km. RTF 0.78 at 1280x720/30 Hz, 15–24 s to the first image, about
2 GB of RAM; Gazebo here is physics-bound (collision meshes cost ~16% of real time). A wheel
crossing a pothole moved the body up to 11.7 mm, 0.68° pitch and 0.88° roll, with up to 71 mm
of suspension travel; plain road, 0 mm. A real two-machine run has not been tested.

## D097 — The Gazebo closed loop: built, not yet measured

**2026-10-08 · Open**

Committed mid-way when work paused: `gazebo.launch.py` (world, perception, planner, CAN, CAN
monitor, `lane_keeper_node`, road markers, RViz), a car vehicle profile (`configs/sim/car.yaml`)
and a car corridor (`configs/driving/corridor_car.yaml`) the planner selects by parameter, and
a stand-in lane keeper that steers only while the planner is NORMAL or WARNING. Its tests pass
and the 2D sim and video modes are unchanged (31/31 episodes above). The first closed-loop
smoke test was stopped before it finished, so nothing about avoidance has been measured. To
close: wheel–pothole crossings with the planner against a lane-keep-only baseline, false
manoeuvres, CAN counts, RTF.

## D098 — The survey simulation report and RSL: built in part

**2026-10-08 · Open**

`survey/rsl.py` inverts a published PCI–age curve per design.md §3 and refuses to run with an
empty `source:`. The curve is Sharaf, Reichelt, Shahin and Sinha (1987), TRR 1123, pp. 30–39
(PCI = 100 − b·age^m, m = 1.5), fitted to PAVER PCI on US Army roads: not Indian, and the input
here is a vision-estimated PCI, so the RSL is an indication for ranking, not a forecast. The
source was confirmed to exist and to state that model form. No Indian PCI–age model could be
verified (search record in `configs/rsl/published_default.yaml`). Status there: **pending
mentor approval**; `mode: pci_only` is the one-line alternative. Also committed mid-way:
`dashboard/survey_report.py`, `sim/mujoco/gallery.py` (re-rendered frames of each confirmed
track) and `scripts/survey_environments.py`. Not yet run on three roads, and the gallery is
not finished.
