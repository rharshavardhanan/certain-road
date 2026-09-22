"""D072 — does BharatPotHole overlap the India holdout?

Both are Indian dashcam pothole datasets, so shared source footage is entirely
plausible, and Model P is about to train on BharatPotHole while being judged on
india_test. A duplicate spanning the two would invalidate that judgement.

Cross-*dataset*, so the question is "same file", not "same scene": threshold
0.98 per D066. Exhaustive, no hash prefilter, per D063.
"""

import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.dataset.dedupe import norm_vec  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
BPH = repo_root() / "data/raw/bharatpothole/BharatPotHole/BharatPotHole"
DUPLICATE_CORR = 0.98          # D066: cross-dataset means "same file", not "same scene"
CHUNK = 1500


def india_heldout_vectors():
    stems = sorted({Path(x).stem for s in ("india_cal", "india_test")
                    for x in (YOLO_DIR / f"{s}.txt").read_text().splitlines() if x.strip()})
    mat = np.empty((len(stems), 128 * 128), dtype=np.float32)
    for i, s in enumerate(stems):
        mat[i] = norm_vec(YOLO_DIR / "images" / f"{s}.jpg")
    return stems, mat


def main() -> int:
    held_stems, held = india_heldout_vectors()
    print(f"india_cal + india_test: {len(held_stems)} images", flush=True)

    report = {"threshold": DUPLICATE_CORR, "splits": {}}
    for split in ("train", "valid", "test"):
        paths = sorted((BPH / split / "images").glob("*.jpg"))
        print(f"BharatPotHole/{split}: {len(paths)} images ...", flush=True)
        best_overall, hits = -1.0, []
        for start in range(0, len(paths), CHUNK):
            block = paths[start:start + CHUNK]
            mat = np.empty((len(block), 128 * 128), dtype=np.float32)
            for i, p in enumerate(block):
                mat[i] = norm_vec(p)
            corr = mat @ held.T
            best_overall = max(best_overall, float(corr.max()))
            rows, cols = np.where(corr >= DUPLICATE_CORR)
            for r, c in zip(rows, cols, strict=True):
                hits.append({"bph": block[int(r)].stem, "india": held_stems[int(c)],
                             "corr": round(float(corr[r, c]), 4)})
            del corr
        report["splits"][split] = {
            "images": len(paths), "pairs": len(paths) * len(held_stems),
            "max_corr": round(best_overall, 4), "duplicates": hits,
            "duplicate_count": len(hits),
        }
        print(f"   max {best_overall:.4f}   duplicates >= {DUPLICATE_CORR}: {len(hits)}",
              flush=True)

    out = repo_root() / "results" / "T9"
    out.mkdir(parents=True, exist_ok=True)
    (out / "bharatpothole_overlap.json").write_text(json.dumps(report, indent=2))
    total = sum(v["duplicate_count"] for v in report["splits"].values())
    print(f"\nVERDICT: {'CLEAN' if total == 0 else f'{total} DUPLICATES'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
