"""The survey report, built from a small fixture: offline, honest, and the real allocators' plan.

No weights, no GL and no run directory: two tiny roads are written out by hand, and the page is
checked for what it must always carry (D020, D079, D082, D087) and for the numbers it states.
"""

import copy
import io
import re

import pytest
import yaml
from PIL import Image

from certain_road.core.paths import repo_root
from certain_road.dashboard.survey_report import (
    CAPTION,
    Pricing,
    RoadRun,
    build_report,
    downscale_jpeg,
    pooled_plan,
    segment_rows,
)
from certain_road.survey import rsl
from certain_road.survey.allocation import (
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
)

CFG = yaml.safe_load((repo_root() / "configs/report/survey_environments.yaml").read_text())
RSL_RAW = yaml.safe_load((repo_root() / "configs/rsl/published_default.yaml").read_text())
RSL = rsl.parse_config(RSL_RAW)
PRICING = Pricing(mobilisation_cost=50000, cost_per_m2=2500, budget_frac=0.3, worst_share=0.1)
STAMP = {"utc": "2026-10-08 00:00 UTC", "commit": "test"}


def jpeg(colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), colour).save(buf, "JPEG")
    return buf.getvalue()


def seg(i, pci, ref, area, counts=(0, 0, 0)):
    return {
        "index": i,
        "x0_m": 3.0 + 50 * i,
        "x1_m": 53.0 + 50 * i,
        "vision_estimated_pci": pci,
        "pci_ref": ref,
        "area_ref_m2": area,
        "counts": dict(zip(("pothole", "alligator_crack", "linear_crack"), counts, strict=True)),
    }


def detection(hit, n, fa, km=0.15):
    per = {
        c: {
            "instances": n,
            "hit": hit,
            "recall": hit / n if n else None,
            "false_alarm_tracks": fa,
            "false_alarms_per_km": fa / km,
        }
        for c in ("pothole", "alligator_crack", "linear_crack")
    }
    return {"km": km, "per_class": per}


TRACK = {
    "model": "P",
    "cls": "pothole",
    "track": 7,
    "hit_ids": [],
    "false_alarm": True,
    "confirmed_frames": 5,
    "first_x_cam_m": 40.0,
    "best": {"frame": 230, "x_cam_m": 42.6, "score": 0.61, "box": [600, 400, 700, 450]},
    "location": {
        "chainage_m": 51.3,
        "lateral_m": 1.2,
        "lane": "left lane (driving)",
        "segment": 0,
        "error_to_match_m": None,
        "nearest_instance": {"id": 3, "cls": "alligator_crack", "distance_m": 0.0},
    },
    "counted_in_survey": True,
    "crop": "gallery/P_pothole_7.jpg",
    "frame": "gallery/P_pothole_7_frame.jpg",
}


def roads() -> list[RoadRun]:
    good = RoadRun(
        label="Good road, seed 0",
        preset="good",
        seed=0,
        look="v2",
        length_m=160.0,
        run_dir="runs/mujoco/good_seed0_v2",
        segments=[seg(0, 100.0, 100.0, 0.0), seg(1, 100.0, 96.0, 0.4), seg(2, 92.0, 100.0, 0.0)],
        detection=detection(0, 2, 0),
        gallery={"tracks": [], "replay": {"verification": []}},
    )
    hit = dict(copy.deepcopy(TRACK), false_alarm=False, hit_ids=[4], track=9)
    hit["location"]["error_to_match_m"] = 0.2
    hit["crop"], hit["frame"] = "gallery/P_pothole_9.jpg", "gallery/P_pothole_9_frame.jpg"
    poor = RoadRun(
        label="Poor road, seed 0",
        preset="poor",
        seed=0,
        look="v2",
        length_m=160.0,
        run_dir="runs/mujoco/poor_seed0_v2",
        segments=[
            seg(0, 64.0, 70.0, 6.0, (2, 1, 1)),
            seg(1, 81.0, 76.0, 3.0, (0, 1, 2)),
            seg(2, 55.0, 61.0, 9.0, (3, 2, 0)),
        ],
        detection=detection(3, 5, 2),
        drift_alarm_m=150.0,
        gallery={
            "tracks": [TRACK, hit],
            "replay": {
                "verification": [{"frame": 27, "same_boxes": True, "max_px_diff": 0.0, "x_m": 5.0}]
            },
        },
        images={p: jpeg() for t in (TRACK, hit) for p in (t["crop"], t["frame"])},
        stills={"end": jpeg((10, 10, 10))},
        recording="runs/mujoco/poor_seed0_v2.mp4",
        timing={"frames": 900, "drive_wall_s": 150.0, "realtime_x": 0.2},
    )
    return [good, poor]


@pytest.fixture(scope="module")
def built():
    return build_report(roads(), RSL, PRICING, CFG, STAMP)


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r"<title>.*?</title>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def test_the_page_is_self_contained(built):
    page, _ = built
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", page)
    assert "<link" not in page and "@import" not in page
    assert not re.search(r"<script[^>]+src=", page)
    assert not re.search(r"url\(\s*['\"]?https?:", page)
    assert page.count("data:image/jpeg;base64,") == 5  # two crops, two frames, one still


def test_it_says_what_it_is_and_credits_the_textures(built):
    text = visible_text(built[0])
    assert CAPTION in text
    assert "QR4Change, Maske et al. 2025" in text and "BD-N6, Hossain et al." in text
    assert "CC BY 4.0" in text
    assert "Model P" in text and "Model B" in text and "D082" in text


def test_the_rsl_source_and_its_status_are_on_the_page(built):
    text = visible_text(built[0])
    assert "pending mentor approval" in text
    assert "Transportation Research Record 1123" in text
    assert "designed, not built" in text  # no PCI interval is invented


def test_pci_is_always_qualified(built):
    """Terminology (CLAUDE.md): never a bare PCI for this pipeline's quantity.

    Allowed: vision-estimated PCI, reference PCI, and the cited curve's own PCI, which is
    written with its value or as the curve's formula.
    """
    text = visible_text(built[0])
    for m in re.finditer(r"\bPCI\b", text):
        before = text[max(0, m.start() - 20) : m.start()].lower()
        after = text[m.end() : m.end() + 8]
        qualified = before.rstrip().endswith(("vision-estimated", "reference", "paver"))
        curve = re.match(r"\s*(=|\d)", after) is not None
        assert qualified or curve, text[max(0, m.start() - 60) : m.end() + 30]


def test_the_pooled_plan_is_the_real_allocators_choice(built):
    _, data = built
    rows = data["segments"]
    segs = [Segment(r["id"], r["pci"], r["cost"]) for r in rows]
    budget = 0.3 * sum(r["cost"] for r in rows)
    assert data["plan"]["budget"] == pytest.approx(budget)
    assert data["plan"]["plans"]["optimiser"]["chosen"] == allocate_optimal(segs, budget)
    assert data["plan"]["plans"]["worst_first"]["chosen"] == allocate_greedy_worst_first(
        segs, budget
    )
    for r in rows:  # D079's pricing on the reference area, as the end screen prices (D090)
        assert r["cost"] == pytest.approx(50000 + 2500 * r["area_ref_m2"])


def test_both_objectives_are_scored_on_the_reference(built):
    _, data = built
    plan, rows = data["plan"], {r["id"]: r for r in data["segments"]}
    damaged = sorted((r for r in rows.values() if r["pci_ref"] < 100), key=lambda r: r["pci_ref"])
    assert plan["worst"] == [damaged[0]["id"]]  # 10% of 6 segments rounds to 1
    for p in plan["plans"].values():
        assert p["true_benefit"] == pytest.approx(
            sum(100 - rows[i]["pci_ref"] for i in p["chosen"])
        )
        assert p["worst_covered"] == sum(i in p["chosen"] for i in plan["worst"])


def test_rsl_comes_from_the_rsl_stage(built):
    _, data = built
    for r in data["segments"]:
        assert r["rsl"] == pytest.approx(rsl.rsl_years(r["pci"], RSL.curve))
        assert r["rsl_lo"] is None and r["rsl_hi"] is None
        assert r["must_fix"] == (r["rsl"] < RSL.must_fix_rsl_years)


def test_an_interval_in_the_artifact_maps_through(built):
    road = roads()[1]
    road.segments[0] |= {"pci_lo": 58.0, "pci_hi": 75.0}
    rows = segment_rows([road], RSL, PRICING)
    lo, hi = rsl.rsl_interval(58.0, 75.0, RSL.curve)
    assert (rows[0]["rsl_lo"], rows[0]["rsl_hi"]) == (lo, hi)


def test_the_gallery_card_says_what_where_and_whether_it_is_real(built):
    text = visible_text(built[0])
    assert "51.3 m along the road" in text
    assert "1.2 m left of the centre line" in text
    assert "left lane (driving)" in text and "segment 0" in text
    assert "Model P" in text and "confidence 0.61" in text
    assert "False alarm" in text and "nearest ground truth: alligator crack #3" in text
    assert "Matches pothole #4" in text


def test_worst_first_reasons_name_its_order(built):
    page, data = built
    first = data["plan"]["order"][0]
    row = next(r for r in data["segments"] if r["id"] == first)
    assert row["pci"] == min(r["pci"] for r in data["segments"])
    assert "#1 by vision-estimated PCI" in page
    assert "Repair first:" in visible_text(page)


def test_pci_only_mode_gives_band_recommendations_and_no_rsl():
    raw = copy.deepcopy(RSL_RAW) | {"mode": "pci_only"}
    cfg = rsl.parse_config(raw)
    page, data = build_report(roads(), cfg, PRICING, CFG, STAMP)
    assert all(r["rsl"] is None for r in data["segments"])
    text = visible_text(page)
    assert raw["pci_only"]["treatments"]["Poor"] in text
    assert "Recommendation" in text


def test_a_road_without_ground_truth_renders_without_reference_columns():
    road = roads()[1]
    road.detection = None
    road.simulated = False
    for s in road.segments:
        s["pci_ref"] = None
    page, data = build_report([road], RSL, PRICING, CFG, STAMP)
    assert "true_benefit" not in data["plan"]["plans"]["optimiser"]
    assert CAPTION not in page
    assert "Reference band" not in page
    assert "True worst" not in page and "true benefit" not in page.lower()


def test_pooled_plan_explains_every_segment():
    rows = segment_rows(roads(), RSL, PRICING)
    plan = pooled_plan(rows, PRICING)
    assert sorted(plan["order"]) == [r["id"] for r in rows]
    assert set(plan["why"]) == {r["id"] for r in rows}
    zero = next(r for r in rows if r["pci"] == 100.0)
    assert "priority 0" in plan["why"][zero["id"]]["optimiser"]


def test_downscale_keeps_small_images_and_shrinks_large_ones():
    big = io.BytesIO()
    Image.new("RGB", (1920, 1080), (5, 5, 5)).save(big, "PNG")
    out = Image.open(io.BytesIO(downscale_jpeg(big.getvalue(), 960, 78)))
    assert out.size == (960, 540)
    small = Image.open(io.BytesIO(downscale_jpeg(jpeg(), 960, 78)))
    assert small.size == (32, 24)
