import pandas as pd
import pytest

from certain_road.perception.predict import load_class_map, remap_class_ids


def test_rdd2022_map_merges_d00_and_d10():
    m = load_class_map("rdd2022_4class")
    assert m[0] == 0 and m[1] == 0, "D00 and D10 must both become linear_crack"
    assert m[2] == 1, "D20 -> alligator_crack"
    assert m[3] == 2, "D40 -> pothole"


def test_identity_map_is_a_noop():
    assert load_class_map("identity_3class") == {0: 0, 1: 1, 2: 2}


def test_remap_preserves_row_count():
    """Merging is a relabel, not a combine — two boxes stay two boxes."""
    df = pd.DataFrame({"class_id": [0, 1, 2, 3], "score": [0.9, 0.8, 0.7, 0.6]})
    out = remap_class_ids(df, load_class_map("rdd2022_4class"))
    assert len(out) == 4
    assert list(out["class_id"]) == [0, 0, 1, 2]


def test_remap_rejects_an_id_absent_from_the_map():
    """An unmapped class must fail loudly, not silently vanish."""
    df = pd.DataFrame({"class_id": [7], "score": [0.9]})
    with pytest.raises(ValueError, match="7"):
        remap_class_ids(df, load_class_map("rdd2022_4class"))


def test_load_class_map_rejects_unknown_name():
    with pytest.raises(ValueError, match="nonexistent_map"):
        load_class_map("nonexistent_map")
