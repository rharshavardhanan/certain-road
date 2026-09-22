"""The last line of defence before a six-hour run reads its first image.

`test_splits.py` asserts the lists in *this repo* are clean. This asserts the
guard that runs inside the kernel, against whatever file is actually on Kaggle
after an upload, a dataset version bump, or a hand-edited yaml.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kaggle" / "train"))

from train import assert_no_forbidden_prefix, preflight_dataset  # noqa: E402


def write_list(root: Path, name: str, entries: list[str]) -> None:
    (root / name).write_text("".join(f"./images/{e}.jpg\n" for e in entries))


def test_clean_training_list_passes(tmp_path):
    write_list(tmp_path, "nonindia_train.txt", ["Japan__Japan_1", "Norway__Norway_2"])
    assert_no_forbidden_prefix(
        tmp_path, {"train": "nonindia_train.txt", "forbid_prefixes": ["India__"]})


def test_a_single_india_entry_stops_the_run(tmp_path):
    write_list(tmp_path, "nonindia_train.txt",
               ["Japan__Japan_1", "India__India_000259", "Norway__Norway_2"])
    with pytest.raises(SystemExit, match="REFUSING TO TRAIN"):
        assert_no_forbidden_prefix(
            tmp_path, {"train": "nonindia_train.txt", "forbid_prefixes": ["India__"]})


def test_every_list_is_checked_not_just_the_first(tmp_path):
    """Model B trains on a list of files; a leak in the second must still stop it."""
    write_list(tmp_path, "clean.txt", ["Japan__Japan_1"])
    write_list(tmp_path, "dirty.txt", ["India__India_000259"])
    with pytest.raises(SystemExit, match="REFUSING TO TRAIN"):
        assert_no_forbidden_prefix(
            tmp_path, {"train": ["clean.txt", "dirty.txt"], "forbid_prefixes": ["India__"]})


def test_no_forbidden_prefixes_means_no_guard(tmp_path):
    """Model B legitimately trains on india_train; the guard must not fire."""
    write_list(tmp_path, "india_train.txt", ["India__India_000259"])
    assert_no_forbidden_prefix(tmp_path, {"train": "india_train.txt"})
    assert_no_forbidden_prefix(
        tmp_path, {"train": "india_train.txt", "forbid_prefixes": []})


def test_prefix_match_is_anchored_to_the_filename(tmp_path):
    """'./images/India__x.jpg' must match; a path containing 'India' must not."""
    write_list(tmp_path, "t.txt", ["Japan__Japan_India_lookalike"])
    assert_no_forbidden_prefix(tmp_path, {"train": "t.txt", "forbid_prefixes": ["India__"]})


# --- preflight_dataset ------------------------------------------------------
#
# Model P died once on a dataset version that carried 8,000 labels and 0 images.
# Ultralytics reported every pair corrupt and the GPU session produced nothing.
# These cover that case directly, plus the mirror case and the one thing that
# must NOT abort: a background image whose label file is legitimately empty.

PJOB = {"train": "p_train.txt", "val": "p_val.txt", "names": {"0": "pothole"}}


def make_pool(root: Path, name: str, stems: list[str], *,
              images: bool = True, labels: bool = True,
              boxes: str = "0 0.5 0.5 0.2 0.2\n") -> None:
    """Write a miniature YOLO pool; omit either side to simulate a partial upload."""
    from PIL import Image

    (root / "images").mkdir(exist_ok=True)
    (root / "labels").mkdir(exist_ok=True)
    for stem in stems:
        if images:
            Image.new("RGB", (32, 32), (128, 128, 128)).save(root / "images" / f"{stem}.jpg")
        if labels:
            (root / "labels" / f"{stem}.txt").write_text(boxes)
    (root / name).write_text("".join(f"./images/{s}.jpg\n" for s in stems))


def test_complete_pool_passes_with_counts(tmp_path):
    make_pool(tmp_path, "p_train.txt", ["a", "b", "c"])
    make_pool(tmp_path, "p_val.txt", ["v1"])
    report = preflight_dataset(tmp_path, PJOB)
    assert report["p_train.txt"] == {
        "role": "train", "listed": 3, "images_present": 3, "labels_present": 3}
    assert report["scan"] == {"pairs": 4, "missing": 0, "empty": 0, "corrupt": 0}


def test_labels_without_images_is_refused(tmp_path):
    """The exact failure that killed a Model P run."""
    make_pool(tmp_path, "p_train.txt", ["a", "b", "c"], images=False)
    make_pool(tmp_path, "p_val.txt", ["v1"])
    with pytest.raises(SystemExit,
                       match=r"lists 3 entries but the mount has 0 images and 3 labels"):
        preflight_dataset(tmp_path, PJOB)


def test_images_without_labels_is_refused(tmp_path):
    make_pool(tmp_path, "p_train.txt", ["a", "b"], labels=False)
    make_pool(tmp_path, "p_val.txt", ["v1"])
    with pytest.raises(SystemExit, match=r"2 images and 0 labels"):
        preflight_dataset(tmp_path, PJOB)


def test_empty_label_file_is_not_an_error(tmp_path):
    """Most images in a pothole pool carry no box; refusing those refuses the pool."""
    make_pool(tmp_path, "p_train.txt", ["a", "b"], boxes="")
    make_pool(tmp_path, "p_val.txt", ["v1"])
    report = preflight_dataset(tmp_path, PJOB)
    assert report["scan"]["empty"] == 2
    assert report["scan"]["corrupt"] == 0


def test_a_corrupt_image_stops_the_run(tmp_path):
    make_pool(tmp_path, "p_train.txt", ["a", "b"])
    make_pool(tmp_path, "p_val.txt", ["v1"])
    (tmp_path / "images" / "b.jpg").write_bytes(b"not a jpeg")
    with pytest.raises(SystemExit, match=r"0 missing and 1 corrupt"):
        preflight_dataset(tmp_path, PJOB)


def test_the_val_list_is_checked_too(tmp_path):
    """Selection happens on india_val; a broken val list ruins the run just as thoroughly."""
    make_pool(tmp_path, "p_train.txt", ["a", "b"])
    make_pool(tmp_path, "p_val.txt", ["v1", "v2"], images=False)
    with pytest.raises(SystemExit, match=r"p_val\.txt lists 2 entries"):
        preflight_dataset(tmp_path, PJOB)


def test_every_list_in_a_multi_list_train_is_checked(tmp_path):
    """Model B trains on two lists; a partial upload of the second must still stop it."""
    make_pool(tmp_path, "one.txt", ["a"])
    make_pool(tmp_path, "two.txt", ["b"], images=False)
    make_pool(tmp_path, "p_val.txt", ["v1"])
    with pytest.raises(SystemExit, match=r"two\.txt lists 1 entries"):
        preflight_dataset(tmp_path, {**PJOB, "train": ["one.txt", "two.txt"]})
