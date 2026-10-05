# DA-2: two screenshots, then the source zip rebuilt from HEAD

2026-10-05 · for the DA-2 review · executed inline (TodoWrite is not available here)

**Goal:** deliverable 5 (Screenshots) is complete with two captures in
`results/figures/`, the DA-2 pack is committed, and `dist/certain-road-DA2-source.zip` is
a plain `git archive HEAD` that passes `scripts/check_repo.py` the way a reviewer runs it.

## Brainstorm — what the request did not state

- **The DA-2 pack is uncommitted, and another session wrote it.** That covers
  `README-DA2.md`, the four DA-2 documents, `results/figures/` 01–20 with `MANIFEST.md`,
  its plan, and the `/dist/` line in `.gitignore`. A commit naming only the two new
  figures would leave HEAD with a manifest listing 20 missing files.
  `certain-road-08` owns the pack and agreed (2026-10-05) that this session commits it,
  by explicit path.
- **Its MuJoCo work stays out:** `sim/`, `configs/sim/mujoco.yaml` and `textures.yaml`,
  the mujoco-demo plan, and the `mujoco` line in `pyproject.toml`, `uv.lock` and
  `requirements.txt`. The MuJoCo simulator is not started.
- **The figures are captures, not byte copies.** The manifest says every file is a byte
  copy of a committed file, "except two", so that sentence must also name 21 and 22.
- **The frame is chosen by evidence, not by eye.** It is the frame where the most of
  Model P's confirmed tracks that hit a ground-truth pothole (`gt_score.json`) are live at
  once, so it shows confirmed tracks on real potholes rather than false alarms.
- **Stale numbers 08 flagged:** "all 84 decisions" (D086 has landed since); "438 passed
  at `0a9d02a`"; the manifest's "except two"; and README-DA2's "6 of 6", which was
  measured on an overlay zip, not on HEAD. Each is recounted, not assumed.
- **The zip check needs git.** `check_repo.py` reads the repo through git, so the zip is
  checked as README-DA2 tells a reviewer: extract, `git init`, a snapshot commit, then
  `check_repo.py`. This runs in a sandbox that hides the original checkout, with the
  locked links repointed at a home directory that does not exist. The script is a copy
  of 08's `reviewer_sim.sh`.
- **README-DA2 sits inside the zip it describes.** If its numbers change, the zip is
  rebuilt and checked again.

## Tasks

1. **Figure 21, the dashboard.** Headless Chrome through the DevTools protocol, full page,
   `prefers-color-scheme: light`. *Done when* the PNG opens and shows the whole page.
2. **Figure 22, a video frame.** The frame chosen as above, extracted with `ffmpeg`.
   *Done when* the PNG shows green confirmed-track boxes with their IDs.
3. **Docs.** Manifest rows 21–22 and its header; DA2-EVIDENCE page 5 complete, plus the
   stale numbers on pages 4, 12 and 13. *Done when* a number check (`numcheck.py`, with
   its snapshot sources recomputed live) reports 0 mismatches.
4. **Commit** the pack by explicit path, gated on `check_repo.py`; then a map-only commit.
   *Done when* `git status` lists only 08's MuJoCo work.
5. **Zip.** `git archive --format=zip --prefix=certain-road/ HEAD -- . ':(exclude)data'
   ':(exclude)runs'`, run through the reviewer check, README-DA2 corrected if needed,
   rebuilt and checked again. *Done when* the check exits 0 on the final zip; report its
   size and file count.
