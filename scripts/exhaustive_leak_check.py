"""D062 — prove the India holdout is clean by comparing *every* pair.

The dHash audit could only ever confirm that none of the pairs **it flagged**
were same-scene. That is circular: two frames of one location a few metres apart
can differ by more than Hamming 12, in which case neither the grouper nor the
audit ever compares them, and the leak goes unseen precisely because the
prefilter missed it.

No prefilter is needed. Every image is already a unit-norm 128x128 vector, so
correlation for all pairs is one matrix multiply: 4,623 x 2,312 over 16,384
dimensions is ~1.7e11 multiply-adds, seconds in BLAS. "Leak closed" becomes
provable rather than assumed.

Vectors are cached so the test suite can assert the same bound without
recomputing them.
"""

import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.dataset.dedupe import SAME_SCENE_CORR, norm_vec  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO = repo_root() / CFG["paths"]["yolo"]
CACHE = YOLO / "_vectors"
NONINDIA_CHUNK = 4000


def split_names(split: str) -> list[str]:
    return [Path(x).stem for x in (YOLO / f"{split}.txt").read_text().splitlines() if x.strip()]


def vectors(names: list[str], tag: str) -> np.ndarray:
    """Load or build the stacked unit-norm matrix for `names`."""
    CACHE.mkdir(parents=True, exist_ok=True)
    npy, idx = CACHE / f"{tag}.npy", CACHE / f"{tag}.json"
    if npy.exists() and idx.exists() and json.loads(idx.read_text()) == names:
        return np.load(npy)
    print(f"  building {len(names)} vectors for {tag} ...", flush=True)
    mat = np.empty((len(names), 128 * 128), dtype=np.float32)
    for i, n in enumerate(names):
        mat[i] = norm_vec(YOLO / "images" / f"{n}.jpg")
    np.save(npy, mat)
    idx.write_text(json.dumps(names))
    return mat


def top_pairs(corr: np.ndarray, left: list[str], right: list[str], k: int):
    flat = np.argpartition(corr.ravel(), -k)[-k:]
    flat = flat[np.argsort(-corr.ravel()[flat])]
    out = []
    for f in flat:
        i, j = divmod(int(f), corr.shape[1])
        out.append({"left": left[i], "right": right[j], "corr": round(float(corr[i, j]), 4)})
    return out


def main() -> int:
    print("=== check 1: india_train x india_heldout (exhaustive) ===", flush=True)
    train = split_names("india_train")
    held = sorted(set(split_names("india_val")) | set(split_names("india_cal"))
                  | set(split_names("india_test")))
    a, b = vectors(train, "india_train"), vectors(held, "india_heldout_all")
    corr = a @ b.T
    c1_max = float(corr.max())
    c1_bad = int((corr >= SAME_SCENE_CORR).sum())
    c1_top = top_pairs(corr, train, held, 20)
    print(f"  pairs compared : {corr.size:,}")
    print(f"  max correlation: {c1_max:.4f}")
    print(f"  pairs >= {SAME_SCENE_CORR}: {c1_bad}")
    del corr

    print("\n=== check 2: all India x nonindia_train (exhaustive, chunked) ===", flush=True)
    india = sorted(set(split_names("india_full")))
    ia = vectors(india, "india_full")
    non = split_names("nonindia_train")
    c2_max, c2_bad, best = -1.0, 0, []
    for start in range(0, len(non), NONINDIA_CHUNK):
        names = non[start:start + NONINDIA_CHUNK]
        nb = vectors(names, f"nonindia_train_{start // NONINDIA_CHUNK}")
        block = ia @ nb.T
        c2_max = max(c2_max, float(block.max()))
        c2_bad += int((block >= SAME_SCENE_CORR).sum())
        best.extend(top_pairs(block, india, names, 10))
        print(f"  chunk {start // NONINDIA_CHUNK}: running max {c2_max:.4f}", flush=True)
        del block
    best.sort(key=lambda r: -r["corr"])
    print(f"  pairs compared : {len(india) * len(non):,}")
    print(f"  max correlation: {c2_max:.4f}")
    print(f"  pairs >= {SAME_SCENE_CORR}: {c2_bad}")

    payload = {
        "same_scene_corr": SAME_SCENE_CORR,
        "india_internal": {"pairs": len(train) * len(held), "max_corr": round(c1_max, 4),
                           "count_over_threshold": c1_bad, "top20": c1_top},
        "india_vs_nonindia": {"pairs": len(india) * len(non), "max_corr": round(c2_max, 4),
                              "count_over_threshold": c2_bad, "top10": best[:10]},
        "verdict": "CLEAN" if (c1_bad == 0 and c2_bad == 0) else "LEAK",
    }
    out = repo_root() / "results" / "T2"
    (out / "exhaustive_leak.json").write_text(json.dumps(payload, indent=2))
    print(f"\nVERDICT: {payload['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
