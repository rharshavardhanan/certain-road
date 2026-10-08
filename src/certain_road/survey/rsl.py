"""PCI -> RSL: remaining service life from a published deterioration curve (design.md §3).

**Why it exists.** A repair list ranked on condition alone cannot say how long a segment has
left. The design inverts a deterioration curve: a curve gives condition as a function of
age, so a surveyed condition gives an equivalent age, and the distance from that age to the
curve's end of service life is the remaining service life:

    age_now  = ((pci_new - PCI)          / slope) ** (1 / exponent)
    age_term = ((pci_new - pci_terminal) / slope) ** (1 / exponent)
    RSL      = max(0, age_term - age_now)

which is the inverse of the published form `PCI = pci_new - slope * age ** exponent`.

**The refusal (D018).** The design wrote that form without a citation. Coefficients without a
source are an invented number dressed as engineering, so `load_config` refuses any config
whose `source:` is empty, in either mode. The shipped config cites Sharaf et al. (1987) and is
marked pending the mentor's approval.

**Intervals map through exactly.** RSL is non-decreasing in PCI (a better road has at least
as much life left), so an interval `[pci_lo, pci_hi]` maps to `[rsl(pci_lo), rsl(pci_hi)]`
with no recalibration: a monotone transform of a valid interval is a valid interval
(design.md §3). The clamp at zero keeps that true below the terminal value.

**`mode: pci_only`** is the design's alternative: no curve, a recommendation from the
condition band alone. It is a config switch, not a code path anyone has to remember.

**What it is not.** The curve was fitted to PAVER PCI on US Army installation roads; the
input here is a vision-estimated PCI, which only follows a condition index's structure
(survey/scoring.py). The output is the life the cited curve gives a pavement at that index,
an indication for ranking. It is not a forecast for a real road, and it is not calibrated for
India.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from certain_road.survey.scoring import band

MODES = ("curve", "pci_only")
# Unit conversion, not a tunable: how many of a curve's age units make one year.
AGE_UNITS_PER_YEAR = {"months": 12.0, "years": 1.0}
PCI_SCALE = (0.0, 100.0)


class SourceMissing(ValueError):
    """The RSL config names no source. The stage does not run on uncited coefficients."""


@dataclass(frozen=True)
class Curve:
    """`PCI = pci_new - slope * age ** exponent`, ending service at `pci_terminal`."""

    name: str
    pci_new: float
    slope: float
    exponent: float
    age_unit: str
    pci_terminal: float

    def __post_init__(self) -> None:
        if self.slope <= 0 or self.exponent <= 0:
            raise ValueError(f"curve {self.name!r}: slope and exponent must be positive")
        if self.age_unit not in AGE_UNITS_PER_YEAR:
            raise ValueError(f"curve {self.name!r}: unknown age unit {self.age_unit!r}")
        if not PCI_SCALE[0] <= self.pci_terminal < self.pci_new <= PCI_SCALE[1]:
            raise ValueError(f"curve {self.name!r}: need 0 <= pci_terminal < pci_new <= 100")


@dataclass(frozen=True)
class RslConfig:
    mode: str
    source: str
    status: str
    curve: Curve | None
    must_fix_rsl_years: float
    treatments: dict[str, str] = field(default_factory=dict)
    treatments_source: str = ""


@dataclass(frozen=True)
class Assessment:
    """One segment's RSL (mode `curve`) or band recommendation (mode `pci_only`).

    `rsl_lo` and `rsl_hi` are set only when the input carried a PCI interval. A point
    estimate is never widened into an interval here: no interval in, no interval out.
    """

    mode: str
    condition_band: str
    rsl_years: float | None
    rsl_lo: float | None
    rsl_hi: float | None
    recommendation: str | None
    must_fix: bool | None  # D019: worst-case RSL below the threshold; None without an RSL


def _require(text: object, what: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise SourceMissing(
            f"RSL stage refuses to run: {what} is empty. Enter the published relationship's "
            "citation, or select mode: pci_only with its own source (design.md §3, D018)."
        )
    return text.strip()


def parse_config(raw: dict) -> RslConfig:
    """Validate a loaded RSL config. Refuses an empty `source:` before anything else."""
    source = _require(raw.get("source"), "source:")
    mode = raw.get("mode")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    curve = None
    treatments: dict[str, str] = {}
    treatments_source = ""
    if mode == "curve":
        c = raw.get("curve") or {}
        curve = Curve(
            name=str(c["name"]),
            pci_new=float(c["pci_new"]),
            slope=float(c["slope"]),
            exponent=float(c["exponent"]),
            age_unit=str(c["age_unit"]),
            pci_terminal=float(c["pci_terminal"]),
        )
    else:
        p = raw.get("pci_only") or {}
        treatments_source = _require(p.get("source"), "pci_only.source:")
        treatments = {str(k): str(v) for k, v in (p.get("treatments") or {}).items()}
        if not treatments:
            raise ValueError("mode pci_only needs a pci_only.treatments table")
    return RslConfig(
        mode=mode,
        source=source,
        status=str(raw.get("status", "")),
        curve=curve,
        must_fix_rsl_years=float(raw["must_fix_rsl_years"]),
        treatments=treatments,
        treatments_source=treatments_source,
    )


def load_config(path: Path) -> RslConfig:
    return parse_config(yaml.safe_load(Path(path).read_text()))


def _check_pci(pci: float) -> None:
    if not PCI_SCALE[0] <= pci <= PCI_SCALE[1]:  # also rejects NaN
        raise ValueError(f"PCI {pci} outside {PCI_SCALE}")


def equivalent_age(pci: float, curve: Curve) -> float:
    """The age, in the curve's own unit, at which the curve reaches `pci`.

    Above `pci_new` the curve has no age; a vision-estimated PCI can only reach 100, which
    is `pci_new` for every curve this module accepts, so that case is age zero.
    """
    _check_pci(pci)
    drop = max(0.0, curve.pci_new - pci)
    return (drop / curve.slope) ** (1.0 / curve.exponent)


def service_life_years(curve: Curve) -> float:
    """Age at the end of service, in years: the RSL of a new pavement."""
    return equivalent_age(curve.pci_terminal, curve) / AGE_UNITS_PER_YEAR[curve.age_unit]


def rsl_years(pci: float, curve: Curve) -> float:
    """Remaining service life, in years. Zero at or below the curve's terminal value."""
    per_year = AGE_UNITS_PER_YEAR[curve.age_unit]
    remaining = equivalent_age(curve.pci_terminal, curve) - equivalent_age(pci, curve)
    return max(0.0, remaining / per_year)


def rsl_interval(pci_lo: float, pci_hi: float, curve: Curve) -> tuple[float, float]:
    """`[pci_lo, pci_hi] -> [rsl(pci_lo), rsl(pci_hi)]`, valid because RSL is monotone."""
    if pci_lo > pci_hi:
        raise ValueError(f"interval reversed: [{pci_lo}, {pci_hi}]")
    return rsl_years(pci_lo, curve), rsl_years(pci_hi, curve)


def assess(
    pci: float,
    cfg: RslConfig,
    *,
    pci_lo: float | None = None,
    pci_hi: float | None = None,
) -> Assessment:
    """RSL (or the band recommendation) for one segment's vision-estimated PCI."""
    _check_pci(pci)
    has_interval = pci_lo is not None and pci_hi is not None
    if has_interval and not pci_lo <= pci <= pci_hi:
        raise ValueError(f"point {pci} outside its interval [{pci_lo}, {pci_hi}]")
    name = band(pci)
    if cfg.mode == "pci_only":
        return Assessment("pci_only", name, None, None, None, cfg.treatments.get(name), None)
    assert cfg.curve is not None  # parse_config guarantees it in mode curve
    point = rsl_years(pci, cfg.curve)
    lo = hi = None
    if has_interval:
        lo, hi = rsl_interval(pci_lo, pci_hi, cfg.curve)
    worst = point if lo is None else lo
    return Assessment("curve", name, point, lo, hi, None, worst < cfg.must_fix_rsl_years)
