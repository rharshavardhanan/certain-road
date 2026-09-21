# Dataset summary — RDD2022, all six non-India countries

**Source:** RDD2022, DOI `10.6084/m9.figshare.21431547.v1`, CC BY 4.0. Same 13.26 GB
outer archive as the India subset (D032/D036); `extract_country` unwraps the two-level
per-country nesting for each of `China_Drone`, `China_MotorBike`, `Czech`, `Japan`,
`Norway`, `United_States`.

## Approved design

The detector trains on **all seven countries**; conformal calibration and testing stay
**India-only** (`calib`/`test` unchanged from the India-only baseline). A conformal
guarantee is only meaningful relative to a describable population — calibrating on a
blend of six countries would produce intervals valid for an artificial mixture that
exists nowhere, and deployment is Indian roads, so `calib` and `test` must remain
Indian. See `docs/DECISIONS.md` D041.

This document covers extraction, census and conversion only. Split redesign and
retraining are separate, later work — `dataset split` was not run for the new
countries and no training was launched.

## Extraction

All six countries were extracted with the existing `extract_country` (D036), which
streams each inner per-country zip to a temporary file (1 MiB chunks) before
extracting it, rather than reading the member into memory. Extraction of all six
completed in well under two minutes total (fast local SSD); Norway — the largest
inner zip at 10.6 GB — extracted in ~28 seconds.

**Memory verified, not assumed:** Norway's extraction was re-run under
`/usr/bin/time -l`. Peak process RSS was **63,651,840 bytes (~61 MB)** — roughly
0.6% of the 10.6 GB member being copied — confirming the streaming implementation
never materializes the inner zip in memory.

**Disk:** 775 GiB free before extraction, 760 GiB free after (six countries add
~15 GB raw). Plenty of headroom; the 13 GB outer archive was never re-downloaded.

| Country | Train images | Train annotations | Test images (unlabelled) | Total images |
|---|---|---|---|---|
| China_Drone | 2,401 | 2,401 | 0 | 2,401 |
| China_MotorBike | 1,977 | 1,977 | 500 | 2,477 |
| Czech | 2,829 | 2,829 | 709 | 3,538 |
| Japan | 10,506 | 10,506 | 2,627 | 13,133 |
| Norway | 8,161 | 8,161 | 2,040 | 10,201 |
| United_States | 4,805 | 4,805 | 1,200 | 6,005 |
| India (existing, D036) | 7,706 | 7,706 | 1,959 | 9,665 |

All six new countries are 1:1 image:annotation within `train/` (unlike India, no
orphan images occur in the annotated set). These measured counts match D032's
originally published table exactly for all six; D032's numbers were previously
verified only for India (corrected by D036) and are now confirmed against the real
archive for the rest.

`China_Drone` ships no `test/` directory at all — every one of its images is
annotated.

## Class census

`certain-road dataset census --country <X>` over each country's full annotation set.
No `PARSE_ERROR` rows occurred for any country — every XML file parsed cleanly.

**China_Drone** (2,401 annotations, 3,840 boxes):

| Class | Boxes | Status |
|---|---|---|
| D00 | 1,426 | KEEP |
| D10 | 1,263 | KEEP |
| Repair | 769 | DROP |
| D20 | 293 | KEEP |
| D40 | 86 | KEEP |
| Block crack | 3 | DROP |

Total 3,840; kept 3,068; dropped 772.

**China_MotorBike** (1,977 annotations, 4,927 boxes):

| Class | Boxes | Status |
|---|---|---|
| D00 | 2,678 | KEEP |
| D10 | 1,096 | KEEP |
| D20 | 641 | KEEP |
| Repair | 277 | DROP |
| D40 | 235 | KEEP |

Total 4,927; kept 4,650; dropped 277.

**Czech** (2,829 annotations, 1,745 boxes):

| Class | Boxes | Status |
|---|---|---|
| D00 | 988 | KEEP |
| D10 | 399 | KEEP |
| D40 | 197 | KEEP |
| D20 | 161 | KEEP |

Total 1,745; kept 1,745; dropped 0. Only the four official CRDDC2022 classes appear.

**Japan** (10,506 annotations, 24,754 boxes):

| Class | Boxes | Status |
|---|---|---|
| D20 | 6,199 | KEEP |
| D00 | 4,049 | KEEP |
| D44 | 3,995 | DROP |
| D10 | 3,979 | KEEP |
| D50 | 3,553 | DROP |
| D40 | 2,243 | KEEP |
| D43 | 736 | DROP |

Total 24,754; kept 16,470; dropped 8,284. `D44`/`D50`/`D43` are the same
non-CRDDC2022 strings D037 found in India, now confirmed present in a second
country at much larger absolute counts (Japan's `D44` alone, 3,995, is nearly four
times India's 1,062).

**Norway** (8,161 annotations, 11,229 boxes):

| Class | Boxes | Status |
|---|---|---|
| D00 | 8,570 | KEEP |
| D10 | 1,730 | KEEP |
| D20 | 468 | KEEP |
| D40 | 461 | KEEP |

Total 11,229; kept 11,229; dropped 0. Only the four official classes.

**United_States** (4,805 annotations, 11,014 boxes):

| Class | Boxes | Status |
|---|---|---|
| D00 | 6,750 | KEEP |
| D10 | 3,295 | KEEP |
| D20 | 834 | KEEP |
| D40 | 135 | KEEP |

Total 11,014; kept 11,014; dropped 0. Only the four official classes.

**Unrecognised class strings found, across all six countries:**

| String | Country | Boxes | Also seen in India (D037)? |
|---|---|---|---|
| D44 | Japan | 3,995 | yes (1,062) |
| D50 | Japan | 3,553 | yes (28) |
| Repair | China_Drone, China_MotorBike | 769 + 277 = 1,046 | no |
| D43 | Japan | 736 | yes (57) |
| Block crack | China_Drone | 3 | no |

`Repair` and `Block crack` are new strings not present in India's census; `D44`,
`D50`, `D43` recur from India in Japan at larger scale. `SOURCE_TO_ID` is unchanged
(D038's three-class mapping); every one of these boxes is counted and dropped, never
silently discarded.

## Conversion

`certain-road dataset convert --country <X>` for each. `SOURCE_TO_ID` (D038: D00 and
D10 merge to `linear_crack`, D20 → `alligator_crack`, D40 → `pothole`) applies
unchanged to every country.

| Country | Label files written | Boxes kept | Boxes rejected | Rejection breakdown |
|---|---|---|---|---|
| China_Drone | 2,401 | 3,068 | 772 | unknown_class:Repair 769, unknown_class:Block crack 3 |
| China_MotorBike | 1,977 | 4,650 | 277 | unknown_class:Repair 277 |
| Czech | 2,829 | 1,745 | 0 | — |
| Japan | 10,506 | 16,469 | 8,285 | unknown_class:D44 3,995, unknown_class:D50 3,553, unknown_class:D43 736, degenerate_box 1 |
| Norway | 8,161 | 11,229 | 0 | — |
| United_States | 4,805 | 11,014 | 0 | — |

**Reconciliation (kept + dropped = census total), per country:**

- China_Drone: 3,068 + 772 = 3,840 ✓ (census total 3,840)
- China_MotorBike: 4,650 + 277 = 4,927 ✓ (census total 4,927)
- Czech: 1,745 + 0 = 1,745 ✓ (census total 1,745)
- Japan: 16,469 + 8,285 = 24,754 ✓ (census total 24,754)
- Norway: 11,229 + 0 = 11,229 ✓ (census total 11,229)
- United_States: 11,014 + 0 = 11,014 ✓ (census total 11,014)

Japan is the one country where `convert`'s kept count (16,469) differs from the
census's naive class-keep count (16,470): one box among the class-keep set had a
`degenerate_box` geometry (zero-area after clamping/sorting) and was dropped during
conversion, a check the census does not perform. It is fully accounted for under
`degenerate_box` in the rejection breakdown, so the arithmetic still closes exactly
against the census total — no unexplained gap.

## Combined per-class box counts (all seven countries)

Counted directly from the generated YOLO label files (`data/processed/<country>/labels_all/*.txt`),
which is the ground truth of what a training run would actually see — not
re-derived from the per-country class census, so it already reflects the one
Japan `degenerate_box` drop.

| Country | linear_crack | alligator_crack | pothole | total kept |
|---|---|---|---|---|
| India | 1,623 | 2,021 | 3,187 | 6,831 |
| China_Drone | 2,689 | 293 | 86 | 3,068 |
| China_MotorBike | 3,774 | 641 | 235 | 4,650 |
| Czech | 1,387 | 161 | 197 | 1,745 |
| Japan | 8,028 | 6,198 | 2,243 | 16,469 |
| Norway | 10,300 | 468 | 461 | 11,229 |
| United_States | 10,045 | 834 | 135 | 11,014 |
| **Combined** | **37,846** | **10,616** | **6,544** | **55,006** |

**Class balance shift:** in the India-only baseline, `linear_crack` was both the
smallest class (1,623 of 6,831 boxes, 23.8%) and the weakest by mAP50 (0.2842). In
the combined seven-country corpus it is now the **largest** class by a wide margin
(37,846 of 55,006 boxes, 68.8%) — every non-India country is dominated by `D00`
(longitudinal crack), which alone contributes far more boxes than all of India's
`linear_crack` instances combined. `alligator_crack` grows from 2,021 to 10,616
(19.3% of the combined total) and `pothole`, previously the largest class in India
(3,187 of 6,831, 46.7%), shrinks to the smallest share of the combined corpus (6,544
of 55,006, 11.9%) even though its absolute count roughly doubles. Whether the
tenfold increase in raw `linear_crack` examples improves that class's mAP50, or
whether the new majority-class imbalance instead hurts `pothole` and
`alligator_crack` recall, is a question for the retraining run this task does not
launch.

## Verification

```
uv run ruff check .            # All checks passed!
uv run ruff format --check .   # 35 files already formatted
uv run lint-imports             # Contracts: 2 kept, 0 broken.
uv run pytest -q                # 52 passed
```

No source files changed in this task — extraction, census and conversion all ran
through the existing `certain-road dataset {fetch,census,convert}` commands, so the
suite count is unchanged from the pre-task baseline.

`data/`, `runs/` and `models/` remain gitignored; `git status` is clean of anything
under those trees after this work.
