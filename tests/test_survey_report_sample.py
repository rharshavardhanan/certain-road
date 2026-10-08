"""survey.sample must count and score exactly as the MuJoCo survey does, box for box.

The ROS survey node scores through survey.sample; the MuJoCo demo through sim/mujoco/survey.py.
If the two drift, a Gazebo road and its MuJoCo twin would be scored by different rules.
"""

import numpy as np
import pytest

from certain_road.survey import sample
from sim.mujoco.road import load_config
from sim.mujoco.scene import design_camera
from sim.mujoco.survey import PROJECT, in_roi, roi, score_boxes, survey_camera

CFG = load_config()
CAMERA = survey_camera(design_camera())
NEAR, FAR, HALF = roi(CFG)
SC = PROJECT["scoring"]
CLASSES = list(SC["deduct_weights"])


def boxes(seed: int, n: int) -> list[tuple]:
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        x1, y1 = rng.uniform(0, 1200), rng.uniform(250, 690)
        out.append(
            (str(rng.choice(CLASSES)), x1, y1, x1 + rng.uniform(5, 300), y1 + rng.uniform(3, 60))
        )
    return out


@pytest.mark.parametrize("seed", range(5))
def test_roi_matches_the_simulators(seed):
    for b in boxes(seed, 200):
        mine = sample.in_roi(b, CAMERA, near_m=NEAR, far_m=FAR, half_width_m=HALF)
        assert mine == in_roi(b, CAMERA, CFG), b


@pytest.mark.parametrize("seed", range(5))
def test_score_matches_the_simulators(seed):
    counted = [
        b
        for b in boxes(seed, 60)
        if sample.in_roi(b, CAMERA, near_m=NEAR, far_m=FAR, half_width_m=HALF)
    ]
    for seg_m in (SC["segment_m"], 35.0):
        mine = sample.score_boxes(
            counted,
            CAMERA,
            segment_m=seg_m,
            lane_width_m=SC["lane_width_m"],
            weights=SC["deduct_weights"],
        )
        theirs = score_boxes(counted, CAMERA, seg_m)
        assert mine["pci"] == pytest.approx(theirs["pci"])
        assert mine["band"] == theirs["band"]
        assert mine["distress"] == theirs["distress"]
        assert mine["area_m2"] == pytest.approx(theirs["area_m2"])
