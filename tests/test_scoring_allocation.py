"""T12 — scoring must stay monotone, and the ILP must actually beat greedy."""

import math

import pytest

from certain_road.survey.allocation import (
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
    allocate_random,
    total_cost,
    total_priority,
)
from certain_road.survey.scoring import (
    Camera,
    band,
    box_footprint_m2,
    cumulative_distance_m,
    deduct_value,
    robust_vision_density,
    segment_distress,
    segment_index,
    vision_density,
    vision_estimated_pci,
)

CAM = Camera(f=935.5, cx=640.0, cy=360.0, cam_h=1.3, pitch=math.radians(10.0))


def test_bands_cover_every_score_without_gaps():
    assert [band(s) for s in (100, 86, 85, 71, 70, 56, 55, 41, 40, 26, 25, 11, 10, 0)] == [
        "Good",
        "Good",
        "Satisfactory",
        "Satisfactory",
        "Fair",
        "Fair",
        "Poor",
        "Poor",
        "Very Poor",
        "Very Poor",
        "Serious",
        "Serious",
        "Failed",
        "Failed",
    ]


def test_deduct_is_zero_at_zero_distress():
    assert deduct_value(0.0, weight=30) == 0.0


def test_deduct_is_monotone_in_vision_density():
    values = [deduct_value(d, weight=20) for d in range(0, 50)]
    assert all(b >= a for a, b in zip(values, values[1:]))  # noqa: B905


def test_deduct_is_concave_so_early_damage_counts_most():
    first = deduct_value(5, 30) - deduct_value(0, 30)
    later = deduct_value(105, 30) - deduct_value(100, 30)
    assert first > later


def test_vision_estimated_pci_clips_to_the_band_range():
    assert vision_estimated_pci({"pothole": 500.0}) == 0.0
    assert vision_estimated_pci({}) == 100.0


def test_worse_distress_never_raises_the_score():
    mild = vision_estimated_pci({"pothole": deduct_value(1, 30)})
    severe = vision_estimated_pci({"pothole": deduct_value(40, 30)})
    assert severe < mild


def test_footprint_grows_with_a_larger_box_at_the_same_range():
    small = box_footprint_m2(600, 600, 680, 650, CAM)
    large = box_footprint_m2(500, 600, 780, 650, CAM)
    assert small is not None and large is not None and large > small


def test_footprint_is_none_above_the_horizon():
    """No ground intersection, so no area - and no invented number."""
    assert box_footprint_m2(600, 10, 680, 20, CAM) is None


def test_vision_density_is_a_percentage_of_the_lane_rectangle():
    assert vision_density(8.75, segment_m=50, lane_width_m=3.5) == pytest.approx(5.0)


def test_robust_density_inflates_by_the_certified_miss_rate():
    assert robust_vision_density(10.0, 0.2) == pytest.approx(12.5)


def test_robust_density_refuses_an_uncertified_alpha():
    with pytest.raises(ValueError, match="certified"):
        robust_vision_density(10.0, 0.2, certified=False)
    with pytest.raises(ValueError, match="alpha"):
        robust_vision_density(10.0, 1.0)


def test_segments_follow_cumulative_distance():
    lats = [0.0, 0.0002, 0.0004, 0.0009]
    dist = cumulative_distance_m(lats, [0.0] * 4)
    assert dist[0] == 0.0 and all(b > a for a, b in zip(dist, dist[1:]))  # noqa: B905
    # 0.0002 deg of latitude is ~22.2 m, so the fixes land at 0, 22.2, 44.5, 100.1 m.
    # Segment 1 is genuinely empty here - a gap the scorer must tolerate.
    assert [round(d, 1) for d in dist] == [0.0, 22.2, 44.5, 100.1]
    assert segment_index(dist, 50.0) == [0, 0, 0, 2]


# --- allocation --------------------------------------------------------------


def knapsack_trap():
    """One cheap-but-not-worst pair beats the single worst segment."""
    return [
        Segment(0, vision_estimated_pci=10, cost=100),  # priority 90
        Segment(1, vision_estimated_pci=20, cost=50),  # priority 80
        Segment(2, vision_estimated_pci=25, cost=50),  # priority 75
    ]


def test_optimal_beats_greedy_on_the_knapsack_trap():
    segments, budget = knapsack_trap(), 100.0
    best = allocate_optimal(segments, budget)
    greedy = allocate_greedy_worst_first(segments, budget)
    assert best == [1, 2] and greedy == [0]
    assert total_priority(segments, best) > total_priority(segments, greedy)


def test_no_policy_ever_exceeds_the_budget():
    segments = [Segment(i, vision_estimated_pci=i % 100, cost=10 + i) for i in range(40)]
    for chosen in (
        allocate_optimal(segments, 200.0),
        allocate_greedy_worst_first(segments, 200.0),
        allocate_random(segments, 200.0, seed=3),
    ):
        assert total_cost(segments, chosen) <= 200.0


def test_zero_budget_repairs_nothing():
    assert allocate_optimal(knapsack_trap(), 0.0) == []


def test_ample_budget_repairs_everything():
    assert allocate_optimal(knapsack_trap(), 10_000.0) == [0, 1, 2]


def test_traffic_weight_shifts_priority():
    quiet = Segment(0, vision_estimated_pci=50, cost=10, traffic_weight=1.0)
    busy = Segment(1, vision_estimated_pci=50, cost=10, traffic_weight=3.0)
    assert busy.priority == 3 * quiet.priority


def test_random_policy_is_reproducible():
    segments = [Segment(i, vision_estimated_pci=i, cost=5) for i in range(30)]
    assert allocate_random(segments, 50.0, seed=9) == allocate_random(segments, 50.0, seed=9)


def test_bands_cover_continuous_scores_between_the_integer_edges():
    """Vision-estimated PCI is continuous; the spec's bands are written with
    integer edges. 70.04 sits between Fair's 70 and Satisfactory's 71 and used to
    raise — about one real score in fifteen. A score belongs to the band whose
    lower edge it has reached."""
    assert band(85.5) == "Satisfactory"
    assert band(70.036) == "Fair"
    assert band(40.999) == "Very Poor"
    assert band(10.5) == "Failed"
    assert band(99.99) == "Good"


# --- the counts-per-100 m fallback -----------------------------------------
#
# The module docstring promised it; nothing implemented it. The unit travels with
# the value so a dashboard can never compare a percentage with a count.


def test_segment_distress_is_vision_density_when_every_footprint_is_known():
    value, unit = segment_distress([1.75, 1.75], segment_m=50, lane_width_m=3.5)
    assert unit == "vision_density_pct"
    assert value == pytest.approx(2.0)  # 3.5 m2 of a 175 m2 lane rectangle


def test_one_missing_footprint_falls_back_to_counts_per_100m():
    """Mixing projected area with unprojectable boxes would understate the
    segment silently, so the whole segment changes unit instead."""
    value, unit = segment_distress([1.0, None, 2.0], segment_m=50, lane_width_m=3.5)
    assert unit == "count_per_100m"
    assert value == pytest.approx(6.0)  # 3 boxes over 50 m


def test_a_segment_with_no_distress_is_zero_vision_density():
    assert segment_distress([], segment_m=50, lane_width_m=3.5) == (0.0, "vision_density_pct")
