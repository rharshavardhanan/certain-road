"""A fresh locked run must not commit a link that escapes the repository (D084).

`pothole_only_root` is the step of `scripts/eval_locked.py` that builds a 1-class
model's ground truth inside the run directory, and the only step that creates links.
The 2,312 links of the existing Model P run point at absolute paths and dangle on any
other clone. This runs that step on a tiny temporary fixture shaped like the repository
(never a real locked set, never a model) and checks the links it makes: relative, inside
the fixture's root, and pointing at the very pixels the source split holds.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))  # escaping_links: one definition, shared

from eval_locked import POTHOLE, pothole_only_root  # noqa: E402
from test_repo_hygiene import escaping_links  # noqa: E402

OTHER_CLASS = (POTHOLE + 1) % 3


def _fixture(repo: Path) -> Path:
    source = repo / "data" / "yolo"
    (source / "images").mkdir(parents=True)
    (source / "labels").mkdir(parents=True)
    for stem, rows in {
        "India__a": [f"{POTHOLE} 0.5 0.5 0.1 0.1", f"{OTHER_CLASS} 0.2 0.2 0.1 0.1"],
        "India__b": [f"{OTHER_CLASS} 0.3 0.3 0.1 0.1"],
    }.items():
        (source / "images" / f"{stem}.jpg").write_bytes(f"pixels of {stem}".encode())
        (source / "labels" / f"{stem}.txt").write_text("\n".join(rows) + "\n")
    (source / "india_heldout.txt").write_text("./images/India__a.jpg\n./images/India__b.jpg\n")
    return source


def test_a_fresh_locked_run_links_relative_and_stays_inside_the_repo(tmp_path):
    source = _fixture(tmp_path)
    out_dir = tmp_path / "results" / "LOCKED" / "P_india_heldout_run"

    root = pothole_only_root(out_dir, source, "india_heldout")

    links = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_symlink())
    assert links == [
        "results/LOCKED/P_india_heldout_run/gt_root/images/India__a.jpg",
        "results/LOCKED/P_india_heldout_run/gt_root/images/India__b.jpg",
    ]
    assert escaping_links(tmp_path, links) == []
    for stem in ("India__a", "India__b"):
        link = root / "images" / f"{stem}.jpg"
        assert not os.path.isabs(os.readlink(link))
        assert link.read_bytes() == (source / "images" / f"{stem}.jpg").read_bytes()


def test_the_derived_ground_truth_keeps_only_potholes_as_class_zero(tmp_path):
    source = _fixture(tmp_path)
    root = pothole_only_root(tmp_path / "run", source, "india_heldout")
    assert (root / "labels" / "India__a.txt").read_text() == "0 0.5 0.5 0.1 0.1\n"
    assert (root / "labels" / "India__b.txt").read_text() == ""
    assert (root / "india_heldout.txt").read_text() == (
        "./images/India__a.jpg\n./images/India__b.jpg\n"
    )
