"""Acquire RDD2022.

RDD2022 ships as a single 13.26 GB zip with no per-country download (D032), so
we fetch the whole archive once and extract only the country we need. That
archive is nested two levels deep — an outer zip of per-country zips, each
rooted at `<Country>/` (D036) — which `extract_country` unwraps.
"""

import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import requests

# Inner per-country zips are stored uncompressed inside the outer archive
# (verified 2026-08-06, D036), so streaming the copy in fixed-size chunks
# never needs to hold more than one chunk in memory regardless of how large
# the member is (Norway.zip alone is 10.6 GB).
COPY_CHUNK_BYTES = 1024 * 1024

FIGSHARE_API = "https://api.figshare.com/v2/articles/21431547"
ZIP_NAME = "RDD2022_released_through_CRDDC2022.zip"
ZIP_URL = "https://ndownloader.figshare.com/files/38030910"

# Figshare redirects this URL to S3 (s3-eu-west-1.amazonaws.com), which throttles
# *per connection* — measured at ~0.75 MB/s on a link that otherwise sustains
# 12.8 MB/s. S3 honours byte-range requests (HTTP 206), so parallel connections
# multiply observed throughput: aria2c -x16 measured 7.4 MB/s, cutting a 4.4-hour
# download to ~28 minutes (D034). This is why aria2c is preferred over a single
# -threaded curl here specifically — not a general aria2c-over-curl preference —
# so don't "simplify" this back to curl alone.
#
# Caveat: aria2c cannot resume a partial file that curl (or anything else)
# started, because it needs its own `.aria2` control file to track which byte
# ranges landed. Resuming a curl-started partial with aria2c silently falls back
# to a single connection, losing the speedup. Switching downloaders mid-transfer
# means discarding the partial file, not resuming it.
ARIA2_CONNECTIONS = 16

COUNTRIES = {
    "China_Drone",
    "China_MotorBike",
    "Czech",
    "India",
    "Japan",
    "Norway",
    "United_States",
}


def expected_zip_size() -> int:
    """Authoritative size from the Figshare API, so we never trust a partial file."""
    response = requests.get(FIGSHARE_API, timeout=30)
    response.raise_for_status()
    for entry in response.json()["files"]:
        if entry["name"] == ZIP_NAME:
            return int(entry["size"])
    raise RuntimeError(f"{ZIP_NAME} not present in Figshare article listing")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_with_aria2(url: str, dest_dir: Path, filename: str) -> None:
    subprocess.run(
        [
            "aria2c",
            f"-x{ARIA2_CONNECTIONS}",
            f"-s{ARIA2_CONNECTIONS}",
            "-k",
            "10M",
            "--file-allocation=none",
            "--continue=true",
            "-d",
            str(dest_dir),
            "-o",
            filename,
            url,
        ],
        check=True,
    )


def _download_with_curl(url: str, zip_path: Path) -> None:
    subprocess.run(["curl", "-L", "-C", "-", "--fail", "-o", str(zip_path), url], check=True)


def download_rdd2022(dest: Path) -> Path:
    """Download the archive, resuming if a partial file is present."""
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / ZIP_NAME
    expected = expected_zip_size()

    if zip_path.exists() and zip_path.stat().st_size == expected:
        print(f"already complete: {zip_path}")
        return zip_path

    print(f"downloading {expected / 1e9:.2f} GB -> {zip_path}")
    if shutil.which("aria2c"):
        _download_with_aria2(ZIP_URL, dest, ZIP_NAME)
    else:
        _download_with_curl(ZIP_URL, zip_path)

    actual = zip_path.stat().st_size
    if actual != expected:
        raise RuntimeError(f"size mismatch: got {actual}, expected {expected}")

    return zip_path


def extract_country(zip_path: Path, country: str, dest: Path) -> Path:
    """Extract one country from the archive's two-level nesting (D036).

    The outer archive holds one uncompressed per-country zip per entry, named
    `RDD2022/<country>.zip`; that inner zip's own root is `<country>/`, not
    `RDD2022/<country>/`. We extract the inner zip's contents into
    `dest / "RDD2022" / <country>` so the rest of the codebase sees the flat
    layout it already expects.
    """
    if country not in COUNTRIES:
        raise ValueError(f"unknown country {country!r}; expected one of {sorted(COUNTRIES)}")

    inner_name = f"RDD2022/{country}.zip"
    country_dest = dest / "RDD2022" / country
    country_dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as outer:
        if inner_name not in outer.namelist():
            raise ValueError(f"{inner_name!r} not found in {zip_path}")

        # Stream the (potentially multi-GB, e.g. Norway's 10.6 GB) member to a
        # temporary file rather than reading it into memory, then open that
        # file as its own zip archive.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp_path = Path(tmp.name)
            with outer.open(inner_name) as member:
                shutil.copyfileobj(member, tmp, length=COPY_CHUNK_BYTES)

    try:
        with zipfile.ZipFile(tmp_path) as inner:
            inner.extractall(dest / "RDD2022")
    finally:
        tmp_path.unlink(missing_ok=True)

    return country_dest
