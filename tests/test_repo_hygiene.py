"""A fresh clone must not depend on one machine's home directory (D084).

Two kinds of committed file still do, and are pinned here rather than fixed:

* `results/` holds the absolute paths each evaluation or verification ran with. They
  are provenance, and `results/LOCKED/` is never rewritten. That includes the 2,312
  image symlinks of the locked Model P evaluation, whose targets are absolute.
* `configs/data/*.yaml` carry the absolute `path:` that `scripts/build_pool.py`
  writes. `scripts/mps_sanity.py` hands `model_a.yaml` to ultralytics unresolved, and
  ultralytics resolves a relative `path` against its own `datasets_dir`, not the repo
  (D040), so making them relative would break it.

Anything outside these pins fails, and so does any change to the pins themselves.
"""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME_PATH = re.compile(rb"/(?:Users|home)/[^/\s\"'`]+/")
LOCKED_LINK_DIR = "results/LOCKED/P_india_heldout_run/gt_root/images/"
LOCKED_LINK_COUNT = 2312  # gt_root/india_heldout.txt lists the same 2,312 images
PINNED_HOME_PATHS = {
    # build_pool.py output, consumed unresolved by mps_sanity.py (D040)
    "configs/data/india_cal.yaml",
    "configs/data/india_full.yaml",
    "configs/data/india_heldout.yaml",
    "configs/data/india_test.yaml",
    "configs/data/india_train.yaml",
    "configs/data/india_val.yaml",
    "configs/data/model_a.yaml",
    "configs/data/model_b.yaml",
    "configs/data/nonindia_val.yaml",
    # locked evaluations: never rewritten
    "results/LOCKED/A_india_full_run/data.yaml",
    "results/LOCKED/B_india_heldout_run/data.yaml",
    "results/LOCKED/P_india_heldout_run/data.yaml",
    "results/LOCKED/P_india_heldout_run/gt_root/labels.cache",
    # provenance of verification and open evaluation runs
    "results/T5/roadsight-train-a_verification.json",
    "results/T5/roadsight-train-b_verification.json",
    "results/T6_A_nonindia_val/data.yaml",
    "results/T9/B_india_val_run/data.yaml",
    "results/T9/B_vs_P_india_val.json",
    "results/T9/P_india_val_run/data.yaml",
}


def tracked(root: Path) -> list[tuple[str, str]]:
    """(mode, path) for every file git tracks."""
    out = subprocess.run(
        ["git", "ls-files", "-s", "-z"], cwd=root, capture_output=True, check=True
    ).stdout.decode()
    entries = []
    for record in filter(None, out.split("\0")):
        meta, path = record.split("\t", 1)
        entries.append((meta.split()[0], path))
    return entries


def escaping_links(root: Path, links: list[str]) -> list[str]:
    """Symlinks whose target is absolute or climbs out of the repository."""
    bad = []
    for link in links:
        target = os.readlink(root / link)
        resolved = os.path.normpath(os.path.join(os.path.dirname(link), target))
        if os.path.isabs(target) or resolved == ".." or resolved.startswith("../"):
            bad.append(link)
    return sorted(bad)


def test_no_committed_symlink_escapes_the_repo_beyond_the_locked_pin():
    links = [p for mode, p in tracked(ROOT) if mode == "120000"]
    escaping = escaping_links(ROOT, links)
    assert [p for p in escaping if not p.startswith(LOCKED_LINK_DIR)] == []
    assert len(escaping) == LOCKED_LINK_COUNT


def test_an_absolute_or_climbing_link_is_caught(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "real.txt").write_text("x")
    os.symlink("real.txt", tmp_path / "a" / "inside")
    os.symlink(str(tmp_path / "a" / "real.txt"), tmp_path / "a" / "absolute")
    os.symlink("../../elsewhere", tmp_path / "a" / "climbing")
    links = ["a/inside", "a/absolute", "a/climbing"]
    assert escaping_links(tmp_path, links) == ["a/absolute", "a/climbing"]


def test_no_home_directory_path_outside_the_pinned_files():
    found = {
        p
        for mode, p in tracked(ROOT)
        if mode != "120000" and HOME_PATH.search((ROOT / p).read_bytes())
    }
    assert found == PINNED_HOME_PATHS
