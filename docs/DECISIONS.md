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

Current design spec: [`superpowers/specs/2026-08-06-certain-road-design.md`](superpowers/specs/2026-08-06-certain-road-design.md)

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

**2026-08-07 · Accepted · refines D016**

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

Timeboxed spike per D025/D032 (see `docs/water-pothole-viability.md` for full
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
converted, seven-country label corpus (`docs/dataset-multicountry-summary.md`).
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
[`superpowers/plans/2026-08-16-seven-week-schedule.md`](superpowers/plans/2026-08-16-seven-week-schedule.md).

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
[`superpowers/plans/2026-08-16-seven-week-schedule.md`](superpowers/plans/2026-08-16-seven-week-schedule.md).

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
