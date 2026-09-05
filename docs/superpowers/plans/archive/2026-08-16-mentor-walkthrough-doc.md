# Plan — mentor walkthrough document

**2026-08-16 · branch `week-1-foundation`**

A documentation-only task with a single deliverable, so this plan is deliberately
short: there is one file to write and its correctness is checkable by reading it
against the code it describes. No source changes, no tests, no decision-log entry
(nothing about the design changes).

## Context

The project owner presents to their mentor tomorrow (2026-08-17). The existing
`docs/PROJECT-OVERVIEW.md` is a *design* document — it argues for choices and
assumes the reader knows what mAP and a conformal interval are. What is missing is a
*walkthrough*: what each file and folder does, where the models and data came from,
how the training code works, and what conformal prediction is in plain language.

**Audience (owner-confirmed):** technically literate but not an ML person. Every ML
term is defined at first use. Delivery is a markdown file in the repo only — no
published web page.

## Constraints

- Every claim about the code must be read out of the code, not inferred from the
  design docs. `PROJECT-OVERVIEW.md` is already stale in at least one place (it
  says run 3 is "running"; it is stopped at epoch 12 of 23).
- The repo's terminology rules apply — this file is checked in. `vision_density`,
  `apparent_severity`, `pci_ref`, "vision-estimated PCI", "evaluation segment".
- Report training state as it actually is on disk, including the paused runs and
  the harness's -0.0288 mAP50 divergence. A presentation document that overstates
  progress is worse than one that under-promises.

## Task 1 — write `docs/MENTOR-WALKTHROUGH.md`

**Goal.** A single self-contained document that a non-ML technical reader can follow
end to end, covering: repo map, every file's purpose, the models and their
provenance, the dataset acquisition and categorisation, the training code and its
knobs, every run and its numbers, the remaining model options, the evaluation
harness, and conformal prediction in layman's terms.

**Why.** Without it the owner has to explain twelve files, four training runs and a
statistics concept from memory, live, to someone who cannot be assumed to know what
a bounding box is. The existing overview argues design; it does not orient a newcomer.

**Files.** Create `docs/MENTOR-WALKTHROUGH.md`. No other file is touched.

**Steps.**
1. Read every source file, config, and the decision log — done before writing, so
   file descriptions quote real function names and real numbers.
2. Verify live state from disk rather than from docs: split counts from
   `splits.json`, epoch counts from each run's `results.csv`, test count from
   `pytest --collect-only`, image dimensions and a real label file for the worked
   conversion example.
3. Write the document, glossary first, conformal prediction as the centrepiece.
4. Close with a demo command sheet and a likely-questions section, both of which
   are what the document is actually *for*.

**Done when.** `docs/MENTOR-WALKTHROUGH.md` exists and:
- `uv run ruff check .` and `uv run lint-imports` still pass (docs are excluded from
  ruff, so this only proves nothing was broken);
- every numeric claim in it matches a command's output pasted in the verification
  step — specifically 74 collected tests, India splits 4617/757/1548/784,
  `multicountry_v8s_ext2` at 12 epochs, harness mAP50 0.3932 vs reference 0.4220;
- no bare `density`, bare `severity`, `pci_true`, or bare "PCI" appears, checkable
  with `grep -nE '\b(pci_true|bare)\b'` and a read-through.
