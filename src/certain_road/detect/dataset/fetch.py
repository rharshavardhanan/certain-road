"""Acquire RDD2022.

RDD2022 ships as a single 13.26 GB zip with no per-country download (D032), so
we fetch the whole archive once and extract only the country we need.
"""

import hashlib
import subprocess
import zipfile
from pathlib import Path

import requests

FIGSHARE_API = "https://api.figshare.com/v2/articles/21431547"
ZIP_NAME = "RDD2022_released_through_CRDDC2022.zip"
ZIP_URL = "https://ndownloader.figshare.com/files/38030910"
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


def download_rdd2022(dest: Path) -> Path:
    """Download the archive, resuming if a partial file is present."""
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / ZIP_NAME
    expected = expected_zip_size()

    if zip_path.exists() and zip_path.stat().st_size == expected:
        print(f"already complete: {zip_path}")
        return zip_path

    print(f"downloading {expected / 1e9:.2f} GB -> {zip_path}")
    subprocess.run(
        ["curl", "-L", "-C", "-", "--fail", "-o", str(zip_path), ZIP_URL],
        check=True,
    )

    actual = zip_path.stat().st_size
    if actual != expected:
        raise RuntimeError(f"size mismatch: got {actual}, expected {expected}")

    return zip_path


def extract_country(zip_path: Path, country: str, dest: Path) -> Path:
    """Extract only `RDD2022/<country>/` from the archive."""
    if country not in COUNTRIES:
        raise ValueError(f"unknown country {country!r}; expected one of {sorted(COUNTRIES)}")

    prefix = f"RDD2022/{country}/"
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.startswith(prefix)]
        if not members:
            raise ValueError(f"no entries under {prefix!r} in {zip_path}")
        archive.extractall(dest, members=members)

    return dest / "RDD2022" / country
