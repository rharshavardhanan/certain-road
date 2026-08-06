"""Deterministic four-way split.

Assignment is by salted hash of the filename rather than a seeded shuffle, so
that adding or removing files never reshuffles the existing ones. That
stability matters: `calib` leaking into `train` at any point would silently
void every conformal guarantee in the project (D009).
"""

import hashlib
import json
from pathlib import Path

SALT = "certain-road-v1"

# Cumulative upper bounds over a uniform [0, 1) hash.
SPLIT_BOUNDS: dict[str, tuple[float, float]] = {
    "train": (0.00, 0.60),
    "val": (0.60, 0.70),
    "calib": (0.70, 0.90),
    "test": (0.90, 1.00),
}


def _unit_hash(stem: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{stem}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def assign_split(stem: str, salt: str = SALT) -> str:
    value = _unit_hash(stem, salt)
    for name, (low, high) in SPLIT_BOUNDS.items():
        if low <= value < high:
            return name
    return "test"  # only reachable at exactly 1.0


def build_splits(stems: list[str], salt: str = SALT) -> dict[str, list[str]]:
    splits: dict[str, list[str]] = {name: [] for name in SPLIT_BOUNDS}
    for stem in stems:
        splits[assign_split(stem, salt)].append(stem)
    for names in splits.values():
        names.sort()
    return splits


def materialise(
    splits: dict[str, list[str]],
    image_src: Path,
    label_src: Path,
    out_root: Path,
) -> None:
    """Lay out images/<split>/ and labels/<split>/ for ultralytics.

    Images are symlinked rather than copied: same result, no duplicated GB.
    """
    for split, stems in splits.items():
        img_dir = out_root / "images" / split
        lbl_dir = out_root / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for stem in stems:
            source_image = image_src / f"{stem}.jpg"
            if not source_image.exists():
                continue
            link = img_dir / f"{stem}.jpg"
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(source_image.resolve())

            source_label = label_src / f"{stem}.txt"
            if source_label.exists():
                (lbl_dir / f"{stem}.txt").write_text(source_label.read_text())


def write_manifest(splits: dict[str, list[str]], path: Path, salt: str = SALT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "salt": salt,
                "bounds": {k: list(v) for k, v in SPLIT_BOUNDS.items()},
                "counts": {k: len(v) for k, v in splits.items()},
                "stems": splits,
            },
            indent=2,
        )
    )
