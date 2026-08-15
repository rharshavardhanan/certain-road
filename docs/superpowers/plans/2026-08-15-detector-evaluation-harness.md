# Detector Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Be able to run *any* road-damage detector — ours or an external 4-class RDD2022 model — on the untouched India test set and compare them fairly.

**Why now:** the project cannot currently execute its own model-selection procedure. There is no inference path and no evaluation code, and every external RDD2022 model uses a 4-class taxonomy whose indices do not align with ours. Comparing them naively would score potholes against alligator cracks and produce numbers that look plausible and are wrong.

**Explicit constraint from the project owner: DO NOT START ANY TRAINING.** The sequence is *build machinery → test current model → test pretrained models → choose → then train.* This plan covers the first step only.

**Tech Stack:** Python 3.12, ultralytics (inference only), torchmetrics (mAP), pandas, pydantic.

## Global Constraints

- **Python 3.12**, `uv` only. Never `pip`.
- **Stages never import each other**; only `artifacts` and `core` are shared. `lint-imports` green.
- **No magic numbers**; tunables live in `configs/`.
- **Terminology binding**: `vision_density` never bare `density`; `apparent_severity` never bare `severity`; `pci_ref` never `pci_true`; "vision-estimated PCI" never bare "PCI"; "evaluation segment" never "road segment".
- **Taxonomy is frozen**: `0 = linear_crack, 1 = alligator_crack, 2 = pothole`. Do not introduce classes.
- **`calib` and `test` are never used for training or model selection.** This harness only *reads* `test`.
- `data/`, `runs/`, `models/` gitignored — commit code, configs, docs only.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Do not edit prior plans or the design spec; corrections go to `docs/DECISIONS.md`.

## The two design decisions that make this valid

### 1. Every model goes through the identical evaluation path

If our model were scored by `ultralytics.val()` and candidates by a different implementation, the comparison would be meaningless. **One inference path, one metric implementation, all models — including ours.**

Validation that the harness is correct: our own `multicountry_v8s` must score **close to 0.4220 mAP50**, the number ultralytics already reported for it. A large divergence means the harness is wrong, not that the model changed. **This is a required check, not a nice-to-have.**

### 2. mAP and the confidence sweep measure different things

mAP integrates the whole precision-recall curve, so it is computed over predictions above a **minimal floor (0.001)**. Raising the threshold truncates the curve and depresses mAP artificially.

The owner-requested sweep — **0.10, 0.15, 0.20, 0.25** — applies to *operating-point* metrics: precision, recall, F1, and per-class recall. Report:

- **one** mAP50 / mAP50-95 per model (conf floor 0.001)
- **four** rows of P / R / F1 / per-class recall, one per threshold

## Class remapping

External RDD2022 models emit four classes. Ours emits three.

```
external            ours
0  D00 longitudinal  ─┐
1  D10 transverse    ─┴─> 0  linear_crack
2  D20 alligator     ───> 1  alligator_crack
3  D40 pothole       ───> 2  pothole
```

Per the owner: **D00 and D10 predictions are merged into `linear_crack` during evaluation.** Both contribute; D00 alone is not used. This mirrors D038, where the same merge was applied to labels for ASTM reasons.

Merging happens on **predictions**, before metrics, and is a pure relabel — boxes are not combined, deduplicated, or NMS'd across the merge. A frame with one D00 box and one D10 box yields two `linear_crack` predictions.

## File structure

| File | Responsibility |
|---|---|
| `configs/eval/thresholds.yaml` | conf sweep values, IoU, mAP floor, latency reps |
| `configs/eval/class_maps.yaml` | named remaps, e.g. `rdd2022_4class` → our 3 |
| `src/certain_road/detect/predict.py` | weights + images → `DetectionRow` frame, with remap |
| `src/certain_road/detect/evaluate.py` | detections + labels → metrics |
| `src/certain_road/detect/candidates.py` | candidate registry: name, source URL, class map |
| `docs/detector-benchmark.md` | the results table (generated, committed) |

---

### Task 1: Class remapping

**Files:** create `configs/eval/class_maps.yaml`, `src/certain_road/detect/predict.py` (remap portion); test `tests/test_detect_remap.py`

**Interfaces produced:**
- `load_class_map(name: str) -> dict[int, int]`
- `remap_class_ids(df: pd.DataFrame, class_map: dict[int, int]) -> pd.DataFrame`
- `IdentityMap` for our own 3-class models

- [ ] **Step 1: Write `configs/eval/class_maps.yaml`**

```yaml
# Remaps external model class indices onto our frozen taxonomy:
#   0 = linear_crack, 1 = alligator_crack, 2 = pothole
#
# Indices DO NOT align across taxonomies. External class 2 is alligator
# crack; ours is pothole. Evaluating without a remap silently scores
# potholes against alligator cracks and produces plausible-looking wrong
# numbers - the exact failure this project exists to prevent.

maps:
  identity_3class:
    description: our own models, already in the frozen taxonomy
    mapping: {0: 0, 1: 1, 2: 2}

  rdd2022_4class:
    description: >
      Standard RDD2022 taxonomy (D00, D10, D20, D40). D00 and D10 both map
      to linear_crack, matching D038's merge of the same two classes in our
      labels. Merging is a pure relabel of predictions: boxes are not
      combined or deduplicated.
    mapping: {0: 0, 1: 0, 2: 1, 3: 2}
```

- [ ] **Step 2: Write the failing test**

```python
def test_rdd2022_map_merges_d00_and_d10():
    m = load_class_map("rdd2022_4class")
    assert m[0] == 0 and m[1] == 0, "D00 and D10 must both become linear_crack"
    assert m[2] == 1, "D20 -> alligator_crack"
    assert m[3] == 2, "D40 -> pothole"


def test_identity_map_is_a_noop():
    assert load_class_map("identity_3class") == {0: 0, 1: 1, 2: 2}


def test_remap_preserves_row_count():
    """Merging is a relabel, not a combine — two boxes stay two boxes."""
    df = pd.DataFrame({"class_id": [0, 1, 2, 3], "score": [.9, .8, .7, .6]})
    out = remap_class_ids(df, load_class_map("rdd2022_4class"))
    assert len(out) == 4
    assert list(out["class_id"]) == [0, 0, 1, 2]


def test_remap_rejects_an_id_absent_from_the_map():
    """An unmapped class must fail loudly, not silently vanish."""
    df = pd.DataFrame({"class_id": [7], "score": [.9]})
    with pytest.raises(ValueError, match="7"):
        remap_class_ids(df, load_class_map("rdd2022_4class"))
```

- [ ] **Step 3: Run and watch fail** · **Step 4: Implement** · **Step 5: Run and pass** · **Step 6: Commit**

---

### Task 2: `detect predict`

**Files:** `src/certain_road/detect/predict.py`, `configs/eval/thresholds.yaml`, `tests/test_detect_predict.py`, CLI wiring

**Interfaces produced:**
- `predict_to_detections(weights: Path, image_dir: Path, *, class_map, conf: float, device: str, imgsz: int) -> pd.DataFrame` conforming to `DetectionRow`
- CLI: `certain-road detect predict --weights W --images D --out P [--class-map NAME]`

**Design intent:** this is the inference path the whole project has been missing. `assess` needs it for real data; the benchmark needs it for candidates. It must produce a `DetectionRow`-conformant table so `write_artifact` validates it.

- [ ] **Step 1: Write `configs/eval/thresholds.yaml`**

```yaml
# mAP is computed over the full precision-recall curve, so it uses a minimal
# floor. Raising the confidence threshold truncates the curve and depresses
# mAP artificially - it does not "tune" it.
map_conf_floor: 0.001

# The owner-requested sweep. These apply to OPERATING-POINT metrics
# (precision, recall, F1, per-class recall), not to mAP. 0.10 is the
# optimum reported by one external benchmark; it is swept rather than
# assumed.
operating_thresholds: [0.10, 0.15, 0.20, 0.25]

iou_thresholds_map50: 0.50
imgsz: 640
latency_warmup: 5
latency_reps: 50
```

- [ ] **Step 2: Write the failing test** — build a tiny image dir in `tmp_path`, assert the returned frame satisfies `DetectionRow.columns()`, that `img_w`/`img_h` match the real images, that `x2 > x1` and `y2 > y1`, and that a 4-class model's output is remapped before return.
- [ ] **Step 3: Run and watch fail** · **Step 4: Implement** · **Step 5: Run and pass**
- [ ] **Step 6: Wire CLI onto the existing `STAGE_APPS["detect"]`** — do not create a parallel app
- [ ] **Step 7: Commit**

---

### Task 3: `detect eval` — metrics

**Files:** `src/certain_road/detect/evaluate.py`, `tests/test_detect_evaluate.py`, CLI wiring

**Interfaces produced:**
- `load_ground_truth(labels_dir, images_dir) -> pd.DataFrame` (YOLO txt → absolute xyxy)
- `compute_map(preds, gt, *, num_classes) -> dict` — mAP50, mAP50-95, per-class AP50
- `compute_operating_metrics(preds, gt, conf) -> dict` — P, R, F1, per-class R, FP count
- `measure_latency(weights, *, device, imgsz, reps, warmup) -> dict` — mean/p50/p95 ms
- CLI: `certain-road detect eval --weights W --split test --class-map NAME --out report.md`

**Dependency decision to make explicit:** use `torchmetrics.detection.MeanAveragePrecision` rather than hand-rolling mAP. Hand-written mAP is a classic source of subtly wrong numbers, and this metric decides which detector becomes the final product model. If `torchmetrics` is unacceptable, say so before implementing — do not silently hand-roll it.

- [ ] **Step 1: Write the failing tests**

```python
def test_perfect_predictions_score_map50_of_one():
    """Feeding ground truth back as predictions must score 1.0."""


def test_no_predictions_scores_zero_not_nan():
    """An empty prediction set must not poison the metric."""


def test_ground_truth_loader_converts_yolo_to_absolute_xyxy():
    """YOLO is normalised centre-format; boxes must come back in pixels."""


def test_operating_metrics_recall_falls_as_threshold_rises():
    """Sanity: a stricter threshold cannot increase recall."""


def test_empty_images_contribute_false_positives_not_missed_detections():
    """58% of our test set has no objects; they can only generate FPs."""
```

- [ ] **Step 2: Run and watch fail** · **Step 3: Implement** · **Step 4: Run and pass**
- [ ] **Step 5: Wire CLI** · **Step 6: Commit**

---

### Task 4: Validate the harness against a known number

**This task exists because a wrong harness would silently corrupt the model-selection decision.**

- [ ] **Step 1: Run the harness on `multicountry_v8s/weights/best.pt` over the India test split**
- [ ] **Step 2: Compare to the number ultralytics already reported: mAP50 0.4220, mAP50-95 0.1857**

Agreement within **±0.01 mAP50** means the harness is trustworthy. A larger gap means it is wrong — investigate and report; **do not adjust the harness until it matches and then declare success.** Report the real divergence and its cause.

Expect small differences from NMS defaults and IoU-matching details; document whatever you find.

- [ ] **Step 3: Record the outcome in the report and commit**

---

### Task 5: Benchmark the current model, all thresholds

- [ ] **Step 1:** Evaluate `multicountry_v8s` and `india_v1` on the India test split
- [ ] **Step 2:** Report per model — mAP50, mAP50-95, per-class AP50, and a four-row P/R/F1/per-class-recall table at 0.10 / 0.15 / 0.20 / 0.25
- [ ] **Step 3:** Report latency (mean, p50, p95 ms/image on MPS)
- [ ] **Step 4:** Write `docs/detector-benchmark.md` with the table, the exact test-set definition (784 India images, 330 positive, 454 empty), and the harness-validation result from Task 4
- [ ] **Step 5:** Commit

**Note for interpretation, to be stated in the document:** 454 of 784 test images contain no objects, so precision is dominated by false positives on empty frames. This matters for the product — a false positive inflates `vision_density` and depresses vision-estimated PCI.

---

### Task 6: Candidate registry — no downloads yet

- [ ] **Step 1:** Create `src/certain_road/detect/candidates.py` — a registry of name, source URL, licence, class map, expected class count, and a `verified: bool` field
- [ ] **Step 2:** Populate with candidates whose weights are **confirmed downloadable**, starting with the HuggingFace `SreekarAditya/yolo-rdd2022-benchmark` variants (CC BY 4.0)
- [ ] **Step 3:** For each candidate record **what is unknown** — critically, whether its training set overlaps our `calib`/`test`
- [ ] **Step 4:** Commit

**No weights are downloaded in this task.** Downloading and evaluating candidates is the *next* piece of work and needs the owner's go-ahead.

---

## Definition of done

- [ ] `uv run pytest` green; `lint-imports` green; `ruff` clean
- [ ] `certain-road detect predict` produces a `DetectionRow`-conformant artifact
- [ ] `certain-road detect eval` reports mAP + a four-threshold operating table
- [ ] Class remapping merges D00+D10 and **fails loudly** on an unmapped id
- [ ] Harness validated against the known 0.4220 within ±0.01, or the divergence explained
- [ ] `docs/detector-benchmark.md` committed with current-model results
- [ ] **No training run started. No candidate weights downloaded.**

## Explicitly out of scope

Downloading candidate weights · fine-tuning anything · any training run · modifying the split · touching `calib` or `test` beyond reading `test` for evaluation.

## The conformal constraint, restated

External weights may be used for **benchmarking and as fine-tuning initialisation**. The **final conformal detector must have a controlled training history** in which `calib` and `test` were provably never seen. An externally trained model's image list is unknown, so it cannot serve as the final detector without fine-tuning under our control — and even then, the question of whether its *pretraining* saw our calibration images must be recorded as a stated limitation.
