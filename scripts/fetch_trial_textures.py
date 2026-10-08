"""Rebuild data/raw/trial_textures from the public CC BY sources (D094).

    uv run python scripts/fetch_trial_textures.py

The 49 texture photos arrived as `indian_road_textures.zip` and are gitignored (D086).
`docs/texture-provenance.md` maps each one to its dataset and original file, so a machine
without the zip can rebuild them:

- **QR4Change** (18 potholes) come one by one from Mendeley; each file's SHA-256 is checked
  against the one Mendeley publishes.
- **BD-N6** (31 cracks and asphalt) are read out of the 14 GB and 49 GB Zenodo zips with
  HTTP range requests, so only the needed members download.

The curated set was downscaled so the long side is 3000 px, keeping the aspect exactly;
`natural_px_per_m` in configs/sim/textures.yaml was set at that size. Each image is resized
to the size the file map records, and a mismatched aspect stops the run. Resampling and JPEG
encoding mean the pixels are not the zip's, byte for byte: geometry and scale are.
"""

from __future__ import annotations

import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

import cv2
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

ROOT = repo_root()
OUT = ROOT / "data" / "raw" / "trial_textures"
MENDELEY = "https://data.mendeley.com/public-api/datasets/zndzygc3p3"
# QR4Change v2's pothole/yes and pothole/no folders, which hold the `Img (N).jpg` files
POTHOLE_FOLDERS = ["7e90d513-bcc6-428c-a171-2c358628cf7c", "a17c191d-f252-41d2-a956-c805411e3007"]
ZENODO = {
    "Part1": "https://zenodo.org/records/18072573/files/Road%20Dataset%201.zip?download=1",
    "Part2": "https://zenodo.org/records/18114226/files/Road%20Dataset%202.zip?download=1",
}
JPEG_QUALITY = 95
TIMEOUT_S = 300


def parse(line: str) -> tuple[str, str, str | None, str, int, int] | None:
    """One file-map line, `out  <-  source / original file / WxH`, or None.

    Split on " / " with spaces: the source names a DOI, which holds a bare '/'.
    """
    line = line.strip().rstrip("`").strip()
    if "<-" not in line or not line[-1:].isdigit():
        return None
    out, right = (x.strip() for x in line.split("<-", 1))
    source, orig, size = (x.strip() for x in right.split(" / "))
    part = re.search(r"Part([12])", source)
    w, h = size.split("x")
    src = "QR4Change" if source.startswith("QR4Change") else "BD-N6"
    return out, src, f"Part{part.group(1)}" if part else None, orig, int(w), int(h)


class RangeFile(io.RawIOBase):
    """A seekable, read-only file over HTTP range requests."""

    def __init__(self, url: str) -> None:
        self.url, self.pos, self.session = url, 0, requests.Session()
        self.size = int(self.session.head(url, allow_redirects=True).headers["content-length"])

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, buf) -> int:
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buf), self.size) - 1
        r = self.session.get(
            self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=TIMEOUT_S
        )
        r.raise_for_status()
        n = len(r.content)
        buf[:n] = r.content
        self.pos += n
        return n


def main() -> None:
    text = (ROOT / "docs" / "texture-provenance.md").read_text()
    rows = [r for ln in text.splitlines() if (r := parse(ln))]
    print(f"{len(rows)} entries in the file map")

    mendeley: dict[str, dict] = {}
    for folder in POTHOLE_FOLDERS:
        params = {"folder_id": folder, "version": 2}
        for f in requests.get(f"{MENDELEY}/files", params=params, timeout=TIMEOUT_S).json():
            mendeley.setdefault(f["filename"], f["content_details"])

    zips: dict[str, zipfile.ZipFile] = {}
    for out, src, part, orig, w, h in rows:
        if src == "QR4Change":
            cd = mendeley[orig]
            data = requests.get(cd["download_url"], timeout=TIMEOUT_S).content
            if hashlib.sha256(data).hexdigest() != cd["sha256_hash"]:
                sys.exit(f"SHA-256 mismatch for {orig}")
        else:
            if part not in zips:
                zips[part] = zipfile.ZipFile(io.BufferedReader(RangeFile(ZENODO[part]), 1 << 20))
            names = [n for n in zips[part].namelist() if n.rsplit("/", 1)[-1] == orig]
            if len(names) != 1:
                sys.exit(f"{orig}: {len(names)} matches in BD-N6 {part}")
            data = zips[part].read(names[0])

        dest = OUT / out
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        img = cv2.imread(str(dest))  # applies EXIF orientation, as the demo's loader does
        if (img.shape[1], img.shape[0]) != (w, h):
            if abs(img.shape[1] * h / img.shape[0] - w) > 1:
                sys.exit(f"{out}: {img.shape[1]}x{img.shape[0]} is not a resize of {w}x{h}")
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(dest), img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        print(f"{out}  <-  {orig}  {w}x{h}", flush=True)
    print(f"{len(rows)} textures in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
