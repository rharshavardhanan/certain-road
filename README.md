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

One detector feeds **two pipelines that never touch** (D049):

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
   Serial · CAN · Null · Sim
```

**Stages never import each other.** They communicate only through typed Parquet artifacts
on disk, and `import-linter` enforces it in CI — `driving/` and `canbus/` may not import
`survey/`, and `survey/` may not import `driving/`. A cross-pipeline import fails the build.

That rule is what makes the schedule work: the survey side is built and tested against
synthetic fixtures, with no trained model, no GPU and no hardware, so a 12-hour training run
never blocks development.

The control transport is abstract (D049), so the same `driving/` modules run against a
serial link, a CAN bus, a null sink, or the simulator without knowing the difference. The
simulator is simply a fourth `Transport` (D050) — real YOLO and real decision logic, with
only actuation synthesised.

## Status

Built, tested, in CI: the `uv` project and `typer` CLI, the stage-isolation contracts,
versioned Parquet artifact IO, the RDD2022 data pipeline, detector training, the detector
evaluation harness, the drive pipeline (corridor test, decision state machine, CAN
protocol), the simulator, and the drive recorder. **186 tests.**

Designed and specified, not yet written: `assess` (boxes → vision-estimated PCI), `rsl`,
the budget optimiser, and the dashboard.

Conformal prediction was **cut from the sprint** (D051). The survey pipeline ends at
vision-estimated PCI; the calibration split is preserved so the layer can be added back
without redoing the data work.

## The detector, honestly

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

# the architecture is enforced, not just described
uv run lint-imports
uv run pytest

# what the CLI offers
uv run certain-road --help

# what is actually in the data — every class string, KEEP or DROP
uv run certain-road dataset census --country India

# evaluate the trained detector end to end (a few minutes on MPS)
uv run certain-road perception eval \
  --weights runs/detect/models/yolo/multicountry_v8s/weights/best.pt \
  --split test --country india --out /tmp/eval.md

# inference producing a typed artifact
uv run certain-road perception predict \
  --weights runs/detect/models/yolo/multicountry_v8s/weights/best.pt \
  --images data/processed/india/images/test \
  --out /tmp/detections.parquet

# the drive pipeline, no hardware required
uv run certain-road sim run --scenario centre
```

> ⚠️ Do not run `dataset split` during a demo — it clears and re-links image directories.

Torch runs on the **MPS (Metal)** backend, not CUDA. `data/`, `models/` and `runs/` are
gitignored; the dataset is acquired with `certain-road dataset fetch`.

## Layout

```
configs/     every tunable — no magic numbers in code
docs/        design, decisions, walkthrough, dataset cards
scripts/     fixture generation and training progress
src/         the certain_road package, one module per stage
tests/       186 tests, including the architecture contracts
```

## Documentation

| Document | What it is |
|---|---|
| [`docs/design.md`](docs/design.md) | The authoritative design spec |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every choice, why it was made, and what superseded it — append-only, 54 entries |
| [`docs/MENTOR-WALKTHROUGH.md`](docs/MENTOR-WALKTHROUGH.md) | What every file is and how it works, from first principles |
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
