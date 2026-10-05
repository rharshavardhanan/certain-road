"""The drive loop's rules: D082's channels, the gate row, and the 5 m survey samples.

These need no weights, GPU or GL: they test the rules the loop applies, not the models.
"""

import pytest

from certain_road.core.geometry import ground_point
from sim.mujoco.drive import PROJECT, frame_positions, gate_row, keep
from sim.mujoco.road import load_config
from sim.mujoco.scene import design_camera

CFG = load_config()


def test_d082_potholes_from_p_cracks_from_b_never_both():
    assert keep("P", "pothole", CFG)
    assert not keep("B", "pothole", CFG)  # B's pothole channel is discarded, never summed
    assert keep("B", "linear_crack", CFG) and keep("B", "alligator_crack", CFG)
    assert not keep("P", "linear_crack", CFG)


def test_gate_row_is_where_the_design_detect_range_meets_the_road():
    cam = design_camera()
    v = gate_row(cam)
    fwd, _ = ground_point(
        cam["w"] / 2,
        v,
        f=cam["f"],
        cx=cam["w"] / 2,
        cy=cam["h"] / 2,
        cam_h=cam["height"],
        pitch=cam["pitch"],
    )
    assert fwd == pytest.approx(PROJECT["edge"]["detect_range_m"], rel=1e-9)


def test_every_ninth_frame_is_a_five_metre_survey_sample():
    xs, sampled = frame_positions(100.0, CFG)
    step = PROJECT["edge"]["sample_every_m"]
    marks = [x for x, s in zip(xs, sampled, strict=True) if s]
    assert marks[:3] == pytest.approx([0.0, step, 2 * step])
    assert sum(sampled) * CFG["drive"]["frames_per_sample"] == pytest.approx(
        len(xs), abs=CFG["drive"]["frames_per_sample"]
    )
