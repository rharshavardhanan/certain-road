"""D061 — one implementation of image similarity, shared by every caller.

There were briefly two: the audit hashed with PIL/LANCZOS and the grouper with
cv2/INTER_AREA. Different resampling gives different hashes, so the audit flagged
pairs the grouper had never even considered, and the leak it was meant to close
stayed open. A duplicate-detection routine that disagrees with itself is worse
than none, because it reports success.

The grouping prefilter is deliberately **looser** than the audit threshold
(`GROUP_HAMMING` > `AUDIT_HAMMING`). Anything the audit can flag must already
have been considered for grouping, or the audit can find leaks the grouper was
structurally unable to prevent.
"""

from pathlib import Path

import cv2
import numpy as np

AUDIT_HAMMING = 6
GROUP_HAMMING = 12          # strictly looser, so grouping is a superset
SAME_SCENE_CORR = 0.93      # calibrated by inspection: 0.94+ is visibly the same
                            # location, 0.915- is a different scene sharing a layout
POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
CHUNK = 512


def dhash(path: Path) -> np.uint64:
    """64-bit difference hash. cv2/INTER_AREA everywhere — see module docstring."""
    im = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise FileNotFoundError(path)
    px = cv2.resize(im, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (px[:, 1:] > px[:, :-1]).ravel()
    return np.uint64(int("".join("1" if b else "0" for b in bits), 2))


def norm_vec(path: Path) -> np.ndarray:
    """Mean-centred, unit-norm 128x128 grayscale: dot product is correlation."""
    im = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise FileNotFoundError(path)
    v = cv2.resize(im, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    v -= v.mean()
    n = float(np.linalg.norm(v))
    return v / n if n else v


def hamming_pairs(
    left: np.ndarray, right: np.ndarray, max_distance: int, *, same_set: bool = False
) -> list[tuple[int, int, int]]:
    """Index pairs within `max_distance`. `same_set` yields each pair once."""
    found = []
    for start in range(0, len(left), CHUNK):
        block = left[start:start + CHUNK]
        xor = np.bitwise_xor(block[:, None], right[None, :])
        dist = POPCOUNT[xor.view(np.uint8).reshape(*xor.shape, 8)].sum(-1)
        for i, j in zip(*np.where(dist <= max_distance), strict=True):
            a, b = start + int(i), int(j)
            if same_set and a >= b:
                continue
            found.append((a, b, int(dist[i, j])))
    return found


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
