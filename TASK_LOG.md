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
| U1 | Kaggle auth | T3, T5, T6, T7, T9 | **satisfied** — `~/.kaggle/access_token` (ACCESS_TOKEN auth), user `harshavardhananr` |
| U2 | RDD2022 archive or permission to download | T1 | **satisfied** — all 7 countries present under `data/raw/RDD2022/` |
| U3 | Webots R2025a installed | T13 | **missing** — no `/Applications/Webots.app` |
| U4 | Jetson SSH alias `jetson` (optional) | T14 | unknown |
| U5 | Chennai recordings (video + sensor `.jsonl`) | T15 | not yet needed |
| U6 | Is a Jetson available? | decides T8 | **unconfirmed** — T8 deferred, not run |

## Progress

| task | state | notes |
|---|---|---|
| T0 | mostly done | `git init` skipped (repo has 64 commits); step 3 open on package naming; step 5 blocked on U1 |
| T1 | **done** | all counts match reference exactly; Japan discrepancy resolved |
| T2 | **done** | 12 leakage tests green; D059 replaced the block split |
| T3 | ready | U1 satisfied; D061 audit runs first |
| T4 | **done** | PASS, worst loss diff 2.1% |
| T5 | blocked | U1 — and it is a **full training run**, not a verification (see gate below) |
| T6 | blocked | U1 (T5) |
| T7 | blocked | U1 (T5) |
| T8 | deferred | U6 unconfirmed; do not run |
| T9 | blocked | U1 |
| T10 | **module done** | conformal.py + 50 tests; experiments await T6 |
| T11 | **module done** | drift.py + 11 tests; experiments await T6 |
| T12 | **module done** | geometry/scoring/allocation + 57 tests; experiment pending |
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


### 2026-09-22 — T1 done

`scripts/audit_raw.py` and `scripts/qa_raw.py`; report at
`results/T1/raw_audit.{json,md}`.

**All seven countries match the reference facts exactly — worst relative
deviation 0.00000.** Images 1:1 with XML everywhere; zero orphans in either
direction, zero parse errors, zero out-of-bounds boxes, zero `<size>`/JPEG
mismatches across all 38,385 annotations.

**The Japan discrepancy from D055 is resolved.** `Japan_001265` carries a `D20`
box with `xmin == xmax == 198.0` — zero width, the only degenerate box in the
dataset. Raw 6,199 and converted 6,198 are both correct and differ by exactly
this box, which the converter drops correctly. No action needed.

**Twelve raw class names present**, of which four are kept: `Block crack`,
`D00`, `D01`, `D0w0`, `D10`, `D11`, `D20`, `D40`, `D43`, `D44`, `D50`, `Repair`.
(`D0w0` is a typo of `D00`.) The raw four-class audit is what makes D038's merge
auditable rather than assumed.

**Visual QA: all 56 frames viewed. Box geometry correct in every country** — no
transposed axes or normalisation mix-up, which the count tables alone could not
have caught. Three findings carry past T1:
- **United_States is Google Street View** — every frame is watermarked "© Google".
  A provenance and licensing fact, not only a domain one.
- **China_Drone is top-down aerial** — valid for crack appearance, but T13's IPM
  geometry has no meaning for it.
- **Czech has a fixed windscreen mesh artifact** occluding the top ~20% of every
  frame, so a model sees it as background rather than noise.

**Dimensions, for T2:** Japan has **4 distinct sizes** (319 images are not
600x600) and Norway **3**, all ultra-wide. Only Norway exceeds `max_side: 1280`,
so it is the only country T2 resizes — 8,161 images.

QA renders are gitignored (21 MB, regenerated deterministically by
`scripts/qa_raw.py`).

### 2026-09-22 — T2 done

`src/certain_road/perception/dataset/pool.py`, `scripts/build_pool.py`,
`tests/test_splits.py`; report at `results/T2/split_audit.{json,md}`.

**D059 — the block split was rejected on evidence.** T2 asked for adjacent-ID
frames to be checked first. They are not consecutive: 400-pair correlation gave
+0.487 adjacent vs +0.483 random, a difference of +0.004, with 1/400 adjacent
near-duplicates against 0/400 random. India is split per image instead, at the
spec's 60/10/15/15. The conformal consequence is written out in D059.

**No earlier split lists existed** — no `splits/` directory and no list files
anywhere, so the 24,412 / 6,267 figures had nothing on disk behind them. Built
fresh per the spec's fallback. The result lands at **24,537 / 6,142**, close to
those figures but not identical.

**Pool:** 38,385 images materialised in 1.3 min. **Norway was the only country
resized** (8,161, 4040->1280), exactly as T1 predicted. Only rejections are
unknown classes plus the single `degenerate_box` — Japan_001265, as T1 found.

**Counts reconcile to T1 exactly**: India 7,706 images / 6,831 instances,
non-India 30,679 images. Fractions within ~0.6pp of target.

**India is 46.65% pothole by instance vs non-India's 6.97%** — a 6.7x gap and
the main driver of what T6 will measure as the generalization gap.

**12 leakage tests pass**, asserting against the materialised lists rather than
the code that wrote them. The firewall test confirms india_cal and india_test
reach none of Model B's train or val lists.

**Fixed a real gitignore bug found here:** `data/` was unanchored, so it also
matched `configs/data/` and would have silently excluded every dataset YAML T2
writes. Now `/data/`.

QA: 50 pool frames viewed across all nine splits; boxes align everywhere,
including Norway after its resize.

### 2026-09-22 — T10, T11, T12 modules

New leaf package `certain_road.assess` (8th import contract: imports no
pipeline) and `core/geometry.py`, which both `sim` and `survey` need and the
independence contracts forbid them sharing directly.

- **T10 conformal.py** — 50 tests. The prefix-equivalence property is checked
  against brute-force re-matching over 40 random cases at 7 thresholds; the
  finite-sample `+1` has its own test; 2,000-trial exchangeability at alpha
  0.05/0.10/0.20 confirms the bound.
- **T11 drift.py** — 11 tests. Growing bag and randomised tie-breaking each have
  a dedicated test; the Ville bound is verified over 1,000 streams.
- **T12 geometry/scoring/allocation** — sub-millimetre IPM round-trip over a
  30-point grid, and it independently reproduces two T13 design figures
  (f = 935.5 px, 2.2 m nearest ground).

**D062: PuLP cannot run on this machine.** Its bundled CBC is an x86_64 binary
(`bad CPU type in executable`), Rosetta is absent, and `brew install cbc` is
blocked on an unaccepted Xcode licence. Allocation now uses an exact
priority-indexed DP — same optimum, no binary dependency, and it handles float
costs and large budgets that a budget-indexed table could not.

Terminology held to CLAUDE.md throughout: `vision_density`, never bare density;
"vision-estimated PCI", never bare PCI; "evaluation segment".

### 2026-09-22 — T4 PASS, and Kaggle auth is live

**T4 passes.** MPS and CPU training losses agree to within **2.1%** (tolerance
25%), all non-zero:

| loss | MPS | CPU | rel diff |
|---|---|---|---|
| box | 3.28277 | 3.21326 | 0.021 |
| cls | 6.82689 | 6.75885 | 0.010 |
| dfl | 2.66284 | 2.65386 | 0.003 |

Ultralytics warned that `scatter_reduce_mps` and `index_put_with_accumulate_mps`
have no deterministic implementation despite `deterministic=True`, so MPS runs
are not bit-reproducible even at a fixed seed. Numerically sound, not
reproducible — which is a second reason D060 keeps Model A on Kaggle.

**Measured:** MPS 1.1 it/s at batch 16; CPU 5.2 s/it (MPS ~5.7x faster); clean
validation 0.028 s/image.

| | train/epoch | val/epoch | per epoch | total |
|---|---|---|---|---|
| Model A, 40 ep | 23.2 min | 2.9 min | 26.1 min | **17.4 h** |
| Model B, 25 ep | 9.1 min | 0.4 min | 9.4 min | **3.9 h** |

**The naive formula was rejected and why.** Dividing the `fraction=0.02` wall
time by 0.02 gives 100 min/epoch and 67 h for Model A. That is wrong: of the
116.8 s measured, only ~28 s was training — the rest is one-time startup (weight
load, AMP check, dataset scan), and dividing multiplies it by 50, inventing ~74
minutes of phantom time per epoch. The table above uses the measured 1.1 it/s.

**A first val timing had to be discarded.** It ran at 5.7 s/it because this
session was running the 2,000-trial conformal and 1,000-stream drift tests
concurrently. Re-measured with nothing else running: 0.028 s/image, ~200x
faster. The contaminated figure was never used.

**Verdict against D060:** Model A on the Mac is 17.4 h and forbidden regardless.
Model B at 3.9 h satisfies both of D060's conditions, so the Mac is a usable
overnight fallback for B — though Kaggle stays the default.

**U1 is satisfied.** `~/.kaggle/access_token` (CLI 2.2.4 ACCESS_TOKEN auth),
user `harshavardhananr`, written to `configs/project.yaml`. The token was pasted
in chat, so it should be rotated once T5 is running.
