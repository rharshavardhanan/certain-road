# Workspace cleanup and repo reorganisation — design

**2026-09-22** · supersedes nothing; recorded as D054

## Problem

Two separate problems wearing one costume.

**On disk:** the working tree is 28 GB, of which ~12.9 GB is provably redundant —
a 12 GB source archive that was already extracted, 564 MB of a dataset ruled
NO-GO in D039, 196 MB of smoke-test and LR-bug training runs, 18 MB of external
weights rejected in D053, and 25 MB of unnamed ultralytics validation dumps
across 21 directories, 14 of them empty.

**On GitHub:** the most-read file in the repository, `README.md`, is 0 bytes.
`pyproject.toml` still carries uv's `"Add your description here"` placeholder.
Two long documents — `PROJECT-OVERVIEW.md` (604 lines) and
`MENTOR-WALKTHROUGH.md` (1,377 lines) — cover the same thirteen topics and both
end with a section titled "The one-paragraph summary". The current design spec
sits three directories deep.

## Non-goals

- Committing weights. `models/`, `runs/` and `data/` stay gitignored. Git LFS was
  considered and declined: 395 MB of checkpoints in git history is unrecoverable.
- Removing `torchvision` / `tqdm` from `pyproject.toml`. Neither is imported
  directly, but ultralytics pins both and the explicit torchvision pin guards the
  torch pairing. Two lines saved is not worth the breakage risk.
- Relocating `docs/superpowers/plans/`. The global workflow writes every plan to
  exactly that path; moving it breaks the documented pipeline and saves nothing
  at repository root.
- Rewriting git history. It is already clean: 3.4 MB, no blob over 292 KB.

## Design

### Disk

Delete, all inside gitignored trees:

| path | size | justification |
|---|---|---|
| `data/raw/RDD2022_released_through_CRDDC2022.zip` | 12 GB | extracted already; sha256 recorded in `CHECKSUMS.txt`; no code reads the zip |
| `data/raw/water_potholes/`, `data/processed/water_potholes/` | 564 MB | D039 NO-GO; finding preserved in `docs/datasets/water-pothole-viability.md` |
| `runs/detect/models/yolo/multicountry_v8s_ext/` | 130 MB | killed after one epoch by the LR bug; superseded by `_ext2` |
| `runs/detect/models/yolo/multicountry_v8s_smoke/` | 49 MB | smoke test |
| `models/candidates/yolo12s_RDD2022_best.pt` | 18 MB | D053 rejected as unmeasurable; re-downloadable from HuggingFace |
| `runs/detect/models/yolo/india_v1_smoke/` | 17 MB | smoke test |
| `runs/detect/val*/`, `runs/detect/train/` | 25 MB | unnamed validation dumps; 14 of 21 are empty |
| `yolov8n.pt`, `yolov8s.pt` (repo root) | 28 MB | ultralytics re-fetches bare-name checkpoints on demand |
| `runs/detect/models/yolo/india_v1/weights/last.pt` | 6 MB | run completed; `best.pt` at epoch 84 is the D042 baseline |
| `runs/detect/models/yolo/india_v8s/` | 1.4 MB | aborted run, produced no weights |
| `.import_linter_cache/`, `.pytest_cache/`, `.ruff_cache/` | ~100 KB | regenerable |

Compress `runs/logs/*.log` (18 MB to roughly 1 MB). The per-epoch metrics already
live in each run's `results.csv`; the logs are progress-bar output.

Preserved without modification, verified by sha256 before and after:

- `runs/detect/models/yolo/multicountry_v8s/weights/{best,last}.pt` — the
  benchmarked model (D042, D043). `last.pt` is the start point named in
  `configs/train/yolov8s_continue.yaml` and must not be removed.
- `runs/detect/models/yolo/multicountry_v8s_ext2/weights/{best,last}.pt` — the
  paused 12/23-epoch continuation, kept whole by owner decision.
- `runs/detect/models/yolo/india_v1/weights/best.pt` — the D042 baseline.

`data/raw/RDD2022/` is load-bearing, not a duplicate: every image under
`data/processed/*/images/` is a symlink into it. 46,091 links resolve today and
must still resolve afterwards.

### Repository

Root after the change:

```
.github/  configs/  docs/  scripts/  src/  tests/
README.md  CLAUDE.md  pyproject.toml  uv.lock
.gitignore  .importlinter  .python-version
```

`configs/` and `scripts/` stay where they are, by owner decision. `docs/` is
slimmed:

- `PROJECT-OVERVIEW.md` merged into `MENTOR-WALKTHROUGH.md`, then deleted.
- `docs/superpowers/specs/2026-08-06-certain-road-design.md` surfaced to
  `docs/design.md`; inbound links in `CLAUDE.md` and `docs/DECISIONS.md` updated.
- The three dataset documents grouped under `docs/datasets/`.

### Small fixes

`README.md` written from empty. `pyproject.toml` description replaced. `.gitignore`
loses the dead `!configs/assess/curves/` negation — that directory was never
created — and gains `.import_linter_cache/`.

## Verification

- `uv run pytest` — 186 passed, matching the pre-cleanup baseline.
- `uv run lint-imports` — stage isolation contracts hold.
- `uv run ruff check` — clean.
- sha256 of all five preserved checkpoints unchanged.
- 46,091 `data/processed/` symlinks still resolve, 0 broken.
- `git status` clean after commit; no file in the diff larger than 100 KB.
