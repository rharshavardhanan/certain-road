# Kernel-side dataset pre-flight, D073 amendment, Model P relaunch

2026-09-22 · supersedes the `kaggle datasets files` readiness check added in 99faaf7

## Why this exists

Model P has died twice, both times on infrastructure, never on the model:

1. Pushed before the dataset finished processing → `FileNotFoundError: p_train.txt`.
2. The dataset version landed **8,000 labels and 0 images**. Ultralytics scanned
   9,689 entries, reported every one "corrupt: No such file or directory", and
   the run burned a GPU slot producing nothing.

The check written after failure 1 asked Kaggle `datasets files` whether the
images were there. That check is wrong in a way that matters: the endpoint
**paginates**, so a file on page 2 reads as absent, and a prefix that happens to
sort onto page 1 reads as present no matter how few of its members uploaded. It
answers a question about an API listing when the question is about the bytes the
trainer will open.

The only place that can answer it is the kernel, after the mount resolves,
against the same list files the trainer reads. That is what this adds.

## Brainstorm — what the spec did not state

Fully specified ask, so this is thin. Three things it surfaced:

- **The label-path rule must be ultralytics' own.** If the pre-flight derives
  `labels/x.txt` by a rule of its own devising, it can pass while the trainer
  still finds nothing. A pre-flight that disagrees with the thing it guards is
  worse than no pre-flight, because it converts a loud failure into a confident
  one. Import `img2label_paths`; do not reimplement it.
- **Empty label files are legitimate and must not abort.** india_train is 4,622
  images carrying 2,025 pothole boxes — most images are background. Ultralytics
  counts those as `ne` (empty), not `nm`/`nc`. Aborting on `ne` would refuse
  every correctly-built pothole pool.
- **Two checks, cheapest first.** Existence is ~1s over 11k paths; the
  ultralytics verify decodes every image and costs a minute or two. The observed
  failure is caught by the cheap one, so run it first and abort there — the
  common case should report in seconds, not after a full decode pass.

## Scope guard (ponytail)

One function, one call site, one test block. No retry logic, no partial-upload
repair, no caching layer. The pre-flight's only job is to refuse.

---

## Task 1 — the kernel refuses to train against a dataset it cannot read

**Goal** `train.py` aborts before the optimiser sees an image if any listed
image or label is absent from the mount, or if ultralytics' own scan reports a
missing or corrupt pair, in either the train or the val list.

**Why** Without it, a partial dataset upload costs a full GPU session and
returns a number that has to be thrown away — which has now happened once and
came within one push of happening twice.

**Files** `kaggle/train/train.py`

**Steps**
1. Add `preflight_dataset(root, job) -> dict`, resolving train (str or list) and
   val through the same `root` used by `write_data_yaml`.
2. Pass 1 — existence: for each list, count entries, images present, labels
   present via `img2label_paths`. Abort with all three counts per list if either
   present-count is short of the entry count.
3. Pass 2 — `verify_image_label` over every pair in a thread pool; sum `nm`/`nc`.
   Abort with the counts and the first three messages if either is non-zero.
   `ne` is reported but never aborts.
4. Call it in `main()` immediately after `assert_no_forbidden_prefix`, before
   `YOLO(...)`. Print the per-list counts on success so the log carries proof.

**Done when** `preflight_dataset(Path("data/yolo_pothole"), <P job>)` run locally
prints `train 9689/9689 images, 9689/9689 labels` and `val 772/772` with
`missing=0 corrupt=0`, and returns without raising.

---

## Task 2 — the guard is tested, not just written

**Goal** The pre-flight's abort and pass paths are covered by unit tests that
run without a GPU, without Kaggle and without the real pool.

**Why** This guard only ever executes in an environment nobody can debug
interactively. If it is wrong it fails a run silently or blocks a good one; both
are expensive and neither is reproducible after the fact.

**Files** `tests/test_kaggle_guard.py`

**Steps**
1. Fixture building a tiny on-disk pool: `images/`, `labels/`, a list file.
2. Test: complete pool passes and returns the expected counts.
3. Test: **labels present, images absent** — the exact observed failure — aborts
   with `SystemExit` naming both counts.
4. Test: image present, label absent aborts.
5. Test: an image with an empty label file passes (background image, `ne`).
6. Test: the val list is checked too, not only train.
7. Test: a list-of-lists `train` value has every member checked.

**Done when** `uv run pytest tests/test_kaggle_guard.py -q` passes with the new
tests, and the full suite is still green.

---

## Task 3 — D073 says what the leakage measurement actually licenses

**Goal** D073 records BharatPotHole's effective diversity as **153 train
videos**, bars BPH val and test from every evaluation, and makes no claim about
annotation convention.

**Why** Two distinct errors to remove. Counting 5,067 frames as 5,067
independent images overstates the training signal by ~33×, which would make any
later "BPH is the bulk of the pothole data" argument wrong about what the bulk
consists of. And the leakage finding says only that BPH's split is not held out;
it is silent on whether BPH boxes are drawn to the same convention as RDD2022.
Letting a frame-index result stand in for an annotation-quality result is
borrowing evidence from one question to settle another. Convention is judged on
india_val, where the two conventions actually compete.

**Files** `docs/DECISIONS.md`

**Steps** Amend the D073 body; leave the numbers intact; add the diversity line
and the explicit "not evidence about annotation convention" sentence.

**Done when** D073 contains "153 train videos", bars BPH val/test from
evaluation, and no sentence in it mentions annotation convention except to
disclaim it.

---

## Task 4 — Model P runs

**Goal** Model P is training on Kaggle, launched only after the pre-flight
passed locally against the same lists.

**Why** It is the blocking dependency for the B-vs-P comparison on india_val,
which is the actual decision.

**Files** none (invocation only)

**Steps**
1. Run the pre-flight locally against `data/yolo_pothole` with the P job.
2. Commit tasks 1–3.
3. `scripts/kaggle_push.py p <sources>`; confirm accepted.

**Done when** `kaggle kernels status .../roadsight-train-p` reports running or
complete, and the kernel log shows the pre-flight's count lines above the first
epoch.

---

## Task 5 — the B-vs-P comparison is ready before P lands

**Goal** A script that scores Model B and Model P on `india_val` against
pothole-only ground truth, through one scorer and the frozen eval block, and
reports pothole AP50, AP50-95, and recall + false alarms per image at
`report_conf` and at a matched recall.

**Why** Built while P trains, so the selection number is one command away rather
than an hour of scripting under pressure to finish. More importantly, a
comparison harness written *after* seeing a result is a harness that can be
shaped by it.

**Files** `scripts/t9_b_vs_p.py`, `tests/test_operating_points.py`

**Steps**
1. Confirm the two pools agree: same 772 stems, same 342 pothole boxes,
   byte-identical images.
2. Each model runs NMS under the class count it was trained with; B is filtered
   to its pothole channel afterwards, so its crack detections are discarded
   rather than charged as false alarms.
3. One pycocotools GT object, pothole-only, shared by both.
4. Greedy per-image matching at IoU 0.5 in descending confidence, then a
   confidence sweep giving recall and false alarms per image.
5. Report recall 0.8 if reachable, and the highest recall **both** models reach
   either way — a matched-recall comparison at a recall only one can hit is not
   a comparison.
6. Unit-test the matching and sweep on synthetic boxes.

**Done when** `pytest tests/test_operating_points.py -q` passes and the script
runs end to end against B's weights and P's.

---

## Task 6 — the decision

**Goal** B vs P reported on india_val, every model tried named, and — if P loses
— P2 proposed rather than launched.

**Why** Selection is the point of all of the above. D072 fixed the rule:
india_val only, and the contingency is asked for, not assumed.

**Files** `results/T9/B_vs_P_india_val.json`, `docs/DECISIONS.md`

**Steps**
1. Pull P's weights when the kernel completes.
2. Run `scripts/t9_b_vs_p.py`.
3. Report B, P and every earlier model tried.
4. If P loses: state the P2 proposal (india_train oversampled 3x, otherwise
   identical) and **stop for approval**. Do not launch it.

**Done when** the comparison JSON exists and the recommendation is stated with
its numbers.
