"""Trial-photo textures: curated, prepared, and checked against the training data.

The photos are in data/raw/trial_textures/ (gitignored). Which file is which class, how
to crop it and which files are unusable are recorded in configs/sim/textures.yaml, so a
placed instance's class is the curated class, never the folder name.

`--check` enforces the rule that no texture is an image the detectors were trained on.
Each photo's mean-centred 128x128 vector (`dedupe.norm_vec`) is compared with every
RDD2022 training pool (the cached vectors) and every BharatPotHole split. A correlation at
or above D066's 0.98 copy threshold fails. This catches copies of whole images, not
crops; the provenance in the manifest covers crops.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

from certain_road.core.paths import repo_root
from certain_road.perception.dataset.dedupe import norm_vec

MANIFEST = repo_root() / "configs/sim/textures.yaml"
VECTORS = repo_root() / "data/yolo/_vectors"
MAX_CROP_PX = 1200
BPH = repo_root() / "data/raw/bharatpothole/BharatPotHole/BharatPotHole"


@dataclass(frozen=True)
class Spec:
    name: str
    cls: str
    path: Path
    crop: tuple[float, float, float, float]
    natural_px_per_m: float  # 0 when the photo has no usable scale
    usable: bool
    note: str


def manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text())


def specs(usable_only: bool = True) -> list[Spec]:
    m = manifest()
    root = repo_root() / m["root"]
    if not root.is_dir():
        raise SystemExit(f"texture folder missing: {root}")
    out = []
    for e in m["damage"]:
        src = m["sources"][e["file"].split("/")[0]]
        s = Spec(
            Path(e["file"]).stem,
            e["cls"],
            root / e["file"],
            tuple(e.get("crop", (0, 0, 1, 1))),
            float(m["natural_px_per_m"].get(src, 0)),
            e.get("usable", True),
            e.get("note", ""),
        )
        if s.usable or not usable_only:
            out.append(s)
    return out


def asphalt_paths() -> list[Path]:
    m = manifest()
    return [repo_root() / m["root"] / a["file"] for a in m["asphalt"]]


def _read(path: Path) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if im is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def flatten(rgb: np.ndarray, sigma_frac: float) -> np.ndarray:
    """Divide out low-frequency illumination (vignette, glare gradient), keep the mean."""
    lum = rgb.mean(axis=2)
    sigma = sigma_frac * max(rgb.shape[:2])
    low = cv2.GaussianBlur(lum, (0, 0), sigma) + 1e-3
    return np.clip(rgb * (lum.mean() / low)[..., None], 0, 1)


@lru_cache(maxsize=64)
def crop(spec: Spec, sigma_frac: float) -> np.ndarray:
    rgb = _read(spec.path)
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = spec.crop
    c = rgb[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
    s = MAX_CROP_PX / max(c.shape[:2])
    if s < 1:  # a road texel is ~6 mm; 1200 px is ample for any patch
        c = cv2.resize(c, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return flatten(c, sigma_frac) if spec.natural_px_per_m else c


def crop_px(spec: Spec) -> tuple[int, int]:
    """Crop size in original pixels (w, h), from the header alone."""
    w, h = Image.open(spec.path).size
    x0, y0, x1, y1 = spec.crop
    return int((x1 - x0) * w), int((y1 - y0) * h)


def catalogue(sigma_frac: float) -> dict[str, list[tuple]]:
    """class -> [(name, aspect, natural px/m, crop w px, crop h px)] for road.generate."""
    out: dict[str, list[tuple]] = {}
    for s in specs():
        w, h = crop_px(s)
        aspect = max(w, h) / min(w, h)
        out.setdefault(s.cls, []).append((s.name, aspect, s.natural_px_per_m, max(w, h), min(w, h)))
    return out


def by_name() -> dict[str, Spec]:
    return {s.name: s for s in specs()}


def _bph_paths() -> list[Path]:
    return sorted(
        p for p in BPH.glob("*/images/*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )


def check(threshold: float) -> int:
    texs = specs(usable_only=False) + [
        Spec(p.stem, "asphalt", p, (0, 0, 1, 1), 0, True, "") for p in asphalt_paths()
    ]
    t = np.stack([norm_vec(s.path) for s in texs])
    best = np.full(len(texs), -1.0)
    where = [""] * len(texs)
    pools = sorted(VECTORS.glob("*.npy"))
    for f in pools:
        m = np.load(f, mmap_mode="r")
        c = t @ np.asarray(m).T
        i = c.argmax(axis=1)
        for k in range(len(texs)):
            if c[k, i[k]] > best[k]:
                best[k], where[k] = float(c[k, i[k]]), f"{f.stem}[{i[k]}]"
    bph = _bph_paths()
    for start in range(0, len(bph), 1024):
        chunk = bph[start : start + 1024]
        m = np.stack([norm_vec(p) for p in chunk])
        c = t @ m.T
        i = c.argmax(axis=1)
        for k in range(len(texs)):
            if c[k, i[k]] > best[k]:
                best[k], where[k] = float(c[k, i[k]]), chunk[i[k]].name
    order = np.argsort(-best)
    print(
        f"compared {len(texs)} textures with {len(pools)} RDD2022 vector pools "
        f"and {len(bph)} BharatPotHole images"
    )
    for k in order[:5]:
        print(f"  {texs[k].name:14} max corr {best[k]:.4f}  ({where[k]})")
    kept = {}
    for s in specs():
        kept[s.cls] = kept.get(s.cls, 0) + 1
    print("kept per class:", kept, "| asphalt:", len(asphalt_paths()))
    worst = float(best.max())
    print(
        f"max correlation with any training image: {worst:.4f} "
        f"({'<' if worst < threshold else '>='}{threshold})"
    )
    return 0 if worst < threshold else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load((repo_root() / "configs/sim/mujoco.yaml").read_text())
    if args.check:
        sys.exit(check(cfg["copy_check_corr"]))


if __name__ == "__main__":
    main()
