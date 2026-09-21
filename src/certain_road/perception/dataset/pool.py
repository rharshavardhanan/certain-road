"""T2 — one image pool, no duplicate files, leakage-proof split lists.

Every image lands exactly once in `data/yolo/images/`, named `<Country>__<stem>`,
and splits are plain text lists of `./images/<name>.jpg`. Ultralytics resolves
`./` against the txt's own directory, so the identical files work unchanged on
Kaggle without rewriting a single path.

Assignment is by **salted hash of the filename**, not a seeded shuffle, for the
reason D009 gave: a hash is stable when the file set changes, so adding or
removing images never silently moves an unrelated image from train into test. A
seeded shuffle reshuffles everything the moment one file appears.

India is split per-image rather than in blocks of 50. D059 measured adjacent-ID
correlation at +0.004 over random pairs, so the near-duplicate leak that blocking
defends against does not exist in this dataset.
"""

import hashlib
import random
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image

from certain_road.perception.dataset.convert import to_yolo_lines
from certain_road.perception.dataset.voc import parse_voc

SALT = "roadsight-pool-v1"
JPEG_QUALITY = 95


def pool_name(country: str, stem: str) -> str:
    """`<Country>__<stem>`, per T2.

    RDD2022 stems already begin with the country, so this repeats it. That is
    deliberate: one prefix rule covers RDD2022, BharatPotHole (T9) and Chennai
    (T15) alike, and the leakage tests stay a plain string check across all three.
    """
    return f"{country}__{stem}"


def unit_hash(name: str, salt: str = SALT) -> float:
    """Stable value in [0, 1) from the name alone."""
    digest = hashlib.sha256(f"{salt}:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def split_nonindia(
    stems_by_country: dict[str, list[str]], *, val_frac: float, salt: str = SALT
) -> dict[str, list[str]]:
    """Per-country 80/20. Splitting per country keeps every country's val share
    proportional; a single global split would let one large country dominate."""
    train: list[str] = []
    val: list[str] = []
    for country, stems in sorted(stems_by_country.items()):
        for stem in sorted(stems):
            name = pool_name(country, stem)
            (val if unit_hash(name, salt) < val_frac else train).append(name)
    return {"nonindia_train": sorted(train), "nonindia_val": sorted(val)}


def split_india(
    stems: list[str], *, fracs: dict[str, float], salt: str = SALT
) -> dict[str, list[str]]:
    """Per-image split into india_train/val/cal/test at the configured fractions.

    Cumulative thresholds over one hash keep the four subsets mutually exclusive
    by construction: an image cannot land in two bands of the same number line.
    """
    order = ["india_train", "india_val", "india_cal", "india_test"]
    bounds, running = [], 0.0
    for key in order:
        running += fracs[key]
        bounds.append(running)

    out: dict[str, list[str]] = {k: [] for k in order}
    for stem in sorted(stems):
        name = pool_name("India", stem)
        h = unit_hash(name, salt)
        for key, bound in zip(order, bounds, strict=True):
            if h < bound:
                out[key].append(name)
                break
        else:
            out[order[-1]].append(name)          # rounding remainder -> test (T2.3)
    return {k: sorted(v) for k, v in out.items()}


def split_india_grouped(
    stems: list[str],
    *,
    fracs: dict[str, float],
    groups: list[list[str]],
    salt: str = SALT,
    class_counts: dict[str, tuple[int, int]] | None = None,
    balance_weight: float = 4.0,
) -> dict[str, list[str]]:
    """Split India keeping same-scene groups intact (D061).

    A plain per-image hash scatters near-duplicate frames of one location across
    train and test, which inflates the India result. Here the unit of assignment
    is a *group* of images showing the same place, not an image.

    Groups are placed largest-first into whichever split is furthest below its
    target count. Hashing each group independently would be simpler but lets a
    1,312-image group land anywhere and wreck the fractions; deficit-filling keeps
    them close while the ordering stays deterministic — size first, then the
    salted hash of the group's first member.

    `class_counts` maps each image to `(pothole_instances, total_instances)`. When
    given, placement also tracks pothole share: filling purely by count let
    `india_val` drift to 51.6% pothole against 46% elsewhere, because whole scene
    groups carry correlated class mixes and a small split absorbs one badly. The
    guard matters — the India pothole share is the headline domain-shift number,
    and a val split that is 5 points richer in potholes reports a different
    problem than the one being solved.
    """
    order = ["india_train", "india_val", "india_cal", "india_test"]
    member_of: dict[str, int] = {}
    units: list[list[str]] = []
    for group in groups:
        present = sorted(m for m in group if m in set(stems))
        if len(present) > 1:
            for m in present:
                member_of[m] = len(units)
            units.append(present)
    units.extend([[s] for s in sorted(stems) if s not in member_of])

    units.sort(key=lambda u: (-len(u), unit_hash(u[0], salt)))

    targets = {k: fracs[k] * len(stems) for k in order}
    out: dict[str, list[str]] = {k: [] for k in order}

    if class_counts is None:
        for unit in units:
            key = max(order, key=lambda k: targets[k] - len(out[k]))
            out[key].extend(unit)
        return {k: sorted(v) for k, v in out.items()}

    pot = {k: 0 for k in order}
    tot = {k: 0 for k in order}
    all_pot = sum(class_counts.get(s, (0, 0))[0] for s in stems)
    all_tot = sum(class_counts.get(s, (0, 0))[1] for s in stems)
    goal = all_pot / all_tot if all_tot else 0.0

    for unit in units:
        u_pot = sum(class_counts.get(m, (0, 0))[0] for m in unit)
        u_tot = sum(class_counts.get(m, (0, 0))[1] for m in unit)
        best, best_score = order[0], -1e18
        for k in order:
            need = (targets[k] - len(out[k])) / max(targets[k], 1.0)
            projected_tot = tot[k] + u_tot
            share = (pot[k] + u_pot) / projected_tot if projected_tot else goal
            score = need - balance_weight * abs(share - goal)
            if score > best_score:
                best, best_score = k, score
        out[best].extend(unit)
        pot[best] += u_pot
        tot[best] += u_tot
    return {k: sorted(v) for k, v in out.items()}


def sample_replay(train: list[str], n: int, seed: int) -> list[str]:
    """Fixed sample of non-India train used to rehearse Model B against forgetting."""
    rng = random.Random(seed)
    return sorted(rng.sample(sorted(train), min(n, len(train))))


def materialise_one(
    *,
    country: str,
    stem: str,
    img_src: Path,
    xml_src: Path,
    images_dir: Path,
    labels_dir: Path,
    max_side: int,
    min_box_px: float,
) -> tuple[bool, Counter]:
    """Write one image+label pair into the pool. Returns (resized?, rejections)."""
    name = pool_name(country, stem)
    ann = parse_voc(xml_src)

    with Image.open(img_src) as im:
        real_w, real_h = im.size
        resized = max(real_w, real_h) > max_side
        if resized:
            scale = max_side / max(real_w, real_h)
            out = im.convert("RGB").resize(
                (round(real_w * scale), round(real_h * scale)), Image.LANCZOS
            )
            out.save(images_dir / f"{name}.jpg", quality=JPEG_QUALITY)

    if not resized:
        # Copy the bytes rather than re-encode: re-saving an unchanged image
        # costs quality for nothing.
        shutil.copyfile(img_src, images_dir / f"{name}.jpg")

    # Labels are normalised, so a resize leaves them untouched — but they must be
    # normalised against the REAL size, not a <size> the XML may have got wrong.
    lines, rejected = to_yolo_lines(ann, size=(real_w, real_h), min_box_px=min_box_px)
    (labels_dir / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
    return resized, rejected


def write_split_txt(names: list[str], path: Path) -> None:
    """One `./images/<name>.jpg` per line — relative so Kaggle needs no rewrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"./images/{n}.jpg\n" for n in names))
