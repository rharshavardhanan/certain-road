"""The last line of defence before a six-hour run reads its first image.

`test_splits.py` asserts the lists in *this repo* are clean. This asserts the
guard that runs inside the kernel, against whatever file is actually on Kaggle
after an upload, a dataset version bump, or a hand-edited yaml.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kaggle" / "train"))

from train import assert_no_forbidden_prefix  # noqa: E402


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
