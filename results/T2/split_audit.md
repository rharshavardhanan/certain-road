# T2 — split audit

Salt `roadsight-pool-v1`, seed 0. India is split per image, not in blocks of 50 — see D059.

| split | images | backgrounds | linear_crack | alligator_crack | pothole | total |
|---|---|---|---|---|---|---|
| india_cal | 1156 | 682 | 256 | 271 | 457 | 984 |
| india_full | 7706 | 4483 | 1623 | 2021 | 3187 | 6831 |
| india_heldout | 2312 | 1347 | 506 | 582 | 947 | 2035 |
| india_test | 1156 | 665 | 250 | 311 | 490 | 1051 |
| india_train | 4623 | 2691 | 969 | 1258 | 1938 | 4165 |
| india_val | 771 | 445 | 148 | 181 | 302 | 631 |
| nonindia_replay | 5000 | 1669 | 5810 | 1441 | 508 | 7759 |
| nonindia_train | 24537 | 8070 | 29025 | 6901 | 2681 | 38607 |
| nonindia_val | 6142 | 2065 | 7198 | 1694 | 676 | 9568 |

## Pothole share

- India: **46.7%** of instances
- non-India: **7.0%** of instances

## D10

D00 and D10 are merged into linear_crack; India has only 68 D10 instances (D037/D038/D055).

## Rejected boxes

- `unknown_class:D44`: 5057
- `unknown_class:D50`: 3581
- `unknown_class:Repair`: 1046
- `unknown_class:D43`: 793
- `unknown_class:D01`: 179
- `unknown_class:D11`: 45
- `unknown_class:Block crack`: 3
- `unknown_class:D0w0`: 1
- `degenerate_box`: 1

## Resized images

`max_side` is 1280; everything else is copied byte-for-byte.

- Norway: 8161

---

Split fractions, the India/non-India pothole share and the visual-QA
notes are in `findings.md` alongside this file. This file is generated
by `scripts/build_pool.py` and is overwritten on every run;
`findings.md` is authored and is not.
