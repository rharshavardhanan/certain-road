# RoadSight — task log

Running state for the T0–T17 specification. `docs/DECISIONS.md` is the durable
record of *why*; this file is the record of *what has been done*.

**Order:** T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7 → T9 → T10 → T11 → T12 → T13 →
T14 → T15 → T16 → T17. T8 runs only if there is no Jetson.

## Amendments to the spec

Two decisions amend the specification as written. Both are logged in full in
`docs/DECISIONS.md`.

**D055 — taxonomy stays the frozen three-class merge (amends D038, does not
supersede it).**
- `classes: {0: linear_crack, 1: alligator_crack, 2: pothole}`, `pothole_class: 2`.
- Every hard-coded class `3` reads `cfg.pothole_class` instead: `eval_locked`
  pothole-only evaluation (T9), BharatPotHole remap (T9), simulation class
  filter (T13), conformal matching (T10).
- T1's **raw** four-class audit is unchanged — it counts D00/D10/D20/D40 in the
  source XML, before the merge.
- Primary metric is 3-class mAP over the **merged** classes. This is *not* the
  spec's 3-class mAP (which excludes D10 from a four-class set). The report must
  say which it means at the point of use.
- The "D10 unreliable" note is replaced by: "D00 and D10 are merged into
  `linear_crack`; India has only 68 D10 instances."
- `scoring.deduct_weights: {linear_crack: 8, alligator_crack: 20, pothole: 30}`.
- Reference facts restated merged; **Japan alligator_crack is 6,198 in the
  converted labels vs 6,199 quoted** — one instance, 0.016%, inside T1's 1%
  tolerance. T1 identifies the cause.
- No existing checkpoint becomes Model A until its `args.yaml` and data lists
  prove it was trained from COCO `yolov8s.pt` on the non-India split only with
  the fixed hyperparameters. Otherwise Model A is reported as untrained.

**D056 — `uv` + Python 3.12 retained over the spec's pip + 3.11.**
- `requirements.txt` is generated (`uv export --format requirements-txt
  --no-hashes`), never hand-edited; regenerate whenever `uv.lock` changes.
- Kaggle kernels install **only** `ultralytics==8.4.115` plus `pycocotools`.
- T13 opens by verifying a trivial Webots controller runs under the 3.12 venv.

## Blocked on the user

| id | need | blocks | state |
|---|---|---|---|
| U1 | Kaggle: phone-verified account, `~/.kaggle/kaggle.json` (chmod 600), username in `configs/project.yaml` | T3, T5, T6, T7, T9 | **missing** — no `~/.kaggle/kaggle.json`; `kaggle.username` is `CHANGE_ME` |
| U2 | RDD2022 archive or permission to download | T1 | **satisfied** — all 7 countries present under `data/raw/RDD2022/` |
| U3 | Webots R2025a installed | T13 | **missing** — no `/Applications/Webots.app` |
| U4 | Jetson SSH alias `jetson` (optional) | T14 | unknown |
| U5 | Chennai recordings (video + sensor `.jsonl`) | T15 | not yet needed |
| U6 | Is a Jetson available? | decides T8 | **unconfirmed** — T8 deferred, not run |

## Progress

| task | state | notes |
|---|---|---|
| T0 | mostly done | `git init` skipped (repo has 64 commits); step 3 open on package naming; step 5 blocked on U1 |
| T1 | ready | unblocked — all 7 countries present locally |
| T2 | not started | |
| T3 | blocked | U1 |
| T4 | not started | |
| T5 | blocked | U1 — and it is a **full training run**, not a verification (see gate below) |
| T6 | blocked | U1 (T5) |
| T7 | blocked | U1 (T5) |
| T8 | deferred | U6 unconfirmed; do not run |
| T9 | blocked | U1 |
| T10–T12 | not started | buildable against existing predictions once T6 lands |
| T13 | blocked | U3 |
| T14 | not started | |
| T15 | blocked | U5 |
| T16–T17 | not started | |

## Entries

### 2026-09-22 — T0 started
- D055 and D056 written to `docs/DECISIONS.md`; D038 marked `amended by D055`.
- `CLAUDE.md` environment line updated to state Python 3.12 and the generated
  `requirements.txt` rule.
- `requirements.txt` generated from `uv.lock` (210 pins, `ultralytics==8.4.115`).
- Verified against the converted labels: six of seven reference rows match
  exactly; Japan alligator_crack differs by one instance (see D055).

### 2026-09-22 — T0 continued
- `configs/project.yaml` written with the D055 amendments; validated that
  `pothole_class` resolves to `pothole` and every class has a deduct weight.
- Dependencies added via `uv add`: matplotlib, scipy, pycocotools, pulp,
  streamlit, folium, streamlit-folium, pyserial, obd, kaggle, opencv-python,
  pillow. **torch 2.13.0, torchvision 0.28.0 and ultralytics 8.4.115 unchanged**;
  only pyarrow moved 25.0.0 -> 25.0.1. `torch.backends.mps.is_available()` True.
- `requirements.txt` regenerated from the updated lock (126 packages resolved).
- Suite green: **186 passed, 7 import contracts kept**.
- **U1 confirmed missing** — `kaggle datasets list --mine` returns
  "Authentication required to call the Kaggle API."
- **T2 overlap found:** `parse_voc` already exists in
  `src/certain_road/perception/dataset/voc.py`, and `convert.py` already carries
  `SOURCE_TO_ID = {"D00": 0, "D10": 0, "D20": 1, "D40": 2}` implementing D038's
  merge. T2 extends these rather than writing `src/roadsight/voc.py` fresh.

### 2026-09-22 — D057, D058, and the Model A gate

**Package: `certain_road` stays** (D057). Spec paths remap; T0's done-when is
`import certain_road`. Mapping table of spec modules to existing code is in D057.

**Commits: local, per task, never push** (D058). Always commit before
`eval_locked` so the stamped git hash matches the code that produced the number.

**U6 unconfirmed — T8 deferred**, not run.

#### Model A verification gate (D055) — VERDICT: no existing checkpoint qualifies

Three candidate runs on disk. The gate requires: trained from COCO `yolov8s.pt`,
on the **non-India split only**, with the fixed `train_A` hyperparameters.

| run | init weights | model size | training data | verdict |
|---|---|---|---|---|
| `multicountry_v8s` | `yolov8s.pt` (COCO) ✓ | 11,136,761 (v8s) ✓ | **4,617 India images in train; 757 India as val** ✗ | **FAIL** |
| `india_v1` | own `last.pt` (resume) ✗ | 3,011,433 (**v8n**) ✗ | India only ✗ | **FAIL** |
| `multicountry_v8s_ext2` | `multicountry_v8s/last.pt` ✗ | — | inherits India ✗ | **FAIL** |

`multicountry_v8s` training-set composition, counted from the materialised split:

```
Japan 10506 · Norway 8161 · United_States 4805 · India 4617
Czech 2829 · China_Drone 2401 · China_MotorBike 1977   (train, 35,296)
India 757                                              (val)
```

India is in both. It was trained on and used for early stopping, so it cannot
support any held-out India claim.

It also misses `train_A` on eight hyperparameters: epochs 27/40, patience 9/10,
batch 16/32, optimizer `auto`→MuSGD/AdamW, lr0 0.01/0.001, close_mosaic 5/10,
save_period -1/5, workers 8/4. Per D043, `optimizer: auto` additionally
*discards* the configured `lr0`, so its effective learning rate was never 0.01
either.

The Colab `geo_v8s_A2` run had the correct non-India composition but is
**incomplete (15/30 epochs)**, used batch 48 / close_mosaic 8 / 30 epochs, and
lives only on Google Drive — it is not local and does not qualify.

**Model A is untrained. T5 is a full training run**, blocked on U1.

