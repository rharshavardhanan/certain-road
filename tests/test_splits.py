"""T2 — the split lists must be leakage-proof, and these tests are the proof.

Everything here reads the *materialised* lists under `data/yolo/`, not the
functions that generated them. A test that re-derives a split from the same code
that wrote it cannot catch a bug in that code; these assert against the files
training will actually read.

`data/` is gitignored, so the suite skips cleanly on a fresh clone and runs for
real once `scripts/build_pool.py` has been executed.
"""

from pathlib import Path

import pytest
import yaml

from certain_road.core.paths import repo_root

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO = repo_root() / CFG["paths"]["yolo"]
INDIA_SUBSETS = ["india_train", "india_val", "india_cal", "india_test"]
NUM_CLASSES = len(CFG["classes"])

pytestmark = pytest.mark.skipif(
    not (YOLO / "india_full.txt").exists(),
    reason="image pool not built; run scripts/build_pool.py",
)


def names(split: str) -> set[str]:
    lines = (YOLO / f"{split}.txt").read_text().splitlines()
    return {Path(line).stem for line in lines if line.strip()}


def all_splits() -> list[str]:
    return sorted(p.stem for p in YOLO.glob("*.txt"))


def test_no_india_in_any_nonindia_split():
    for split in (s for s in all_splits() if s.startswith("nonindia")):
        leaked = {n for n in names(split) if n.startswith("India__")}
        assert not leaked, f"{split} contains India: {sorted(leaked)[:5]}"


def test_india_subsets_are_pairwise_disjoint():
    for i, a in enumerate(INDIA_SUBSETS):
        for b in INDIA_SUBSETS[i + 1:]:
            overlap = names(a) & names(b)
            assert not overlap, f"{a} & {b} share {sorted(overlap)[:5]}"


def test_india_subsets_union_to_india_full():
    union = set().union(*(names(s) for s in INDIA_SUBSETS))
    assert union == names("india_full")


def test_india_heldout_is_exactly_cal_plus_test():
    assert names("india_heldout") == names("india_cal") | names("india_test")


def test_nonindia_train_and_val_are_disjoint():
    assert not (names("nonindia_train") & names("nonindia_val"))


def test_replay_is_a_subset_of_nonindia_train():
    assert names("nonindia_replay") <= names("nonindia_train")


def test_calibration_and_test_never_reach_model_b_training():
    """The firewall. Model B trains on india_train + nonindia_replay and
    validates on india_val; cal and test must appear in none of them."""
    forbidden = names("india_cal") | names("india_test")
    for split in ("india_train", "nonindia_replay", "india_val"):
        assert not (names(split) & forbidden), f"{split} leaks held-out India"


def test_model_b_yaml_never_references_a_heldout_list():
    cfg = yaml.safe_load((repo_root() / "configs" / "data" / "model_b.yaml").read_text())
    referenced = set(cfg["train"] if isinstance(cfg["train"], list) else [cfg["train"]])
    referenced.add(cfg["val"])
    assert not (referenced & {"india_cal.txt", "india_test.txt", "india_heldout.txt"})


def test_model_a_yaml_references_no_india_list():
    cfg = yaml.safe_load((repo_root() / "configs" / "data" / "model_a.yaml").read_text())
    referenced = [cfg["train"], cfg["val"]]
    # Anchored: "nonindia_train.txt" contains the substring "india".
    assert not any(r.startswith("india_") for r in referenced), referenced


def test_every_listed_image_has_a_label_file():
    for split in all_splits():
        for name in names(split):
            assert (YOLO / "images" / f"{name}.jpg").exists(), f"{split}: missing image {name}"
            assert (YOLO / "labels" / f"{name}.txt").exists(), f"{split}: missing label {name}"


def test_every_label_line_is_well_formed():
    for label in (YOLO / "labels").glob("*.txt"):
        for line in label.read_text().splitlines():
            if not line.strip():
                continue
            parts = line.split()
            assert len(parts) == 5, f"{label.name}: {line!r}"
            cls = int(parts[0])
            assert 0 <= cls < NUM_CLASSES, f"{label.name}: class {cls}"
            for value in map(float, parts[1:]):
                assert 0.0 <= value <= 1.0, f"{label.name}: {value} out of [0,1]"


def test_external_sets_never_appear_in_a_training_list():
    """T9's BharatPotHole and T15's Chennai are evaluation-only, forever.

    They do not exist yet; this test exists now so that adding them cannot
    quietly put them into training later.
    """
    for split in ("nonindia_train", "india_train", "nonindia_replay"):
        for name in names(split):
            assert not name.startswith(("BharatPotHole__", "Chennai__")), name


# --- D061: same-scene groups must never span an India split -------------------

SCENE_GROUPS = repo_root() / "results" / "T2" / "india_scene_groups.json"


@pytest.mark.skipif(not SCENE_GROUPS.exists(), reason="run scripts/scene_groups.py")
def test_no_scene_group_spans_india_splits():
    """The D061 firewall.

    Near-duplicate frames of one location - same pipes, same signboard, seconds
    apart - are as contaminating as an identical file: a model that trained on
    one has effectively seen the other. Grouping is transitive, so a chain of
    overlapping frames along one stretch of road stays whole.
    """
    import json

    groups = json.loads(SCENE_GROUPS.read_text())["groups"]
    membership = {split: names(split) for split in INDIA_SUBSETS}

    offenders = []
    for gid, members in groups.items():
        landed = {s for s, pool in membership.items() if pool & set(members)}
        if len(landed) > 1:
            offenders.append((gid, sorted(landed), len(members)))
    assert not offenders, f"{len(offenders)} scene groups span splits: {offenders[:3]}"


@pytest.mark.skipif(not SCENE_GROUPS.exists(), reason="run scripts/scene_groups.py")
def test_every_grouped_image_is_still_present_exactly_once():
    """Regrouping must not lose or duplicate an image."""
    import json

    groups = json.loads(SCENE_GROUPS.read_text())["groups"]
    grouped = {m for members in groups.values() for m in members}
    union = set().union(*(names(s) for s in INDIA_SUBSETS))
    assert grouped <= union
    counts = [sum(m in names(s) for s in INDIA_SUBSETS) for m in sorted(grouped)]
    assert set(counts) == {1}, "a grouped image appears in more than one split"
