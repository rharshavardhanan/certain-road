"""The dashboard reads files and runs the T12 optimiser; it must never hide either objective.

Two properties matter more than any rendering detail:

* A missing or unreadable result is shown as "not run", never as an exception and
  never as a silently empty table (the spec's done-when).
* At any budget the optimiser's plan and the worst-first plan are shown side by
  side with true-worst-20 coverage for each (D079). The optimiser maximises total
  benefit, which can defer the worst road entirely; a view that showed only its
  set would hide that.
"""

import json

import pytest

from certain_road.dashboard.plans import two_plans
from certain_road.dashboard.results import NotRun, load_json


def test_present_json_loads(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"map50": 0.4}))
    assert load_json(f) == {"map50": 0.4}


def test_missing_json_is_not_run_and_names_the_file(tmp_path):
    out = load_json(tmp_path / "T13" / "sim.json")
    assert isinstance(out, NotRun)
    assert out.reason == "missing"
    assert "T13" in str(out) and "not run" in str(out)


def test_malformed_json_is_not_run_rather_than_a_crash(tmp_path):
    f = tmp_path / "half_written.json"
    f.write_text('{"map50": 0.')
    out = load_json(f)
    assert isinstance(out, NotRun)
    assert out.reason.startswith("unreadable")


def network(rows):
    """rows: (true_pci, observed_pci, cost). Uniform traffic."""
    return {
        "segments": [
            {"id": i, "true_pci": t, "observed_pci": o, "robust_pci": o, "cost": c, "traffic": 1.0}
            for i, (t, o, c) in enumerate(rows)
        ]
    }


# One failed road that is expensive, four moderate roads that are cheap. The budget
# buys either the failed road alone (benefit 90) or all four moderate ones (4 x 40).
KNAPSACK_TRAP = network([(10.0, 10.0, 400.0)] + [(60.0, 60.0, 100.0)] * 4)
BUDGET_FRACTION = 400.0 / 800.0


def test_the_optimiser_defers_the_worst_road_that_worst_first_repairs():
    plans = two_plans(KNAPSACK_TRAP, BUDGET_FRACTION, worst_k=1)
    opt, wf = plans["optimiser"], plans["worst_first"]
    assert opt["true_benefit"] == pytest.approx(160.0)
    assert wf["true_benefit"] == pytest.approx(90.0)
    assert opt["worst_repaired"] == 0 and wf["worst_repaired"] == 1
    assert opt["worst_deferred"] == [0]
    assert wf["worst_deferred"] == []


def test_both_plans_respect_the_budget():
    plans = two_plans(KNAPSACK_TRAP, BUDGET_FRACTION, worst_k=1)
    for name in ("optimiser", "worst_first"):
        assert plans[name]["cost"] <= plans["budget"] + 1e-9, name


def test_share_of_oracle_is_measured_against_the_truth():
    """The oracle optimises the truth; here observed equals truth, so the
    optimiser matches it exactly and worst-first falls short."""
    plans = two_plans(KNAPSACK_TRAP, BUDGET_FRACTION, worst_k=1)
    assert plans["optimiser"]["share_of_oracle"] == pytest.approx(1.0)
    assert plans["worst_first"]["share_of_oracle"] == pytest.approx(90.0 / 160.0)


def test_plans_rank_on_observed_condition_not_on_the_truth():
    """A survey sees observed condition. If observation hides the failed road,
    worst-first cannot target it either — the plans must not peek at the truth."""
    hidden = network([(10.0, 95.0, 400.0)] + [(60.0, 60.0, 100.0)] * 4)
    plans = two_plans(hidden, BUDGET_FRACTION, worst_k=1)
    assert plans["worst_first"]["worst_repaired"] == 0


# --- the rendered page ----------------------------------------------------------

from certain_road.dashboard.render import build_page  # noqa: E402

STAMP = {"utc": "2026-09-29 00:00 UTC", "commit": "abc1234"}


def test_a_results_tree_with_nothing_in_it_renders_every_section_as_not_run(tmp_path):
    page = build_page(tmp_path, STAMP, worst_k=20)
    for section in ('id="map"', 'id="models"', 'id="simulation"', 'id="conformal"', 'id="drift"'):
        assert section in page, section
    assert page.count("Not run.") >= 6
    assert "results/T12/demo_network.json" in page
    assert "Potholes come from Model P and cracks from Model B (D082)" in page


def test_the_allocation_view_shows_both_plans_and_says_whose_recall_it_used(tmp_path):
    demo = tmp_path / "results/T12/demo_network.json"
    demo.parent.mkdir(parents=True)
    net = network([(10.0, 10.0, 400.0)] + [(60.0, 60.0, 100.0)] * 4)
    net |= {
        "seed": 0,
        "alpha": 0.5,
        "tau": 0.117,
        "recall": {"linear_crack": 0.36, "alligator_crack": 0.64, "pothole": 0.53},
    }
    demo.write_text(json.dumps(net))
    page = build_page(tmp_path, STAMP, worst_k=1)
    assert "Optimiser" in page and "Worst-first" in page
    assert 'id="opt-worst"' in page and 'id="wf-worst"' in page
    assert (
        "potholes included &mdash; at Model B&#x27;s recall" in page
        or "potholes included &mdash; at Model B's recall" in page
    )
    assert "P's recall is not used here" in page or "P&#x27;s recall is not used here" in page
    data = json.loads(
        page.split('<script id="plan-data" type="application/json">')[1]
        .split("</script>")[0]
        .replace("<\\/", "</")
    )
    at50 = data["positions"]["observed_pci"]["50"]
    assert at50["optimiser"]["worst"] == 0 and at50["worst_first"]["worst"] == 1


def test_no_absolute_local_path_reaches_the_shared_file(tmp_path):
    """The page is meant to be passed around; "not run" notes must not leak a home directory."""
    page = build_page(tmp_path, STAMP, worst_k=20)
    assert str(tmp_path) not in page
    assert "results/T14" in page  # the path is still named, just relatively


def test_figure_alt_text_states_the_drift_results_from_the_data(tmp_path):
    """Hand-written alt text once overstated T11. It must come from drift.json."""
    t11 = tmp_path / "results/T11"
    t11.mkdir(parents=True)
    for png in ("martingale_traces.png", "delay_hist.png"):
        (t11 / png).write_bytes(b"\x89PNG\r\n")
    shift = {
        "detected": 197,
        "alarmed_in_null_prefix": 3,
        "never_alarmed": 0,
        "delay_frames": {"median": 77.0, "p90": 121.2},
    }
    (t11 / "drift.json").write_text(
        json.dumps(
            {
                "n_streams": 200,
                "plain": {
                    "statistic": "plain",
                    "alarm_threshold": 100,
                    "null_false_alarm_rate": 0.005,
                    "shift": {
                        "detected": 6,
                        "alarmed_in_null_prefix": 1,
                        "never_alarmed": 193,
                        "delay_frames": {"median": 1248.5},
                    },
                },
                "cusum": {
                    "statistic": "cusum",
                    "alarm_threshold": 10000,
                    "null_false_alarm_rate": 0.005,
                    "shift": shift,
                },
            }
        )
    )
    page = build_page(tmp_path, STAMP, worst_k=20)
    assert "the plain martingale alarms in 6 of 200 streams" in page
    assert "197 of 200 streams alarm after India begins, median 77 India frames" in page
    assert "3 alarm inside the non-India prefix" in page
    assert "every shifted stream" not in page and "cannot recover" not in page
