# Training on Colab (T4)

## Read this first: what fits in a free session

A free Colab session lasts **up to ~5 h 20 min, not guaranteed**. That single constraint
decides which run to do.

| run | setup | training | total | fits |
|---|---|---|---|---|
| **India** (4,617 train) | ~15 min | 50 ep x ~1.5 min | **~1.5 h** | yes, with 3 h headroom |
| Multi-country (35,296) | ~35 min | 50 ep x ~7 min | **~6.4 h** | **no** |

**Do the India run.** Multi-country overruns, and trimming epochs to squeeze it in
reintroduces the exact truncation this run exists to eliminate.

Headroom is not luxury here: free resources are explicitly "not guaranteed", so leave room
for a slow download or one retry.

**Do not plan to resume across sessions.** `save_period` checkpoints are insurance against a
crash, not a strategy for finishing a long run — ultralytics' `resume=True` already failed on
this project (D043), rebuilding the head at COCO's `nc=80` and refusing to load our 3-class
weights. Never bet a multi-hour run on discovering whether it behaves differently this time.

Disk is not a constraint either way: India needs ~14 GB of the ~112 GB available,
multi-country ~27 GB.

**What the India run answers.** v8n-India vs v8s-India on identical data — the clean capacity
ablation that D042 confounded by moving model size and training data together. That question
is currently unanswered.



**Do not upload the dataset.** `train`+`val` is 10 GB — hours of upload on a home
connection. Colab pulls RDD2022 from Figshare at datacenter speed instead, and because our
split is a **salted hash of the filename** (D009), regenerating it there produces a
*bit-identical* split. Upload the repo (a few MB); let Colab rebuild the data.

That also removes a whole class of mistake: nothing has to be kept in sync by hand.

---

## The one rule that must not break

**`calib` and `test` must never reach training.**

They are protected two ways and you should verify both, because everything downstream
depends on it:

1. `configs/dataset/rdd2022_*.yaml` references **only** `train` and `val` — the split code
   writes it that way deliberately.
2. `detect train` **refuses to run** on a data yaml that names `calib` or `test`.

Cell 4 below checks the split counts match this machine exactly. If they differ, stop —
the salt or the source data changed, and the run would not be comparable to anything.

---

## Notebook

### Cell 1 — GPU check

```python
!nvidia-smi --query-gpu=name,memory.total --format=csv
```

Expect a **T4, 15360 MiB**. If you get a K80, `Runtime → Change runtime type → T4`. A K80
is roughly 3× slower and lacks the tensor cores this benefits from.

### Cell 2 — get the code

```python
!git clone -b week-1-foundation https://github.com/<you>/certain-road.git
%cd certain-road
!pip -q install ultralytics pyyaml pandas pyarrow pydantic
```

If the repo is private, upload a zip of it instead — it is only a few MB. **Do not include
`data/`, `runs/` or `models/`.**

### Cell 3 — rebuild the dataset

```python
!python -m certain_road.cli dataset fetch   --country India
!python -m certain_road.cli dataset convert --country India
```

The fetch is 13.26 GB and takes ~5–10 min on Colab. For the multi-country run, repeat
`fetch`/`convert` for `Japan`, `Norway`, `United_States`, `Czech`, `China_MotorBike`,
`China_Drone` — the archive is downloaded once and cached.

### Cell 4 — rebuild the split, then VERIFY IT

```python
!python -m certain_road.cli dataset split --country India

import json
counts = json.load(open("data/processed/india/splits.json"))["counts"]
print(counts)
assert counts == {"train": 4617, "val": 757, "calib": 1548, "test": 784}, \
    "SPLIT MISMATCH — stop. This run would not be comparable to anything."
```

**Do not skip the assert.** A silently different split is the failure that makes every
number afterwards meaningless, and it looks like success.

For multi-country, expect `train: 35296` with val/calib/test unchanged at 757/1548/784.

### Cell 5 — checkpoint to Drive so a disconnect costs nothing

```python
from google.colab import drive
drive.mount("/content/drive")
!mkdir -p /content/drive/MyDrive/certain-road-runs
```

Colab **will** disconnect — idle timeouts, session caps, preemption. Without this you lose
the whole run.

### Cell 6 — the training config

```python
config = """
model: yolov8s.pt
epochs: 50
patience: 15
imgsz: 640
batch: 32
device: 0
workers: 8
seed: 0
project: /content/drive/MyDrive/certain-road-runs
name: india_v8s_colab
exist_ok: false
save_period: 5

fliplr: 0.5
flipud: 0.0
degrees: 0.0
translate: 0.1
scale: 0.5
mosaic: 1.0
close_mosaic: 10
"""
open("configs/train/yolov8s_colab.yaml", "w").write(config)
```

Four things differ from the Mac config, each for a reason:

| | Mac | Colab | why |
|---|---|---|---|
| `device` | `mps` | `0` | CUDA |
| `batch` | 16 | **32** | the T4's 15 GB takes it; better throughput and steadier batch-norm |
| `save_period` | −1 | **5** | a checkpoint every 5 epochs, on Drive, so a disconnect costs ≤5 epochs |
| `epochs`/`patience` | 27 / 9 | **50 / 15** | see below |

**`epochs: 50, patience: 15` is the point of this run.** The 27-epoch run was cut short by a
time budget, not by convergence — its best landed on the final epoch with five consecutive
improvements. Here, patience decides the ending. If it stops at 34, that is the answer;
if it runs all 50, that is also the answer. Either beats guessing.

### Cell 7 — train

```python
!python -m certain_road.cli detect train \
    --config configs/train/yolov8s_colab.yaml --country India
```

Expect roughly **1–2 min/epoch** → ~1.5 h for 50 epochs on India.

Multi-country is 6–9 min/epoch, i.e. 5–7 h of training on top of ~35 min of setup. That
**exceeds the free session cap** — see the note at the top. Run it on a paid session or a
local GPU, not by trimming epochs.

### Cell 8 — evaluate on the held-out test set

```python
!python -m certain_road.cli perception eval \
    --weights /content/drive/MyDrive/certain-road-runs/india_v8s_colab/weights/best.pt \
    --split test --country india --class-map identity_3class
```

This is the number that counts. `test` was never trained on and never used for early
stopping, so it is directly comparable to `multicountry_v8s`'s **0.3932**.

### Cell 9 — retrieve the weights

`best.pt` is already on Drive. Download it from there, or:

```python
from google.colab import files
files.download("/content/drive/MyDrive/certain-road-runs/india_v8s_colab/weights/best.pt")
```

---

## What to send back

The `.pt` alone is not enough to reproduce or defend a result. Send:

1. **`best.pt`**
2. **`results.csv`** — the full per-epoch trajectory. This is what answers "did it converge?", which the 27-epoch run could not.
3. **`args.yaml`** — what ultralytics actually ran, which is not always what the config said (`optimizer: auto` silently overrode `lr0` once already — D043).
4. **The Cell 4 split counts** — proof the data matched.
5. **The Cell 8 eval output** — the held-out number.

---

## Two traps worth naming

**`optimizer: auto` discards your `lr0`.** It happened on this project already (D043). Check
the log line reading `optimizer: ... (lr=...)` and confirm it says what you configured.

**Batch changes between machines.** The Mac config uses 16, this uses 32. The comparison
against `multicountry_v8s` is therefore "different training setup, same held-out test set" —
which is a fair comparison of *outcomes*, but not a controlled experiment on epoch count.
Describe it that way.

**A different split invalidates everything.** Not just the new model's numbers — the
*comparison* too. Cell 4's assert is the whole safeguard; treat a mismatch as a stop, not a
warning.
