"""`build_perception`: the rules the simulator and the runtime share.

The scenario matrix (`test_sim_matrix.py`) and the runtime tests reach this module only
through whole runs, so a regression in one rule shows up, if at all, as a changed
scenario outcome. These pin the three rules its docstring names: which hazard governs,
when confirmation applies, and what counts as blocking an escape.

Box coordinates were chosen with the corridor's own `in_path` and `lateral_zone`, and
each test re-asserts the geometry it relies on, so a corridor change fails loudly here
rather than silently changing what is being tested.
"""

from certain_road.artifacts.schema import Detection
from certain_road.driving.confirm import Confirmer
from certain_road.driving.corridor import Corridor, Zone, in_path, lateral_zone, urgency
from certain_road.driving.perceive import build_perception

IMG_W, IMG_H = 640, 480
ESCAPE_LANES = 1.0
CORRIDOR = Corridor(
    center_x=0.5,
    top_y=0.4,
    top_half_width=0.1,
    bottom_y=1.0,
    bottom_half_width=0.4,
    min_overlap=0.3,
    near_proximity=0.6,
    imminent_proximity=0.8,
)


def _det(x1, y1, x2, y2) -> Detection:
    return Detection(
        class_name="pothole", score=0.9, x1=x1, y1=y1, x2=x2, y2=y2, img_w=IMG_W, img_h=IMG_H
    )


NEAR = _det(290, 400, 350, 460)  # centred, low in the frame: nearest
FAR = _det(305, 230, 335, 260)  # centred, high in the frame
STRADDLER = _det(490, 380, 610, 440)  # in the path by overlap, but its centre is RIGHT
LEFT_EDGE = _det(0, 380, 40, 440)  # outside the path, in the left escape lane


def _zone(d: Detection) -> Zone:
    return lateral_zone(d, CORRIDOR, escape_lanes=ESCAPE_LANES)


def _judge(dets, confirmer=None):
    return build_perception(
        dets, CORRIDOR, confirmer or Confirmer(required=1, window=1), escape_lanes=ESCAPE_LANES
    )


def test_the_geometry_these_tests_rely_on():
    assert in_path(NEAR, CORRIDOR, min_overlap=CORRIDOR.min_overlap)
    assert in_path(FAR, CORRIDOR, min_overlap=CORRIDOR.min_overlap)
    assert in_path(STRADDLER, CORRIDOR, min_overlap=CORRIDOR.min_overlap)
    assert _zone(STRADDLER) is Zone.RIGHT
    assert not in_path(LEFT_EDGE, CORRIDOR, min_overlap=CORRIDOR.min_overlap)
    assert _zone(LEFT_EDGE) is Zone.LEFT


def test_the_nearest_in_path_detection_governs():
    perception, governing = _judge([FAR, NEAR])
    assert governing is NEAR
    assert perception.hazard is not None
    assert perception.hazard.urgency == urgency(NEAR, CORRIDOR)


def test_nothing_is_a_hazard_until_the_confirmer_confirms():
    confirmer = Confirmer(required=2, window=3)
    first, governing = _judge([NEAR], confirmer)
    assert governing is NEAR and first.hazard is None
    second, _ = _judge([NEAR], confirmer)
    assert second.hazard is not None


def test_the_governing_hazard_never_blocks_its_own_escape():
    alone, governing = _judge([STRADDLER])
    assert governing is STRADDLER
    assert not alone.right_blocked
    # The same box blocks the right escape once something nearer governs instead.
    behind, governing = _judge([NEAR, STRADDLER])
    assert governing is NEAR
    assert behind.right_blocked and not behind.left_blocked


def test_another_detection_in_an_escape_lane_blocks_that_lane_only():
    perception, _ = _judge([NEAR, LEFT_EDGE])
    assert perception.left_blocked and not perception.right_blocked
