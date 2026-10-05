# Camera-Based Pothole and Crack Survey for Road Maintenance Planning

Source code for DA-2 · Robot Perception (BCSE425L) · repository `certain-road`

This archive holds the repository's tracked files: code, configuration, tests, committed
results and documents. It was made with `git archive`, so it carries no git history and
none of the gitignored data.

## Start here

1. [`docs/ONBOARDING.md`](docs/ONBOARDING.md): one page covering what the system is, how to
   install and check it, where things live, and what has not run.
2. [`docs/DA2-EVIDENCE.md`](docs/DA2-EVIDENCE.md): each DA-2 deliverable, the files that
   satisfy it, and its status.
3. [`results/RESULTS.md`](results/RESULTS.md): every result, each table naming the file it
   was read from.

## Check it

You need [`uv`](https://docs.astral.sh/uv/), which provides Python 3.12 and every pinned
dependency, and `git`. No GPU is needed.

```bash
uv sync --all-extras --dev
git init -q && git add -A && git -c user.name=reviewer -c user.email=reviewer@localhost commit -qm snapshot
uv run python scripts/check_repo.py
```

`scripts/check_repo.py` runs every check CI runs: ruff, the format check, the
stage-isolation contracts, the test suite, the repo map and the freshness of every
generated file. It exits non-zero if any of them fails.

The `git` line is needed because the checks read the repository through git, and an
archive has no `.git`. Without it, two tests in `tests/test_repo_hygiene.py` fail and the
repo-map step stops.

This archive, extracted and checked that way on macOS on 2026-10-05, gave
`6 of 6 steps passed`. The check ran in a sandbox that could not read the original
checkout, with the 2,312 links below pointing at a home directory that does not exist, as
on a reviewer's machine:

- `pytest`: 422 passed and 16 skipped. Each skipped test needs the gitignored image pool,
  and its skip message names the script that builds it.
- `repo map`: rewrote `docs/REPO-MAP.md`. The map inventories git history, and a snapshot
  has a single commit, so this step reports a change and never fails.

On Windows the 2,312 links described below extract as plain files, and the two link
checks in `tests/test_repo_hygiene.py` will report them.

## Not included

- `data/`: the RDD2022 images (about 22 GB). `uv run certain-road dataset fetch` downloads
  them.
- `runs/` and `models/`: training runs and trained weights from the Kaggle runs. The locked
  results in `results/LOCKED/` record each weight file's sha256.
- The 2,312 image links in `results/LOCKED/P_india_heldout_run/gt_root/images/` point at the
  original machine and do not resolve here (D084). The image list and labels beside them
  are the record.

## DA-2 documents

| Document | What it is |
|---|---|
| [`docs/DA2-EVIDENCE.md`](docs/DA2-EVIDENCE.md) | One page per deliverable, each with its status |
| [`docs/DA2-SCOPE-CHANGE.md`](docs/DA2-SCOPE-CHANGE.md) | The deck's scope-change slides, numbers from `results/` |
| [`docs/CHALLENGES.md`](docs/CHALLENGES.md) | Five challenges: what broke, how it was found, what changed |
| [`docs/wiring-esp32p4.svg`](docs/wiring-esp32p4.svg) | The ESP32-P4 sensor-hub wiring, a design that has not been built |
| [`results/figures/MANIFEST.md`](results/figures/MANIFEST.md) | The deck's figures, each with its source |
