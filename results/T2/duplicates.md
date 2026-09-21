# D061 — near-duplicate audit

64-bit dHash, flagged at Hamming distance <= 6.

| comparison | left | right | flagged pairs |
|---|---|---|---|
| india_train vs cal+test | 4623 | 2312 | **1940** |
| nonindia_train vs val | 24537 | 6142 | 3964 |

## India cross-split pairs (closest 25)

| left (train) | right (held out) | distance |
|---|---|---|
| India__India_002600 | India__India_002587 | 1 |
| India__India_003671 | India__India_009321 | 1 |
| India__India_003688 | India__India_003702 | 1 |
| India__India_004221 | India__India_000663 | 1 |
| India__India_004331 | India__India_003702 | 1 |
| India__India_004331 | India__India_008244 | 1 |
| India__India_004331 | India__India_009225 | 1 |
| India__India_000112 | India__India_005976 | 2 |
| India__India_001054 | India__India_003178 | 2 |
| India__India_001308 | India__India_003114 | 2 |
| India__India_001680 | India__India_009225 | 2 |
| India__India_003500 | India__India_009321 | 2 |
| India__India_003691 | India__India_002093 | 2 |
| India__India_004586 | India__India_003262 | 2 |
| India__India_004630 | India__India_005117 | 2 |
| India__India_005772 | India__India_008607 | 2 |
| India__India_006039 | India__India_004136 | 2 |
| India__India_006378 | India__India_004710 | 2 |
| India__India_007295 | India__India_009130 | 2 |
| India__India_007378 | India__India_002093 | 2 |
| India__India_007525 | India__India_003178 | 2 |
| India__India_007791 | India__India_006248 | 2 |
| India__India_007833 | India__India_001889 | 2 |
| India__India_007833 | India__India_002587 | 2 |
| India__India_007833 | India__India_005039 | 2 |

## Non-India

3964 pairs cross nonindia_train/val. Reported as a count only (D061): these inflate validation optimism and so affect early stopping, but they cannot reach the India sets the headline claim is measured on.
