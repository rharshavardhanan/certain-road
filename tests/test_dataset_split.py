from certain_road.detect.dataset.split import SPLIT_BOUNDS, assign_split, build_splits

STEMS = [f"India_{i:06d}" for i in range(4000)]


def test_assignment_is_deterministic():
    assert assign_split("India_000004") == assign_split("India_000004")


def test_salt_changes_assignment_distribution():
    a = [assign_split(s, salt="one") for s in STEMS]
    b = [assign_split(s, salt="two") for s in STEMS]
    assert a != b


def test_splits_are_disjoint_and_complete():
    splits = build_splits(STEMS)
    assert set(splits) == set(SPLIT_BOUNDS)

    seen = set()
    for names in splits.values():
        assert not (seen & set(names)), "a stem appears in more than one split"
        seen |= set(names)
    assert seen == set(STEMS)


def test_proportions_are_within_tolerance():
    splits = build_splits(STEMS)
    total = len(STEMS)
    expected = {"train": 0.60, "val": 0.10, "calib": 0.20, "test": 0.10}
    for name, share in expected.items():
        actual = len(splits[name]) / total
        assert abs(actual - share) < 0.02, f"{name}: {actual:.3f} vs {share}"


def test_calib_never_overlaps_train_or_val():
    """Conformal validity depends on this and nothing else enforces it."""
    splits = build_splits(STEMS)
    calib = set(splits["calib"])
    assert not (calib & set(splits["train"]))
    assert not (calib & set(splits["val"]))


def test_adding_files_does_not_move_existing_ones():
    """Hash-based assignment must be stable as the dataset grows."""
    before = build_splits(STEMS[:2000])
    after = build_splits(STEMS)
    for name, names in before.items():
        assert set(names) <= set(after[name])
