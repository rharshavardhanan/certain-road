"""Tests for the driving corridor geometry (Task A).

The corridor is deliberately not the survey ROI (see configs/driving/
corridor.yaml and D049/D050) -- these tests use a small, hand-picked corridor
so the expected geometry is easy to reason about, plus two tests that the
real shipped config loads correctly.
"""

from pathlib import Path

import pytest

from certain_road.artifacts.schema import Detection
from certain_road.driving.corridor import (
    CORRIDOR_CONFIG_PATH,
    Corridor,
    corridor_polygon,
    in_path,
    load_corridor,
    overlap_fraction,
)

IMG_W, IMG_H = 640, 480


def _corridor(**overrides) -> Corridor:
    defaults = dict(
        center_x=0.5,
        top_y=0.4,
        top_half_width=0.1,
        bottom_y=1.0,
        bottom_half_width=0.4,
        min_overlap=0.3,
    )
    defaults.update(overrides)
    return Corridor(**defaults)


def _det(x1, y1, x2, y2, img_w=IMG_W, img_h=IMG_H, class_name="pothole", score=0.9) -> Detection:
    return Detection(
        class_name=class_name, score=score, x1=x1, y1=y1, x2=x2, y2=y2, img_w=img_w, img_h=img_h
    )


def test_corridor_polygon_has_four_vertices_and_widens_toward_camera():
    corridor = _corridor()
    poly = corridor_polygon(corridor, IMG_W, IMG_H)

    assert poly.shape == (4, 2)

    top_width = poly[1][0] - poly[0][0]
    bottom_width = poly[2][0] - poly[3][0]
    assert bottom_width > top_width > 0


def test_centred_low_box_is_in_path():
    corridor = _corridor()
    det = _det(280, 440, 360, 470)  # centred, near the bottom of frame

    assert overlap_fraction(det, corridor) == pytest.approx(1.0)
    assert in_path(det, corridor, min_overlap=corridor.min_overlap) is True


def test_frame_edge_box_is_not_in_path():
    corridor = _corridor()
    det = _det(0, 440, 40, 470)  # hugs the left edge of the frame

    assert overlap_fraction(det, corridor) == pytest.approx(0.0)
    assert in_path(det, corridor, min_overlap=corridor.min_overlap) is False


def test_straddling_box_overlap_is_strictly_between_zero_and_one():
    corridor = _corridor()
    det = _det(40, 440, 140, 470)  # straddles the corridor's left edge

    frac = overlap_fraction(det, corridor)
    assert 0.0 < frac < 1.0


def test_box_above_corridor_top_is_not_in_path():
    corridor = _corridor()
    det = _det(280, 50, 360, 150)  # entirely above the corridor's horizon edge

    assert overlap_fraction(det, corridor) == pytest.approx(0.0)
    assert in_path(det, corridor, min_overlap=corridor.min_overlap) is False


def test_fully_inside_box_has_overlap_of_exactly_one():
    corridor = _corridor()
    det = _det(300, 450, 340, 470)  # small box, well inside the corridor

    assert overlap_fraction(det, corridor) == pytest.approx(1.0)


def test_load_corridor_reads_the_real_shipped_config():
    corridor = load_corridor(CORRIDOR_CONFIG_PATH)

    assert 0.0 <= corridor.top_y < corridor.bottom_y <= 1.0
    assert 0.0 < corridor.top_half_width < corridor.bottom_half_width
    assert 0.0 < corridor.min_overlap <= 1.0


def test_load_corridor_rejects_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_corridor(tmp_path / "does-not-exist.yaml")
