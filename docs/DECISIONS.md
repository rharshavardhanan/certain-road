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
