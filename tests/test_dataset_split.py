import json

from certain_road.detect.dataset.split import (
    SPLIT_BOUNDS,
    assign_split,
    build_splits,
    materialise,
    write_manifest,
)

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


def _make_fake_dataset(tmp_path, stems, with_image=True, with_label=True):
    image_src = tmp_path / "images"
    label_src = tmp_path / "labels_all"
    image_src.mkdir(exist_ok=True)
    label_src.mkdir(exist_ok=True)
    for stem in stems:
        if with_image:
            (image_src / f"{stem}.jpg").write_bytes(b"fake-jpeg-bytes")
        if with_label:
            (label_src / f"{stem}.txt").write_text("0 0.5 0.5 0.1 0.1\n")
    return image_src, label_src


FAKE_STEMS = [f"India_{i:04d}" for i in range(200)]


def test_materialise_creates_matching_image_and_label_counts_per_split(tmp_path):
    image_src, label_src = _make_fake_dataset(tmp_path, FAKE_STEMS)
    out_root = tmp_path / "out"
    splits = build_splits(FAKE_STEMS)

    reports = materialise(splits, image_src, label_src, out_root)

    for name in SPLIT_BOUNDS:
        images = {p.stem for p in (out_root / "images" / name).glob("*.jpg")}
        labels = {p.stem for p in (out_root / "labels" / name).glob("*.txt")}
        assert images == labels
        assert len(images) == len(splits[name])
        assert reports[name].requested == len(splits[name])
        assert reports[name].linked == len(splits[name])
        assert reports[name].skipped_missing_image == 0


def test_calib_never_overlaps_train_or_val_on_disk(tmp_path):
    """The conformal firewall, verified physically rather than only in memory."""
    image_src, label_src = _make_fake_dataset(tmp_path, FAKE_STEMS)
    out_root = tmp_path / "out"
    splits = build_splits(FAKE_STEMS)

    materialise(splits, image_src, label_src, out_root)

    calib_images = {p.name for p in (out_root / "images" / "calib").glob("*.jpg")}
    train_images = {p.name for p in (out_root / "images" / "train").glob("*.jpg")}
    val_images = {p.name for p in (out_root / "images" / "val").glob("*.jpg")}
    assert not (calib_images & train_images)
    assert not (calib_images & val_images)

    # No stem may appear in more than one split's images directory at all.
    seen: set[str] = set()
    for name in SPLIT_BOUNDS:
        stems_here = {p.stem for p in (out_root / "images" / name).glob("*.jpg")}
        assert not (seen & stems_here), f"stem duplicated on disk in split {name}"
        seen |= stems_here


def test_missing_image_is_skipped_and_leaves_no_orphan_label(tmp_path):
    stems = FAKE_STEMS
    image_src, label_src = _make_fake_dataset(tmp_path, stems)
    missing_stem = stems[0]
    (image_src / f"{missing_stem}.jpg").unlink()
    out_root = tmp_path / "out"
    splits = build_splits(stems)

    reports = materialise(splits, image_src, label_src, out_root)

    missing_split = assign_split(missing_stem)
    assert reports[missing_split].skipped_missing_image == 1
    assert reports[missing_split].requested == len(splits[missing_split])
    assert reports[missing_split].linked == len(splits[missing_split]) - 1
    assert not (out_root / "images" / missing_split / f"{missing_stem}.jpg").exists()
    assert not (out_root / "labels" / missing_split / f"{missing_stem}.txt").exists()


def test_rerun_after_removing_a_stem_leaves_no_stale_file(tmp_path):
    stems = FAKE_STEMS
    image_src, label_src = _make_fake_dataset(tmp_path, stems)
    out_root = tmp_path / "out"
    splits = build_splits(stems)
    materialise(splits, image_src, label_src, out_root)

    removed_stem = stems[0]
    removed_split = assign_split(removed_stem)
    (image_src / f"{removed_stem}.jpg").unlink()
    (label_src / f"{removed_stem}.txt").unlink()
    remaining_stems = [s for s in stems if s != removed_stem]
    new_splits = build_splits(remaining_stems)

    materialise(new_splits, image_src, label_src, out_root)

    assert not (out_root / "images" / removed_split / f"{removed_stem}.jpg").exists()
    assert not (out_root / "labels" / removed_split / f"{removed_stem}.txt").exists()
    # Everything else in that split should still be present.
    images = {p.stem for p in (out_root / "images" / removed_split).glob("*.jpg")}
    assert images == set(new_splits[removed_split])


def test_write_manifest_counts_match_actual_split_sizes(tmp_path):
    stems = FAKE_STEMS
    splits = build_splits(stems)
    manifest_path = tmp_path / "splits.json"

    write_manifest(splits, manifest_path)

    data = json.loads(manifest_path.read_text())
    assert set(data["counts"]) == set(SPLIT_BOUNDS)
    for name, names in splits.items():
        assert data["counts"][name] == len(names)
        assert sorted(data["stems"][name]) == sorted(names)
