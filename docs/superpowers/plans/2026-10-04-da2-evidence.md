# DA-2 review pack

2026-10-04 · written overnight for the DA-2 review on 2026-10-05 · nothing committed

> **For agentic workers:** executed inline with superpowers:executing-plans. TodoWrite is not
> available in this harness, so the checkboxes below are the running state.

**Goal:** the six DA-2 deliverables exist in the repo and as one submission zip, each one
traceable to a file or a result, under the new topic **Camera-Based Pothole and Crack Survey
for Road Maintenance Planning**.

**Architecture:** documents and copies only. No code changes, no GPU, no new experiments.
Every number is read from `results/` or `docs/DECISIONS.md`; every figure is a byte copy of
a committed file, except one hand-drawn SVG labelled as a design.

## Brainstorm — what the request did not state

The request was fully specified, so the brainstorm went to the constraints it could not
contain. The session was non-interactive and the request said "generate these tonight", so
these were decided rather than asked. Each one is open to review.

- **The reader is the DA-2 panel** (Robot Perception, BCSE425L, VIT Chennai), who saw the
  Review 1 deck (`CertainRoad_Review_One.pdf`, 2026-08-17). It is not in the repo and is
  cited by filename and page.
- **Topic.** The new title goes on every document produced tonight. `README.md`,
  `CLAUDE.md`, `docs/design.md` and the dashboard keep their titles. Retitling them is a
  separate change.
- **No commit** (global rule; D058 covers spec tasks only). `git archive HEAD` would omit
  tonight's files, so the zip is built from HEAD's tree plus the new files through a
  throwaway index (`GIT_INDEX_FILE`). The real index and every ref are untouched.
- **Concurrent sessions edit this repo.** Only new files plus one `.gitignore` line.
  `DECISIONS.md`, `REPO-MAP.md`, `RESULTS.md` and `README.md` are not touched, and
  `check_repo.py` is not run in the real tree, because its map step rewrites `REPO-MAP.md`.
- **`tests/test_repo_hygiene.py` fails any committed file that contains an absolute
  home-directory path** (outside its pinned list). The new files use repo-relative paths
  only, and this plan describes the rule without writing one out.
- **A git archive is not a git repo.** `check_repo.py` calls git, so the zip is checked the
  way a reviewer gets it: extracted, then `git init` before the checks run.
- **Honest status.** T13, T14 and T15 never ran (REPO-MAP §10a). The ESP32-P4 and MPU6050
  appear in no decision or config, so the wiring diagram is labelled as a design.
- **The CRC switch was a spec choice, not evidence.** D085 records that the RoadSight spec
  adopted at T0 (`a23bf6a`) made the certified miss rate the core claim. The evidence then
  shaped how CRC was run (D070, D076, D077). The scope-change slides say so.
- **Ultralytics' confusion matrices are not copied.** The project reports confusion from
  its own scorer at conf 0.25 (`results/T7/A_vs_B_india_test.json`). PR-curve legends are
  ultralytics' AP; the manifest names the pycocotools figure beside each one.

Log gaps found while sourcing. None is fixed here; `DECISIONS.md` is append-only and other
sessions write to it.

- D004 rejected conformal risk control on false negatives in favour of a segment-level
  vision-estimated PCI interval. T10 built exactly that, and D004/D005 are still Accepted.
  D085 records only D051's reversal.
- D074 says the four Kaggle smoke failures are recorded in D060. D060 does not mention
  them. They are in `TASK_LOG.md` (2026-09-22) and `kaggle/train/train.py`.
- Nothing records the choice of ESP32-P4 or MPU6050. `docs/design.md`'s hardware appendix
  and the Review 1 deck list a Jetson Orin Nano, a camera and a NEO-6M GPS only.
- `CLAUDE.md` says digitized curve points are committed in `configs/assess/curves/`. That
  directory does not exist, and `survey/scoring.py` says it uses no D6433 deduct curves,
  while D016 and D017 are still Accepted.

## Global constraints

- Title string, exactly: `Camera-Based Pothole and Crack Survey for Road Maintenance Planning`.
- Terminology (`CLAUDE.md`): vision-estimated PCI, never bare PCI; reference PCI /
  `pci_ref`, never `pci_true`; `vision_density`, `apparent_severity`; "evaluation segment"
  for RDD2022 partitions.
- No absolute home path in any new file. Links and paths are repo-relative.
- Every number in `docs/DA2-SCOPE-CHANGE.md` names the `results/` file and key it comes
  from.
- Status words in `docs/DA2-EVIDENCE.md`: **complete** means the named files cover the
  deliverable; **partial** means part is covered and the page names the absent part;
  **missing** means nothing in the repo covers it.

## Files

| File | Change | Responsibility |
|---|---|---|
| `docs/wiring-esp32p4.svg` | create | ESP32-P4 sensor hub wiring, labelled as a design |
| `results/figures/*` | create | byte copies of the deck's figures |
| `results/figures/MANIFEST.md` | create | each copy's source, producer and what it shows |
| `docs/CHALLENGES.md` | create | five challenges: what broke, how it was found, what changed |
| `docs/DA2-SCOPE-CHANGE.md` | create | the deck's scope-change slides, numbers from `results/` |
| `docs/DA2-EVIDENCE.md` | create | one page per DA-2 deliverable, with status and files |
| `README-DA2.md` | create | the archive's front page |
| `.gitignore` | modify | ignore `/dist/` |
| `dist/certain-road-DA2-source.zip` | create (ignored) | the submission archive |

---

## Task 1 — wiring diagram

**Goal** A standalone SVG shows the ESP32-P4 wired to a NEO-6M (VCC, GND, TX) and an
MPU6050 (VCC, GND, SCL, SDA), the 3.3 V-only rule, and the USB link to the Jetson.

**Why** DA-2 asks for wiring and the repo has none. A diagram that reads as a built
prototype would overclaim T14, which never ran.

**Files** `docs/wiring-esp32p4.svg`

**Steps**
- [x] Draw it by hand: white background, `<title>`/`<desc>`, colour per signal.
  ESP32-P4 pins are labelled by function (3V3, GND, UART RX, I²C SCL, I²C SDA) because
  the GPIO matrix makes the pin numbers a firmware choice.
- [x] Note on the diagram: design for T14, not built or tested. Name the defaults it
  assumes: NMEA at 9600 baud, I²C address 0x68 with AD0 low, 100 Hz IMU
  (`configs/project.yaml` `edge.imu_hz`).
- [x] Render to PNG with `qlmanage` in the scratchpad, look at it, fix overlaps.

**Done when** `python3 -c "import xml.dom.minidom as m; print(m.parse('docs/wiring-esp32p4.svg').documentElement.tagName)"`
prints `svg`, and
`python3 -c "s=open('docs/wiring-esp32p4.svg').read(); print([t for t in ['ESP32-P4','NEO-6M','MPU6050','VCC','GND','TX','SCL','SDA','3.3 V','USB','Jetson','not built'] if t not in s])"`
prints `[]`.

## Task 2 — figures folder and manifest

**Goal** `results/figures/` holds byte copies of the 20 figures a DA-2 deck would use, in
deck order. `MANIFEST.md` names each copy's source file, its producer and what it shows.

**Why** The figures are spread over 10 directories under `results/`, with four files named
`BoxPR_curve.png`. A deck built from them by hand would mislabel at least one.

**Files** `results/figures/01-…19-*`, `results/figures/MANIFEST.md`

**Steps**
- [x] Copy 18 result figures, the simulator render (`runs/sim/centre.png`, the only
  screenshot of the running software) and the Task 1 SVG under numbered descriptive names.
- [x] Write the manifest from what each figure itself shows (viewed, not inferred from its
  filename), with the producing script or the commit that added it.
- [x] List what was deliberately not copied, and why.

**Done when**
`python3 -c "import re,filecmp,os; rows=re.findall(r'^\| \x60([0-9]{2}-[^\x60]+)\x60 \| \x60([^\x60]+)\x60', open('results/figures/MANIFEST.md').read(), re.M); bad=[c for c,s in rows if not filecmp.cmp('results/figures/'+c, s, shallow=False)]; extra=set(os.listdir('results/figures'))-{c for c,_ in rows}-{'MANIFEST.md'}; print(len(rows), 'rows', bad, sorted(extra))"`
prints `20 rows [] []`.

## Task 3 — challenges

**Goal** `docs/CHALLENGES.md` covers the five challenges (the same-scene leak D061/D063,
the drift alarm D078, the Kaggle smoke failures, the India gap correction D069, the
Bengaluru silence D080). Each has what broke, how it was found, what changed, and the
evidence files.

**Why** "Challenges" is a DA-2 deliverable. The decision log holds all five, spread over
roughly 3,400 lines, and two of them have no D-number of their own.

**Files** `docs/CHALLENGES.md`

**Steps**
- [x] Draft each section from its entries. Take the after-numbers from the result files
  where they exist (`results/T2/exhaustive_leak.json`, `results/T11/drift.json`,
  `results/T6/localisation.json`, `results/video/2DV-cYmIvT4/extent.json`).
- [x] Cite the smoke failures where they are actually recorded (`TASK_LOG.md`,
  `kaggle/train/train.py`, the kernel-preflight plan), not D060.

**Done when** the Task 7 number check prints every challenge number as found in its source.

## Task 4 — scope-change slides

**Goal** `docs/DA2-SCOPE-CHANGE.md` is a deck section of four slides: the title change,
promised against built, what the evidence forced, and what moved to the next phase. Every
number is read from `results/` and cites the file and key.

**Why** DA-1 promised a split-conformal interval on each evaluation segment's
vision-estimated PCI, an abstention rule and RSL (Review 1 deck p.15, 17, 22). DA-2
delivers conformal risk control on the pothole miss rate, a drift alarm and the budget
optimiser. The panel will ask why.

**Files** `docs/DA2-SCOPE-CHANGE.md`

**Steps**
- [x] Map each DA-1 promise to its deck page and to what was built or deferred.
- [x] Write the evidence slide from `results/T10/feasibility.json`,
  `results/T10/conformal.json`, `results/T11/drift.json` and `results/T12/allocation.json`.
- [x] State plainly that CRC came from the spec at T0 (D085), not from the evidence.

**Done when** the Task 7 number check prints `0 mismatches` for this file.

## Task 5 — evidence index

**Goal** `docs/DA2-EVIDENCE.md` has a summary table and one page per DA-2 deliverable
(architecture, algorithm, model, source code, screenshots, preliminary results, sensor
selection, wiring, embedded setup, integration, prototype, testing, challenges). Each page
names the exact files and carries a status of complete, partial or missing.

**Why** The panel checks deliverables against a list. Without the index, each check means
a search through 4,954 tracked files.

**Files** `docs/DA2-EVIDENCE.md`

**Steps**
- [x] Write the summary table, then one page per deliverable, page-broken for printing.
- [x] Mark hardware honestly: T14 was not run, and no firmware or photo exists.
- [x] Give each page a "show it" line where a file or command exists.

**Done when**
`python3 -c "import re,subprocess,os; t=open('docs/DA2-EVIDENCE.md').read(); heads=re.findall(r'^## \d+\. (.+)$', t, re.M); st=re.findall(r'^\*\*Status: (complete|partial|missing)\*\*', t, re.M); print(len(heads), len(st))"`
prints `13 13`, and the Task 7 path check finds every cited path.

## Task 6 — submission archive

**Goal** `dist/certain-road-DA2-source.zip` holds HEAD's tracked files plus tonight's
deliverables, with no `data/` or `runs/` entries and `README-DA2.md` at its root. Extracted
and checked the way a reviewer would, its result is stated in `README-DA2.md`.

**Why** Source code is a DA-2 deliverable, and a working copy carries about 25 GB of
gitignored data and runs (`data/` 22 GB, `runs/` 2.6 GB).

**Files** `README-DA2.md`, `.gitignore`, `dist/certain-road-DA2-source.zip`

**Steps**
- [x] Write `README-DA2.md`: title, what the archive is, start at `docs/ONBOARDING.md`,
  check with `scripts/check_repo.py` (and what a snapshot needs first), what is not
  included.
- [x] Add `/dist/` to `.gitignore`.
- [x] Build: a throwaway index from HEAD plus the new files, `git write-tree`, then
  `git archive --format=zip --prefix=certain-road/ <tree> -- . ':(exclude)data' ':(exclude)runs'`.
- [x] Extract into the scratchpad, `git init` and commit there, run `uv sync --all-extras --dev`
  and `uv run python scripts/check_repo.py`, and record the result in `README-DA2.md`.
  If `README-DA2.md` changes, rebuild.

**Rebuild after the files are committed** (then the zip is plain `git archive HEAD`):

```bash
git archive --format=zip --prefix=certain-road/ -o dist/certain-road-DA2-source.zip HEAD -- . ':(exclude)data' ':(exclude)runs'
```

**Done when**
`unzip -Z1 dist/certain-road-DA2-source.zip | grep -cE '^certain-road/(data|runs)/'` prints
`0`;
`unzip -Z1 dist/certain-road-DA2-source.zip | grep -cE '^certain-road/(README-DA2.md|docs/DA2-EVIDENCE.md|docs/DA2-SCOPE-CHANGE.md|docs/CHALLENGES.md|docs/wiring-esp32p4.svg|results/figures/MANIFEST.md|configs/data/model_a.yaml)$'`
prints `7`; and the extracted copy's `check_repo.py` output is pasted in the session record.

## Task 7 — verification before claiming done

**Goal** Evidence, not assertion, that the pack is correct and broke nothing.

**Why** Every number in these documents will be read aloud to a panel.

**Files** none (scratchpad scripts only)

**Steps**
- [x] Number check: a list of (string in doc, source file, key) for every quoted figure,
  each asserted against the JSON or text it cites.
- [x] Path check: every backticked repo path in the new docs exists in the archive tree,
  or is flagged in the text as gitignored.
- [x] Home-path regex from `tests/test_repo_hygiene.py` over every new file: no match.
- [x] Terminology scan: no `pci_true`, no bare `PCI`, `density` or `severity`.
- [x] `uv run pytest` in the real repo: same count as before tonight, exit 0.
- [x] `git status --short` lists only the files in the table above.

**Done when** each check's output is pasted in the session record with its exit code.
