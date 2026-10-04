"""The T2 split functions, on synthetic names: no image pool needed.

`test_splits.py` checks the materialised split lists, but it needs the gitignored image
pool and skips on every clone, so CI never exercised the split logic. These test the
pure functions behind those lists: every image in exactly one split, near the
configured fractions, stable when the file set grows (D009), and same-scene groups
kept whole (D061).
"""

import yaml

from certain_road.core.paths import repo_root
from certain_road.perception.dataset.pool import (
    pool_name,
    sample_replay,
    split_india,
    split_india_grouped,
    split_nonindia,
    unit_hash,
)

SPLIT = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())["split"]
FRACS = SPLIT["india_fracs"]
STEMS = [f"India_{i:06d}" for i in range(2000)]
FRACTION_TOLERANCE = 0.03  # about 4.5 standard deviations for the smallest split at n = 2000


def _assert_partition(splits: dict[str, list[str]], names: list[str]) -> None:
    every = [n for members in splits.values() for n in members]
    assert sorted(every) == sorted(names)
    assert len(every) == len(set(every))


def test_unit_hash_is_stable_in_the_unit_interval_and_salted():
    h = unit_hash("India__India_000001")
    assert h == unit_hash("India__India_000001")
    assert 0.0 <= h < 1.0
    assert h != unit_hash("India__India_000001", salt="another-salt")


def test_every_india_image_lands_in_exactly_one_split_near_its_fraction():
    splits = split_india(STEMS, fracs=FRACS)
    _assert_partition(splits, [pool_name("India", s) for s in STEMS])
    for key, frac in FRACS.items():
        assert abs(len(splits[key]) / len(STEMS) - frac) < FRACTION_TOLERANCE


def test_adding_an_image_never_moves_another_d009():
    before = split_india(STEMS, fracs=FRACS)
    after = split_india([*STEMS, "India_999999"], fracs=FRACS)
    for key in FRACS:
        assert set(before[key]) <= set(after[key])


def test_nonindia_split_is_per_country_and_disjoint():
    stems = {"Japan": [f"Japan_{i:06d}" for i in range(500)], "Norway": ["Norway_000001"]}
    splits = split_nonindia(stems, val_frac=SPLIT["nonindia_val_frac"])
    names = [pool_name(c, s) for c, ss in stems.items() for s in ss]
    _assert_partition(splits, names)
    assert all(n.split("__")[0] in stems for n in names)


def test_a_same_scene_group_is_never_split_d061():
    groups = [STEMS[0:40], STEMS[100:105], STEMS[500:502]]
    counts = {s: (i % 2, 1) for i, s in enumerate(STEMS)}
    for class_counts in (None, counts):
        splits = split_india_grouped(STEMS, fracs=FRACS, groups=groups, class_counts=class_counts)
        _assert_partition(splits, STEMS)
        for group in groups:
            homes = {k for k, members in splits.items() if set(group) & set(members)}
            assert len(homes) == 1, (group[0], homes)


def test_the_replay_sample_is_deterministic_and_capped():
    train = [f"Japan__Japan_{i:06d}" for i in range(50)]
    assert sample_replay(train, 10, seed=0) == sample_replay(train, 10, seed=0)
    assert len(sample_replay(train, 10, seed=0)) == 10
    assert sample_replay(train, 500, seed=0) == sorted(train)
