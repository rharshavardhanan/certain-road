"""D072 — a pothole-only pool for Model P.

Separate label tree, shared images where they already exist. Everything except
the pothole class is *dropped*, not merged: a one-class detector that has seen
cracks labelled as background learns to reject them, which is the behaviour the
avoidance pipeline wants.

BharatPotHole is already single-class and 0-indexed, so it needs no remap - only
a prefix, so the leakage tests keep working as plain string checks.

`india_cal` and `india_test` are absent by construction, exactly as in the main
pool (D063): the held-out images are never copied here and never uploaded.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
POTHOLE = CFG["pothole_class"]
BPH = repo_root() / "data/raw/bharatpothole/BharatPotHole/BharatPotHole"
POOL = repo_root() / "data" / "yolo_pothole"


def remap_india(split: str) -> list[str]:
    """Copy India images, keeping only pothole boxes, remapped to class 0."""
    names = []
    for line in (YOLO_DIR / f"{split}.txt").read_text().splitlines():
        if not line.strip():
            continue
        stem = Path(line).stem
        kept = []
        for row in (YOLO_DIR / "labels" / f"{stem}.txt").read_text().splitlines():
            if row.strip() and int(row.split()[0]) == POTHOLE:
                kept.append("0 " + " ".join(row.split()[1:]))
        dst_img = POOL / "images" / f"{stem}.jpg"
        if not dst_img.exists():
            os.link(YOLO_DIR / "images" / f"{stem}.jpg", dst_img)
        (POOL / "labels" / f"{stem}.txt").write_text("\n".join(kept) + ("\n" if kept else ""))
        names.append(stem)
    return names


def copy_bph(split: str) -> list[str]:
    names = []
    for img in sorted((BPH / split / "images").glob("*.jpg")):
        name = f"BharatPotHole__{img.stem}"
        shutil.copyfile(img, POOL / "images" / f"{name}.jpg")
        src = BPH / split / "labels" / f"{img.stem}.txt"
        rows = [r for r in src.read_text().splitlines() if r.strip()] if src.exists() else []
        # already class 0 = pothole; assert rather than assume
        for r in rows:
            if int(r.split()[0]) != 0:
                raise SystemExit(f"{src} has class {r.split()[0]}, expected 0")
        (POOL / "labels" / f"{name}.txt").write_text("\n".join(rows) + ("\n" if rows else ""))
        names.append(name)
    return names


def write_list(names, path):
    path.write_text("".join(f"./images/{n}.jpg\n" for n in names))


def main() -> int:
    if POOL.exists():
        shutil.rmtree(POOL)
    (POOL / "images").mkdir(parents=True)
    (POOL / "labels").mkdir()

    india_train = remap_india("india_train")
    india_val = remap_india("india_val")
    bph_train = copy_bph("train")
    bph_val = copy_bph("valid")

    write_list(sorted(india_train + bph_train), POOL / "p_train.txt")
    write_list(sorted(india_val), POOL / "p_val.txt")
    write_list(sorted(bph_val), POOL / "p_bph_val.txt")

    held = {Path(x).stem for s in ("india_cal", "india_test")
            for x in (YOLO_DIR / f"{s}.txt").read_text().splitlines() if x.strip()}
    present = {p.stem for p in (POOL / "images").glob("*.jpg")}
    assert not (present & held), "held-out India reached the pothole pool"

    def boxes(names):
        return sum(len([r for r in (POOL / "labels" / f"{n}.txt").read_text().splitlines()
                        if r.strip()]) for n in names)

    manifest = {
        "classes": {0: "pothole"},
        "india_train": {"images": len(india_train), "pothole_boxes": boxes(india_train)},
        "bph_train": {"images": len(bph_train), "pothole_boxes": boxes(bph_train)},
        "india_val": {"images": len(india_val), "pothole_boxes": boxes(india_val)},
        "bph_val": {"images": len(bph_val), "pothole_boxes": boxes(bph_val)},
        "p_train_total": len(india_train) + len(bph_train),
        "held_out_present": 0,
        "bharatpothole_license": "CC BY 4.0 (Roboflow dashcam-mg6en v14)",
    }
    (POOL / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
