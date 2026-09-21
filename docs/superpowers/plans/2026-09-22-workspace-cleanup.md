# Workspace Cleanup and Repo Reorganisation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover ~12.9 GB of provably redundant disk, and make the GitHub repository legible to a first-time reader, without touching a single checkpoint that matters.

**Architecture:** Two independent workstreams. Tasks 1–2 operate exclusively inside gitignored trees (`data/`, `models/`, `runs/`) and produce no commit. Tasks 3–6 touch only tracked files and each end in a commit. Nothing in 1–2 can break 3–6 or vice versa, so a failure in either leaves the other intact.

**Tech Stack:** zsh, git, gzip, `uv run pytest`, `uv run lint-imports`, `uv run ruff`.

Design spec: [`../specs/2026-09-22-workspace-cleanup-design.md`](../specs/2026-09-22-workspace-cleanup-design.md)

## Global Constraints

- **Never delete these five files.** sha256 verified before and after:
  `runs/detect/models/yolo/multicountry_v8s/weights/best.pt` ·
  `runs/detect/models/yolo/multicountry_v8s/weights/last.pt` ·
  `runs/detect/models/yolo/multicountry_v8s_ext2/weights/best.pt` ·
  `runs/detect/models/yolo/multicountry_v8s_ext2/weights/last.pt` ·
  `runs/detect/models/yolo/india_v1/weights/best.pt`
- **Never touch `data/raw/RDD2022/`.** 46,091 symlinks under `data/processed/` point into it.
- `models/`, `runs/`, `data/` stay gitignored. No checkpoint is ever committed.
- Baseline to match at the end: **186 tests passing**, **0 broken symlinks**.
- Every task that changes a design decision updates `docs/DECISIONS.md` in the same commit (project rule).
- Pre-cleanup evidence lives in the scratchpad: `baseline-weights.txt`, `baseline-disk.txt`, `baseline-tests.txt`.

---

### Task 1: Redundant disk artifacts removed

**Goal:** The working tree drops from 28 GB to roughly 15 GB, and every remaining byte is either source, a keeper checkpoint, or the raw dataset the symlinks depend on.

**Why:** 12.9 GB of the tree is a source archive that was already extracted, a dataset ruled NO-GO, smoke tests, an LR-bug run, and external weights already rejected in D053. None of it is reachable from any code path; all of it is in the way.

**Files:**
- Delete: `data/raw/RDD2022_released_through_CRDDC2022.zip`
- Delete: `data/raw/water_potholes/`, `data/processed/water_potholes/`
- Delete: `runs/detect/models/yolo/{multicountry_v8s_ext,multicountry_v8s_smoke,india_v1_smoke,india_v8s}/`
- Delete: `runs/detect/models/yolo/india_v1/weights/last.pt`
- Delete: `models/candidates/yolo12s_RDD2022_best.pt`
- Delete: `runs/detect/val*/`, `runs/detect/train/`
- Delete: `yolov8n.pt`, `yolov8s.pt` (repo root)
- Delete: `.import_linter_cache/`, `.pytest_cache/`, `.ruff_cache/`

**Interfaces:**
- Consumes: the five sha256 values in `baseline-weights.txt`.
- Produces: nothing later tasks depend on. No commit — every path is gitignored.

- [x] **Step 1: Assert the keepers exist before deleting anything**

```bash
shasum -a 256 -c /path/to/scratchpad/baseline-weights.txt
```
Expected: five `OK` lines. If any line fails, stop — do not proceed to Step 2.

- [x] **Step 2: Delete the redundant run directories and the rejected external weights**

```bash
rm -rf runs/detect/models/yolo/multicountry_v8s_ext \
       runs/detect/models/yolo/multicountry_v8s_smoke \
       runs/detect/models/yolo/india_v1_smoke \
       runs/detect/models/yolo/india_v8s \
       models/candidates
rm -f  runs/detect/models/yolo/india_v1/weights/last.pt
```

- [x] **Step 3: Delete the validation dumps, root checkpoints and caches**

```bash
rm -rf runs/detect/val runs/detect/val-* runs/detect/train
rm -f  yolov8n.pt yolov8s.pt
rm -rf .import_linter_cache .pytest_cache .ruff_cache
```

- [x] **Step 4: Delete the NO-GO dataset (D039)**

```bash
rm -rf data/raw/water_potholes data/processed/water_potholes
```

- [x] **Step 5: Delete the 12 GB source archive (already extracted)**

```bash
rm -f data/raw/RDD2022_released_through_CRDDC2022.zip
```

- [x] **Step 6: Re-verify the keepers and the symlinks**

```bash
shasum -a 256 -c /path/to/scratchpad/baseline-weights.txt
find data/processed -type l ! -exec test -e {} \; -print | wc -l
```

**Done when:** all five checkpoints report `OK`, the broken-symlink count is `0`, `du -sh .` reports under 16 GB, and `ls runs/detect/models/yolo/` lists exactly `india_v1`, `multicountry_v8s`, `multicountry_v8s_ext2`.

---

### Task 2: Training logs compressed

**Goal:** `runs/logs/` drops from 18 MB to about 1 MB with every line still readable via `zcat`.

**Why:** three logs account for 17 of the 18 MB and are ultralytics progress-bar output. The per-epoch metrics they appear to hold are already in each run's `results.csv`. Deleting them loses the console record; compressing costs nothing and keeps it.

**Files:**
- Modify: `runs/logs/*.log` → `runs/logs/*.log.gz`

**Interfaces:**
- Consumes: nothing. Produces: nothing. No commit — `runs/` is gitignored.

- [x] **Step 1: Compress every log in place**

```bash
gzip -9 runs/logs/*.log
```

- [x] **Step 2: Confirm the content survived**

```bash
zcat runs/logs/train_v8s_continue_attempt1_lr_bug.log.gz | wc -l
du -sh runs/logs
```

**Done when:** `du -sh runs/logs` reports ≤ 2 MB, and the `zcat` line count is greater than zero (this file is the evidence behind D043 and must remain readable).

---

### Task 3: `docs/` slimmed to one walkthrough and a surfaced design doc

**Goal:** `docs/` holds one deep walkthrough instead of two overlapping documents, and the current design spec is reachable at `docs/design.md` rather than three directories down.

**Why:** `PROJECT-OVERVIEW.md` (604 lines) and `MENTOR-WALKTHROUGH.md` (1,377 lines) cover the same thirteen topics and both end with a section titled "The one-paragraph summary". Two documents describing one system drift apart; the next person to update one will forget the other.

**Files:**
- Modify: `docs/MENTOR-WALKTHROUGH.md` (absorb anything unique from the overview)
- Delete: `docs/PROJECT-OVERVIEW.md`
- Move: `docs/superpowers/specs/2026-08-06-certain-road-design.md` → `docs/design.md`
- Move: `docs/dataset-card-rdd2022-india.md`, `docs/dataset-multicountry-summary.md`, `docs/water-pothole-viability.md` → `docs/datasets/`
- Modify: `CLAUDE.md`, `docs/DECISIONS.md` (inbound links)

**Interfaces:**
- Consumes: nothing. Produces: `docs/design.md` and `docs/datasets/*`, which Task 4's README links to.

- [x] **Step 1: Diff the two documents section by section**

Read both headings lists. For every `PROJECT-OVERVIEW.md` section, decide: already covered in the walkthrough (drop) or unique (port). Sections 9 (Blockers) and 11 (Engineering principles) have no walkthrough equivalent — expect those to port.

- [x] **Step 2: Port the unique sections into `MENTOR-WALKTHROUGH.md`**

Insert ported content before `## 17. Questions you are likely to be asked`, renumbering the tail.

- [x] **Step 3: Move the files with `git mv` so history follows**

```bash
git rm docs/PROJECT-OVERVIEW.md
git mv docs/superpowers/specs/2026-08-06-certain-road-design.md docs/design.md
mkdir -p docs/datasets
git mv docs/dataset-card-rdd2022-india.md   docs/datasets/rdd2022-india.md
git mv docs/dataset-multicountry-summary.md docs/datasets/multicountry-summary.md
git mv docs/water-pothole-viability.md      docs/datasets/water-pothole-viability.md
```

- [x] **Step 4: Repair every inbound link**

```bash
grep -rn "PROJECT-OVERVIEW\|superpowers/specs/2026-08-06\|dataset-card-rdd2022-india\|dataset-multicountry-summary\|water-pothole-viability" \
  --include='*.md' . | grep -v '^./docs/superpowers/plans/archive/'
```
Expected after fixing: no hits outside `docs/superpowers/plans/archive/` (archived plans are a historical record and keep their original links).

- [x] **Step 5: Verify no link is dangling**

```bash
grep -rhoE '\]\(([^)]+\.md)[^)]*\)' --include='*.md' docs CLAUDE.md README.md \
  | sed -E 's/.*\(([^)#]+).*/\1/' | sort -u
```
Check each relative target resolves.

- [x] **Step 6: Commit**

```bash
git add -A docs CLAUDE.md
git commit -m "docs: merge overview into walkthrough, surface design doc, group dataset cards"
```

**Done when:** `ls docs/*.md` lists exactly `DECISIONS.md`, `MENTOR-WALKTHROUGH.md`, `colab-training-guide.md`, `design.md`, `detector-benchmark.md`; the Step 4 grep returns nothing outside the archive; every link from Step 5 resolves.

---

### Task 4: `README.md` written

**Goal:** A reader landing on the GitHub page understands what the project is, what it is not, what the numbers actually say, and how to run it — without opening another file.

**Why:** the single most-read file in the repository is 0 bytes. Every other problem in this cleanup is invisible next to that one.

**Files:**
- Modify: `README.md` (currently empty)

**Interfaces:**
- Consumes: `docs/design.md`, `docs/MENTOR-WALKTHROUGH.md`, `docs/DECISIONS.md`, `docs/detector-benchmark.md` (Task 3 must land first).
- Produces: nothing.

- [x] **Step 1: Write the README**

Required content, in order: one-line statement of what the system decides; the
D001 framing (a prioritisation system, not a pothole detector); the pipeline as
a single arrow chain; the honest detector numbers from `docs/detector-benchmark.md`
(mAP50 0.3932, and why the external model's 0.9765 was rejected under D053);
repository layout; quickstart commands lifted verbatim from the walkthrough's
demo cheat sheet; a pointer table to the four main documents; status.

Terminology rules from `CLAUDE.md` are binding: `vision_density`,
`apparent_severity`, `pci_ref`, "vision-estimated PCI", "evaluation segment".

- [x] **Step 2: Verify every command in the README actually runs**

```bash
uv run certain-road --help
uv run certain-road perception --help
```
Expected: both exit 0 and list the subcommands the README claims exist.

- [x] **Step 3: Commit**

```bash
git add README.md && git commit -m "docs: write README"
```

**Done when:** `wc -c README.md` is greater than 2000, every command in it exits 0, and every relative link resolves.

---

### Task 5: `pyproject.toml` description and `.gitignore` corrected

**Goal:** The package metadata says what the package is, and `.gitignore` contains no rule for a path that does not exist.

**Why:** `description = "Add your description here"` is uv's scaffold placeholder and appears in package metadata. The `!configs/assess/curves/` negation names a directory that was never created — a rule that has never matched anything, which reads as though provenance data exists when none does.

**Files:**
- Modify: `pyproject.toml:4`
- Modify: `.gitignore:7-8`, and add `.import_linter_cache/`

**Interfaces:**
- Consumes: nothing. Produces: nothing.

- [x] **Step 1: Replace the description placeholder**

```toml
description = "Pavement management decision support: which road segments to repair first under a fixed budget."
```

- [x] **Step 2: Drop the dead negation, add the missing cache**

Remove the `# Provenance IS committed…` comment and its `!configs/assess/curves/` line. Add `.import_linter_cache/` beside `.ruff_cache/`.

- [x] **Step 3: Confirm nothing that was tracked became ignored**

```bash
git ls-files | while read -r f; do git check-ignore -q "$f" && echo "NOW IGNORED: $f"; done
```
Expected: no output.

- [x] **Step 4: Confirm the package still builds its metadata**

```bash
uv run python -c "import importlib.metadata as m; print(m.metadata('certain-road')['Summary'])"
```
Expected: the new description string.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore
git commit -m "chore: real package description; drop dead gitignore rule for configs/assess"
```

**Done when:** Step 3 prints nothing, Step 4 prints the new summary, and `grep -c assess .gitignore` returns 0.

---

### Task 6: D054 recorded and the whole change verified

**Goal:** The decision log explains why the repository looks different, and the full test and architecture suite proves nothing broke.

**Why:** the project rule is explicit — a change that alters a design decision without amending `docs/DECISIONS.md` is an incomplete change. This cleanup moved the design spec, deleted a document and removed rejected weights; all three are decisions.

**Files:**
- Modify: `docs/DECISIONS.md` (index table row + new `## D054` entry at the end)

**Interfaces:**
- Consumes: the outcomes of Tasks 1–5.
- Produces: nothing.

- [x] **Step 1: Add the index row**

Append to the index table, after the D053 row:

```markdown
| D054 | Workspace cleaned and repo reorganised; rejected/superseded weights deleted, keepers named explicitly | Accepted |
```

- [x] **Step 2: Write the D054 entry**

Must state: what was deleted and the decision each deletion follows from (D039 water potholes, D043 the LR-bug `_ext` run, D053 the external weights); the five checkpoints preserved and why each; that `data/raw/RDD2022/` is load-bearing because `data/processed/` symlinks into it; that `models/`/`runs/`/`data/` remain gitignored and Git LFS was declined; that `docs/PROJECT-OVERVIEW.md` was merged into the walkthrough and the design spec surfaced to `docs/design.md`.

- [x] **Step 3: Run the full verification suite**

```bash
uv run pytest
uv run lint-imports
uv run ruff check .
```
Expected: `186 passed`; `Contracts: N kept, 0 broken`; `All checks passed!`.

- [x] **Step 4: Confirm the keepers one last time and check the diff is text-only**

```bash
shasum -a 256 -c /path/to/scratchpad/baseline-weights.txt
git diff --stat HEAD~3
```
Expected: five `OK`; no binary files in the diff.

- [x] **Step 5: Commit**

```bash
git add docs/DECISIONS.md
git commit -m "docs: D054 — workspace cleanup and repo reorganisation"
```

**Done when:** `uv run pytest` reports 186 passed, `lint-imports` reports 0 broken contracts, `ruff check` passes, all five checkpoints verify `OK`, and `git status` is clean.
