# Training on Colab (T4)

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

Expect roughly **1–2 min/epoch** for India (4,617 images) → ~1.5 h for 50 epochs, and
**6–9 min/epoch** for multi-country (35,296) → 5–7 h. The multi-country run is close to
Colab's free session cap, which is exactly why `save_period: 5` matters.

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

**A different split invalidates everything.** Not just the new model's numbers — the
*comparison* too. Cell 4's assert is the whole safeguard; treat a mismatch as a stop, not a
warning.
