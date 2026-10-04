# certain-road

**Which road segments should be repaired first, given a fixed budget?**

That is the question this system answers. It is deliberately *not* "where is a pothole?" —
pothole detection is a solved, crowded problem. Turning detections into a defensible repair
priority list a highways department can act on is not.

A system that says *"there is a pothole at these coordinates"* does not help an agency with
a fixed annual budget. A system that says *"this evaluation segment has a vision-estimated
PCI of 48, its remaining service life is 0.8–1.4 years, repairing it costs ₹3.2 lakh — fund
it before segment 17"* does.

---

## Architecture

The perception stage feeds **two pipelines that never touch** (D049):

```
                    camera / recorded video
                              │
                       [ perception ]          YOLOv8 → bounding boxes
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
         [ driving ]                     [ survey ]
   "what do I do right now?"    "what do we know about this road?"
              │                               │
      corridor test                   evaluation segments
      state machine                  vision-estimated PCI
       Command                               │
              │                         [ dashboard ]
        [ canbus ]                    offline HTML report
        CAN · Null
```

**Stages never import each other.** They communicate only through typed Parquet artifacts
on disk, and `import-linter` enforces it in CI — `driving/` and `canbus/` may not import
`survey/`, and `survey/` may not import `driving/`. A cross-pipeline import fails the build.

That rule is what makes the schedule work: the survey side is built and tested against
synthetic fixtures, with no trained model, no GPU and no hardware, so a 12-hour training run
never blocks development.

The control transport is abstract (D049): `driving/` writes to a `Transport`, and a CAN
transport and a null sink exist; a serial link is designed but not written. The simulator
(D050) runs the same corridor test and decision state machine against scripted scenarios,
with no detector and no hardware.

## Status

Task status is generated from evidence in [`docs/REPO-MAP.md`](docs/REPO-MAP.md) §6;
rerun `uv run python scripts/repo_map.py` for the current state. On 2026-10-04:

- **Done:** the raw audit and leakage-proof splits (T1–T3), the MPS check (T4), Kaggle
  training (T5), locked evaluation of Models A, B and P (T6, T7, T9), conformal risk
  control (T10), the drift alarm (T11), repair allocation (T12), the offline dashboard
  (T16) and [`results/RESULTS.md`](results/RESULTS.md) (T17).
- **Not run:** the Webots simulation (T13), edge hardware (T14) and Chennai footage (T15).
  REPO-MAP §10a says what each waits for.
- **Designed, not built:** the remaining-service-life (RSL) stage (D018 is Open).

## The detector, honestly

The current detectors are Model B (three-class) and Model P (pothole-only, selected for
potholes in D074). Their locked held-out numbers are in
[`results/RESULTS.md`](results/RESULTS.md), generated from `results/LOCKED/`. The table
below is the earlier `multicountry_v8s` benchmark, kept because the rejection of external
weights (D053) rests on it.

| model | source | mAP50 | mAP50-95 | latency |
|---|---|---:|---:|---:|
| `multicountry_v8s` | ours, provenance-controlled | **0.3932** | 0.1662 | 8.4 ms |

A modest detector, and the per-class breakdown says why: alligator cracking reaches AP50
0.5761, potholes 0.3432, and thin low-contrast linear cracks only 0.2603.

An external RDD2022 checkpoint scored 0.9765 mAP50 on the same test set. **That number was
rejected, not celebrated** (D053): it is inconsistent with a held-out evaluation and
indicates the model had already seen those images. Our test split is carved by salted hash
from RDD2022's own training data, so any model trained on RDD2022 has seen it. The full
argument, including the honest limits of the claim, is in
[`docs/detector-benchmark.md`](docs/detector-benchmark.md).

## Quickstart

```bash
uv sync

# every check CI runs: lint, formatting, the architecture contracts, the suite,
# the generated repo map, and the freshness of every generated file
uv run python scripts/check_repo.py

# what the CLI offers
uv run certain-road --help

# the drive pipeline, no hardware required (writes runs/sim/centre.png)
uv run certain-road sim run --scenario centre

# needs the RDD2022 archive under data/raw/ (`certain-road dataset fetch`):
# every class string in the annotations, KEEP or DROP
uv run certain-road dataset census --country India
```

Every script that produced a result, in the order to rerun them, is in
[`docs/REPO-MAP.md`](docs/REPO-MAP.md) §11.

> ⚠️ Do not run `dataset split` during a demo — it clears and re-links image directories.

Torch runs on the **MPS (Metal)** backend, not CUDA. `data/`, `models/` and `runs/` are
gitignored; the dataset is acquired with `certain-road dataset fetch`.

## Layout

```
configs/     every tunable — no magic numbers in code
docs/        design, decisions, generated repo map, walkthrough, dataset cards
kaggle/      the training kernel pushed to Kaggle
results/     committed results; results/LOCKED/ holds the one-shot evaluations
scripts/     experiments, evaluation, the report, the dashboard, repo tooling
src/         the certain_road package, one module per stage
tests/       the test suite, including the architecture contracts
```

## Documentation

| Document | What it is |
|---|---|
| [`docs/ONBOARDING.md`](docs/ONBOARDING.md) | Start here: install, check, where things live, what has not run |
| [`docs/design.md`](docs/design.md) | The authoritative design spec |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every choice, why it was made, and what superseded it — append-only |
| [`docs/REPO-MAP.md`](docs/REPO-MAP.md) | Generated: every file's purpose, task status with evidence, what is left, how to reproduce |
| [`results/RESULTS.md`](results/RESULTS.md) | Generated: every result, each table with the file it was read from |
| [`docs/MENTOR-WALKTHROUGH.md`](docs/MENTOR-WALKTHROUGH.md) | The code from first principles, as it stood on 2026-09-22 (its last update) |
| [`docs/detector-benchmark.md`](docs/detector-benchmark.md) | The India test-set benchmark and the rejected external weights |
| [`docs/datasets/`](docs/datasets/) | Dataset cards, including one rejected dataset and the evidence for rejecting it |

**The decision log is the point.** Wrong turns are marked superseded and left intact rather
than deleted — that history is deliberately visible.

## Terminology

These words are load-bearing and enforced in review, because each prevents a specific
overclaim:

- **`vision_density`**, never bare `density` — ASTM density is a physical area
- **`apparent_severity`**, never bare `severity` — visual prominence, not structural
- **`pci_ref`** / reference PCI, never `pci_true`
- **vision-estimated PCI**, never bare PCI
- **evaluation segment** for RDD2022 partitions, never "road segment"

The manual-rating set is **validation, never a dev set.** The model is not tuned against it,
and poor agreement is a result to report, not a defect to fix.
