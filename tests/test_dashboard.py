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
