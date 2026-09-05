# Week 2: Assess — Vision-Estimated PCI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `detections.parquet` into `segments_pci.parquet` — a vision-estimated PCI per evaluation segment, computed through an ASTM-D6433-structured pipeline with three named adaptations.

**Architecture:** A new `assess` stage reading `frames.parquet` + `detections.parquet` and writing `segments_pci.parquet`. It must be a **pure function over any detections table**, because week 3's `calibrate` invokes it twice — once on predicted boxes, once on ground-truth boxes — and the difference between those two runs *is* the nonconformity score.

**Tech Stack:** Python 3.12, pandas 3.0.5, pydantic v2, numpy. No new dependencies.

## Global Constraints

- **Python 3.12 exactly**, `uv` only. Never `pip`.
- **Stages never import each other.** `assess` may import only `certain_road.artifacts` and `certain_road.core`. `lint-imports` must stay green.
- **No magic numbers in code.** Every tunable lives in `configs/assess/`.
- **Terminology is binding** across code, schemas, comments and docs:
  - `vision_density`, never bare `density` — ASTM density is physical area; this is image-space
  - `apparent_severity`, never bare `severity` — visual prominence, not structural
  - `pci_ref` / "reference PCI", never `pci_true`
  - "vision-estimated PCI", never bare "PCI"
  - "evaluation segment", never "road segment"
- **`assess` must be pure.** Same detections in → same PCI out. No global state, no reliance on which model produced the boxes.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- `data/`, `runs/`, `models/` are gitignored. `configs/assess/curves/*.csv` **is** committed — it is provenance.
- Do not edit the week-1 plan or the design spec; they are historical records. Corrections go to `docs/DECISIONS.md`.

## Current state

| | |
|---|---|
| Branch | `week-1-foundation`, HEAD `78d95c2`, 59 tests |
| Fixtures | `runs/synthetic/artifacts/` — 1,530 frames, 3,793 detections, **102 evaluation segments**, classes `linear_crack`/`alligator_crack`/`pothole` |
| Real detector | `runs/detect/models/yolo/multicountry_v8s/weights/best.pt` (27 epochs, India test mAP50 0.4220) |
| Training in flight | `multicountry_v8s_ext2`, ~10 h, must not be disturbed |
| Split | India train 4,617 / val 757 / **calib 1,548** / test 784 |

**Nothing in week 2 requires the training run.** All tasks build against the synthetic fixtures; Task 6 optionally uses the existing 27-epoch weights.

## The sourcing problem, stated up front

ASTM D6433's deduct-value curves are **copyrighted chart images** that this project does not have. The plan does **not** pretend otherwise.

Task 3 therefore builds the curve machinery as fully config-driven, with a **mandatory `source:` field that the stage refuses to run without** — the same enforcement pattern D018 uses for the PCI→RSL relationship. Placeholder coefficients ship with `source: ""`, so the pipeline is testable end-to-end but **cannot silently produce a citable number**. Resolving the citation is a human task with three viable routes, recorded in the config header: obtain ASTM D6433 and digitize with WebPlotDigitizer; use coefficients from an open-access paper that publishes them; or fall back to a documented linear-deduct approximation labelled as such.

## File structure

| File | Responsibility |
|---|---|
| `configs/assess/roi.yaml` | trapezoid ROI geometry |
| `configs/assess/severity_bands.yaml` | frozen per-class area-fraction quantile cutpoints |
| `configs/assess/deduct_curves.yaml` | fitted `(alpha, beta)` per class×severity + mandatory `source:` |
| `configs/assess/curves/*.csv` | raw digitized `(vision_density, dv)` points — committed provenance |
| `src/certain_road/assess/geometry.py` | ROI polygon, box-in-ROI area |
| `src/certain_road/assess/severity.py` | area fraction → L/M/H banding |
| `src/certain_road/assess/deduct.py` | DV lookup + **iterative CDV correction** |
| `src/certain_road/assess/pci.py` | orchestration: detections → `segments_pci.parquet` |
| `src/certain_road/artifacts/schema.py` | add `SegmentPciRow` |

## Schema decision

Spec §1 sketches `vision_density_by_class_apparent_sev` as one column. **A dict column in Parquet is a poor contract** — unqueryable, untyped, and awkward for pydantic. Instead, explicit columns, one per class×severity:

```
vd_linear_crack_low, vd_linear_crack_medium, vd_linear_crack_high,
vd_alligator_crack_low, ..., vd_pothole_high        (9 columns)
```

Typed, queryable, and a schema change becomes a visible version bump rather than a silent dict-key change.

---

### Task 1: ROI geometry and vision density

**Files:**
- Create: `configs/assess/roi.yaml`, `src/certain_road/assess/geometry.py`
- Test: `tests/test_assess_geometry.py`

**Interfaces:**
- Produces:
  - `load_roi(path: Path) -> Roi` — frozen dataclass with `top_fraction, bottom_fraction, top_width_fraction, bottom_width_fraction`
  - `roi_polygon(roi: Roi, img_w: int, img_h: int) -> np.ndarray` — 4×2 trapezoid vertices
  - `roi_area_px(roi: Roi, img_w: int, img_h: int) -> float`
  - `box_roi_overlap_px(roi, x1, y1, x2, y2, img_w, img_h) -> float`
  - `vision_density(overlap_px_total: float, roi_area_px_total: float) -> float` — returns percent

**Design intent:** the ROI is a fixed trapezoid approximating the road surface — narrow at the horizon, wide at the bumper. Detections outside it (sky, buildings, adjacent lanes) must not inflate `vision_density`. A box **partially** inside contributes only its overlapping area, not its whole area, or a large box clipped by the horizon would count fully.

- [ ] **Step 1: Write `configs/assess/roi.yaml`**

```yaml
# Fixed trapezoid approximating the road surface in a forward-facing frame.
# Fractions of image dimensions, so this is resolution-independent.
#
# Detections outside the ROI (sky, buildings, adjacent lanes) must not
# contribute to vision_density. These values are a starting point and are
# swept in the D029 sensitivity analysis: if vision-estimated PCI moves a lot
# under a +/-20% perturbation here, the pipeline is measuring its own
# configuration rather than the road.

top_fraction: 0.55           # horizon line, as a fraction of image height
bottom_fraction: 1.0         # bottom edge of frame
top_width_fraction: 0.25     # trapezoid width at the horizon
bottom_width_fraction: 0.95  # trapezoid width at the bumper
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_assess_geometry.py`:

```python
import numpy as np
import pytest

from certain_road.assess.geometry import (
    box_roi_overlap_px,
    load_roi,
    roi_area_px,
    roi_polygon,
    vision_density,
)
from certain_road.core.paths import repo_root

ROI = load_roi(repo_root() / "configs" / "assess" / "roi.yaml")
W = H = 600


def test_polygon_is_a_trapezoid_with_four_vertices():
    poly = roi_polygon(ROI, W, H)
    assert poly.shape == (4, 2)
    top_width = abs(poly[1][0] - poly[0][0])
    bottom_width = abs(poly[2][0] - poly[3][0])
    assert bottom_width > top_width, "road should widen toward the camera"


def test_roi_area_is_positive_and_below_image_area():
    area = roi_area_px(ROI, W, H)
    assert 0 < area < W * H


def test_box_fully_inside_contributes_its_whole_area():
    # centred, low in the frame — comfortably inside the trapezoid
    overlap = box_roi_overlap_px(ROI, 290, 560, 310, 580, W, H)
    assert overlap == pytest.approx(20 * 20, rel=0.05)


def test_box_fully_outside_contributes_nothing():
    # top-left corner: sky, far outside the trapezoid
    assert box_roi_overlap_px(ROI, 0, 0, 40, 40, W, H) == 0.0


def test_partial_box_contributes_only_the_overlap():
    # straddles the horizon: must be less than its full area, more than zero
    full = 200 * 200
    overlap = box_roi_overlap_px(ROI, 200, 250, 400, 450, W, H)
    assert 0 < overlap < full


def test_vision_density_is_a_percentage():
    assert vision_density(50.0, 200.0) == pytest.approx(25.0)
    assert vision_density(0.0, 200.0) == 0.0


def test_vision_density_of_empty_roi_is_zero_not_nan():
    """A segment with no usable ROI must not poison downstream arithmetic."""
    assert vision_density(0.0, 0.0) == 0.0
```

- [ ] **Step 3: Run it and watch it fail**

Run: `uv run pytest tests/test_assess_geometry.py -v`
Expected: FAIL — `ModuleNotFoundError: certain_road.assess.geometry`

- [ ] **Step 4: Implement geometry**

Use the shoelace formula for polygon area and Sutherland–Hodgman polygon clipping for box∩trapezoid overlap. Both are short and dependency-free; do not add shapely for this.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_assess_geometry.py -v` → all seven PASS.

- [ ] **Step 6: Commit**

```
feat: ROI trapezoid geometry and vision_density

Fixed trapezoid in image-fraction coordinates so it is resolution
independent. Boxes contribute only their overlap with the ROI, not their
full area - a box clipped by the horizon must not count in full.

vision_density is image-space area fraction, deliberately not ASTM
physical density (D015).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 2: Apparent severity banding

**Files:**
- Create: `src/certain_road/assess/severity.py`, `configs/assess/severity_bands.yaml`
- Create: `scripts/fit_severity_bands.py`
- Test: `tests/test_assess_severity.py`

**Interfaces:**
- Produces:
  - `SEVERITY_LEVELS = ("low", "medium", "high")`
  - `load_severity_bands(path) -> dict[str, tuple[float, float]]` — class → (low/med cutpoint, med/high cutpoint)
  - `band_for(area_fraction: float, cutpoints: tuple[float, float]) -> str`

**Design intent (D014, D028):** RDD2022 has no severity annotations, so `apparent_severity` is a **visual-prominence proxy** derived from each detection's own area fraction. Cutpoints are per-class quantiles **computed once on the train split and frozen into config** — never recomputed at inference, or the bands would drift with the data being assessed.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from certain_road.assess.severity import SEVERITY_LEVELS, band_for, load_severity_bands
from certain_road.core.paths import repo_root

BANDS = load_severity_bands(repo_root() / "configs" / "assess" / "severity_bands.yaml")


def test_every_class_has_two_cutpoints_in_order():
    for cls, (lo, hi) in BANDS.items():
        assert 0 < lo < hi, f"{cls}: cutpoints must be positive and ordered"


def test_banding_is_exhaustive_and_ordered():
    lo, hi = 0.01, 0.05
    assert band_for(0.005, (lo, hi)) == "low"
    assert band_for(0.03, (lo, hi)) == "medium"
    assert band_for(0.10, (lo, hi)) == "high"


def test_boundaries_are_deterministic_not_ambiguous():
    lo, hi = 0.01, 0.05
    assert band_for(lo, (lo, hi)) in SEVERITY_LEVELS
    assert band_for(hi, (lo, hi)) in SEVERITY_LEVELS
    # a value exactly on a cutpoint must land in exactly one band, always the same
    assert band_for(lo, (lo, hi)) == band_for(lo, (lo, hi))


def test_zero_area_is_low_not_an_error():
    assert band_for(0.0, (0.01, 0.05)) == "low"
```

- [ ] **Step 2: Run it and watch it fail**

- [ ] **Step 3: Implement `severity.py`**

- [ ] **Step 4: Write `scripts/fit_severity_bands.py`**

Computes per-class 33rd/67th percentiles of ROI-relative area fraction **over the train split only**, and writes `configs/assess/severity_bands.yaml` with a header recording the split, date, and detection count it was fitted on.

**It must refuse to run on any split other than `train`.** Fitting on `calib` would leak calibration data into the assessment model.

- [ ] **Step 5: Fit the bands on real train-split labels and commit the result**

Run against `data/processed/multicountry/labels/train`. Report the resulting cutpoints and the per-class counts they were derived from.

- [ ] **Step 6: Run tests, then commit**

---

### Task 3: Deduct values and the iterative CDV correction

**Files:**
- Create: `src/certain_road/assess/deduct.py`, `configs/assess/deduct_curves.yaml`, `configs/assess/curves/README.md`
- Test: `tests/test_assess_deduct.py`

**Interfaces:**
- Produces:
  - `load_deduct_curves(path) -> DeductCurves` — raises `UnsourcedCurvesError` if `source:` is empty
  - `deduct_value(curves, class_name, apparent_severity, vision_density) -> float`
  - `corrected_deduct_value(deducts: list[float], curves) -> float` — the iterative q-correction
  - `UnsourcedCurvesError(Exception)`

**Design intent (D016, D017):** `DV = min(100, alpha + beta·log₁₀(vision_density))` per class×severity. The **full iterative CDV correction is implemented, not simplified** — it is ~40 lines and is the difference between something a pavement engineer recognises as PCI and a weighted penalty sum.

- [ ] **Step 1: Write `configs/assess/deduct_curves.yaml` with an empty source**

```yaml
# Deduct value curves: DV = min(100, alpha + beta * log10(vision_density_pct))
# per (class, apparent_severity).
#
# SOURCE IS MANDATORY AND CURRENTLY EMPTY. The assess stage refuses to run
# until it is filled — the same enforcement D018 applies to the PCI->RSL
# relationship. This prevents the pipeline from silently producing a number
# that looks citable but is not.
#
# Three routes to resolve it, in order of preference:
#   1. Obtain ASTM D6433 and digitize the asphalt deduct curves with
#      WebPlotDigitizer, committing the raw points to configs/assess/curves/.
#   2. Use coefficients from an open-access paper that publishes them, cited
#      here by DOI.
#   3. Fall back to a documented linear-deduct approximation, labelled as an
#      approximation everywhere it is reported.
#
# The coefficients below are PLACEHOLDERS chosen only to exercise the
# arithmetic. They are not fitted to any curve and must not be reported.

source: ""   # <- MUST be filled before assess will run

max_deduct: 100.0

curves:
  linear_crack:
    low:    {alpha: 10.0, beta: 12.0}
    medium: {alpha: 20.0, beta: 16.0}
    high:   {alpha: 32.0, beta: 20.0}
  alligator_crack:
    low:    {alpha: 14.0, beta: 15.0}
    medium: {alpha: 26.0, beta: 19.0}
    high:   {alpha: 40.0, beta: 23.0}
  pothole:
    low:    {alpha: 18.0, beta: 14.0}
    medium: {alpha: 32.0, beta: 18.0}
    high:   {alpha: 48.0, beta: 22.0}

# Correction curve for multiple distresses. m is the allowable number of
# deducts: m = 1 + (9/98)(100 - max_deduct_value), capped at 10.
correction:
  m_slope: 0.0918367   # 9/98
  m_cap: 10
```

- [ ] **Step 2: Write the failing test**

```python
import pytest

from certain_road.assess.deduct import (
    UnsourcedCurvesError,
    corrected_deduct_value,
    deduct_value,
    load_deduct_curves,
)


def test_empty_source_is_refused(tmp_path):
    """An unsourced curve set must fail loudly, not silently produce numbers."""
    p = tmp_path / "c.yaml"
    p.write_text('source: ""\nmax_deduct: 100.0\ncurves: {}\ncorrection: {m_slope: 0.09, m_cap: 10}\n')
    with pytest.raises(UnsourcedCurvesError, match="source"):
        load_deduct_curves(p)


def test_deduct_rises_with_vision_density(sourced_curves):
    low = deduct_value(sourced_curves, "pothole", "high", 1.0)
    high = deduct_value(sourced_curves, "pothole", "high", 10.0)
    assert high > low


def test_deduct_is_capped_at_max(sourced_curves):
    assert deduct_value(sourced_curves, "pothole", "high", 1e6) <= 100.0


def test_zero_density_yields_zero_deduct(sourced_curves):
    """log10(0) is undefined; a segment with no damage must deduct nothing."""
    assert deduct_value(sourced_curves, "pothole", "high", 0.0) == 0.0


def test_higher_severity_deducts_more(sourced_curves):
    d = [deduct_value(sourced_curves, "pothole", s, 5.0) for s in ("low", "medium", "high")]
    assert d[0] < d[1] < d[2]


def test_cdv_of_single_deduct_is_that_deduct(sourced_curves):
    assert corrected_deduct_value([37.0], sourced_curves) == pytest.approx(37.0, abs=1e-6)


def test_cdv_of_no_deducts_is_zero(sourced_curves):
    assert corrected_deduct_value([], sourced_curves) == 0.0


def test_cdv_is_less_than_the_naive_sum(sourced_curves):
    """The whole point of the correction: penalties do not simply add up."""
    deducts = [40.0, 30.0, 20.0, 10.0]
    assert corrected_deduct_value(deducts, sourced_curves) < sum(deducts)


def test_cdv_is_at_least_the_largest_deduct(sourced_curves):
    deducts = [40.0, 30.0, 20.0]
    assert corrected_deduct_value(deducts, sourced_curves) >= 40.0


def test_cdv_never_exceeds_100(sourced_curves):
    assert corrected_deduct_value([95.0, 90.0, 85.0, 80.0], sourced_curves) <= 100.0
```

Add a `sourced_curves` fixture in `tests/conftest.py` that loads the real config with `source` overridden to a test string, so the other tests can exercise the arithmetic without the citation existing yet.

- [ ] **Step 3: Run it and watch it fail**

- [ ] **Step 4: Implement the iterative CDV correction**

The ASTM D6433 procedure, which must be implemented faithfully:

1. Sort individual deduct values descending.
2. Compute `m = 1 + (9/98)(100 − HDV)` where HDV is the highest deduct value; cap at 10.
3. Reduce the number of deducts to `m`: keep the largest `⌊m⌋`, and scale the next one by the fractional part of `m`.
4. Let `q` = the number of deducts greater than 2.0. Compute total deduct.
5. `CDV = f(total_deduct, q)` from the correction curve.
6. Set the smallest deduct greater than 2.0 to exactly 2.0, decrement `q`, and repeat from 4.
7. **CDV is the maximum over all iterations.**

Implement `f(total, q)` as a documented parametric approximation of the correction curve family, with its own entry in the config and its own `source` requirement. **State clearly in the docstring that this is an approximation** until real curves are sourced.

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

---

### Task 4: `SegmentPciRow` artifact schema

**Files:**
- Modify: `src/certain_road/artifacts/schema.py`
- Test: `tests/test_artifacts_io.py` (add round-trip)

**Interfaces:**
- Produces: `SegmentPciRow` with `artifact_name = "segments_pci"`, `schema_version = "1.0.0"`

Columns: `segment_id, survey_date, n_frames, n_detections, roi_area_px_total`, the **nine** `vd_<class>_<severity>` columns, `total_deduct, q_value, cdv, pci`.

- [ ] **Step 1: Write the failing round-trip test** (mirror the existing `FrameRow` temporal test)
- [ ] **Step 2: Run it and watch it fail**
- [ ] **Step 3: Add the model**
- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 5: The `assess` stage and CLI

**Files:**
- Create: `src/certain_road/assess/pci.py`
- Modify: `src/certain_road/cli.py`
- Test: `tests/test_assess_pci.py`

**Interfaces:**
- Produces:
  - `assess_segments(frames: pd.DataFrame, detections: pd.DataFrame, roi, bands, curves, *, score_threshold: float) -> pd.DataFrame`
  - CLI: `certain-road assess run --frames <p> --detections <p> --out <p>`

**Design intent (D007) — the property this whole stage is built around:** `assess_segments` must be **pure over any detections table**. Week 3's `calibrate` calls it twice — on predicted boxes and on ground-truth boxes — and `|pci_pred − pci_ref|` is the nonconformity score. If assess behaves differently depending on where boxes came from, the conformal guarantee is meaningless.

Ground-truth boxes have no `score`. The signature therefore takes an explicit `score_threshold`, and callers pass `0.0` for ground truth. **The function must never inspect anything model-specific.**

- [ ] **Step 1: Write the failing test**

```python
def test_assess_is_pure_over_any_detections_table(...):
    """The property the conformal layer depends on (D007)."""
    a = assess_segments(frames, detections, roi, bands, curves, score_threshold=0.0)
    b = assess_segments(frames, detections, roi, bands, curves, score_threshold=0.0)
    pd.testing.assert_frame_equal(a, b)


def test_every_segment_appears_even_with_no_detections(...):
    """A segment with zero damage is PCI 100, not a missing row."""
    result = assess_segments(frames, detections.iloc[0:0], roi, bands, curves, score_threshold=0.0)
    assert len(result) == frames.segment_id.nunique()
    assert (result["pci"] == 100.0).all()


def test_pci_is_bounded(...):
def test_more_damage_lowers_pci(...):
def test_score_threshold_filters_detections(...):
def test_detections_outside_roi_do_not_change_pci(...):
```

- [ ] **Step 2: Run and watch fail**
- [ ] **Step 3: Implement `pci.py`**
- [ ] **Step 4: Wire the CLI onto the existing `STAGE_APPS["assess"]`**
- [ ] **Step 5: Run on the synthetic fixtures**

```bash
uv run certain-road assess run \
  --frames runs/synthetic/artifacts/frames.parquet \
  --detections runs/synthetic/artifacts/detections.parquet \
  --out runs/synthetic/artifacts/segments_pci.parquet
```

Report the PCI distribution across the 102 evaluation segments: min, median, max, and how many fall in each condition band. **A distribution clustered at one value means the fixtures or the curves are not exercising the arithmetic** — report it rather than proceeding.

- [ ] **Step 6: Commit**

---

### Task 6: Real detections end-to-end

**Files:**
- Modify: `src/certain_road/cli.py` (add `detect predict`)
- Create: `src/certain_road/detect/predict.py`
- Test: `tests/test_detect_predict.py`

**Interfaces:**
- Produces: `predict_to_detections(weights: Path, image_dir: Path, *, device: str) -> pd.DataFrame` conforming to `DetectionRow`

Runs the existing 27-epoch `multicountry_v8s/weights/best.pt` over the **calib split** to produce a real `detections.parquet`, then assesses it. This is the first end-to-end vision-estimated PCI on real data and the direct input to week 3.

**Do not disturb the in-flight training run.** Inference on 1,548 images is short, but run it detached and check `ps` first.

- [ ] **Step 1–4:** TDD the predict wrapper against a tiny image directory
- [ ] **Step 5:** Run on the calib split, write `runs/real/calib/detections.parquet`
- [ ] **Step 6:** Assess it; report the PCI distribution and compare its shape to the synthetic run
- [ ] **Step 7:** Commit

---

## Week 2 definition of done

- [ ] `uv run pytest` green; `lint-imports` green; `ruff` clean
- [ ] `assess` produces `segments_pci.parquet` from synthetic fixtures for all 102 evaluation segments
- [ ] PCI spans a usable range, not clustered at one value
- [ ] `assess_segments` proven pure over any detections table — the D007 property week 3 depends on
- [ ] Deduct curves **refuse to run** with an empty `source:`
- [ ] Severity bands fitted on the **train split only** and frozen to config
- [ ] Real detections from the 27-epoch model assessed end-to-end
- [ ] `docs/DECISIONS.md` updated for any decision this work alters

## Open question for the mentor — blocking by week 3

**The ASTM D6433 deduct curves.** `assess` will not run without a `source:`. Route 1 (obtain the standard, digitize with WebPlotDigitizer) is preferred and is a 3-day timebox per D031. Routes 2 and 3 are documented fallbacks in the config header. This is the week-2 analogue of D018 and needs the same conversation.
