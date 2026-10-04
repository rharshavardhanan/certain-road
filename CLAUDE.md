# certain-road

A pavement management decision-support system. It answers **"which road segments
should be repaired first, given a fixed budget?"** — not "where is a pothole".

Camera → YOLOv8s detectors (Model B, three-class; Model P, pothole-only) →
vision-estimated PCI → conformal interval → RSL interval (designed, not built) →
budget optimiser → offline HTML dashboard.

**Status (2026-10-04, from [`docs/REPO-MAP.md`](docs/REPO-MAP.md) §6):** built and
tested. T1–T7, T9–T12, T16 and T17 have their outputs. T13 (simulation), T14 (edge
hardware) and T15 (Chennai footage) are not run; §10a says what each waits for. T0
and T8 have no output to check. The map is generated from evidence: rerun
`uv run python scripts/repo_map.py` instead of trusting this paragraph.
`uv run python scripts/check_repo.py` runs every check CI runs.

## Read these first

- [`docs/design.md`](docs/design.md) — the current design.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — the decision log: every choice, why it
  was made, and what superseded it.
- [`docs/ONBOARDING.md`](docs/ONBOARDING.md) — one page: install, check, where
  things live, what has not run.
- [`docs/REPO-MAP.md`](docs/REPO-MAP.md) — generated: what every file does, task
  status with its evidence, and what is left.

## Maintaining the decision log

**Any change that alters a design decision must update `docs/DECISIONS.md` in the
same commit.** A code change that contradicts the log without amending it is an
incomplete change.

- Append a new numbered entry `Dnnn`. Never renumber, never delete.
- When a decision is replaced, mark the old entry `Superseded by Dnnn` and leave its
  text intact. The wrong turn stays visible — that history is the point.
- Add the entry to the index table at the top.
- Keep the spec document in sync when the change is structural.

## Conventions

- **Python 3.12** via `uv` only. Own `pyproject.toml` and committed `uv.lock` —
  never the shared `~/PROJECTS/venv`. `requirements.txt` is *generated* from the
  lock (`uv export --format requirements-txt --no-hashes`) and never hand-edited;
  Kaggle kernels install only `ultralytics==<pin>` plus `pycocotools` (D056).
- Torch/YOLO run on the MPS (Metal) backend, not CUDA.
- **Stages never import each other.** They communicate only through typed artifacts
  on disk. `import-linter` enforces this in CI; a cross-stage import fails the build.
  Only `artifacts/` and `core/` are shared.
- No magic numbers in code. Every tunable lives in `configs/`.
- Terminology is load-bearing and enforced in review:
  - `vision_density`, never bare `density` (ASTM density is physical area)
  - `apparent_severity`, never bare `severity` (visual prominence, not structural)
  - `pci_ref` / "reference PCI", never `pci_true`
  - "vision-estimated PCI", never bare "PCI"
  - "evaluation segment" for RDD2022 partitions, never "road segment"
- The manual-rating set is **validation, never a dev set.** The model is not tuned
  against it, and poor agreement is a result to report, not a defect to fix.
- `data/`, `models/` and `runs/` are gitignored. Digitized curve points in
  `configs/assess/curves/` are committed — they are provenance, not data.
