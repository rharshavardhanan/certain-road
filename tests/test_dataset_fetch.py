import hashlib
import zipfile

import pytest

from certain_road.detect.dataset.fetch import extract_country, sha256_of


def test_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"certain-road")
    assert sha256_of(f) == hashlib.sha256(b"certain-road").hexdigest()


def _fake_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("RDD2022/India/train/images/India_000004.jpg", b"jpeg")
        z.writestr("RDD2022/India/train/annotations/xmls/India_000004.xml", b"<annotation/>")
        z.writestr("RDD2022/Japan/train/images/Japan_000001.jpg", b"jpeg")


def test_extract_country_takes_only_that_country(tmp_path):
    zip_path = tmp_path / "rdd.zip"
    _fake_zip(zip_path)

    out = extract_country(zip_path, "India", tmp_path / "raw")

    assert (out / "train" / "images" / "India_000004.jpg").exists()
    assert (out / "train" / "annotations" / "xmls" / "India_000004.xml").exists()
    assert not (tmp_path / "raw" / "RDD2022" / "Japan").exists()


def test_extract_country_rejects_unknown_country(tmp_path):
    zip_path = tmp_path / "rdd.zip"
    _fake_zip(zip_path)
    with pytest.raises(ValueError, match="Atlantis"):
        extract_country(zip_path, "Atlantis", tmp_path / "raw")
