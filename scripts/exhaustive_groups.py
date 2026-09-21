"""D062 — build scene groups from an EXHAUSTIVE comparison, not a hash prefilter.

`scene_groups.py` grouped from dHash candidates, so any same-scene pair the hash
missed was never a grouping candidate and survived into the split. The exhaustive
check found 1,373 such pairs across the India boundary. Groups are now built from
every India-India pair, so the split is clean by construction rather than by
iteration.

It also drops non-India training images that duplicate an India image. Model A
trains on non-India and is measured on India, so a duplicate spanning the two is
a direct leak into the headline claim. Removing the *non-India* side keeps the
India evaluation sets whole and costs a fraction of a percent of training data.
"""

import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.dataset.dedupe import SAME_SCENE_CORR, UnionFind  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO = repo_root() / CFG["paths"]["yolo"]
CACHE = YOLO / "_vectors"
BLOCK = 1500


def load(tag: str) -> tuple[list[str], np.ndarray]:
    return json.loads((CACHE / f"{tag}.json").read_text()), np.load(CACHE / f"{tag}.npy")


def main() -> int:
    india, iv = load("india_full")
    print(f"exhaustive India x India over {len(india):,} images ...", flush=True)
    uf = UnionFind(len(india))
    linked = 0
    for start in range(0, len(india), BLOCK):
        block = iv[start:start + BLOCK] @ iv.T
        rows, cols = np.where(block >= SAME_SCENE_CORR)
        for r, c in zip(rows, cols, strict=True):
            a, b = start + int(r), int(c)
            if a < b:
                uf.union(a, b)
                linked += 1
        del block
    groups: dict[int, list[str]] = {}
    for i, name in enumerate(india):
        groups.setdefault(uf.find(i), []).append(name)
    multi = {str(k): sorted(v) for k, v in groups.items() if len(v) > 1}
    sizes = sorted((len(v) for v in multi.values()), reverse=True)
    print(f"  linked pairs {linked:,} -> {len(multi)} groups covering "
          f"{sum(sizes):,} images; largest {sizes[0] if sizes else 0}")

    print("\nexhaustive India x nonindia_train ...", flush=True)
    drop: set[str] = set()
    worst = -1.0
    for chunk in range(99):
        tag = f"nonindia_train_{chunk}"
        if not (CACHE / f"{tag}.json").exists():
            break
        names, nv = load(tag)
        block = iv @ nv.T
        worst = max(worst, float(block.max()))
        cols = np.where((block >= SAME_SCENE_CORR).any(axis=0))[0]
        drop.update(names[int(c)] for c in cols)
        del block
    print(f"  max {worst:.4f}; dropping {len(drop)} non-India training images")

    out = repo_root() / "results" / "T2"
    (out / "india_scene_groups.json").write_text(json.dumps({
        "method": "exhaustive India x India pixel correlation (no hash prefilter)",
        "same_scene_corr": SAME_SCENE_CORR, "india_images": len(india),
        "linked_pairs": linked, "groups": multi, "group_count": len(multi),
        "grouped_images": sum(sizes), "largest_group": sizes[0] if sizes else 0,
    }, indent=2))
    (out / "nonindia_excluded.json").write_text(json.dumps({
        "reason": "duplicates an India image at corr >= "
                  f"{SAME_SCENE_CORR}; Model A must not train on it",
        "max_corr": round(worst, 4), "count": len(drop), "stems": sorted(drop),
    }, indent=2))
    print(f"\nwrote india_scene_groups.json ({len(multi)} groups) and "
          f"nonindia_excluded.json ({len(drop)} stems)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
