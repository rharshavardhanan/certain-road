import hashlib
import io
import zipfile

import pytest

from certain_road.detect.dataset import fetch
from certain_road.detect.dataset.fetch import extract_country, sha256_of


def test_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"certain-road")
    assert sha256_of(f) == hashlib.sha256(b"certain-road").hexdigest()


def _inner_zip_bytes(country: str, image_stem: str) -> bytes:
    """Build an inner per-country zip rooted at `<Country>/`, matching reality:
    the outer archive holds `RDD2022/<Country>.zip`, and *that* archive's root
    is `<Country>/`, not `RDD2022/<Country>/`.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(f"{country}/train/images/{country}_{image_stem}.jpg", b"jpeg")
        z.writestr(
            f"{country}/train/annotations/xmls/{country}_{image_stem}.xml",
            b"<annotation/>",
        )
    return buffer.getvalue()


def _fake_outer_zip(path, countries=("India", "Japan")):
    """Build a nested fake archive: an outer zip whose members are themselves
    per-country zips, matching the real RDD2022 archive's two-level nesting.
    """
    with zipfile.ZipFile(path, "w") as outer:
        for country in countries:
            outer.writestr(f"RDD2022/{country}.zip", _inner_zip_bytes(country, "000004"))


def test_extract_country_takes_only_that_country(tmp_path):
    zip_path = tmp_path / "rdd.zip"
    _fake_outer_zip(zip_path)

    out = extract_country(zip_path, "India", tmp_path / "raw")

    assert (out / "train" / "images" / "India_000004.jpg").exists()
    assert (out / "train" / "annotations" / "xmls" / "India_000004.xml").exists()
    assert not (tmp_path / "raw" / "RDD2022" / "Japan").exists()


def test_extract_country_rejects_unknown_country(tmp_path):
    zip_path = tmp_path / "rdd.zip"
    _fake_outer_zip(zip_path)
    with pytest.raises(ValueError, match="Atlantis"):
        extract_country(zip_path, "Atlantis", tmp_path / "raw")


def test_extract_country_missing_inner_member_raises_clear_error(tmp_path):
    """The outer archive is missing `RDD2022/India.zip` entirely (e.g. a
    truncated or mismatched archive) — the error must name what was looked
    for, not surface a bare KeyError from zipfile.
    """
    zip_path = tmp_path / "rdd.zip"
    _fake_outer_zip(zip_path, countries=("Japan",))

    with pytest.raises(ValueError, match="RDD2022/India.zip"):
        extract_country(zip_path, "India", tmp_path / "raw")


def _recorder(dest, expected_size):
    """Fake subprocess.run that records the command and materializes the expected file."""
    calls = []

    def fake_run(cmd, check=True):
        calls.append(cmd)
        (dest / fetch.ZIP_NAME).write_bytes(b"0" * expected_size)

    return calls, fake_run


def test_download_prefers_aria2c_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "expected_zip_size", lambda: 4)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/usr/local/bin/aria2c")
    calls, fake_run = _recorder(tmp_path, 4)
    monkeypatch.setattr(fetch.subprocess, "run", fake_run)

    fetch.download_rdd2022(tmp_path)

    assert len(calls) == 1
    assert calls[0][0] == "aria2c"


def test_download_falls_back_to_curl_when_aria2c_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "expected_zip_size", lambda: 4)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: None)
    calls, fake_run = _recorder(tmp_path, 4)
    monkeypatch.setattr(fetch.subprocess, "run", fake_run)

    fetch.download_rdd2022(tmp_path)

    assert len(calls) == 1
    assert calls[0][0] == "curl"
