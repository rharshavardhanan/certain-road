"""The offline dashboard (D020): one self-contained HTML file built from result files.

No server, no CDN, no external library — figures are embedded, the budget slider
selects among plans the real T12 optimiser computed at every budget step, and the
page works by double-click in a room with no network.

Three rules are enforced here rather than left to whoever edits the markup:

* **Both objectives, always (D079).** The allocation view never shows the
  optimiser's plan without the worst-first plan beside it, each with its
  true-worst-20 coverage and total benefit.
* **Attribution (D082).** Potholes come from Model P and cracks from Model B, and
  their pothole outputs are never summed. Numbers that came from T12's simulation
  say, where they appear, that it used Model B's recall for every class.
* **Not run is visible.** Every table and figure reads through `load_json` /
  `existing`; a missing input renders as "not run" and names the file.
"""

import base64
import html
import json
from pathlib import Path

from certain_road.dashboard.plans import two_plans
from certain_road.dashboard.results import NotRun, existing, load_json
from certain_road.survey.scoring import band

TEMPLATE = Path(__file__).with_name("template.html")
BUDGET_STEPS = [f / 100 for f in range(5, 61)]  # 5% .. 60% of total repair cost
CONDITIONS = {"observed_pci": "Observed condition", "robust_pci": "Conformal robust condition"}
ATTRIBUTION = (
    "Potholes come from Model P and cracks from Model B (D082). Their pothole "
    "outputs are never summed."
)


def esc(x) -> str:
    return html.escape(str(x))


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def not_run(nr: NotRun, what: str) -> str:
    return (
        f'<div class="not-run" role="note"><strong>Not run.</strong> {esc(what)} '
        f'<span class="src">Looked for <code>{esc(nr.path)}</code> ({esc(nr.reason)}).'
        f"</span></div>"
    )


def source(root: Path, path: Path) -> str:
    return f'<p class="src">Source: <code>{esc(path.relative_to(root))}</code></p>'


def table(head: list[str], rows: list[list[str]], *, numeric_from: int = 1) -> str:
    """Rows are pre-escaped HTML cells. Columns from `numeric_from` are right-aligned."""
    th = "".join(
        f'<th scope="col"{" class=num" if i >= numeric_from else ""}>{h}</th>'
        for i, h in enumerate(head)
    )
    body = "".join(
        "<tr>"
        + "".join(
            (
                f'<th scope="row">{c}</th>'
                if i == 0
                else f"<td{' class=num' if i >= numeric_from else ''}>{c}</td>"
            )
            for i, c in enumerate(r)
        )
        + "</tr>"
        for r in rows
    )
    return (
        f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


# --- allocation -------------------------------------------------------------


def precompute(net: dict, worst_k: int) -> dict:
    """Both plans at every budget step and condition, from the real optimiser."""
    positions: dict = {}
    for cond in CONDITIONS:
        positions[cond] = {}
        for f in BUDGET_STEPS:
            p = two_plans(net, f, condition=cond, worst_k=worst_k)
            positions[cond][str(round(f * 100))] = {
                "budget": round(p["budget"]),
                **{
                    k: {
                        "chosen": p[k]["chosen"],
                        "cost": round(p[k]["cost"]),
                        "benefit": round(p[k]["true_benefit"], 1),
                        "share": round(p[k]["share_of_oracle"], 4),
                        "worst": p[k]["worst_repaired"],
                    }
                    for k in ("optimiser", "worst_first")
                },
            }
    first = two_plans(net, BUDGET_STEPS[0], worst_k=worst_k)
    order = sorted(net["segments"], key=lambda s: s["true_pci"])
    return {
        "worst": first["worst"],
        "worst_k": first["worst_k"],
        "segments": [
            {
                "id": s["id"],
                "true": s["true_pci"],
                "obs": s["observed_pci"],
                "rob": s["robust_pci"],
                "cost": s["cost"],
                "band": band(s["true_pci"]),
            }
            for s in order
        ],
        "positions": positions,
    }


def allocation_section(root: Path, worst_k: int) -> tuple[str, str]:
    """Returns (section html, embedded plan data json)."""
    demo_path = root / "results/T12/demo_network.json"
    net = load_json(demo_path)
    if isinstance(net, NotRun):
        return (
            not_run(
                net,
                "The allocation view needs T12's demo network "
                "(scripts/exp_allocation.py --export-demo).",
            ),
            "null",
        )
    data = precompute(net, worst_k)
    r = net["recall"]
    provenance = (
        f'<p class="provenance">These plans come from T12\'s simulation, which detected '
        f"every class &mdash; <strong>potholes included &mdash; at Model B's recall</strong> "
        f"(certified &alpha; {esc(net['alpha'])} at threshold {esc(net['tau'])}: linear crack "
        f"{r['linear_crack']:.2f}, alligator {r['alligator_crack']:.2f}, pothole "
        f"{r['pothole']:.2f}). Under D082 a survey takes potholes from Model P; P's recall "
        f"is not used here. False alarms are not simulated. One synthetic network, seed "
        f"{esc(net['seed'])}, fixed in advance.</p>" + source(root, demo_path)
    )
    averages = allocation_averages(root)
    radios = "".join(
        f'<label class="seg-opt"><input type="radio" name="cond" value="{c}"'
        f"{' checked' if c == 'observed_pci' else ''}><span>{esc(label)}</span></label>"
        for c, label in CONDITIONS.items()
    )
    body = f"""
<div class="controls">
  <div class="slider">
    <label for="budget">Budget <output id="budget-out" for="budget">10%</output>
      <span class="muted">of total repair cost &middot; <span id="budget-abs"></span></span></label>
    <input type="range" id="budget" min="5" max="60" step="1" value="10">
  </div>
  <fieldset class="seg"><legend>Plans rank on</legend>{radios}</fieldset>
</div>
<p class="verdict" id="verdict" aria-live="polite"></p>
<div class="table-wrap compare-wrap">
<table class="compare">
  <caption>T12 simulation: every class, potholes included, detected at Model B's recall
    &mdash; not Model P's (D082). Full provenance below the strip.</caption>
  <thead><tr><th scope="col"><span class="sr">Measure</span></th>
    <th scope="col" class="num"><span class="swatch sw-opt"></span>Optimiser
      <span class="how">maximises total benefit</span></th>
    <th scope="col" class="num"><span class="swatch sw-wf"></span>Worst-first
      <span class="how">repairs the worst road that fits</span></th></tr></thead>
  <tbody>
    <tr class="key"><th scope="row">True worst {data["worst_k"]} repaired</th>
      <td class="num"><span id="opt-worst"></span></td>
      <td class="num"><span id="wf-worst"></span></td></tr>
    <tr class="key"><th scope="row">True benefit repaired, share of the oracle</th>
      <td class="num"><span id="opt-share"></span></td>
      <td class="num"><span id="wf-share"></span></td></tr>
    <tr><th scope="row">Segments repaired</th>
      <td class="num" id="opt-n"></td><td class="num" id="wf-n"></td></tr>
    <tr><th scope="row">Spend</th>
      <td class="num" id="opt-cost"></td><td class="num" id="wf-cost"></td></tr>
  </tbody>
</table>
</div>
<figure class="strip" aria-describedby="strip-cap">
  <div class="strip-zone" style="--k:{data["worst_k"]};--n:{len(data["segments"])}">
    <span>true worst {data["worst_k"]}</span></div>
  <div class="strip-row"><span class="strip-label">Optimiser</span>
    <svg id="strip-opt" class="cells" viewBox="0 0 1000 1" preserveAspectRatio="none"
      role="img" aria-label="Segments the optimiser repairs, worst on the left"></svg></div>
  <div class="strip-row"><span class="strip-label">Worst-first</span>
    <svg id="strip-wf" class="cells" viewBox="0 0 1000 1" preserveAspectRatio="none"
      role="img" aria-label="Segments worst-first repairs, worst on the left"></svg></div>
  <div class="strip-axis"><span>worst true condition</span><span>best</span></div>
  <figcaption id="strip-cap">{len(data["segments"])} evaluation segments ordered by <em>true</em>
    vision-estimated PCI. A filled mark is repaired, a pale one deferred. Plans rank on what a
    survey observes; the ordering here is the truth only a synthetic network has.</figcaption>
  <div id="tip" class="tip" hidden></div>
</figure>
{provenance}
<h3>The true worst {data["worst_k"]}, road by road</h3>
<p class="lede">Which of the worst roads each plan repairs at this budget. This table is the
chart above in words.</p>
<div class="table-wrap"><table id="worst-table">
  <thead><tr><th scope="col">Segment</th><th scope="col">Optimiser</th>
    <th scope="col">Worst-first</th><th scope="col" class="num">True PCI</th>
    <th scope="col" class="num">Observed PCI</th><th scope="col" class="num">Repair cost</th>
    </tr></thead>
  <tbody></tbody></table></div>
{averages}"""
    return body, json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def allocation_averages(root: Path) -> str:
    path = root / "results/T12/allocation.json"
    d = load_json(path)
    if isinstance(d, NotRun):
        return not_run(d, "T12's averages over 1,000 networks.")
    head = next(p for p in d["operating_points"] if p["role"] == "headline")
    names = {
        "oracle": "Oracle (the truth; not runnable)",
        "nominal": "Optimiser, observed",
        "robust": "Optimiser, conformal robust",
        "greedy": "Worst-first",
        "random": "Random",
    }
    fracs = sorted({r["budget_fraction"] for r in d["rows"]})
    rows = []
    for pol, label in names.items():
        cells = [label]
        for f in fracs:
            r = next(
                x
                for x in d["rows"]
                if x["regime"] == "uniform_traffic"
                and x["alpha"] == head["alpha"]
                and x["budget_fraction"] == f
                and x["policy"] == pol
            )
            cells.append(
                f'{pct(r["benefit_vs_oracle"], 0)} <span class="muted">&middot;</span> '
                f"{pct(r['mean_worst20_share'], 0)}"
            )
        rows.append(cells)
    return (
        f"<h3>Averaged over {d['generator']['n_trials']:,} networks</h3>"
        f'<p class="lede">Each cell: share of oracle benefit &middot; share of the true '
        f"worst 20 repaired. Uniform traffic, certified &alpha; {head['alpha']}. The same "
        f"simulation as above &mdash; <strong>Model B's recall for every class, "
        f"potholes included</strong>; not Model P's (D082).</p>"
        + table(["Policy"] + [f"{round(f * 100)}% budget" for f in fracs], rows)
        + source(root, path)
        + '<p class="lede after-src">The same averages drawn against budget, '
        "for both traffic regimes. "
        "In this figure <em>nominal</em> is the optimiser on observed condition, <em>robust</em> "
        "the optimiser on conformal robust condition, and <em>greedy</em> is worst-first.</p>"
        + figure(
            root,
            "results/T12/allocation.png",
            "Policies against budget, certified alpha 0.50.",
            alt="Repair allocation at certified alpha 0.5: share of oracle benefit and share "
            "of the true worst 20 repaired, by policy and budget, for uniform and varying "
            "traffic.",
        )
    )


# --- models -----------------------------------------------------------------


def detector_section(root: Path) -> str:
    out = []
    p = root / "results/LOCKED/A_india_full.json"
    d = load_json(p)
    out.append("<h3>Model A on India, locked (T6)</h3>")
    if isinstance(d, NotRun):
        out.append(not_run(d, "Model A's locked India evaluation."))
    else:
        pc = d["pycocotools_metrics"]
        rows = [
            [esc(c), f"{v['ap50']:.4f}", f"{v['instances']:,}"] for c, v in pc["per_class"].items()
        ]
        rows.append(
            [
                "<strong>mAP50</strong>",
                f"<strong>{pc['map50']:.4f}</strong>",
                f"{d['images']:,} images",
            ]
        )
        out += [table(["Class", "AP50", "Instances"], rows), source(root, p)]

    p = root / "results/T7/A_vs_B_india_test.json"
    d = load_json(p)
    out.append("<h3>Model A vs Model B on india_test (T7)</h3>")
    if isinstance(d, NotRun):
        out.append(not_run(d, "The A vs B comparison."))
    else:
        rows = [
            [esc(c), f"{d['A']['per_class_ap50'][c]:.4f}", f"{d['B']['per_class_ap50'][c]:.4f}"]
            for c in d["A"]["per_class_ap50"]
        ]
        rows.append(
            [
                "<strong>mAP50</strong>",
                f"<strong>{d['A']['map50']:.4f}</strong>",
                f"<strong>{d['B']['map50']:.4f}</strong>",
            ]
        )
        out += [table(["Class", "A", "B"], rows), source(root, p)]

    out.append(
        "<h3>Model B vs Model P on potholes (T9)</h3>"
        '<p class="lede"><code>india_val</code> chose P (D074); locked '
        "<code>india_test</code> is the unbiased check, where the two are "
        "indistinguishable. " + esc(ATTRIBUTION) + "</p>"
    )
    pv, pt = (
        root / "results/T9/B_vs_P_india_val.json",
        root / "results/T9/B_vs_P_india_test_LOCKED.json",
    )
    dv, dt = load_json(pv), load_json(pt)
    if isinstance(dt, NotRun):
        out.append(not_run(dt, "The locked B vs P comparison."))
    else:
        rows = []
        for m in ("B", "P"):
            val = "not run" if isinstance(dv, NotRun) else f"{dv['models'][m]['pothole_ap50']:.4f}"
            t = dt["models"][m]
            rows.append(
                [
                    f"Model {m}",
                    val,
                    f"{t['pothole_ap50']:.4f}",
                    f"{t['at_conf_0.25']['recall']:.4f}",
                    f"{t['at_conf_0.25']['false_alarms_per_image']:.4f}",
                ]
            )
        ci = dt["bootstrap_P_minus_B"]["pothole_ap50"]["ci95"]
        out += [
            table(
                [
                    "",
                    "AP50, india_val",
                    "AP50, india_test",
                    "Recall @0.25",
                    "False alarms/img @0.25",
                ],
                rows,
            ),
            f'<p class="note">P &minus; B pothole AP50 on india_test, 95% CI over '
            f"{dt['bootstrap_units']['count']:,} scene groups: [{ci[0]:+.4f}, {ci[1]:+.4f}].</p>",
            source(root, pv),
            source(root, pt),
        ]
    return "\n".join(out)


def conformal_section(root: Path) -> str:
    p = root / "results/T10/conformal.json"
    d = load_json(p)
    if isinstance(d, NotRun):
        return not_run(d, "T10 conformal risk control.")
    out = [
        '<p class="lede">T10 certifies each model\'s pothole miss rate separately. Under '
        "D082 the survey's potholes come from Model P, so P's rows are the operative "
        "certificate; B's are shown because T12 ran on B. The certificate controls misses, "
        "not false alarms.</p>"
    ]
    means = {
        c: {r["alpha"]: r for r in d["resampling"]["cases"][c]} for c in d["resampling"]["cases"]
    }
    for case, label in (
        ("P_india_cal_to_test", "Model P, calibrated on india_cal"),
        ("B_india_cal_to_test", "Model B, calibrated on india_cal"),
        ("A_nonindia_to_test", "Model A, calibrated on non-India (the shift)"),
    ):
        rows = []
        for r in d["cases"][case]["table"]:
            m = means[case].get(r["alpha"], {})
            if not r["feasible"]:
                rows.append([f"{r['alpha']:.2f}", "infeasible", "&ndash;", "&ndash;", "&ndash;"])
                continue
            rows.append(
                [
                    f"{r['alpha']:.2f}",
                    f"{r['tau']:.3f}",
                    f"{r['test_risk']:.4f}",
                    f"{m['mean_test_risk']:.4f}" if m.get("feasible_draws") else "&ndash;",
                    f"{r['false_alarms_per_image']:.2f}",
                ]
            )
        out += [
            f"<h3>{esc(label)}</h3>",
            table(
                [
                    "Certified &alpha;",
                    "Threshold",
                    "Miss rate, india_test",
                    f"Mean over {d['n_resamples']} re-partitions",
                    "False alarms/img",
                ],
                rows,
            ),
        ]
    out.append(source(root, p))
    return "\n".join(out)


def drift_section(root: Path) -> str:
    p = root / "results/T11/drift.json"
    d = load_json(p)
    if isinstance(d, NotRun):
        return not_run(d, "T11 drift alarm.")
    rows = []
    for k in ("plain", "cusum"):
        r, s = d[k], d[k]["shift"]
        f = s["delay_frames"]
        rows.append(
            [
                esc(r["statistic"]),
                f"{r['alarm_threshold']:g}",
                f"{r['null_false_alarm_rate']:.3f}",
                f"{s['detected']}/{d['n_streams']}",
                f"{f['median']:g}" if f else "&ndash;",
            ]
        )
    return (
        '<p class="lede">Model A\'s frame scores: 500 non-India frames, then India. '
        "Both statistics at the same null false-alarm rate.</p>"
        + table(
            [
                "Statistic",
                "Threshold",
                "Null false alarms",
                "Shift detected",
                "Median delay, frames",
            ],
            rows,
        )
        + source(root, p)
    )


def drift_alts(root: Path) -> tuple[str, str]:
    """Alt text for the two T11 figures, stated from drift.json so it cannot go stale.

    Hand-written alt text once claimed every CUSUM stream alarmed "within a few hundred
    India frames" — which counted three streams that alarmed before India began — and
    that the plain martingale "cannot recover", against its 6 of 200 detections.
    """
    d = load_json(root / "results/T11/drift.json")
    if isinstance(d, NotRun):
        return (
            "Martingale traces for both drift statistics.",
            "Detection delay with the CUSUM reset.",
        )
    n, pl, cu = d["n_streams"], d["plain"]["shift"], d["cusum"]["shift"]
    traces = (
        f"After the shift to India, the plain martingale alarms in {pl['detected']} of "
        f"{n} streams; with the CUSUM reset, {cu['detected']} of {n}."
    )
    f = cu["delay_frames"]
    delay = (
        f"With the CUSUM reset, {cu['detected']} of {n} streams alarm after India begins"
        + (f", median {f['median']:g} India frames" if f else "")
        + f"; {cu['alarmed_in_null_prefix']} alarm inside the non-India prefix and "
        f"{cu['never_alarmed']} never alarm."
    )
    return traces, delay


def figure(root: Path, rel: str, caption: str, *, alt: str) -> str:
    f = existing(root / rel)
    if isinstance(f, NotRun):
        return not_run(f, caption)
    b64 = base64.b64encode(f.read_bytes()).decode()
    return (
        f'<figure class="fig"><img src="data:image/png;base64,{b64}" alt="{esc(alt)}" '
        f'loading="lazy"><figcaption>{esc(caption)} <code>{esc(rel)}</code></figcaption></figure>'
    )


# --- page -------------------------------------------------------------------


def build_page(root: Path, stamp: dict, *, worst_k: int) -> str:
    alloc, plan_json = allocation_section(root, worst_k)
    t14 = root / "results/T14"
    edge_dbs = sorted(t14.glob("*.sqlite")) + sorted(t14.glob("*.db")) if t14.exists() else []
    map_html = (
        not_run(
            NotRun(t14, "no edge survey database"),
            "The map draws detections and segments from T14's edge database. "
            "T14 has not produced one, so there is nothing real to map.",
        )
        if not edge_dbs
        else f"<p>Edge databases found: {', '.join(esc(p.name) for p in edge_dbs)}.</p>"
    )
    sim = existing(root / "results/T13")
    sim_html = (
        not_run(sim, "T13's detect-and-avoid simulation has no results.")
        if isinstance(sim, NotRun)
        else "<p>T13 results present.</p>"
    )
    models = "\n".join(
        [
            detector_section(root),
            '<h2 id="conformal">Conformal risk control (T10)</h2>',
            conformal_section(root),
            figure(
                root,
                "results/T10/risk_vs_alpha.png",
                "Miss rate against certified alpha.",
                alt="Calibrated in India the bound holds; calibrated elsewhere it breaks.",
            ),
            figure(
                root,
                "results/T10/false_alarms_vs_alpha.png",
                "False alarms per image at the certified threshold.",
                alt="The certificate controls misses, not false alarms.",
            ),
            figure(
                root,
                "results/T10/resampled_risk_hist.png",
                "Re-partitioned miss rates at alpha 0.20.",
                alt="Across re-partitions, India calibration centres on alpha; "
                "non-India calibration never comes close.",
            ),
            '<h2 id="drift">Drift alarm (T11)</h2>',
            drift_section(root),
            figure(
                root,
                "results/T11/martingale_traces.png",
                "Martingale traces, both statistics.",
                alt=drift_alts(root)[0],
            ),
            figure(
                root,
                "results/T11/delay_hist.png",
                "Detection delay with the CUSUM reset.",
                alt=drift_alts(root)[1],
            ),
        ]
    )
    page = TEMPLATE.read_text()
    for key, value in {
        "@@ALLOCATION@@": alloc,
        "@@PLAN_DATA@@": plan_json,
        "@@MAP@@": map_html,
        "@@MODELS@@": models,
        "@@SIMULATION@@": sim_html,
        "@@ATTRIBUTION@@": esc(ATTRIBUTION),
        "@@STAMP@@": esc(f"Built {stamp['utc']} from commit {stamp['commit']}."),
    }.items():
        page = page.replace(key, value)
    # Paths print relative to the repository. An absolute path would put the author's
    # home directory into a file meant to be shared, and means nothing on another machine.
    for prefix in (esc(str(root)) + "/", str(root) + "/"):
        page = page.replace(prefix, "")
    return page
