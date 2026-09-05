# certain-road — a walkthrough

**Written 2026-08-16 · branch `week-1-foundation` · 35 commits · 74 tests · 45 logged decisions**

This document explains the project from the ground up: what it is, what every file and
folder does, where the models and the data came from, how the training code works, what
has been tried, and what conformal prediction is in plain language.

It assumes you are technically literate but not an ML specialist. Every machine-learning
term is defined the first time it appears.

Two companion documents already exist and are **not** replaced by this one:

- [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md) — the *design* argument. Why each choice
  was made, what the thesis contribution is, what the target numbers are.
- [`DECISIONS.md`](DECISIONS.md) — the decision log. 45 numbered entries, append-only.
  Anything below that says "(D0nn)" points at an entry there.

This document is the *walkthrough*: what things **are** and how they **work**.

---

## Contents

1. [The 60-second version](#1-the-60-second-version)
2. [Vocabulary](#2-vocabulary)
3. [The problem, and why it is not pothole detection](#3-the-problem-and-why-it-is-not-pothole-detection)
4. [The pipeline](#4-the-pipeline)
5. [Repo map — folders](#5-repo-map--folders)
6. [Every file, explained](#6-every-file-explained)
7. [The models — what they are and where they came from](#7-the-models--what-they-are-and-where-they-came-from)
8. [The data — where it came from and how it was downloaded](#8-the-data--where-it-came-from-and-how-it-was-downloaded)
9. [Categorizing the data](#9-categorizing-the-data)
10. [The training code, walked through](#10-the-training-code-walked-through)
11. [Every training run and its numbers](#11-every-training-run-and-its-numbers)
12. [Model options — what to do next](#12-model-options--what-to-do-next)
13. [Measuring the detector — the evaluation harness](#13-measuring-the-detector--the-evaluation-harness)
14. [Conformal prediction, explained properly](#14-conformal-prediction-explained-properly)
15. [What is done and what is not](#15-what-is-done-and-what-is-not)
16. [Demo cheat sheet](#16-demo-cheat-sheet)
17. [Questions you are likely to be asked](#17-questions-you-are-likely-to-be-asked)

---

## 1. The 60-second version

A camera on a vehicle records the road. Software finds the cracks and potholes in each
frame, converts them into a **pavement condition score** for each stretch of road,
attaches an **honest error bar** to that score, converts the score into **how many years
of life the road has left**, and then solves a **budget problem**: given ₹X crore, which
stretches do we repair first?

The interesting part is the error bar. Anyone can produce a number. This project produces
a number *with a statistically guaranteed range around it*, and then shows that using the
range instead of the number **changes which roads get funded**.

**Where we are:** the skeleton, the data pipeline, the detector training, and the
detector evaluation harness are built and tested. The condition-scoring, error-bar,
service-life, budget and dashboard stages are designed and specified but not yet written.

---

## 2. Vocabulary

Everything in this table is defined properly where it is used later. This is here so you
can point at it during the conversation.

| Term | What it means here |
|---|---|
| **Model** | A file full of numbers (weights) plus the code that runs them. Give it an image, it gives back an answer. |
| **Weights / checkpoint** | The learned numbers themselves, saved as a `.pt` file. `yolov8s.pt` is 23 MB of numbers. |
| **Bounding box** | A rectangle drawn around one object in an image, stored as four coordinates. |
| **Class** | The label attached to a box — here one of `linear_crack`, `alligator_crack`, `pothole`. |
| **Annotation / label** | A human-drawn box + class, used as the correct answer during training. |
| **Detector** | A model that outputs boxes + classes + a confidence score for each. |
| **Confidence score** | The model's own 0–1 opinion of how sure it is about one box. Not a probability in any calibrated sense — this matters later. |
| **Training** | Showing the model thousands of labelled images repeatedly and nudging its weights each time it gets one wrong. |
| **Epoch** | One complete pass over the whole training set. 100 epochs = the model saw every training image 100 times. |
| **Batch** | How many images are processed at once before the weights are nudged. Ours is 16. |
| **Learning rate** | How big each nudge is. Too big and the model thrashes; too small and it never gets anywhere. |
| **Augmentation** | Randomly flipping/scaling/shifting training images so the model learns the object, not the photograph. |
| **Train / val / test split** | Three disjoint piles of images. Train teaches the model; val monitors it during training; test is opened once at the end for the reported number. |
| **Overfitting** | The model memorises the training images instead of learning the pattern. Detected by train performance improving while val performance does not. |
| **Inference** | Running a trained model on new images. The cheap, fast operation. |
| **IoU** (intersection over union) | Overlap between two boxes, 0–1. Used to decide whether a predicted box "found" a real one. 0.5 is the usual bar. |
| **Precision** | Of the boxes the model drew, what fraction were real? Low precision = crying wolf. |
| **Recall** | Of the real defects, what fraction did the model find? Low recall = missing potholes. |
| **mAP50** | Mean Average Precision at IoU 0.5. One number, 0–1, summarising the whole precision-vs-recall trade-off. The standard detection score. |
| **mAP50-95** | The same thing averaged over ten increasingly strict overlap requirements (0.5 to 0.95). Much harsher; rewards precise box placement. |
| **Fine-tuning** | Starting from a model someone else trained on a big generic dataset and continuing training on your specific data. This is what we do. |
| **MPS** | Apple's GPU backend ("Metal Performance Shaders"). The Mac equivalent of CUDA. All training here runs on it. |
| **PCI** | Pavement Condition Index. A civil-engineering standard (ASTM D6433) scoring a pavement 0–100. 100 is perfect. |
| **RSL** | Remaining Service Life. How many years until the road hits an unacceptable condition. |
| **Conformal prediction** | The method that turns a single predicted number into a range with a guaranteed hit-rate. Section 14. |

---

## 3. The problem, and why it is not pothole detection

**The question the system answers:** *"Which road segments should be repaired first,
given a fixed budget?"*

**The question it does not answer:** *"Where is a pothole?"*

Pothole detection is a solved, crowded problem — there are dozens of published models.
Imagine a highways department with ₹100 crore a year. A system that says *"there is a
pothole at 13.08°N, 80.27°E"* gives them a list they cannot act on. A system that says:

> *"Segment 42 has a vision-estimated PCI of 48. We are 90% confident the true value is
> between 42 and 55. Its remaining service life is 0.8–1.4 years. Repairing it costs
> ₹3.2 lakh. Fund it before Segment 17."*

…gives them a budget line. That is the product.

There are three contributions, and the middle one is the novel one:

| # | Contribution | Plain meaning |
|---|---|---|
| 1 | Edge AI | Automatic distress detection from a vehicle camera |
| 2 | **Trustworthy AI** | **A calibrated error bar on the condition estimate** |
| 3 | Decision support | That error bar measurably changing which roads get funded |

**One framing correction worth stating out loud.** `PROJECT-OVERVIEW.md` says in places
that "the detector is not the contribution." For the thesis argument that is true. But the
project owner's standing instruction is that the mentor requires **a properly fine-tuned
detector that performs well** — the current mAP50 of ~0.42 is a **baseline to beat, not a
result to defend**. The deliverable is a working road-inspection product, not only an
experiment. Sections 11–13 are written on that basis.

---

## 4. The pipeline

Seven stages. Each one reads a file, does one job, and writes a file.

```
Camera / recorded video
        ↓
   [ ingest ]        sample frames every ~L metres, group into segments
        ↓  frames.parquet
   [ detect ]        YOLOv8 → bounding boxes            ← BUILT
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

**The single most important architectural rule: stages never import each other.** They
communicate only through typed files on disk (Parquet — a compressed columnar table
format, think "a fast, typed CSV"). A tool called `import-linter` enforces this in
continuous integration, and a cross-stage import **fails the build**.

Why this matters practically: `assess`, `calibrate`, `optimize` and `report` can all be
built and tested against **synthetic fake data**, with no trained model, no GPU, no camera
and no hardware. A 12-hour training run never blocks development. This one choice is what
makes a 7-week timeline possible.

---

## 5. Repo map — folders

```
certain-road/
├── src/certain_road/       all the actual code (~1,600 lines)
│   ├── core/               path resolution — the only thing everything may import
│   ├── artifacts/          the file format contract between stages
│   ├── ingest/             stage 1 — empty, planned
│   ├── detect/             stage 2 — BUILT (dataset prep, training, inference, evaluation)
│   ├── assess/             stage 3 — empty, planned (week 2)
│   ├── calibrate/          stage 4 — empty, planned (week 3)
│   ├── rsl/                stage 5 — empty, planned (week 5)
│   ├── optimize/           stage 6 — empty, planned (week 5)
│   ├── report/             stage 7 — empty, planned (week 7)
│   └── cli.py              the single command-line entrypoint
├── configs/                every tunable number in the project
│   ├── dataset/            which folders hold which split
│   ├── train/              training hyperparameters, one file per run
│   └── eval/               evaluation thresholds and class remaps
├── tests/                  74 automated tests
├── scripts/                two utilities that are not part of the pipeline
├── docs/                   design spec, decision log, dataset cards, plans, this file
├── data/          [ignored by git] 26 GB raw + 208 MB processed
├── runs/          [ignored by git] training outputs, weights, logs
├── models/        [ignored by git] symlink target for trained weights
├── .github/workflows/      continuous integration
├── pyproject.toml          dependencies and tool settings
├── uv.lock                 exact pinned versions of every dependency
├── .importlinter           the stage-isolation rules
└── CLAUDE.md               project conventions
```

The empty stage folders each contain a one-line `__init__.py`. They exist on purpose: the
`import-linter` contract names all seven, so the isolation rule is enforced from day one
rather than retrofitted after the code is written.

---

## 6. Every file, explained

### 6.1 Project-level configuration

| File | What it does |
|---|---|
| [`pyproject.toml`](../pyproject.toml) | The project manifest. Names the 10 runtime dependencies (pandas, pyarrow, pydantic, pyyaml, requests, torch, torchvision, tqdm, typer, ultralytics), pins Python to 3.12, defines the `certain-road` command, and configures the linter and test runner. |
| `uv.lock` | The exact resolved version of every dependency and sub-dependency. Committed, so the project reproduces byte-for-byte on another machine. |
| `.python-version` | Pins Python 3.12. Ultralytics and torch have not been verified against 3.13 here. |
| [`.importlinter`](../.importlinter) | 29 lines that encode the architecture. Two contracts: *stages must never import each other*, and *`artifacts`/`core` must not import any stage*. |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Runs the linter, the architecture contracts, and the test suite on every push. |
| [`CLAUDE.md`](../CLAUDE.md) | Project conventions — including the terminology rules in §17. |
| `README.md` | Currently empty. |
| `.gitignore` | Keeps `data/`, `models/` and `runs/` out of version control. 26 GB of road photos does not belong in git. |

### 6.2 The shared plumbing

**[`core/paths.py`](../src/certain_road/core/paths.py)** — 31 lines. Every path in the
project comes from here. `repo_root()` walks up the directory tree until it finds
`pyproject.toml`; `data_dir()`, `raw_dir()`, `processed_dir()` and `models_dir()` build on
it. The point is that nothing depends on which directory you happen to be standing in when
you run a command — a real bug class in ML projects, and one that bit this project once
(D040, see §10).

**[`artifacts/schema.py`](../src/certain_road/artifacts/schema.py)** — 57 lines,
*definitions only, no logic*. Declares exactly what each inter-stage file looks like, as a
`pydantic` model (a Python class that validates its own data).

- `FrameRow` — one sampled video frame: id, timestamp, survey date, lat/lon, speed,
  cumulative distance, which segment it belongs to, image path.
- `DetectionRow` — one detected defect: frame id, detection id, class name, confidence
  score, the four box coordinates, and the image's width and height.

Each carries a `schema_version`. Bumping it makes older files **unreadable on purpose**.

**[`artifacts/io.py`](../src/certain_road/artifacts/io.py)** — 94 lines. The only way to
read or write an artifact. `write_artifact` checks the columns match the schema exactly
(missing *or* extra columns both raise), validates every row, then stamps the artifact
name and schema version into the Parquet file's metadata. `read_artifact` refuses to
return anything whose stamp does not match what the code expects, raising `SchemaMismatch`.

Why bother: the failure this prevents is *silent*. A stage reading a file whose meaning
changed three commits ago will happily produce numbers. Wrong ones.

### 6.3 The command-line interface

**[`cli.py`](../src/certain_road/cli.py)** — 383 lines, the largest file. Built with
`typer`. It creates one sub-command group per pipeline stage plus a `dataset` group, and
it is **the only module in the project allowed to know about more than one stage at a
time**. Everything you actually run lives here:

| Command | What it does |
|---|---|
| `dataset fetch` | Download RDD2022 and extract one country |
| `dataset census` | Count every class string in the raw annotations *before* converting anything |
| `dataset convert` | Turn VOC XML annotations into YOLO label files |
| `dataset split` | Build the deterministic four-way split and the training data file |
| `detect train` | Train a YOLOv8 model |
| `detect predict` | Run a trained model over a folder of images → a detections artifact |
| `detect eval` | Score a model: mAP, a precision/recall sweep, and latency |

Note the imports are *inside* each function, not at the top of the file. That is
deliberate: it keeps `certain-road --help` instant instead of waiting several seconds for
torch to load.

### 6.4 The dataset pipeline (`detect/dataset/`)

**[`fetch.py`](../src/certain_road/detect/dataset/fetch.py)** — 153 lines. Downloads the
13.26 GB RDD2022 archive and extracts one country. Full story in §8.

**[`voc.py`](../src/certain_road/detect/dataset/voc.py)** — 70 lines. Parses PASCAL VOC
XML, the format RDD2022 ships annotations in. `parse_voc` returns image dimensions plus a
list of boxes; `class_census` counts every class string it finds, *including ones we will
later throw away*, so nothing is ever silently discarded.

**[`convert.py`](../src/certain_road/detect/dataset/convert.py)** — 85 lines. Converts
VOC XML into the YOLO text format, applying the class taxonomy. Holds the two most
consequential dictionaries in the repo:

```python
SOURCE_TO_ID = {"D00": 0, "D10": 0, "D20": 1, "D40": 2}
ID_TO_CLASS  = {0: "linear_crack", 1: "alligator_crack", 2: "pothole"}
```

It also repairs real-world annotation defects — transposed corners, boxes hanging off the
edge of the image — and **counts every rejection by reason**, so the gap between "boxes in
the XML" and "boxes in the labels" is always explainable. Full detail in §9.

**[`split.py`](../src/certain_road/detect/dataset/split.py)** — 223 lines. Assigns each
image to `train`/`val`/`calib`/`test` by **salted hash of the filename**, lays the files
out on disk as symlinks, and writes the data file that the trainer reads. This file
contains the project's most important safety mechanism; §9.4.

### 6.5 The detector (`detect/`)

**[`train.py`](../src/certain_road/detect/train.py)** — 104 lines. Loads a config,
verifies the GPU is available, resolves two classes of path bug, refuses to proceed if the
calibration data is anywhere near the trainer, and hands off to ultralytics. Walked through
line by line in §10.

**[`predict.py`](../src/certain_road/detect/predict.py)** — 132 lines. The project's first
inference path (added 2026-08-15, D044). Weights + a folder of images in, a validated
`DetectionRow` table out. Its structure is deliberate: `_raw_predictions` is the *only*
function that touches ultralytics, `remap_class_ids` relabels classes, and
`predict_to_detections` glues them together — which means the remapping and schema logic
can be unit-tested **without a trained model**. The test suite never runs a real detector.

**[`evaluate.py`](../src/certain_road/detect/evaluate.py)** — 369 lines. Scores a model.
`load_ground_truth` reads the label files back into pixel coordinates (reading each
image's real dimensions with PIL rather than assuming a fixed size). `compute_map`
produces mAP50, mAP50-95 and per-class scores. `compute_operating_metrics` produces
precision/recall/F1 at a specific confidence threshold. `measure_latency` times inference.
`render_report` formats it all as markdown. Detail and one good detective story in §13.

### 6.6 The six empty stages

`ingest/`, `assess/`, `calibrate/`, `rsl/`, `optimize/`, `report/` each contain a one-line
`__init__.py`. Their design is fully specified in
[`docs/superpowers/specs/2026-08-06-certain-road-design.md`](superpowers/specs/2026-08-06-certain-road-design.md)
and the week-2 plan for `assess` is already written. What each will do:

- **`ingest`** — sample one frame per ~L metres of travel rather than every frame. At
  30 fps and 30 km/h, one pothole appears in ~40 consecutive frames; counting it 40 times
  would make every road look catastrophic. Sampling by distance makes double-counting
  *impossible by construction*, which removed the need for an object tracker (D006).
- **`assess`** — turn boxes into a vision-estimated PCI, following the structure of ASTM
  D6433 with three honestly-named adaptations (`vision_density`, `apparent_severity`,
  parametric deduct curves).
- **`calibrate`** — the conformal layer. §14.
- **`rsl`** — invert a deterioration curve to get remaining years.
- **`optimize`** — an exact 0/1 knapsack solver over the budget.
- **`report`** — one self-contained HTML file, with Leaflet and Plotly vendored inline so
  it works with no internet at all.

### 6.7 `configs/` — every tunable number

The rule is: **no magic numbers in code**. If it is a knob, it lives here.

| File | Contents |
|---|---|
| `dataset/rdd2022_india.yaml` | Where the India split lives + the three class names |
| `dataset/rdd2022_multicountry.yaml` | Same, for the merged multi-country split |
| `train/yolov8n.yaml` | Run 1: the nano model on India |
| `train/yolov8s.yaml` | Run 2: the small model on all countries |
| `train/yolov8s_continue.yaml` | Run 3: continuing run 2 at a lower learning rate |
| `train/yolov8s_india.yaml` | Run 4: the small model on India — the clean comparison |
| `eval/thresholds.yaml` | Confidence floor, the operating-point sweep, image size, latency reps |
| `eval/class_maps.yaml` | How to translate another model's class numbering into ours |

These files carry unusually long comments — `yolov8s_continue.yaml` is 84 lines of which
~50 are explanation. That is intentional. Each one records *why* the number is what it is,
including the arithmetic behind the epoch count.

### 6.8 `tests/` — 74 tests

| File | Tests | Covers |
|---|---:|---|
| `test_architecture.py` | 1 | Runs `lint-imports` — the stage-isolation contract, tested like code |
| `test_artifacts_io.py` | 7 | Schema enforcement, version mismatch, round-trips |
| `test_cli.py` | 1 | The CLI starts and lists its stages |
| `test_dataset_convert.py` | 10 | VOC→YOLO maths, corner cases, rejection counting |
| `test_dataset_fetch.py` | 6 | Download resume, size verification, nested-zip extraction |
| `test_dataset_split.py` | 16 | Hash assignment, determinism, **the calib firewall** |
| `test_detect_evaluate.py` | 5 | mAP and operating-metric maths |
| `test_detect_predict.py` | 5 | Inference output shape and schema conformance |
| `test_detect_remap.py` | 5 | Class remapping, and that it fails loudly on unknown classes |
| `test_fixtures.py` | 7 | The synthetic data generator |
| `test_train_config.py` | 11 | Config loading, path resolution, GPU check, firewall check |

`tests/fixtures/synthetic.py` generates fake-but-realistic frames and detections for 102
evaluation segments. This is what lets weeks 2–5 be built before the detector is finished.

### 6.9 `scripts/`

- **`make_fixtures.py`** — writes the synthetic artifacts to `runs/synthetic/` so you can
  exercise the pipeline by hand.
- **`train_progress.py`** — reads a live training run's `results.csv` and prints progress,
  ETA and the metric trend. Used to watch a 12-hour run without tailing a log.

### 6.10 `docs/`

| File | Contents |
|---|---|
| `PROJECT-OVERVIEW.md` | The design argument, contributions, targets, timeline |
| `DECISIONS.md` | 45 numbered decisions, append-only, superseded entries left intact |
| `MENTOR-WALKTHROUGH.md` | This file |
| `dataset-card-rdd2022-india.md` | What is actually in the India subset |
| `dataset-multicountry-summary.md` | The merged multi-country corpus |
| `water-pothole-viability.md` | A rejected dataset, with the evidence for rejecting it |
| `superpowers/specs/` | The authoritative design spec |
| `superpowers/plans/` | Implementation plans, one per work package |

The decision log is worth showing a mentor directly. It is append-only, and wrong turns
stay visible with a `Superseded by Dnnn` marker rather than being edited away.

### 6.11 The gitignored directories

| Path | Size | Contents |
|---|---:|---|
| `data/raw/` | 26 GB | The RDD2022 zip and the extracted countries |
| `data/processed/` | 208 MB | YOLO label files and the split layout (images are symlinks, not copies) |
| `runs/detect/models/yolo/` | — | One folder per training run: weights, metrics CSV, plots |
| `runs/synthetic/` | — | Fake artifacts for developing the later stages |

---

## 7. The models — what they are and where they came from

### 7.1 What YOLO is

YOLO ("You Only Look Once") is a family of object-detection neural networks. The name
describes the trick: rather than scanning an image region by region, it processes the whole
image in a single pass and outputs every box at once. That is why it is fast enough to run
on live video — which is the whole point for a vehicle-mounted camera.

We use **YOLOv8**, via the `ultralytics` Python package. Give it an image; it returns a
list of `(box, class, confidence)` triples.

### 7.2 The size ladder

YOLOv8 ships in five sizes. They are the same architecture at different widths and depths:

| Variant | Parameters | File size | Relative speed | Relative accuracy |
|---|---:|---:|---|---|
| **YOLOv8n** (nano) | 3.01 M | 6.5 MB | fastest | lowest |
| **YOLOv8s** (small) | 11.1 M | 23 MB | ~2× slower than n | better |
| YOLOv8m (medium) | 25.9 M | — | ~4× slower | better still |
| YOLOv8l (large) | 43.7 M | — | ~7× slower | better still |
| YOLOv8x (extra) | 68.2 M | — | slowest | best |

We have used **n** and **s**. The larger three are ruled out for now on a cost argument,
not a capability one: on this Mac they would take 25–40 hours per run for maybe +2–4 mAP
points, and they weaken the "runs at the edge on a small device" story.

### 7.3 How the pretrained weights got here

Two files sit in the repo root:

```
yolov8n.pt    6.5 MB   downloaded 2026-08-07 00:18
yolov8s.pt     23 MB   downloaded 2026-08-07 07:13
```

**Nobody downloaded these by hand.** The training config says `model: yolov8n.pt`, and
`train.py` passes that string straight to `YOLO()`. Ultralytics recognises it as one of its
own published model names, finds no local copy, and fetches it from the ultralytics GitHub
releases page into the current directory. That is the entire acquisition story — it happens
once, automatically, on first use.

Look at `resolve_model_path()` in `train.py` to see how deliberate this is: a bare name with
no path separator (`yolov8s.pt`) is **passed through untouched** so ultralytics can resolve
or download it, while anything containing a slash (a checkpoint under `runs/`) is resolved
against the repo root instead.

### 7.4 What "pretrained" means, and why it matters

These two files are **not** road models. They were trained by ultralytics on COCO — 330,000
photographs of 80 everyday categories: people, cars, dogs, chairs.

Starting from them anyway is called **transfer learning**, and it is the single highest-value
thing in the training setup. A network trained on COCO has already learned, in its early
layers, what an edge is, what a texture boundary is, what a shadow does to a surface. Those
are not car-specific — they are vision-specific. Fine-tuning replaces only the final
classification head (80 categories → our 3) and gently adjusts everything else.

The alternative — starting from random numbers — would need vastly more than 4,617 images
and would produce a worse model. Practically: our runs converge in hours instead of not
converging at all.

### 7.5 Our own trained models

Each training run writes a folder under `runs/detect/models/yolo/<name>/` containing:

| Item | What it is |
|---|---|
| `weights/best.pt` | The checkpoint from whichever epoch scored best on the val split |
| `weights/last.pt` | The checkpoint from the final epoch — the true end state of training |
| `results.csv` | One row per epoch: losses, precision, recall, mAP50, mAP50-95 |
| `results.png` | Those columns plotted |
| `confusion_matrix.png` | Which classes get mistaken for which |
| `BoxPR_curve.png`, `BoxF1_curve.png` | Precision-recall and F1-vs-confidence curves |
| `train_batch*.jpg`, `val_batch*_pred.jpg` | Actual images with boxes drawn — worth opening in a demo |
| `args.yaml` | Every setting the run used, for reproducibility |

`best.pt` vs `last.pt` matters more than it looks. `best.pt` is the peak on the *validation*
split, which can be a lucky epoch. `last.pt` is the genuine endpoint of the optimisation
trajectory — which is why run 3 continues from `last.pt`, not `best.pt` (D043).

---

## 8. The data — where it came from and how it was downloaded

### 8.1 RDD2022

The **Road Damage Dataset 2022**, released for the CRDDC'2022 competition.

| | |
|---|---|
| DOI | `10.6084/m9.figshare.21431547.v1` |
| Licence | CC BY 4.0 (free to use with attribution) |
| Size | **13.26 GB, one single zip file** |
| Contents | 38,385 annotated road images from **seven** countries |
| Format | JPEG images + PASCAL VOC XML annotations |

| Country | Images | **Annotated** |
|---|---:|---:|
| India | 9,665 | **7,706** |
| Japan | 13,133 | 10,506 |
| Norway | 10,201 | 8,161 |
| United States | 6,005 | 4,805 |
| Czech | 3,538 | 2,829 |
| China MotorBike | 2,477 | 1,977 |
| China Drone | 2,401 | 2,401 |

India images are 720 × 720 pixels. The dataset's own published *test* splits are
**unlabelled** and therefore useless to us — every split we use is carved from India's
7,706 annotated training images.

### 8.2 The download, and why it needed its own code

Three things made this harder than `wget`, all recorded in the decision log:

**1. There is no per-country download (D032).** The documentation implies otherwise. There
is one 13.26 GB zip, take it or leave it. India is 527 MB of it. Norway alone is 10.6 GB.

**2. Figshare throttles per connection (D034).** The download redirects to Amazon S3, which
limits each individual connection to roughly 0.75 MB/s on a link that otherwise sustains
12.8 MB/s. A plain single-threaded download would take **4.4 hours**.

The fix is that S3 honours byte-range requests, so multiple connections multiply throughput.
`fetch.py` prefers `aria2c` with 16 parallel connections, measured at **7.4–7.9 MB/s** —
about **28 minutes** instead of 4.4 hours. It falls back to `curl` if `aria2c` is not
installed.

There is a caveat written into the source: `aria2c` **cannot resume a partial file that curl
started**, because it needs its own control file to track which byte ranges arrived.
Switching downloaders mid-transfer means discarding the partial file, not resuming it.

**3. The archive is nested two levels (D036).** The outer zip contains seven per-country
zips, and each inner zip's root is `India/`, not `RDD2022/India/`. `extract_country`
unwraps this. Because Norway's inner zip alone is 10.6 GB, the member is **streamed** to a
temporary file in 1 MB chunks rather than read into memory.

A recorded missed optimisation, kept visible rather than quietly forgotten: because the
inner zips are stored *uncompressed*, a range-read of the zip's central directory could have
fetched India's 527 MB alone. We downloaded 13.26 GB unnecessarily.

**The command:**

```bash
uv run certain-road dataset fetch --country India
```

Which: asks the Figshare API for the authoritative file size (so a partial file is never
mistaken for a complete one), downloads with `aria2c -x16`, verifies the size, computes and
records a SHA-256 checksum, then extracts India.

The checksum is for *our* reproducibility only — Figshare publishes no checksum to verify
against, and the code says so in its own output rather than implying a verification that
did not happen.

### 8.3 Rejected datasets

Three others were investigated and rejected. The reasoning is worth having ready, because
"why not more data?" is an obvious question:

| Dataset | Verdict | Reason |
|---|---|---|
| **RDD2020** | ❌ Rejected | RDD2022 *is* the extended version of it, and contains it. Both report the same 7,706 India images. Adding it contributes **zero new images** while injecting **duplicates** — and duplicates are uniquely destructive here, because the split assigns by filename hash, so the same photo under a different name would land in `train` *and* `calib`. The conformal intervals would come out **too narrow while looking perfectly valid**. |
| **Water-filled potholes** (Mendeley) | ❌ No-go (D039) | Investigated as a distribution-shift test. 713 images, one undifferentiated `pothole` class, and — fatally — **no water/dry distinction anywhere in the annotations**. It could not test what it was wanted for. |
| **Road Anomaly Detection** | ❌ Not pursued | Labels obstacles and surface states (drain hole, sewer cover, wet surface) rather than pavement distress types. Only `pothole` maps onto our taxonomy. |

---

## 9. Categorizing the data

Four steps take raw downloaded files to something a detector can train on. Each is a
separate command that can be re-run independently.

### 9.1 Census — count before you convert

```bash
uv run certain-road dataset census --country India
```

This reads every XML and counts **every class string that appears**, marking each KEEP or
DROP, before a single file is converted. The reason is that datasets lie. The published
RDD2022 documentation describes four classes; the real India annotations contain **ten**
distinct class strings (D037), including `D44`, `D01`, `D43`, `D11`, `D50` and a typo-looking
`D0w0`. A converter that silently skips what it does not recognise would hide all of that.

### 9.2 The taxonomy decision — four classes into three

RDD2022's four official classes:

| Code | Meaning |
|---|---|
| D00 | Longitudinal crack (runs along the road) |
| D10 | Transverse crack (runs across the road) |
| D20 | Alligator crack (interlinked cracking, looks like reptile skin) |
| D40 | Pothole |

The census found that **D10 has only 68 boxes in the entire India subset** — 43 in train, 13
in calibration. That is untrainable; a model cannot learn a category from 43 examples.

**D00 and D10 were merged into one class, `linear_crack` (D038).**

The important part is *why*, because "we merged them because one was rare" is a data-balance
hack and a mentor should push back on it. The real justification is that **ASTM D6433 already
treats longitudinal and transverse cracking as a single distress type sharing one deduct
curve** for asphalt pavements. The merge therefore *increases* fidelity to the standard we
are implementing. It also reduces the deduct-curve digitisation work from four curves to
three.

Final taxonomy, frozen:

| Class id | Class | RDD2022 source | India boxes | All-country boxes |
|---:|---|---|---:|---:|
| 0 | `linear_crack` | D00 + D10 | 1,623 | **37,846** |
| 1 | `alligator_crack` | D20 | 2,021 | 10,616 |
| 2 | `pothole` | D40 | 3,187 | 6,544 |
| | **Total** | | **6,831** | **55,006** |

Everything dropped is **counted, never silently discarded** — `D44` alone is 1,062 boxes in
India.

### 9.3 Conversion — VOC XML to YOLO text

```bash
uv run certain-road dataset convert --country India
```

The two formats say the same thing differently.

**VOC XML** — verbose, absolute pixel corners:

```xml
<annotation>
  <size><width>720</width><height>720</height></size>
  <object>
    <name>D40</name>
    <bndbox><xmin>474</xmin><ymin>570</ymin><xmax>586</xmax><ymax>621</ymax></bndbox>
  </object>
</annotation>
```

**YOLO** — one line per box, class id then centre-x, centre-y, width, height, all as
fractions of the image:

```
2 0.736111 0.827083 0.155556 0.070833
```

Reading that back: class 2 = `pothole`; centre at 73.6% across and 82.7% down; 15.6% of the
image wide and 7.1% tall. On a 720 × 720 image that is a 112 × 51 pixel box centred at
(530, 596) — the bottom-right of the frame, which is where the road surface is. This is a
real line from `India_000027.txt`.

Fractions rather than pixels is what lets the same label file work after the image is resized
for training.

Conversion also repairs real-world annotation defects rather than crashing on them (D035):

| Defect | Handling |
|---|---|
| Corners transposed (`xmax < xmin`) | Sorted — a recoverable ordering problem, not a bad box |
| Box extends past the image edge | Clipped to the image |
| Zero-area box after clipping | Rejected, counted as `degenerate_box` |
| Unrecognised class | Rejected, counted as `unknown_class:<name>` |
| Malformed XML | Counted as `PARSE_ERROR:<Type>`, file skipped, conversion continues |

**Empty label files are written on purpose.** 4,483 of India's 7,706 annotated images contain
no defect at all. These are **negative examples** — pictures of good road — and they are
essential: without them the model learns that every image must contain a crack somewhere.
The effective positive set is 3,223 images, not 7,706.

### 9.4 The split — and the single most consequential rule in the codebase

```bash
uv run certain-road dataset split --country India
```

Four piles, not the usual three:

| Split | India | Multi-country | Purpose |
|---|---:|---:|---|
| `train` | 4,617 | **35,296** | Teaches the detector |
| `val` | 757 | 757 | Watched during training for early stopping |
| `calib` | **1,548** | 1,548 | **Conformal calibration only. Never seen by training.** |
| `test` | 784 | 784 | Opened once, for the final reported number |

**Assignment is by salted SHA-256 hash of the filename, not a random shuffle.** The filename
is hashed to a number between 0 and 1, and fixed bands decide the split: 0–0.60 train,
0.60–0.70 val, 0.70–0.90 calib, 0.90–1.00 test.

Why this is better than a seeded shuffle: with a shuffle, adding or removing a single file
**reshuffles everything**, and calibration images silently migrate into training between runs.
With a hash, every filename's fate is decided by that filename alone, forever.

**The `calib` firewall.** If a single calibration image ever reaches training, every
statistical guarantee in the project is **silently void** — the numbers still come out, they
just quietly lie. It is enforced four separate ways:

1. The generated training data file lists only `train` and `val` keys. `calib` and `test` are
   physically absent from it.
2. `train.py` **refuses to run** on any data file containing the words `calib` or `test`,
   raising before anything loads.
3. Disjointness is asserted both in memory and on disk.
4. The training logs are checked for zero references to those splits.

That is four mechanisms for one rule. It is deliberate: a rule that nothing enforces does not
survive a deadline.

**The multi-country variant.** `--train-only Japan --train-only Norway …` adds other countries
to `train` **only** (D041). They are never four-way split, because a conformal guarantee is
only meaningful relative to a describable population — ours is Indian roads. The code checks
for filename collisions between countries and refuses to proceed if it finds any. Verified
after the class merge: `multicountry/calib` is byte-for-byte identical to `india/calib`.

Files are **symlinked**, not copied — same layout for the trainer, no duplicated gigabytes.

⚠️ **`dataset split` clears and re-links the image directories. Running it while training is
live crashes the training data loader mid-epoch.** That has already cost one run.

---

## 10. The training code, walked through

### 10.1 The command

```bash
uv run certain-road detect train --config configs/train/yolov8s.yaml --country multicountry
```

`--config` picks the hyperparameters; `--country` picks which dataset file to read. They are
separate flags on purpose, so any model config can be pointed at any dataset.

### 10.2 What `train.py` actually does

All 104 lines, in order:

**Step 1 — the firewall check.** Before anything else,
`_check_data_yaml_has_no_calib_firewall_breach` loads the dataset file and raises if it
mentions `calib` or `test`. The dataset config is a hand-editable checked-in file with no
other validation, so this is the last line of defence.

**Step 2 — load the config.** A plain YAML read. Every knob comes from the file; none are
hardcoded.

**Step 3 — verify the GPU.** If the config asks for `mps` and Apple's GPU backend is not
available, it raises immediately rather than silently falling back to the CPU and taking a
week.

**Step 4 — resolve the model path.** `resolve_model_path` passes bare names through so
ultralytics can download them, but resolves anything with a slash against the repo root.

**Step 5 — resolve the dataset path (this one is a real bug that was caught, D040).**
Ultralytics resolves a relative `path:` in a dataset file against **its own global
`datasets_dir` setting** — `~/PROJECTS/datasets` on this machine — not against the working
directory and not against the file's own location. So a committed config saying
`path: data/processed/india` silently points somewhere else entirely.

The fix keeps the committed file portable and resolves at runtime:
`resolve_data_yaml` rewrites `path` to an absolute one, verifies both split directories
actually exist (with an error message that names the missing directory and the command to
fix it), and writes a **disposable copy** to a temp folder — the committed file is never
mutated.

**Step 6 — train.** `YOLO(model).train(data=resolved_yaml, **cfg)`. The config dictionary is
splatted straight in, so adding a knob to the YAML needs no code change.

There is also `--smoke`, which overrides the run to two epochs. Used to prove the whole setup
works before committing 12 hours to it — which is how run 2's epoch count was calculated (see
below).

### 10.3 The knobs, explained

From `configs/train/yolov8n.yaml`:

| Knob | Value | What it means |
|---|---|---|
| `model` | `yolov8n.pt` | Starting weights (§7.3) |
| `epochs` | 100 | Complete passes over the training set |
| `patience` | 20 | Stop early if 20 consecutive epochs fail to improve. Prevents overfitting and wasted hours |
| `imgsz` | 640 | Images are resized to 640×640 before the model sees them. Bigger = more detail, quadratically slower |
| `batch` | 16 | Images processed per weight update. Limited by GPU memory |
| `device` | `mps` | Apple GPU |
| `workers` | 8 | Parallel processes loading and decoding images |
| `seed` | 0 | Fixes the random number generator so the run is reproducible |
| `project` / `name` | `models/yolo` / `india_v1` | Where output goes |
| `exist_ok` | `false` | Refuse to overwrite an existing run folder |

Augmentation — randomly distorting training images so the model learns defects rather than
photographs:

| Knob | Value | Meaning |
|---|---|---|
| `fliplr` | 0.5 | Mirror left-right half the time. A crack is a crack either way |
| `flipud` | **0.0** | **Never** flip vertically. Road scenes have a fixed up-down orientation — sky up, tarmac down. Upside-down road images would teach nonsense |
| `degrees` | 0.0 | No rotation, same reasoning |
| `translate` | 0.1 | Shift up to 10% |
| `scale` | 0.5 | Zoom in/out up to 50% |
| `mosaic` | 1.0 | Stitch four training images into one. Strong augmentation, helps small objects |
| `close_mosaic` | 10 | Turn mosaic **off** for the final 10 epochs, so the model finishes on realistic images |

`flipud: 0.0` is a good one to point at: it is a domain decision, not a default.

### 10.4 The continuation config — a worked example of care

`configs/train/yolov8s_continue.yaml` is 84 lines, ~50 of them comments, and it is the best
single illustration of how the project handles a subtle problem.

The situation: run 2 finished 27 epochs but was clearly **not converged** — its best score
landed on the very final epoch with the early-stop counter at 0/9, and mAP50-95 rose
monotonically across the last five epochs. It was stopped by a clock, not by convergence.

The obvious move — "resume it" — does not work, and the config records exactly why:

- Ultralytics **strips the optimizer state** from checkpoints on normal completion. Both
  `best.pt` and `last.pt` carry `epoch: -1`. There is no learning-rate schedule position or
  epoch counter left to resume from.
- Passing `resume=True` anyway *fails*: ultralytics rebuilds the detection head at the COCO
  default of 80 classes and then cannot load our 3-class weights (a tensor shape mismatch).

So it is not a resume. It loads `last.pt` as plain pretrained weights and trains further
under a fresh but deliberately low-learning-rate schedule:

- **`lr0: 0.001`, `warmup_epochs: 0`.** The finished run decayed from 0.01 down to ~0.0001.
  A fresh run at the default 0.01 would re-warm to full learning rate and **knock the model
  backwards**, destroying most of 11.6 hours of work. Starting at 0.001 — an order of
  magnitude above where the last schedule ended, two orders below where it began — continues
  the decay rather than restarting it.
- **`optimizer: MuSGD` pinned explicitly.** Ultralytics' default `optimizer: auto` *silently
  discards* whatever `lr0` and `momentum` you set and substitutes its own heuristic
  (`lr=0.01`), which recreates exactly the backsliding this config exists to prevent. It
  announces this in a log line that is easy to miss. It was caught by reading the launch log
  before letting the run continue (D043).
- **`patience: 15`, generous on purpose** — this run's job is to let convergence decide the
  stopping point instead of a clock.

Also recorded: the *first* attempt at this run (`_ext`) was killed after one epoch when macOS
entered idle sleep on battery. Hence:

⚠️ **Launch long training under `caffeinate -i`.**

---

## 11. Every training run and its numbers

**Read the split labels carefully** — `val` numbers come from `results.csv` during training,
`test` numbers come from a separate evaluation on held-out data. They are not comparable to
each other.

| # | Run | Model | Data | Epochs | Time | Final **val** mAP50 | India **test** mAP50 | Status |
|---|---|---|---|---:|---:|---:|---:|---|
| 1 | `india_v1` | YOLOv8n (3.01 M) | India 4,617 | 100/100 | 5.3 h | 0.4165 | **0.4081** | ✅ complete |
| 2 | `multicountry_v8s` | YOLOv8s (11.1 M) | Multi 35,296 | 27/27 | 11.6 h | 0.4545 | **0.4220** | ✅ complete |
| 3 | `multicountry_v8s_ext2` | continuation of 2 | Multi 35,296 | **12/23** | 5.0 h | 0.4528 | not measured | ⏸ **paused** |
| 4 | `india_v8s` | YOLOv8s (11.1 M) | India 4,617 | **0/100** | — | — | — | ⏸ **paused before epoch 1** |

> ⚠️ `PROJECT-OVERVIEW.md` still describes run 3 as "running". It is not. It stopped at epoch
> 12 on 15 Aug at 14:42, and run 4 was launched at 14:57 and stopped before completing an
> epoch. **Both were deliberately halted** under a standing instruction: *no training until
> the evaluation machinery exists and the current model has been measured properly.* That
> sequence is build machinery → measure current model → measure published models → choose →
> then train. Correct this line in the overview before presenting.

### 11.1 Per-class results — the interesting finding

Per-class mAP50 on the held-out India test set:

| Class | Run 1 (v8n, India) | Run 2 (v8s, multi-country) | Δ |
|---|---:|---:|---:|
| `linear_crack` | 0.3103 | 0.2855 | **−0.0248** |
| `alligator_crack` | 0.5810 | 0.6185 | +0.0375 |
| `pothole` | 0.3331 | 0.3621 | +0.0290 |

**`linear_crack` got worse despite its training data growing from 1,623 boxes to 37,846** —
a 23× increase. Two candidate explanations, and the experiments run so far **cannot
distinguish them**:

1. **Negative transfer.** Japanese and Norwegian pavement, crack morphology, lane markings
   and camera geometry differ enough that foreign linear cracks taught the model a notion of
   "crack" that does not match Indian roads. Potholes and alligator cracking look much the
   same everywhere — which is exactly why those two improved.
2. **Undertraining.** Run 2 was cut short by a time budget, not converged (§10.4).

Run 3 was designed to settle it: if `linear_crack` recovers with more training it was
undertraining; if it stays flat while the others improve it is genuine domain mismatch.
**Either answer is a reportable finding.** Run 3 is 12 epochs in and paused.

At epoch 12, run 3's val mAP50 is 0.4528 against run 2's endpoint of 0.4545, and val mAP50-95
is 0.2067 against 0.2105 — i.e. **the continuation has not yet recovered its own starting
point**, which is normal for a learning-rate restart but worth saying rather than glossing.

### 11.2 The confounded comparison — say this before you are asked

Run 2 changed **two things at once**: model capacity (3.01 M → 11.1 M parameters) *and*
training data (4,617 → 35,296 images). Its +0.0139 mAP50 over run 1 is therefore a
**combined** before/after and **cannot be attributed to either factor** (D042).

Run 4 (`india_v8s`) exists specifically to fix this. Its config is a byte-for-byte copy of
run 1's except for two lines — `model:` and `name:` — so it isolates capacity alone:

```
run 1    v8n (3.01 M) · India 4,617   · 100 ep → test mAP50 0.4081
run 2    v8s (11.1 M) · Multi 35,296  ·  27 ep → test mAP50 0.4220
run 4    v8s (11.1 M) · India 4,617   · 100 ep → ?
```

It also tests the negative-transfer hypothesis directly: if run 4's `linear_crack` beats run
2's 0.2855, then foreign linear cracks demonstrably hurt Indian performance, and the
regression was domain mismatch rather than undertraining.

---

## 12. Model options — what to do next

| Option | Expected gain | Cost | Verdict |
|---|---|---|---|
| **Finish run 4 (v8s on India only)** | Isolates capacity from data, and directly tests negative transfer | ~6 h | **Highest information per hour** |
| **Finish run 3 (11 more epochs)** | Settles undertraining vs domain mismatch | ~5 h | Strong — it was designed for this question |
| **Fine-tune run 3 on India only** | Standard fix for negative transfer: keep the multi-country gains on pothole/alligator, recover `linear_crack` | ~2 h | **Strongest single accuracy move** |
| Evaluate published RDD2022 models | Free baseline; tells us whether 0.42 is good or poor for this data | hours, no training | Machinery is built; weights not yet downloaded |
| YOLOv8m / v8l | +2–4 mAP points | 25–40 h on MPS | Poor ratio; weakens the edge-deployment story |
| Ensembling + test-time augmentation | How the CRDDC'2022 winner reached F1 0.769 | Large; breaks real-time inference | Contradicts the edge framing |
| Hyperparameter sweep | Unknown, probably small | Many runs | Low priority |
| More Indian data | Best possible domain match | 1–2 weeks sourcing, dedup, licence checks | Only if a genuinely independent source exists |

**Context for the target.** The CRDDC'2022 competition winner reached F1 0.769 across all
six countries — with an ensemble of large models and test-time augmentation, on a test set
dominated by easier countries. India alone is harder.

| | India test mAP50 |
|---|---|
| Current | 0.4220 |
| Plausible with convergence + tuning | 0.48–0.55 |
| Needs ensembling / TTA / larger backbone | 0.60+ |
| Not reachable on this data | 0.75+ |

---

## 13. Measuring the detector — the evaluation harness

Built 2026-08-15 (D044, D045). Before it, the project had **no inference path and no
evaluation code at all** — every number came from ultralytics' own internal validation,
which cannot be pointed at somebody else's model.

### 13.1 What the metrics mean

Build it up from the bottom:

- A prediction **matches** a real defect if they are the same class and their boxes overlap
  by at least an IoU of 0.5.
- **Precision** = matched predictions ÷ all predictions. *"When it says pothole, is it?"*
- **Recall** = matched predictions ÷ all real defects. *"How many did it miss?"*
- These trade off against each other via the confidence threshold. Accept only very confident
  boxes → high precision, low recall. Accept everything → the reverse.
- Sweeping every threshold traces a **precision-recall curve**. The area under it is
  **Average Precision** for one class; averaged over classes it is **mAP50**.
- **mAP50-95** repeats that at ten overlap requirements from 0.5 to 0.95 and averages. It
  punishes sloppy box placement, which is why it is always much lower — our 0.42 mAP50 is
  0.19 mAP50-95.

Two configs, for two different jobs:

- `map_conf_floor: 0.001` — mAP integrates the *whole* curve, so it needs everything. Raising
  this threshold truncates the curve and **artificially depresses mAP**; it does not "tune" it.
- `operating_thresholds: [0.10, 0.15, 0.20, 0.25]` — for the precision/recall/F1 table, which
  reports one *operating point* at a time. One inference pass at the low floor feeds both:
  the sweep filters that single prediction set by score rather than re-running inference four
  times.

### 13.2 Why class remapping matters

Published RDD2022 models emit the original **four** classes. Ours emits **three**. The
indices do not line up:

| Index | External model | Ours |
|---:|---|---|
| 0 | D00 longitudinal | `linear_crack` |
| 1 | D10 transverse | `alligator_crack` |
| 2 | D20 alligator | **`pothole`** |
| 3 | D40 pothole | — |

Scoring an external model's raw output against our labels would **score its potholes against
our alligator cracks** and produce plausible-looking, entirely wrong numbers. That is exactly
the silent failure this project exists to prevent, so `configs/eval/class_maps.yaml` defines
named maps and `remap_class_ids` **raises an error naming the offending class id** if it
meets one that is not in the map. Silently dropping an unmapped class is not an option.

The remap is applied to **predictions, never labels**, and it is a pure relabel — boxes are
never merged or deduplicated.

### 13.3 The detective story worth telling

The harness had one job first: reproduce a number we already knew. Ultralytics had reported
mAP50 = 0.4220 for `multicountry_v8s`. The new harness measured **0.3932** — off by 0.0288,
well outside the ±0.01 tolerance.

**The harness was not tuned to force a match.** The divergence was chased down instead, in
four steps:

1. **Wrong checkpoint?** Running ultralytics' own validation on `best.pt` reproduced
   0.4220305… exactly. Not the cause.
2. **A different non-maximum-suppression setting?** Ultralytics' *validation* path passes
   `multi_label=True`; its *prediction* path defaults to `False`. Forcing it changed the raw
   detection count from 41,595 to 46,484 but moved mAP50 by only +0.0009. Not the dominant
   cause.
3. **Compare actual boxes.** For one image (`India_000027`), the validation path's top box
   was 20–50 px offset from the prediction path's corresponding box, on a 720 px image —
   despite near-identical confidence and class.
4. **The actual cause.** Hooking both pipelines' preprocessing showed validation feeds the
   model a **(16, 3, 672, 672)** tensor while prediction feeds **(1, 3, 640, 640)** for the
   same requested `imgsz=640`. Ultralytics' validation defaults to **`rect=True`** —
   rectangular, stride-rounded batching — while prediction always uses a plain square
   letterbox. Confirmed by re-running validation with `rect` forced both ways:
   **`rect=True` → 0.4220**, **`rect=False` → 0.3937** — matching the harness's independent
   0.3932 to within 0.0005.

**The lesson, and it is the thesis's lesson in miniature:** the same weights, the same
images, and two defensible measurement conventions produce numbers that differ by 0.029 mAP.
A single reported number without its measurement conditions is not a fact. That is precisely
why the project puts an interval around its condition estimate rather than a number.

---

## 14. Conformal prediction, explained properly

This is the novel contribution. It is worth taking slowly.

### 14.1 The problem it solves

Suppose the system looks at a stretch of road and says:

> **Segment 42: vision-estimated PCI = 48.**

Two questions no highways engineer can avoid asking:

1. **How wrong might that be?** Is the truth 46, or 20?
2. **Why should I believe your answer to question 1?**

Machine-learning models are notoriously bad at this. A neural network will report 0.94
confidence on an image it has never seen anything like. Those confidence scores are the
model's opinion of itself, and they are **not calibrated** — of all the things a detector
calls "0.9 confident", nowhere near 90% are correct.

Conformal prediction fixes exactly this, and it is the *only* method that does so with a
mathematical guarantee that does not depend on the model being any good.

### 14.2 The idea, by analogy

A weather forecast that says "tomorrow's high is 31 °C" is nearly useless on its own. One
that says "**28–34 °C, and forecasts like this are right 90% of the time**" is actionable —
because that second clause is a *checkable track record*, not a vibe.

Conformal prediction is a procedure for earning that second clause. And the way it earns it
is almost insultingly simple: **measure how wrong you have been in the past, on data you
never trained on, and use that record to size the error bar.**

### 14.3 How it actually works — split conformal

Concretely, here is the whole method.

**Step 1 — hold data back.** This is what `calib` is: 1,548 images the detector has
*never seen*. Not during training, not for early stopping. Never. (Now you see why the
firewall has four independent enforcement mechanisms — the entire guarantee rests on this
one property being true.)

**Step 2 — measure the error on every held-back segment.** For each calibration segment,
compute both:
- `pci_pred` — what the pipeline estimates from the *detector's* boxes;
- `pci_ref` — what the **identical** computation produces from the *human-annotated* boxes.

The error, called the nonconformity score, is just the gap:

```
sᵢ = | pci_pred,ᵢ − pci_ref,ᵢ |
```

**Step 3 — sort those errors and pick a quantile.** With ~100 calibration segments, sort
all 100 error values smallest to largest and take roughly the **90th** — call it `q̂`. Say
it comes out at 6.5 PCI points. That number means: *on held-out data, this pipeline was
within 6.5 points of the reference answer 90% of the time.*

**Step 4 — use `q̂` as the error bar on every new segment.**

```
interval = [pci_pred − q̂, pci_pred + q̂]     clipped to [0, 100]
```

So Segment 42's estimate of 48 becomes **[41.5, 54.5]**.

**The guarantee:**

```
P(pci_ref ∈ interval) ≥ 1 − α
```

At α = 0.1, that is ≥ 90% coverage. It follows from exchangeability — the assumption that a
new segment is drawn from the same population as the calibration segments — and it holds
**regardless of whether the model is good**. A bad detector does not break the guarantee. It
just produces a wide, honest interval instead of a narrow one. That is the whole point: the
method cannot be gamed into looking confident.

### 14.4 Why the segment, not the box

The interval is attached to **evaluation segments**, not to individual detections (D005).
Governments repair stretches of road; they do not repair bounding boxes. Attaching the
guarantee to the thing the decision is actually about is both a stronger research claim and
statistically cleaner — the segment is the exchangeable unit.

### 14.5 How the interval reaches the funding decision

Three ways, and they are what make this a decision-support system rather than a statistics
exercise.

**(a) It survives the conversion to years, exactly.** Remaining service life is computed by
inverting a deterioration curve. That relationship is **monotone increasing** in PCI — more
condition, more years, always. A monotone transform of a valid interval is a valid interval,
so the endpoints simply map through:

```
[pci_lo, pci_hi]  →  [rsl(pci_lo), rsl(pci_hi)]
```

**Conformal coverage is preserved exactly.** No recalibration, no approximation, no loss.
This is an elegant property and worth stating plainly.

**(b) The optimiser ranks on the worst case.** Segment 42 has 0.8–1.4 years left. A
point-estimate system would rank it on 1.1. This system ranks it on **0.8** — and any
segment whose worst case falls below one year enters the budget as a **hard must-fix**,
ahead of all discretionary spending (D019). That mirrors how road agencies actually budget:
against downside risk, not against expected value.

The optimiser runs **twice** — once ranking on the point estimate, once on the worst case —
and diffs the two funded sets. **That diff is the headline result of the thesis**, and it
falls out as a by-product rather than a bolted-on experiment.

**(c) It knows when to say "I don't know".** PCI condition bands are ~15 points wide. An
interval of [42, 55] sits inside one band — actionable. An interval of [38, 71] straddles
three bands and means nothing. Those get flagged **`inconclusive`**, and the dashboard shows
"human inspection required" instead of a confident wrong number (D013).

A system that admits ignorance where it has it is more useful, and considerably more
trustworthy, than one that never does.

### 14.6 The honest limitation — volunteer this, do not wait to be asked

**The interval covers detector-induced error only.**

It does not cover error in the PCI model itself, in the `vision_density` proxy, in the
`apparent_severity` proxy, or in the deterioration curve. It cannot — because `pci_ref` is
itself computed *through those same models*, just with human boxes instead of predicted ones.

So the interval answers:

> *"Where would this estimate land if the detector were perfect?"*

and **not**:

> *"What is this road's true ASTM PCI?"*

An examiner will find this. Volunteering it converts the weakest point in the project into
evidence of rigour — and it is also why the separate manual-rating validation study exists:
three human raters assigning condition bands blind to 50 stratified segments, reported with
**inter-rater agreement as the ceiling**. A model agreeing at κ = 0.45 where humans agree at
κ = 0.50 is performing near the limit of the task; reporting the first number without the
second badly understates the result.

### 14.7 The numbers that decide whether this worked

The thesis stands or falls on whether the interval is **narrow enough to decide with**:

| Target | Value | Why it is the number |
|---|---|---|
| **`q̂` (interval half-width)** | **≤ 7.5 PCI points** at α = 0.1 | Fits inside one condition band → the segment is actionable |
| Empirical coverage | 86–94% at α = 0.1 | ±4 pp is sampling noise at ~101 evaluation segments |
| `inconclusive` rate | < 20% of segments | Above that, the dashboard mostly says "ask a human" |
| Budget reallocation | 10–20% | Uncertainty visibly changes the decision |
| Unfunded critical km | reduced vs point policy | It changed things *for the better* |

**Nobody yet knows what detector accuracy is needed to reach `q̂` ≤ 7.5.** It depends on how
detection error propagates through the PCI computation — which is exactly what weeks 2–4
measure. That is the research question, not a gap in the plan.

And it is the argument for building `assess` and `calibrate` **before** chasing more mAP: if
`q̂` turns out to be 5, the detector is already good enough and further training is wasted
effort. If `q̂` is 20, you will know precisely which class's error dominates instead of
guessing.

---

## 15. What is done and what is not

### ✅ Built, tested, committed

- `uv` project, Python 3.12, a `typer` CLI, **74 tests**, continuous integration
- **`import-linter` stage-isolation contracts, proven to fire** by deliberately introducing
  a violation and watching the build fail
- Versioned Parquet artifact IO that refuses stale-schema reads
- Synthetic fixtures for 102 evaluation segments — what unblocks weeks 2–5 with no model
- RDD2022 acquired (13.26 GB), census'd, converted, split, with the calib firewall enforced
  four ways
- Multi-country training corpus (35,296 images) built without perturbing India's split
- Two complete detector runs, two paused
- **Detector evaluation harness**: inference path, class remapping, mAP, an operating-point
  sweep, latency measurement — plus the harness-validation investigation in §13.3
- 45 decisions logged; three additional datasets considered and rejected with documented
  reasons (one of them, the water-pothole set, with its own written viability report)

### 📋 Designed and specified, not yet written

**The window is 2026-08-18 → 2026-10-05 — 48 days, ≈7 weeks**, run as **four partitions**
(D047). Full schedule with per-week done-when conditions:
[`superpowers/plans/2026-08-16-seven-week-schedule.md`](superpowers/plans/2026-08-16-seven-week-schedule.md).

| # | Weeks | Dates | Partition | Yields |
|---|---|---|---|---|
| **P1** | 1–2 | Aug 18–31 | **Research core** — `assess` → `calibrate`, coverage table, ⛔ detector frozen | Result 1 |
| **P2** | 3–4 | Sep 1–14 | **Decision layer + validation** — raters, `rsl`, knapsack, policy impact | Results 2 & 3 |
| **P3** | 5–7 | Sep 15–Oct 5 | **Edge deployment** — Jetson, camera + GPS, `ingest`, ONNX/TensorRT, real capture drive | |
| **P4** | 1–7 | Aug 18–Oct 5 | **Dashboard + thesis, written continuously** — there is no spare week at the end | |

**Hardware is sequenced last on purpose.** All three thesis results are complete and
frozen by **Sep 14**, before the Jetson is touched — so a slipped, dead-on-arrival or
never-approved unit costs the *deployment chapter*, not the degree.

**Cut to fit:** the synthetic distribution-shift sweep (Result 4) and the sensitivity
analysis. **Never cut:** the validation study and the coverage table.

**Four dates carry the plan.** *Aug 18* — blockers 1 and 2 close at the mentor meeting,
raters booked, **hardware ordered**. *Aug 31* — coverage table exists, detector freezes;
thesis go/no-go. *Sep 7* — rating session, the one thing more effort cannot compress.
*Sep 22* — if hardware is not in hand, trigger the degraded deployment chapter rather than
waiting.

### ⚠️ Blockers that need a human decision

| # | Blocker | Blocks | Options |
|---|---|---|---|
| 1 | **PCI→RSL citation** (D018) | week 5 | Supply a published PCI→RSL relationship with its citation, **or** select `mode: pci_only` and drive recommendations from PCI bands directly. One-line config change either way. |
| 2 | **ASTM D6433 deduct curves** | week 3 | Obtain D6433 and digitise the curves (preferred), **or** use an open-access paper's published coefficients, **or** a documented linear approximation labelled as such |
| 3 | **Three manual raters** (D027) | week 4 | Three people, ~1 hour each. Must be scheduled in week 3 — the one thing that cannot be compressed by working harder |
| 4 | Jetson Orin Nano hardware | week 8 | Never approved. The deployment chapter degrades gracefully to ONNX export + a latency benchmark + the architecture design |

Blockers 1 and 2 are really the same conversation: *which published relationship do we stand
on?* Both are **enforced in code** — those stages refuse to run while the `source:` field is
empty — so neither can be silently fudged.

---

## 16. Demo cheat sheet

Commands that work right now, in a sensible order to show someone.

```bash
cd ~/PROJECTS/certain-road

# 1. The architecture is enforced, not just described
uv run lint-imports              # the stage-isolation contracts
uv run pytest -q                 # 74 tests

# 2. What the CLI offers
uv run certain-road --help
uv run certain-road dataset --help

# 3. What is actually in the data
uv run certain-road dataset census --country India      # every class string, KEEP/DROP

# 4. Evaluate a trained model end to end (a few minutes on MPS)
uv run certain-road detect eval \
  --weights runs/detect/models/yolo/multicountry_v8s/weights/best.pt \
  --split test --country india \
  --out /tmp/eval.md

# 5. Run inference and produce a typed artifact
uv run certain-road detect predict \
  --weights runs/detect/models/yolo/multicountry_v8s/weights/best.pt \
  --images data/processed/india/images/test \
  --out /tmp/detections.parquet

# 6. How weeks 2-5 get built with no model at all
uv run python scripts/make_fixtures.py
```

**Pictures to open on screen** — these land better than any table:

```
runs/detect/models/yolo/multicountry_v8s/results.png                 metrics over 27 epochs
runs/detect/models/yolo/multicountry_v8s/val_batch0_pred.jpg         real predictions on real roads
runs/detect/models/yolo/multicountry_v8s/confusion_matrix.png        what gets confused with what
runs/detect/models/yolo/multicountry_v8s/BoxPR_curve.png             the precision-recall curve from §13.1
```

⚠️ **Do not run `dataset split` during a demo.** It clears and re-links image directories and
would break a live training run.

---

## 17. Questions you are likely to be asked

**"Why not just use an existing pothole detector?"**
We could, and the harness now exists specifically to evaluate published RDD2022 models on
identical terms. But the detector is an input, not the product. No published detector outputs
a calibrated condition interval or a budget-constrained repair ranking.

**"Is 0.42 mAP good?"**
For India specifically, it is a reasonable fine-tuned baseline — the CRDDC'2022 winner reached
F1 0.769 with an ensemble of large models and test-time augmentation, across six countries
including much easier ones. But 0.42 is **a baseline to beat, not a result to defend**. The
options for beating it are ranked in §12; the fastest is finishing runs 3 and 4, then
fine-tuning on India only.

**"Why did more data make one class worse?"**
Either negative transfer or undertraining — §11.1. The experiment to distinguish them is
designed and half-run. Either outcome is reportable.

**"How do you know the calibration data never leaked into training?"**
Four independent mechanisms, §9.4, one of which is a test in the suite. The guarantee rests
entirely on this, which is why it is enforced four times rather than documented once.

**"Your interval covers detector error only. Isn't that a serious limitation?"**
Yes, and it is stated in bold in the thesis rather than buried — §14.6. It answers "where
would this land if detection were perfect", not "what is the true ASTM PCI". The separate
manual-rating validation study exists to address the part the interval cannot.

**"What if the model is just bad? Doesn't the guarantee break?"**
No — and this is the strongest property of the method. A worse model produces a *wider*
interval, not a false one. Coverage is preserved; only usefulness degrades. The method cannot
be made to look confident by being wrong.

**"Why Parquet files between stages instead of just calling functions?"**
Because it lets four unbuilt stages be developed and tested against synthetic data with no
model, no GPU and no hardware, while 12-hour training runs proceed independently. It is what
makes a 7-week timeline feasible. The isolation is enforced by `import-linter` in CI, not by
good intentions.

**"Why so much documentation for one month of work?"**
The decision log is append-only and wrong turns stay visible. Three of its entries — D036
(the archive is nested differently than documented), D040 (ultralytics resolves paths against
its own setting), D045 (`rect=True` shifts mAP by 0.029) — record facts that contradict the
published documentation and cost hours to establish. Written down, they cost nothing to
rediscover.

### One terminology note, because it will come up

Certain words in this project are **load-bearing and enforced in code review**:

| Always | Never | Because |
|---|---|---|
| `vision_density` | bare `density` | ASTM density is *physical* area in m². Ours is image-space area fraction. A civil engineer would rightly object to the bare word. |
| `apparent_severity` | bare `severity` | ASTM severity depends on crack width, spalling, depth and ride quality — none observable from one monocular frame. Ours measures *visual prominence*. |
| `pci_ref` / "reference PCI" | `pci_true` | It comes from human annotations run through *our own* algorithm, not a certified ASTM field survey. |
| "vision-estimated PCI" | bare "PCI" | Same reason. |
| "evaluation segment" | "road segment" (for RDD2022 partitions) | Ours are random partitions of a photo dataset, not surveyed stretches of highway. |

Each of these prevents one specific overclaim. Using the honest word everywhere means the
overclaim cannot creep in through a variable name six months later.

---

## The one-paragraph summary

A vehicle-mounted camera records the road surface. YOLOv8 detects three distress types.
Detections are aggregated over distance-sampled frames into evaluation segments and converted
into a **vision-estimated PCI** through an ASTM-D6433-structured computation with three
honestly-named adaptations. Split conformal prediction attaches a **calibrated interval** to
that estimate, which propagates exactly through a monotone PCI→RSL transform into a
remaining-service-life interval. A budget-constrained knapsack ranks segments by **worst-case**
remaining life, and the whole chain appears in an offline HTML dashboard where clicking any
segment reveals its full reasoning. The contribution is that the uncertainty is *calibrated*,
*propagated all the way to the decision*, and *measurably changes which roads get funded*.
