"""D061 — group India images that show the same road scene.

The audit found pairs across the train/held-out boundary that are not the same
*frame* but are the same *place*, captured seconds apart: identical stacked
pipes, identical signboards, the same parked vehicles. For generalization that
is just as contaminating as a byte-identical duplicate — a model that has seen
one has effectively seen the other.

Two stages, because neither alone is right:
  1. **dHash <= 6** as a cheap prefilter over all 7,706 India images.
  2. **Pixel correlation >= 0.93** as the decision, calibrated by inspection:
     pairs at 0.94+ are visibly the same location, pairs at 0.915- are different
     scenes that merely share a dashcam composition.

Grouping is transitive by union-find. If A and B are the same place and B and C
are, then all three must land in the same split even when A and C fall below
threshold — a chain of overlapping frames along one stretch of road is exactly
how this data is captured.
"""

import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.dataset.dedupe import (  # noqa: E402
    GROUP_HAMMING,
    SAME_SCENE_CORR,
    UnionFind,
    dhash,
    hamming_pairs,
    norm_vec,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO = repo_root() / CFG["paths"]["yolo"]


def main() -> int:
    names = sorted(p.stem for p in (YOLO / "images").glob("India__*.jpg"))
    print(f"hashing {len(names)} India images ...", flush=True)
    hashes = np.array([dhash(YOLO / "images" / f"{n}.jpg") for n in names], dtype=np.uint64)

    print("finding dHash candidates ...", flush=True)
    candidates = [(a, b) for a, b, _ in
                  hamming_pairs(hashes, hashes, GROUP_HAMMING, same_set=True)]
    print(f"{len(candidates)} candidate pairs; scoring by pixel correlation ...", flush=True)

    cache: dict[int, np.ndarray] = {}

    def vec(i: int) -> np.ndarray:
        if i not in cache:
            cache[i] = norm_vec(YOLO / "images" / f"{names[i]}.jpg")
        return cache[i]

    uf = UnionFind(len(names))
    linked = []
    for a, b in candidates:
        corr = float(vec(a) @ vec(b))
        if corr >= SAME_SCENE_CORR:
            uf.union(a, b)
            linked.append({"a": names[a], "b": names[b], "corr": round(corr, 4)})

    groups: dict[int, list[str]] = {}
    for idx, name in enumerate(names):
        groups.setdefault(uf.find(idx), []).append(name)
    multi = {str(k): sorted(v) for k, v in groups.items() if len(v) > 1}

    grouped_images = sum(len(v) for v in multi.values())
    payload = {
        "max_hamming": GROUP_HAMMING, "same_scene_corr": SAME_SCENE_CORR,
        "india_images": len(names), "candidate_pairs": len(candidates),
        "linked_pairs": len(linked), "groups": multi,
        "group_count": len(multi), "grouped_images": grouped_images,
        "largest_group": max((len(v) for v in multi.values()), default=0),
    }
    out = repo_root() / "results" / "T2"
    (out / "india_scene_groups.json").write_text(json.dumps(payload, indent=2))

    print(f"\nlinked pairs      : {len(linked)}")
    print(f"multi-image groups: {len(multi)}")
    print(f"images in a group : {grouped_images} of {len(names)}")
    print(f"largest group     : {payload['largest_group']} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
