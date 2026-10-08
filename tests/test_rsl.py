"""The RSL stage: refusal without a source, the cited curve's arithmetic, and monotone intervals.

The transcription test is the important one. It checks the shipped config's coefficients
against the numbers Sharaf et al. (1987) derive from them in their own text, so a mistyped
slope fails here rather than in a mentor's reading of the report.
"""

import copy

import pytest
import yaml

from certain_road.core.paths import repo_root
from certain_road.survey import rsl

CONFIG = repo_root() / "configs/rsl/published_default.yaml"
RAW = yaml.safe_load(CONFIG.read_text())


def raw(**over) -> dict:
    out = copy.deepcopy(RAW)
    out.update(over)
    return out


@pytest.mark.parametrize("source", ["", "   ", None])
def test_refuses_to_run_without_a_source(source):
    with pytest.raises(rsl.SourceMissing, match="refuses to run"):
        rsl.parse_config(raw(source=source))


def test_refuses_a_missing_source_key():
    r = raw()
    del r["source"]
    with pytest.raises(rsl.SourceMissing):
        rsl.parse_config(r)


def test_pci_only_refuses_an_uncited_band_table():
    r = raw(mode="pci_only")
    r["pci_only"] = {**r["pci_only"], "source": ""}
    with pytest.raises(rsl.SourceMissing):
        rsl.parse_config(r)


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        rsl.parse_config(raw(mode="guess"))


def test_shipped_config_is_cited_and_pending_approval():
    cfg = rsl.load_config(CONFIG)
    assert "Transportation Research Record 1123" in cfg.source
    assert cfg.status == "pending mentor approval"
    assert cfg.mode == "curve"
    c = cfg.curve
    assert (c.slope, c.exponent, c.age_unit, c.pci_terminal) == (0.0104, 1.5, "months", 70.0)


def test_table5_transcription_reproduces_the_papers_own_numbers():
    """p. 36: 96 months, then 13, 15 and 17 yr to PCI 70; PCI 93 at 36 and 75 at 85 months."""
    slopes = RAW["table5_slopes"]
    life = {}
    for name, slope in slopes.items():
        curve = rsl.Curve(name, 100.0, slope, 1.5, "months", 70.0)
        life[name] = rsl.equivalent_age(70.0, curve)
    assert life["surface_treatment"] == pytest.approx(96.0, abs=0.5)
    assert round(life["thin_overlay"] / 12) == 13
    assert round(life["thick_overlay"] / 12) == 15
    assert round(life["reconstruction_new_asphalt"] / 12) == 17

    def pci_at(slope, months):
        return 100.0 - slope * months**1.5

    assert round(pci_at(slopes["surface_treatment"], 36)) == 93
    assert round(pci_at(slopes["surface_treatment"], 85)) == 75
    assert RAW["curve"]["slope"] == slopes["reconstruction_new_asphalt"]


def test_inverse_round_trips_the_published_form():
    curve = rsl.load_config(CONFIG).curve
    for months in (0.0, 12.0, 60.0, 150.0):
        pci = curve.pci_new - curve.slope * months**curve.exponent
        assert rsl.equivalent_age(pci, curve) == pytest.approx(months)


def test_rsl_of_a_new_pavement_is_its_service_life_and_zero_at_the_terminal():
    curve = rsl.load_config(CONFIG).curve
    assert rsl.rsl_years(100.0, curve) == pytest.approx(rsl.service_life_years(curve))
    assert rsl.service_life_years(curve) == pytest.approx(202.6 / 12, abs=0.01)
    assert rsl.rsl_years(70.0, curve) == 0.0
    assert rsl.rsl_years(40.0, curve) == 0.0  # past the end of service: clamped, not negative


def test_rsl_is_monotone_in_pci():
    curve = rsl.load_config(CONFIG).curve
    grid = [i / 4 for i in range(401)]
    values = [rsl.rsl_years(p, curve) for p in grid]
    assert all(a <= b for a, b in zip(values, values[1:], strict=False))


@pytest.mark.parametrize("lo,point,hi", [(60, 75, 90), (72, 80, 88), (90, 95, 100), (10, 20, 30)])
def test_interval_endpoints_map_through_and_contain_the_point(lo, point, hi):
    cfg = rsl.load_config(CONFIG)
    a = rsl.assess(point, cfg, pci_lo=lo, pci_hi=hi)
    assert (a.rsl_lo, a.rsl_hi) == rsl.rsl_interval(lo, hi, cfg.curve)
    assert a.rsl_lo == rsl.rsl_years(lo, cfg.curve)
    assert a.rsl_hi == rsl.rsl_years(hi, cfg.curve)
    assert a.rsl_lo <= a.rsl_years <= a.rsl_hi


def test_no_interval_in_means_no_interval_out():
    a = rsl.assess(80.0, rsl.load_config(CONFIG))
    assert a.rsl_years is not None
    assert a.rsl_lo is None and a.rsl_hi is None


def test_must_fix_uses_the_worst_case():
    cfg = rsl.load_config(CONFIG)
    assert rsl.assess(65.0, cfg).must_fix  # past PCI 70: no life left
    assert not rsl.assess(95.0, cfg).must_fix
    assert rsl.assess(95.0, cfg, pci_lo=60.0, pci_hi=99.0).must_fix  # the interval's low end


def test_reversed_or_inconsistent_intervals_are_rejected():
    cfg = rsl.load_config(CONFIG)
    with pytest.raises(ValueError):
        rsl.rsl_interval(80, 70, cfg.curve)
    with pytest.raises(ValueError):
        rsl.assess(50.0, cfg, pci_lo=60.0, pci_hi=70.0)


@pytest.mark.parametrize("bad", [-1.0, 100.5, float("nan")])
def test_pci_outside_the_scale_is_rejected(bad):
    with pytest.raises(ValueError):
        rsl.equivalent_age(bad, rsl.load_config(CONFIG).curve)


def test_pci_only_recommends_from_the_band_and_gives_no_rsl():
    cfg = rsl.parse_config(raw(mode="pci_only"))
    a = rsl.assess(60.0, cfg)
    assert a.mode == "pci_only" and a.condition_band == "Fair"
    assert a.recommendation == RAW["pci_only"]["treatments"]["Fair"]
    assert a.rsl_years is None and a.must_fix is None
    every_band = {rsl.assess(p, cfg).condition_band for p in range(0, 101)}
    assert every_band <= set(cfg.treatments)


def test_bad_curves_are_rejected():
    with pytest.raises(ValueError):
        rsl.Curve("x", 100.0, 0.0, 1.5, "months", 70.0)
    with pytest.raises(ValueError):
        rsl.Curve("x", 100.0, 0.01, 1.5, "fortnights", 70.0)
    with pytest.raises(ValueError):
        rsl.Curve("x", 100.0, 0.01, 1.5, "months", 100.0)
