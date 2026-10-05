"""The MuJoCo demo's road generator: reproducible, round-trips, and clusters its damage.

A synthetic texture catalogue stands in for the trial photos, so these run without the
gitignored data/ folder. The random preset reads only the committed split audit.
"""

import json
import math

import numpy as np

from certain_road.core.paths import repo_root
from sim.mujoco.road import CLASSES, Road, generate, load_config

# (name, aspect, natural px/m or 0, crop long px, crop short px)
FAKE = {
    "pothole": [("p1", 1.3, 0, 900, 700), ("p2", 1.1, 0, 800, 720)],
    "linear_crack": [("l1", 3.5, 2000, 3000, 860)],
    "alligator_crack": [("a1", 1.33, 2000, 2700, 2025)],
}


def test_same_seed_gives_the_same_road_byte_for_byte():
    assert generate("poor", 3, FAKE).to_json() == generate("poor", 3, FAKE).to_json()
    assert generate("poor", 3, FAKE).to_json() != generate("poor", 4, FAKE).to_json()


def test_ground_truth_round_trips_through_json():
    road = generate("moderate", 1, FAKE)
    assert Road.from_json(road.to_json()) == road


def test_presets_order_by_damage():
    counts = {p: len(generate(p, 0, FAKE).instances) for p in ("good", "moderate", "poor")}
    assert counts["good"] < counts["moderate"] < counts["poor"]
    assert all(i.cls == "linear_crack" for i in generate("good", 0, FAKE).instances)


def test_every_instance_lies_on_the_carriageway():
    road = generate("poor", 2, FAKE)
    for i in road.instances:
        assert i.bbox[0] >= 0 and i.bbox[2] <= road.length_m
        assert -road.lane_width_m <= i.bbox[1] and i.bbox[3] <= road.lane_width_m
        assert i.cls in CLASSES and i.area_m2 > 0


def test_damage_attracts_damage():
    """Clark-Evans ratio: nearest-neighbour distance over uniform scatter's; below 1 clusters."""
    ratios = []
    for seed in range(5):
        road = generate("poor", seed, FAKE)
        pts = np.array([(i.x_m, i.y_m) for i in road.instances])
        d = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1))
        np.fill_diagonal(d, np.inf)
        density = len(pts) / (road.length_m * 2 * road.lane_width_m)
        ratios.append(d.min(1).mean() / (0.5 / math.sqrt(density)))
    assert np.mean(ratios) < 0.8


def test_mixed_preset_turns_bad_partway():
    for seed in range(3):
        road = generate("mixed", seed, FAKE)
        xs = np.array([i.x_m for i in road.instances])
        half = road.length_m / 2
        assert (xs > half).sum() > 2 * (xs <= half).sum()


def test_random_preset_draws_india_train_class_mix():
    cfg = load_config()
    audit = json.loads((repo_root() / cfg["presets"]["random"]["source"]).read_text())["splits"][
        "india_train"
    ]
    want = np.array([audit["instances"][c] for c in CLASSES], float)
    want /= want.sum()
    got = np.zeros(3)
    for seed in range(40):
        for i in generate("random", seed, FAKE).instances:
            got[CLASSES.index(i.cls)] += 1
    assert np.abs(got / got.sum() - want).max() < 0.08
