"""D061 — find near-duplicate images that cross a split boundary.

D059 showed adjacent *filenames* are uncorrelated. This asks the other question:
do near-identical images exist anywhere in the set? Two frames of the same
pothole seconds apart need not have adjacent ids, and a salted hash scatters them
independently — so one can land in train and its twin in test.

dHash: grayscale, resize to 9x8, compare each pixel with its right neighbour,
pack the 64 booleans into a uint64. Robust to resize and JPEG requantisation,
which matters because Norway was resized 4040 -> 1280 in T2.

Run this BEFORE T3. The upload bakes the splits in; a leak found afterwards
costs a re-upload and invalidates everything trained against it.
"""

import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.dataset.dedupe import (  # noqa: E402
    AUDIT_HAMMING,
    dhash,
    hamming_pairs,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO = repo_root() / CFG["paths"]["yolo"]


def names(split: str) -> list[str]:
    return [Path(x).stem for x in (YOLO / f"{split}.txt").read_text().splitlines() if x.strip()]


def hashes(stems: list[str], cache: dict) -> np.ndarray:
    for s in stems:
        if s not in cache:
            cache[s] = dhash(YOLO / "images" / f"{s}.jpg")
    return np.array([cache[s] for s in stems], dtype=np.uint64)


def close_pairs(a: np.ndarray, b: np.ndarray) -> list[tuple[int, int, int]]:
    return hamming_pairs(a, b, AUDIT_HAMMING)


def compare(label: str, left: str, right_splits: list[str], cache: dict) -> dict:
    ls = names(left)
    rs = sorted({n for s in right_splits for n in names(s)})
    print(f"{label}: hashing {len(ls)} + {len(rs)} ...", flush=True)
    la, ra = hashes(ls, cache), hashes(rs, cache)
    pairs = close_pairs(la, ra)
    out = [{"left": ls[i], "right": rs[j], "distance": d} for i, j, d in pairs]
    out.sort(key=lambda r: r["distance"])
    print(f"{label}: {len(out)} pairs within Hamming {AUDIT_HAMMING}", flush=True)
    return {
        "left_split": left,
        "right_splits": right_splits,
        "left_n": len(ls),
        "right_n": len(rs),
        "pairs": out,
    }


def main() -> int:
    cache: dict = {}
    india = compare("india", "india_train", ["india_cal", "india_test"], cache)
    nonindia = compare("nonindia", "nonindia_train", ["nonindia_val"], cache)

    payload = {
        "max_hamming": AUDIT_HAMMING,
        "method": "dHash 64-bit (9x8 grayscale row diffs)",
        "india_cross_split": india,
        "nonindia_cross_split": nonindia,
    }
    out = repo_root() / "results" / "T2"
    out.mkdir(parents=True, exist_ok=True)
    (out / "duplicates.json").write_text(json.dumps(payload, indent=2))

    md = [
        "# D061 — near-duplicate audit",
        "",
        f"64-bit dHash, flagged at Hamming distance <= {AUDIT_HAMMING}.",
        "",
        "| comparison | left | right | flagged pairs |",
        "|---|---|---|---|",
        f"| india_train vs cal+test | {india['left_n']} | {india['right_n']} | "
        f"**{len(india['pairs'])}** |",
        f"| nonindia_train vs val | {nonindia['left_n']} | {nonindia['right_n']} | "
        f"{len(nonindia['pairs'])} |",
        "",
    ]
    if india["pairs"]:
        md += [
            "## India cross-split pairs (closest 25)",
            "",
            "| left (train) | right (held out) | distance |",
            "|---|---|---|",
        ]
        md += [f"| {p['left']} | {p['right']} | {p['distance']} |" for p in india["pairs"][:25]]
    else:
        md += [
            "## India",
            "",
            "**No India cross-split near-duplicates.** The held-out "
            "India sets contain no image that closely resembles a training image, so "
            "the T6/T7 India numbers are not inflated by memorised frames.",
        ]
    md += [
        "",
        "## Non-India",
        "",
        f"{len(nonindia['pairs'])} pairs cross nonindia_train/val. Reported as a count "
        "only (D061): these inflate validation optimism and so affect early stopping, "
        "but they cannot reach the India sets the headline claim is measured on.",
    ]
    (out / "duplicates.md").write_text("\n".join(md) + "\n")
    print("\n" + "\n".join(md[:9]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
