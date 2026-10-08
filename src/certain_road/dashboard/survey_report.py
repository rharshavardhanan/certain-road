"""The survey report: several surveyed roads, given a remaining life, pooled into one repair plan.

One self-contained offline HTML file (D020): every image inlined, no script or style from
anywhere else, light only like the T16 dashboard (D083). It reads the survey's artifacts;
it detects, scores and renders nothing itself.

**Why it exists.** The end screen of one MuJoCo drive answers "how did the survey do on this
road". A road agency's question is wider: across every road surveyed, which segment gets the
money first, and why. This page pools the segments of several roads under one budget and runs
the real allocators on them (`survey.allocation`), with both of D079's objectives side by
side, because the optimiser and worst-first disagree in a way neither one shows alone.

What it shows, per road and per segment:

- the **vision-estimated PCI**, its band, and the **reference PCI** where a simulation knows
  the truth, labelled as simulation-only;
- the **RSL** from `survey.rsl` (or the band recommendation in `mode: pci_only`), with an
  interval only when the input carried one. No segment-PCI interval exists yet (the segment
  conformal stage is designed, not built), and none is invented here;
- **every confirmed detection** with its frame, box, model (D082), confidence and place on
  the road, and whether the ground truth agrees;
- **detection against the ground truth**: recall and false alarms per km per class.

**What it is not.** Not a field result: on a simulated road every number is a measurement of
the real pipeline on a synthetic surface (D087), and the page says so in its first line. The
RSL is the cited curve's answer for a pavement at that index, not a forecast (survey/rsl.py).
Costs are D079's arbitrary units priced on the reference distressed area, as the end screen
prices them (D090), which only a simulation knows.
"""

from __future__ import annotations

import base64
import html
import io
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from certain_road.survey.allocation import (
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
    total_cost,
)
from certain_road.survey.rsl import RslConfig, assess, rsl_years, service_life_years
from certain_road.survey.scoring import band

CAPTION = "A simulated road scored by the real pipeline: a demonstration, not a field result"
ATTRIBUTION = (
    "Potholes come from Model P and cracks from Model B (D082); their pothole outputs are "
    "never summed."
)
CLASSES = ("pothole", "alligator_crack", "linear_crack")
CLASS_NAMES = {
    "pothole": "pothole",
    "alligator_crack": "alligator crack",
    "linear_crack": "linear crack",
}
MODEL_OF = {"pothole": "P", "alligator_crack": "B", "linear_crack": "B"}
# Display scale for cost-effectiveness: D079 quotes benefit per 100k cost units.
VALUE_PER = 100_000


def esc(x) -> str:
    return html.escape(str(x))


@dataclass
class RoadRun:
    """One surveyed road, as read from its artifacts."""

    label: str
    preset: str
    seed: int
    look: str
    length_m: float
    run_dir: str  # relative to the repository, for the page
    segments: list[dict]
    detection: dict | None = None  # end.json "detection"; None when there is no ground truth
    drift_alarm_m: float | None = None
    gallery: dict | None = None
    images: dict[str, bytes] = field(default_factory=dict)  # gallery path -> JPEG bytes
    stills: dict[str, bytes] = field(default_factory=dict)  # "live" / "end" -> JPEG bytes
    recording: str | None = None
    timing: dict = field(default_factory=dict)
    simulated: bool = True


@dataclass(frozen=True)
class Pricing:
    """D079's repair cost, as the end screen applies it (D090)."""

    mobilisation_cost: float
    cost_per_m2: float
    budget_frac: float
    worst_share: float


# --- numbers -------------------------------------------------------------------------------


def segment_rows(roads: list[RoadRun], rsl_cfg: RslConfig, pricing: Pricing) -> list[dict]:
    """Every segment of every road, with its pooled id, cost and RSL assessment."""
    rows = []
    for r_i, road in enumerate(roads):
        for s in road.segments:
            pci = float(s["vision_estimated_pci"])
            a = assess(pci, rsl_cfg, pci_lo=s.get("pci_lo"), pci_hi=s.get("pci_hi"))
            ref = s.get("pci_ref")
            ref_rsl = (
                rsl_years(float(ref), rsl_cfg.curve)
                if ref is not None and rsl_cfg.curve is not None
                else None
            )
            area = float(s.get("area_ref_m2", 0.0))
            rows.append(
                {
                    "id": len(rows),
                    "road": road.label,
                    "road_index": r_i,
                    "segment": int(s["index"]),
                    "x0_m": float(s["x0_m"]),
                    "x1_m": float(s["x1_m"]),
                    "pci": pci,
                    "band": band(pci),
                    "pci_lo": s.get("pci_lo"),
                    "pci_hi": s.get("pci_hi"),
                    "pci_ref": None if ref is None else float(ref),
                    "band_ref": None if ref is None else band(float(ref)),
                    "counts": s.get("counts", {}),
                    "area_ref_m2": area,
                    "cost": pricing.mobilisation_cost + pricing.cost_per_m2 * area,
                    "rsl": a.rsl_years,
                    "rsl_lo": a.rsl_lo,
                    "rsl_hi": a.rsl_hi,
                    "rsl_ref": ref_rsl,
                    "must_fix": a.must_fix,
                    "recommendation": a.recommendation,
                }
            )
    return rows


def pooled_plan(rows: list[dict], pricing: Pricing) -> dict:
    """Both real allocators on every segment of every road, under one budget (D079, D090).

    Each plan is scored on D079's two objectives against the reference PCI: the true benefit
    repaired, and how many of the true worst N damaged segments it repairs (D091). The oracle
    is the optimiser on the reference PCI: the ceiling, not a plan anyone can run.
    """
    segs = [Segment(r["id"], r["pci"], r["cost"]) for r in rows]
    budget = pricing.budget_frac * sum(r["cost"] for r in rows)
    chosen = {
        "optimiser": allocate_optimal(segs, budget),
        "worst_first": allocate_greedy_worst_first(segs, budget),
    }
    have_truth = all(r["pci_ref"] is not None for r in rows)
    out: dict = {"budget": budget, "budget_frac": pricing.budget_frac, "plans": {}}
    worst: list[int] = []
    benefit: dict[int, float] = {}
    oracle_benefit = None
    if have_truth:
        benefit = {r["id"]: 100.0 - r["pci_ref"] for r in rows}
        damaged = sorted((r for r in rows if r["pci_ref"] < 100.0), key=lambda r: r["pci_ref"])
        n_worst = round(pricing.worst_share * len(rows)) if damaged else 0
        worst = [r["id"] for r in damaged][: max(1, n_worst) if damaged else 0]
        oracle = allocate_optimal([Segment(r["id"], r["pci_ref"], r["cost"]) for r in rows], budget)
        oracle_benefit = sum(benefit[i] for i in oracle)
        out["oracle"] = {"chosen": oracle, "true_benefit": oracle_benefit}
    out["worst"] = worst
    for name, ids in chosen.items():
        plan = {"chosen": ids, "cost": total_cost(segs, ids)}
        if have_truth:
            got = sum(benefit[i] for i in ids)
            plan |= {
                "true_benefit": got,
                "share_of_oracle": got / oracle_benefit if oracle_benefit else None,
                "worst_covered": sum(i in ids for i in worst),
            }
        out["plans"][name] = plan
    out["order"], out["why"] = explain(rows, segs, chosen, budget)
    return out


def explain(
    rows: list[dict], segs: list[Segment], chosen: dict[str, list[int]], budget: float
) -> tuple[list[int], dict[int, dict[str, str]]]:
    """Worst-first order, and one sentence per segment per plan saying why it was or was not funded.

    Worst-first's reasons come from replaying its own pass (same order, same rule); the replay
    must reproduce the real function's choice or this raises, so a sentence can never describe
    a plan other than the one shown. The optimiser chooses a set, not an order, so its sentences
    state what it weighed (priority per cost) and do not invent a ranking.
    """
    order = sorted(segs, key=lambda s: -s.priority)  # allocate_greedy_worst_first's order
    spent, replayed, why = 0.0, [], {}
    opt = set(chosen["optimiser"])
    ratios = {s.segment_id: s.priority / s.cost * VALUE_PER for s in segs}
    funded = [ratios[i] for i in opt if segs[i].priority > 0]
    span = f"{min(funded):.1f}&ndash;{max(funded):.1f}" if funded else "none"
    for rank, s in enumerate(order, start=1):
        left = budget - spent
        if s.cost <= left:
            spent += s.cost
            replayed.append(s.segment_id)
            if s.priority > 0:
                wf = f"#{rank} by vision-estimated PCI; costs {s.cost:,.0f} of {left:,.0f} left."
            else:
                wf = (
                    "Nothing detected (priority 0), funded with money left over: "
                    "allocate_greedy_worst_first spends what remains (D091)."
                )
        else:
            wf = f"#{rank} by vision-estimated PCI; costs {s.cost:,.0f}, only {left:,.0f} left."
        if s.priority <= 0:
            op = "Nothing detected: priority 0 adds nothing to the optimiser's objective."
        elif s.segment_id in opt:
            op = (
                f"In the exact optimiser's best set: {ratios[s.segment_id]:.1f} priority points "
                f"per {VALUE_PER:,} cost units."
            )
        else:
            op = (
                f"Left out of the best set: {ratios[s.segment_id]:.1f} points per "
                f"{VALUE_PER:,}; the funded segments run {span}."
            )
        why[s.segment_id] = {"worst_first": wf, "optimiser": op}
    if sorted(replayed) != sorted(chosen["worst_first"]):
        raise AssertionError("worst-first replay disagrees with allocate_greedy_worst_first")
    return [s.segment_id for s in order], why


def detection_totals(roads: list[RoadRun]) -> dict:
    """Recall and false alarms per km over every road with ground truth, per class."""
    out = {}
    km = sum(r.detection["km"] for r in roads if r.detection)
    for c in CLASSES:
        n = sum(r.detection["per_class"][c]["instances"] for r in roads if r.detection)
        h = sum(r.detection["per_class"][c]["hit"] for r in roads if r.detection)
        fa = sum(r.detection["per_class"][c]["false_alarm_tracks"] for r in roads if r.detection)
        out[c] = {
            "instances": n,
            "hit": h,
            "recall": h / n if n else None,
            "false_alarm_tracks": fa,
            "false_alarms_per_km": fa / km if km else None,
        }
    return {"km": km, "per_class": out}


# --- html pieces ---------------------------------------------------------------------------


def jpeg_uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def num(x, digits: int = 1, none: str = "&ndash;") -> str:
    return none if x is None else f"{x:.{digits}f}"


def band_chip(name: str | None, colours: dict) -> str:
    if name is None:
        return "&ndash;"
    return (
        f'<span class="chip"><span class="sw" style="background:{esc(colours["band"][name])}">'
        f"</span>{esc(name)}</span>"
    )


def rsl_cell(r: dict, cfg: RslConfig) -> str:
    if cfg.mode == "pci_only":
        return esc(r["recommendation"] or "no recommendation for this band")
    point = f"{r['rsl']:.1f} yr"
    if r["rsl"] == 0.0:
        point = '0 yr <span class="muted">(at or past end of life)</span>'
    if r["rsl_lo"] is not None:
        point += f' <span class="muted">[{r["rsl_lo"]:.1f}, {r["rsl_hi"]:.1f}]</span>'
    return point


def plan_marks(seg_id: int, plan: dict) -> str:
    marks = []
    for name, cls, label in (
        ("optimiser", "m-opt", "Optimiser"),
        ("worst_first", "m-wf", "Worst-first"),
    ):
        if seg_id in plan["plans"][name]["chosen"]:
            marks.append(f'<span class="mark {cls}" title="{label} funds it">{label}</span>')
    return " ".join(marks) or '<span class="muted">neither</span>'


def chart(road: RoadRun, rows: list[dict], cfg: dict) -> str:
    """Vision-estimated against reference PCI, per segment along the road. Native tooltips."""
    c, col = cfg["chart"], cfg["colours"]["series"]
    w, h = c["width_px"], c["height_px"]
    left, right, top, bottom = (c["margin_px"][k] for k in ("left", "right", "top", "bottom"))
    dot, gap, nudge = c["marker_r_px"], c["label_gap_px"], c["label_nudge_px"]
    mine = [r for r in rows if r["road"] == road.label]
    values = [r["pci"] for r in mine] + [r["pci_ref"] for r in mine if r["pci_ref"] is not None]
    lo = min([c["pci_floor"], *[10 * (v // 10) for v in values]])
    length = max(r["x1_m"] for r in mine) if mine else 1.0

    def x(m):
        return left + (w - left - right) * m / length

    def y(v):
        return top + (h - top - bottom) * (100 - v) / (100 - lo)

    parts = [
        f'<svg class="pci-chart" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Vision-estimated and reference PCI per segment along {esc(road.label)}">'
    ]
    for v in range(int(lo), 101, 10):
        parts.append(
            f'<line class="grid" x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
            f'<text class="tick" x="{left - gap}" y="{y(v) + nudge:.1f}" '
            f'text-anchor="end">{v}</text>'
        )
    step = c["tick_every_m"]
    for m in range(0, int(length) + 1, step):
        parts.append(
            f'<text class="tick" x="{x(m):.1f}" y="{h - c["x_label_from_bottom_px"]}" '
            f'text-anchor="middle">{m} m</text>'
        )
    for r in mine:
        cx = x((r["x0_m"] + r["x1_m"]) / 2)
        tip = (
            f"Segment {r['segment']} ({r['x0_m']:.0f}-{r['x1_m']:.0f} m): "
            f"vision-estimated PCI {r['pci']:.1f}"
        )
        if r["pci_ref"] is not None:
            tip += f", reference PCI {r['pci_ref']:.1f}"
            parts.append(
                f'<line class="gap" x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(r["pci"]):.1f}" '
                f'y2="{y(r["pci_ref"]):.1f}"/>'
                f'<circle class="ref" cx="{cx:.1f}" cy="{y(r["pci_ref"]):.1f}" r="{dot}" '
                f'stroke="{esc(col["reference"])}"><title>{esc(tip)}</title></circle>'
            )
        parts.append(
            f'<circle class="est" cx="{cx:.1f}" cy="{y(r["pci"]):.1f}" r="{dot}" '
            f'fill="{esc(col["vision"])}"><title>{esc(tip)}</title></circle>'
        )
    parts.append("</svg>")
    legend = (
        f'<div class="legend"><span><span class="dot" style="background:{esc(col["vision"])}">'
        f"</span>vision-estimated PCI</span>"
        + (
            f'<span><span class="ring" style="border-color:{esc(col["reference"])}"></span>'
            "reference PCI (simulation only)</span>"
            if any(r["pci_ref"] is not None for r in mine)
            else ""
        )
        + "</div>"
    )
    return f'<figure class="chart">{legend}{"".join(parts)}</figure>'


def segment_table(road: RoadRun, rows: list[dict], plan: dict, rsl_cfg: RslConfig, cfg) -> str:
    colours = cfg["colours"]
    mine = [r for r in rows if r["road"] == road.label]
    life = "Recommendation (band)" if rsl_cfg.mode == "pci_only" else "RSL"
    has_ref = any(r["pci_ref"] is not None for r in mine)
    head = ["Segment", "Along the road", "Vision-estimated PCI", "Band", life]
    if has_ref:
        head += ["Reference PCI <span class='sim'>sim</span>", "Reference band"]
        if rsl_cfg.mode == "curve":
            head.append("RSL at reference <span class='sim'>sim</span>")
    head += ["Counted (P &middot; A &middot; L)", "Funded by"]
    body = []
    for r in mine:
        interval = (
            f' <span class="muted">[{r["pci_lo"]:.1f}, {r["pci_hi"]:.1f}]</span>'
            if r["pci_lo"] is not None
            else ""
        )
        n = r["counts"]
        cells = [
            f"{r['segment']}",
            f"{r['x0_m']:.0f}&ndash;{r['x1_m']:.0f} m",
            f"<strong>{r['pci']:.1f}</strong>{interval}",
            band_chip(r["band"], colours),
            rsl_cell(r, rsl_cfg),
        ]
        if has_ref:
            cells += [num(r["pci_ref"]), band_chip(r["band_ref"], colours)]
            if rsl_cfg.mode == "curve":
                cells.append(num(r["rsl_ref"]) + " yr" if r["rsl_ref"] is not None else "&ndash;")
        cells += [
            f"{n.get('pothole', 0)} &middot; {n.get('alligator_crack', 0)} &middot; "
            f"{n.get('linear_crack', 0)}",
            plan_marks(r["id"], plan),
        ]
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    th = "".join(f'<th scope="col">{h}</th>' for h in head)
    return (
        f'<div class="table-wrap"><table class="segs"><thead><tr>{th}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def detection_table(det: dict, *, caption: str) -> str:
    rows = []
    for c in CLASSES:
        d = det["per_class"][c]
        rec = "no instance" if d["recall"] is None else f"{d['recall'] * 100:.0f}%"
        fa = d["false_alarms_per_km"]
        rows.append(
            f"<tr><th scope='row'>{esc(CLASS_NAMES[c])} <span class='muted'>(Model "
            f"{MODEL_OF[c]})</span></th><td class='num'>{d['hit']} of {d['instances']}</td>"
            f"<td class='num'>{rec}</td><td class='num'>{d['false_alarm_tracks']}</td>"
            f"<td class='num'>{num(fa)}</td></tr>"
        )
    return (
        f"<div class='table-wrap'><table class='det'><caption>{caption}</caption><thead><tr>"
        "<th scope='col'>Class</th><th scope='col' class='num'>Found</th>"
        "<th scope='col' class='num'>Recall</th><th scope='col' class='num'>False-alarm tracks"
        "</th><th scope='col' class='num'>False alarms per km</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def gallery_section(road: RoadRun, cfg: dict) -> str:
    g = road.gallery
    if not g:
        return (
            '<div class="not-run"><strong>No gallery.</strong> This run has no gallery.json '
            "(python -m sim.mujoco.gallery).</div>"
        )
    colours = cfg["colours"]["class"]
    tracks = sorted(
        g["tracks"],
        key=lambda t: (t["location"] or {}).get("chainage_m", t["first_x_cam_m"]),
    )
    cards = []
    for t in tracks:
        loc = t["location"]
        crop = road.images.get(t.get("crop", ""))
        frame = road.images.get(t.get("frame", "")) if cfg["embed"]["full_frames"] else None
        if t["false_alarm"]:
            near = (loc or {}).get("nearest_instance")
            truth = '<span class="fa">False alarm</span>'
            if near:
                truth += (
                    f" &middot; nearest ground truth: {esc(CLASS_NAMES[near['cls']])} "
                    f"#{near['id']}, {near['distance_m']:.1f} m away"
                )
        else:
            ids = ", ".join(f"#{i}" for i in t["hit_ids"])
            err = (loc or {}).get("error_to_match_m")
            truth = f'<span class="ok">Matches</span> {esc(CLASS_NAMES[t["cls"]])} {ids}'
            if err is not None:
                truth += f" &middot; IPM point {err:.1f} m from its footprint"
        where = "IPM gave no ground point"
        if loc:
            seg = (
                "outside the scored segments"
                if loc["segment"] is None
                else f"segment {loc['segment']}"
            )
            side = "left" if loc["lateral_m"] >= 0 else "right"
            where = (
                f"<strong>{loc['chainage_m']:.1f} m</strong> along the road &middot; "
                f"{abs(loc['lateral_m']):.1f} m {side} of the centre line &middot; "
                f"{esc(loc['lane'])} &middot; {seg}"
            )
        img = (
            f'<img src="{jpeg_uri(crop)}" alt="{esc(CLASS_NAMES[t["cls"]])}, Model {t["model"]}, '
            f'confidence {t["best"]["score"]:.2f}" loading="lazy">'
            if crop
            else '<div class="noimg">no image</div>'
        )
        whole = (
            f'<details><summary>Whole frame</summary><img src="{jpeg_uri(frame)}" alt="Whole '
            f'camera frame at {t["best"]["x_cam_m"]:.1f} m" loading="lazy"></details>'
            if frame
            else ""
        )
        survey = (
            "counted in a 5 m survey sample"
            if t["counted_in_survey"]
            else "not in a survey sample's ROI"
        )
        cards.append(
            f'<article class="card" data-cls="{esc(t["cls"])}" '
            f'data-truth="{"fa" if t["false_alarm"] else "hit"}">{img}'
            f'<div class="card-body"><p class="what"><span class="sw" style="background:'
            f'{esc(colours[t["cls"]])}"></span>{esc(CLASS_NAMES[t["cls"]])} '
            f'<span class="muted">Model {t["model"]} &middot; confidence {t["best"]["score"]:.2f}'
            f"</span></p><p>{where}</p><p>{truth}</p>"
            f'<p class="muted small">Track {t["track"]}, confirmed in {t["confirmed_frames"]} '
            f"frames; picture from frame {t['best']['frame']}, camera at "
            f"{t['best']['x_cam_m']:.1f} m; {survey}.</p>{whole}</div></article>"
        )
    return f'<div class="gallery">{"".join(cards)}</div>'


def replay_note(road: RoadRun) -> str:
    g = road.gallery or {}
    checks = (g.get("replay") or {}).get("verification") or []
    if not checks:
        return "Re-render not verified on this road."
    same = all(c["same_boxes"] for c in checks)
    px = max((c["max_px_diff"] or 0.0) for c in checks)
    return f"Re-render checked on {len(checks)} survey samples: " + (
        f"re-detection gave the logged boxes (largest difference {px:.2f} px)."
        if same
        else "re-detection did not reproduce the logged boxes; treat the pictures as "
        "re-rendered views, not the exact frames."
    )


def road_summary(road: RoadRun, rows: list[dict]) -> dict:
    mine = [r for r in rows if r["road"] == road.label]
    est = [r["pci"] for r in mine]
    ref = [r["pci_ref"] for r in mine if r["pci_ref"] is not None]
    weight = [r["x1_m"] - r["x0_m"] for r in mine]
    mean = sum(p * w for p, w in zip(est, weight, strict=True)) / sum(weight) if mine else None
    mean_ref = (
        sum(p * w for p, w in zip(ref, weight, strict=True)) / sum(weight)
        if ref and len(ref) == len(mine)
        else None
    )
    tracks = (road.gallery or {}).get("tracks", [])
    return {
        "segments": len(mine),
        "mean_pci": mean,
        "mean_pci_ref": mean_ref,
        "worst_pci": min(est) if est else None,
        "worst_band": band(min(est)) if est else None,
        "mae": statistics.mean(abs(r["pci"] - r["pci_ref"]) for r in mine) if ref else None,
        "tracks": len(tracks),
        "false_alarm_tracks": sum(t["false_alarm"] for t in tracks),
    }


# --- page ----------------------------------------------------------------------------------


def build_report(
    roads: list[RoadRun], rsl_cfg: RslConfig, pricing: Pricing, cfg: dict, stamp: dict
) -> tuple[str, dict]:
    """The page and the numbers behind it (written beside it as report.json)."""
    rows = segment_rows(roads, rsl_cfg, pricing)
    plan = pooled_plan(rows, pricing)
    totals = detection_totals(roads)
    summaries = {r.label: road_summary(r, rows) for r in roads}
    simulated = any(r.simulated for r in roads)
    data = {
        "stamp": stamp,
        "caption": CAPTION if simulated else None,
        "rsl": {
            "mode": rsl_cfg.mode,
            "status": rsl_cfg.status,
            "source": rsl_cfg.source,
            "curve": None if rsl_cfg.curve is None else rsl_cfg.curve.__dict__,
            "service_life_years": (
                None if rsl_cfg.curve is None else service_life_years(rsl_cfg.curve)
            ),
        },
        "pricing": pricing.__dict__,
        "roads": [
            {
                "label": r.label,
                "preset": r.preset,
                "seed": r.seed,
                "look": r.look,
                "length_m": r.length_m,
                "run_dir": r.run_dir,
                "recording": r.recording,
                "drift_alarm_m": r.drift_alarm_m,
                "detection": r.detection,
                "summary": summaries[r.label],
                "timing": r.timing,
                "replay": (r.gallery or {}).get("replay"),
            }
            for r in roads
        ],
        "segments": rows,
        "plan": {k: v for k, v in plan.items() if k != "why"},
        "detection_total": totals,
    }
    page = render_page(roads, rows, plan, totals, summaries, rsl_cfg, pricing, cfg, stamp)
    return page, data


def render_page(roads, rows, plan, totals, summaries, rsl_cfg, pricing, cfg, stamp) -> str:
    simulated = any(r.simulated for r in roads)
    by_id = {r["id"]: r for r in rows}
    nav = "".join(f'<a href="#road-{i}">{esc(r.label)}</a>' for i, r in enumerate(roads))
    banner = (
        f'<p class="banner" role="note"><strong>{esc(CAPTION)}.</strong> The roads, their damage '
        "and the camera are simulated; the detectors, the survey scoring, the RSL stage and the "
        "allocators are the project's real code and models.</p>"
        if simulated
        else ""
    )
    # summary cards
    cards = []
    for i, r in enumerate(roads):
        s = summaries[r.label]
        det = r.detection["per_class"] if r.detection else None
        ref = (
            f"<span class='muted'>reference {s['mean_pci_ref']:.1f}</span>"
            if s["mean_pci_ref"] is not None
            else ""
        )
        found = ""
        if det:
            found = "".join(
                f"<li>{esc(CLASS_NAMES[c])}: {det[c]['hit']} of {det[c]['instances']} found, "
                f"{num(det[c]['false_alarms_per_km'])} false alarms/km</li>"
                for c in CLASSES
            )
        cards.append(
            f'<a class="road-card" href="#road-{i}"><h3>{esc(r.label)}</h3>'
            f"<p class='big'>{num(s['mean_pci'])} <span class='unit'>mean vision-estimated "
            f"PCI</span></p><p>{ref}</p>"
            f"<p>{r.length_m:.0f} m &middot; {s['segments']} segments &middot; worst "
            f"{band_chip(s['worst_band'], cfg['colours'])} ({num(s['worst_pci'])})</p>"
            f"<ul class='plain'>{found}</ul></a>"
        )
    # pooled plan
    p = plan["plans"]
    worst = plan["worst"]
    have_truth = bool(worst) or "oracle" in plan

    def objective_cells(name):
        q = p[name]
        if not have_truth:
            return "<td class='num'>&ndash;</td><td class='num'>&ndash;</td>"
        share = q.get("share_of_oracle")
        return (
            f"<td class='num'><strong>{q['worst_covered']} of {len(worst)}</strong></td>"
            f"<td class='num'><strong>{q['true_benefit']:.1f}</strong>"
            + (f" <span class='muted'>({share * 100:.0f}% of oracle)</span>" if share else "")
            + "</td>"
        )

    def listing(ids):
        return (
            ", ".join(f"{esc(by_id[i]['road'])} seg {by_id[i]['segment']}" for i in sorted(ids))
            or "none"
        )

    both = set(p["optimiser"]["chosen"]) & set(p["worst_first"]["chosen"])
    only_opt = set(p["optimiser"]["chosen"]) - both
    only_wf = set(p["worst_first"]["chosen"]) - both
    first = next((by_id[i] for i in plan["order"] if i in set(p["worst_first"]["chosen"])), None)
    headline = ""
    if first is not None:
        agree = "Both plans fund it." if first["id"] in both else "Only worst-first funds it."
        headline = (
            f"<p class='verdict'>Repair first: <strong>{esc(first['road'])}, segment "
            f"{first['segment']}</strong> ({first['x0_m']:.0f}&ndash;{first['x1_m']:.0f} m), "
            f"vision-estimated PCI {first['pci']:.1f} ({esc(first['band'])}), the worst of all "
            f"{len(rows)} segments surveyed. {agree}</p>"
        )
    compare = (
        "<div class='table-wrap'><table class='compare'><thead><tr><th scope='col'>Plan</th>"
        "<th scope='col' class='num'>Segments</th><th scope='col' class='num'>Spend</th>"
        f"<th scope='col' class='num'>True worst {len(worst)} repaired <span class='sim'>sim"
        "</span></th><th scope='col' class='num'>True benefit repaired <span class='sim'>sim"
        "</span></th></tr></thead><tbody>"
        + "".join(
            f"<tr><th scope='row'><span class='sw' style='background:"
            f"{esc(cfg['colours']['series'][k])}'></span>{label} <span class='how'>{how}</span>"
            f"</th><td class='num'>{len(p[k]['chosen'])}</td>"
            f"<td class='num'>{p[k]['cost']:,.0f}</td>{objective_cells(k)}</tr>"
            for k, label, how in (
                ("optimiser", "Optimiser", "maximises total priority within the budget"),
                ("worst_first", "Worst-first", "repairs the worst segment that still fits"),
            )
        )
        + "</tbody></table></div>"
    )
    ranked = []
    for n, i in enumerate(plan["order"], start=1):
        r = by_id[i]
        w = plan["why"][i]
        flag = (
            ' <span class="flag" title="D019: worst-case RSL below the must-fix threshold">'
            "must-fix</span>"
            if r["must_fix"]
            else ""
        )
        ref = num(r["pci_ref"])
        worst_tag = ' <span class="sim">true worst</span>' if i in worst else ""
        ranked.append(
            f"<tr><td class='num'>{n}</td><th scope='row'>{esc(r['road'])} &middot; seg "
            f"{r['segment']}<span class='muted small'> {r['x0_m']:.0f}&ndash;{r['x1_m']:.0f} m"
            f"</span>{worst_tag}</th><td class='num'><strong>{r['pci']:.1f}</strong></td>"
            f"<td>{band_chip(r['band'], cfg['colours'])}</td><td class='num'>{ref}</td>"
            f"<td>{rsl_cell(r, rsl_cfg)}{flag}</td><td class='num'>{r['cost']:,.0f}</td>"
            f"<td>{plan_marks(i, plan)}</td><td class='why'><p><span class='mark m-wf'>"
            f"Worst-first</span> {w['worst_first']}</p><p><span class='mark m-opt'>Optimiser"
            f"</span> {w['optimiser']}</p></td></tr>"
        )
    life_head = "Recommendation" if rsl_cfg.mode == "pci_only" else "RSL"
    priority = f"""
<section id="priority">
<h2>Repair priority across all {len(roads)} roads</h2>
<p class="lede">All {len(rows)} segments pooled under one budget: {pricing.budget_frac * 100:.0f}%
of the cost of repairing every one ({plan["budget"]:,.0f} cost units). Both plans are the real
allocators of <code>certain_road.survey.allocation</code>, ranking on the vision-estimated PCI
(priority = 100 &minus; vision-estimated PCI). Each is scored on D079's two objectives against
the reference PCI: how many of the true worst {len(worst)} damaged segments it repairs, and
the true benefit (100 &minus; reference PCI) it repairs. Neither objective is simply right:
the optimiser buys the most improvement per unit cost and can defer the worst road; worst-first
repairs the worst road first and buys less overall (D079).</p>
{headline}
{compare}
<p class="note">Funded by both: {listing(both)}. Only the optimiser: {listing(only_opt)}. Only
worst-first: {listing(only_wf)}.</p>
<h3>Every segment, worst vision-estimated PCI first</h3>
<p class="lede">Worst-first's own order. Its sentences replay its pass (the replay is checked
against the real function); the optimiser chooses a set, not an order, so its sentences say what
it weighed. Cost is D079's (arbitrary units): mobilisation {pricing.mobilisation_cost:,.0f} plus
{pricing.cost_per_m2:,.0f} per m&sup2; of reference distressed area, as the end screen prices it
(D090); only a simulation knows that area.</p>
<div class="table-wrap"><table class="ranked"><thead><tr><th scope="col" class="num">#</th>
<th scope="col">Road &middot; segment</th><th scope="col" class="num">Vision-estimated PCI</th>
<th scope="col">Band</th><th scope="col" class="num">Reference <span class="sim">sim</span></th>
<th scope="col">{life_head}</th><th scope="col" class="num">Cost</th><th scope="col">Funded by
</th><th scope="col">Why</th></tr></thead><tbody>{"".join(ranked)}</tbody></table></div>
</section>"""
    # roads
    road_html = []
    for i, r in enumerate(roads):
        stills = "".join(
            f'<figure class="still"><img src="{jpeg_uri(r.stills[k])}" alt="{esc(alt)}" '
            f'loading="lazy"><figcaption>{esc(cap)}</figcaption></figure>'
            for k, alt, cap in (
                (
                    "live",
                    f"Live survey screen at the end of the {r.label} drive",
                    "The live screen at the end of the drive.",
                ),
                (
                    "end",
                    f"End screen of the {r.label} drive",
                    "The run's own end screen: its per-road plans at the end screen's budget.",
                ),
            )
            if r.stills.get(k)
        )
        det = (
            detection_table(
                r.detection,
                caption="Confirmed tracks against the ground truth, both lanes (D090).",
            )
            if r.detection
            else ""
        )
        timing = r.timing
        facts = [f"Run: <code>{esc(r.run_dir)}</code>"]
        if r.recording:
            facts.append(f"Recording: <code>{esc(r.recording)}</code>")
        if timing.get("drive_wall_s") is not None:
            facts.append(
                f"Drive: {timing['frames']:,} frames in {timing['drive_wall_s']:.0f} s "
                f"({timing.get('realtime_x', 0):.2f}&times; real time)"
            )
        if r.drift_alarm_m is not None:
            facts.append(f"Drift alarm at {r.drift_alarm_m:.0f} m (D089: fires on clean road)")
        elif r.detection:
            facts.append("No drift alarm")
        road_html.append(
            f"""<section id="road-{i}" class="road">
<h2>{esc(r.label)}</h2>
<p class="lede">{r.length_m:.0f} m, look {esc(r.look)}. {" &middot; ".join(facts)}.</p>
{chart(r, rows, cfg)}
{segment_table(r, rows, plan, rsl_cfg, cfg)}
<p class="note">Counted: boxes whose base fell in a 5 m sample's ROI, the driving lane 3&ndash;8 m
ahead (D006, D089): potholes (P), alligator (A) and linear (L) cracks. The reference PCI is the
ground truth projected and scored by the same code (simulation only).</p>
{det}
<div class="stills">{stills}</div>
<h3>Every confirmed detection on this road</h3>
<p class="lede">One card per confirmed track (D075), in order along the road. {esc(replay_note(r))}
Location: the IPM ground point under each box's bottom centre (<code>core.geometry.ground_point
</code>, design camera, flat road), median over the track's confirmed frames: the near edge of the
damage as the camera saw it.</p>
{gallery_section(r, cfg)}
</section>"""
        )
    # rsl method
    if rsl_cfg.mode == "curve":
        cv = rsl_cfg.curve
        method = (
            f"<p>Mode <code>curve</code>: the deterioration curve <strong>PCI = {cv.pci_new:g} "
            f"&minus; {cv.slope:g} &middot; age<sup>{cv.exponent:g}</sup></strong>, age in "
            f"{esc(cv.age_unit)} ({esc(cv.name)}), inverted: a segment's vision-estimated PCI "
            f"gives an equivalent age, and its RSL is the time left until the curve reaches its "
            f"end of service life, PCI {cv.pci_terminal:g} on the source's scale. A new pavement "
            f"has {service_life_years(cv):.1f} years; at or below PCI {cv.pci_terminal:g} the "
            "RSL is 0. RSL rises with PCI, so an interval maps through its ends unchanged.</p>"
        )
    else:
        method = (
            "<p>Mode <code>pci_only</code>: no deterioration curve. Each segment gets the "
            f"recommendation for its band. Band table source: {esc(rsl_cfg.treatments_source)}</p>"
        )
    rsl_section = f"""
<section id="rsl">
<h2>Remaining service life: the source, and its limits</h2>
<p class="status"><strong>Status: {esc(rsl_cfg.status or "unstated")}.</strong> The design
leaves the choice of curve, or <code>mode: pci_only</code>, to the mentor (D018);
<code>configs/rsl/published_default.yaml</code> switches it in one line.</p>
{method}
<p class="cite"><strong>Source.</strong> {esc(rsl_cfg.source)}</p>
<ul>
<li><strong>Not fitted to this quantity.</strong> The curve was fitted to PAVER PCI on US Army
installation roads; the input here is a vision-estimated PCI, a proxy that follows a condition
index's structure without D6433's deduct curves (<code>survey/scoring.py</code>). Nothing has
measured whether the two scales agree.</li>
<li><strong>Not calibrated for India,</strong> its traffic or its climate. An Indian PCI&ndash;age
model was preferred and none could be verified (the search is recorded in the config).</li>
<li><strong>No interval yet.</strong> The RSL interval needs a vision-estimated PCI interval;
the segment-level conformal stage that would supply it is designed, not built. Every RSL
here is a point, and the code refuses to invent an interval.</li>
<li><strong>Must-fix</strong> marks a segment whose worst-case RSL is below
{rsl_cfg.must_fix_rsl_years:g} year (D019). The allocators above do not apply that constraint;
the flag is shown for reading, not used.</li>
</ul>
</section>"""
    totals_html = (
        detection_table(
            totals,
            caption=f"All {sum(1 for r in roads if r.detection)} roads with ground truth together, "
            f"{totals['km']:.2f} km driven.",
        )
        if any(r.detection for r in roads)
        else ""
    )
    method_section = f"""
<section id="method">
<h2>How these numbers were made</h2>
<ul>
<li><strong>Real:</strong> Model P (potholes) and Model B (cracks), never summed (D082);
ByteTrack and D075's 3-of-5 confirmation; <code>core.geometry</code>'s IPM;
<code>certain_road.survey</code> scoring, segments, RSL and allocation.</li>
<li><strong>Simulated:</strong> the road, its damage, light and camera motion (D087, D092).
The ground truth is exact because the road was generated.</li>
<li><strong>Detection scoring</strong> (D090): a confirmed track hits an instance when its box
overlaps the instance's projected box by IoU above 0.1 in some frame and the classes agree;
recall counts instances that came nearer than the 12 m gate; a false alarm is a confirmed track
that hit nothing of its class, per km driven. Both lanes count.</li>
<li><strong>Pictures</strong> are re-rendered from each run's log at the logged camera position
with the drive's camera settings and its per-frame noise stream replayed, then checked by
re-detecting survey samples (see each road).</li>
</ul>
{totals_html}
</section>"""
    credits = (
        "Textures CC BY 4.0: QR4Change, Maske et al. 2025 (potholes); BD-N6, Hossain et al. "
        "(cracks, asphalt). docs/texture-provenance.md."
        if simulated
        else ""
    )
    page = TEMPLATE.format(
        title=esc(cfg.get("title", "Survey of three simulated roads")),
        nav=nav,
        banner=banner,
        attribution=esc(ATTRIBUTION),
        cards="".join(cards),
        priority=priority,
        roads="".join(road_html),
        rsl=rsl_section,
        method=method_section,
        credits=esc(credits),
        stamp=esc(f"Built {stamp.get('utc', '')} from commit {stamp.get('commit', '')}."),
        css=CSS,
        js=JS,
    )
    return page


def downscale_jpeg(data: bytes, width: int, quality: int) -> bytes:
    """A still for the page: never wider than `width`, re-encoded as JPEG."""
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def write(page: str, data: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path, json_path = out_dir / "report.html", out_dir / "report.json"
    html_path.write_text(page)
    json_path.write_text(json.dumps(data, indent=1, default=str))
    return html_path, json_path


CSS = Path(__file__).with_name("survey_report.css").read_text()

JS = """
(function () {
  var state = { cls: 'all', truth: 'all' };
  function apply() {
    document.querySelectorAll('.card').forEach(function (c) {
      var ok = (state.cls === 'all' || c.dataset.cls === state.cls) &&
               (state.truth === 'all' || c.dataset.truth === state.truth);
      c.hidden = !ok;
    });
  }
  document.querySelectorAll('.filters button').forEach(function (b) {
    b.addEventListener('click', function () {
      var key = b.dataset.key;
      state[key] = b.dataset.value;
      document.querySelectorAll('.filters button[data-key="' + key + '"]').forEach(function (o) {
        o.setAttribute('aria-pressed', o === b ? 'true' : 'false');
      });
      apply();
    });
  });
})();
"""

FILTERS = (
    '<div class="filters" role="group" aria-label="Filter the detection cards">'
    '<span class="muted">Show</span>'
    '<button data-key="cls" data-value="all" aria-pressed="true">all classes</button>'
    '<button data-key="cls" data-value="pothole" aria-pressed="false">potholes</button>'
    '<button data-key="cls" data-value="alligator_crack" aria-pressed="false">alligator</button>'
    '<button data-key="cls" data-value="linear_crack" aria-pressed="false">linear</button>'
    '<span class="muted">&middot;</span>'
    '<button data-key="truth" data-value="all" aria-pressed="true">all</button>'
    '<button data-key="truth" data-value="hit" aria-pressed="false">matched</button>'
    '<button data-key="truth" data-value="fa" aria-pressed="false">false alarms</button></div>'
)

TEMPLATE = (
    """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{title}</title><style>{css}</style></head>
<body>
<div class="bar"><div class="bar-in"><span class="brand">certain-road survey</span>
<nav><a href="#priority">Repair priority</a>{nav}<a href="#rsl">RSL source</a>
<a href="#method">Method</a></nav></div></div>
<main>
<h1>{title}</h1>
{banner}
<p class="lede">{attribution}</p>
<div class="road-cards">{cards}</div>
{priority}
"""
    + FILTERS.replace("{", "{{").replace("}", "}}")
    + """
{roads}
{rsl}
{method}
</main>
<footer><p>{credits}</p><p>{stamp}</p></footer>
<script>{js}</script>
</body></html>
"""
)
