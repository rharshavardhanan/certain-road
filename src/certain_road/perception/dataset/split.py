"""Deterministic four-way split.

Assignment is by salted hash of the filename rather than a seeded shuffle, so
that adding or removing files never reshuffles the existing ones. That
stability matters: `calib` leaking into `train` at any point would silently
void every conformal guarantee in the project (D009).
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from certain_road.perception.dataset.convert import ID_TO_CLASS

SALT = "certain-road-v1"

# Extensions of the files `materialise` owns in images/<split> and labels/<split>.
# Only these are cleared before repopulating a split; nothing else in those
# directories is touched.
IMAGE_SUFFIX = ".jpg"
LABEL_SUFFIX = ".txt"

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


def build_multicountry_splits(
    india_stems: list[str],
    non_india_stems: list[str],
    salt: str = SALT,
) -> dict[str, list[str]]:
    """India gets the ordinary four-way split; every other country joins `train` only.

    Non-India countries are never four-way split — `assign_split` is not even
    called on them. Their calib/test portions would be unused (D041 keeps
    calibration and test India-only, since a conformal guarantee is only
    meaningful relative to a describable deployment population) and computing
    them would just waste extracted data. India's own assignment is produced by
    the exact same `build_splits` call as the India-only path, so adding
    countries here cannot perturb it.
    """
    splits = build_splits(india_stems, salt)
    splits["train"] = sorted(splits["train"] + non_india_stems)
    return splits


@dataclass(frozen=True)
class SplitMaterialiseReport:
    """What actually landed on disk for one split, vs. what was requested.

    RDD2022 India ships 9,665 images but only ~7,706 annotations, so
    `skipped_missing_image` being non-zero is expected, not a bug — the point
    is that it is visible rather than silently absorbed.
    """

    requested: int
    linked: int
    skipped_missing_image: int


def _clear_managed_files(directory: Path, suffix: str) -> None:
    """Remove only the files `materialise` itself manages, never the tree.

    A directory-level `rm -rf` on a path built from config is exactly the
    kind of thing that eats someone's data when a path is wrong; removing by
    known suffix inside a directory we just created/confirmed is not.
    """
    if not directory.exists():
        return
    for path in directory.glob(f"*{suffix}"):
        path.unlink()


def _materialise_with_sources(
    splits: dict[str, list[str]],
    resolve_source: Callable[[str], tuple[Path, Path]],
    out_root: Path,
) -> dict[str, SplitMaterialiseReport]:
    """Shared implementation behind `materialise` and `materialise_multicountry`.

    `resolve_source(stem)` returns the (image_src, label_src) pair that stem
    should be read from, letting the single-country and multi-country cases
    share one code path without either duplicating it.
    """
    reports: dict[str, SplitMaterialiseReport] = {}

    for split, stems in splits.items():
        img_dir = out_root / "images" / split
        lbl_dir = out_root / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        _clear_managed_files(img_dir, IMAGE_SUFFIX)
        _clear_managed_files(lbl_dir, LABEL_SUFFIX)

        linked = 0
        skipped_missing_image = 0

        for stem in stems:
            image_src, label_src = resolve_source(stem)
            source_image = image_src / f"{stem}{IMAGE_SUFFIX}"
            if not source_image.exists():
                skipped_missing_image += 1
                continue
            link = img_dir / f"{stem}{IMAGE_SUFFIX}"
            link.symlink_to(source_image.resolve())
            linked += 1

            source_label = label_src / f"{stem}{LABEL_SUFFIX}"
            if source_label.exists():
                (lbl_dir / f"{stem}{LABEL_SUFFIX}").write_text(source_label.read_text())

        reports[split] = SplitMaterialiseReport(
            requested=len(stems),
            linked=linked,
            skipped_missing_image=skipped_missing_image,
        )

    return reports


def materialise(
    splits: dict[str, list[str]],
    image_src: Path,
    label_src: Path,
    out_root: Path,
) -> dict[str, SplitMaterialiseReport]:
    """Lay out images/<split>/ and labels/<split>/ for ultralytics.

    Images are symlinked rather than copied: same result, no duplicated GB.
    Each split's managed files are cleared before repopulating, so a stem
    dropped from `labels_all` since the last run does not leave a stale
    symlink or label behind. Returns a per-split report of what happened,
    since a missing image is silently skipped rather than raised.
    """
    return _materialise_with_sources(splits, lambda _stem: (image_src, label_src), out_root)


def materialise_multicountry(
    splits: dict[str, list[str]],
    stem_sources: dict[str, tuple[Path, Path]],
    out_root: Path,
) -> dict[str, SplitMaterialiseReport]:
    """Like `materialise`, but stems come from more than one country's raw tree.

    `stem_sources` maps every stem in `splits` to the (image_src, label_src)
    pair it should be read from — built by the caller from each country's own
    `labels_all` directory, never inferred from the stem string, so there is
    no risk of two similarly-prefixed countries (e.g. `China_Drone` /
    `China_MotorBike`) being confused with each other.
    """
    return _materialise_with_sources(splits, stem_sources.__getitem__, out_root)


def write_data_yaml(out_path: Path, data_root: Path, repo_root: Path) -> None:
    """Write the ultralytics data yaml, `path` relative to `repo_root`.

    A relative `path` keeps the file usable on any machine. It is *not*
    resolved against the process working directory by ultralytics — it
    resolves against ultralytics' own `datasets_dir` setting instead
    (D040) — so `certain_road.perception.train` resolves it against
    `repo_root()` itself before handing anything to `YOLO().train()`.
    `calib` and `test` are deliberately absent: ultralytics must never see
    them (D009).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(
            {
                "path": str(data_root.relative_to(repo_root)),
                "train": "images/train",
                "val": "images/val",
                "names": {i: ID_TO_CLASS[i] for i in sorted(ID_TO_CLASS)},
            },
            sort_keys=False,
        )
    )


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
