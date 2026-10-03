"""T17 — generate results/RESULTS.md from the result files. Never hand-edit the output.

Every number in the report is read from a file at build time, and every table is
followed by the file(s) it came from. A missing input becomes a "not run" row,
never an omitted section, so "not run" can't be mistaken for "ran and found
nothing".

Nothing here types a number into prose. T16 learned why: two hand-written figure
descriptions overstated T11 against the file they described. The two facts that
live outside `results/` are read from their files too:

* whether D082 has been written yet, from `docs/DECISIONS.md`;
* who annotated the video ground truth, from the ground-truth CSV's own header.

Both statements therefore change by themselves when those files do.

Model attribution (D082, per the user): potholes come from Model P, cracks from
Model B, and their pothole outputs are never summed. Sections whose numbers came
from Model B's pothole channel say so where the numbers appear.
"""

import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.dashboard.results import NotRun, load_json  # noqa: E402

CITED = [
    "D020",
    "D063",
    "D064",
    "D065",
    "D066",
    "D070",
    "D073",
    "D074",
    "D075",
    "D076",
    "D077",
    "D078",
    "D079",
    "D080",
    "D081",
    "D082",
    "D083",
]
CLASSES = ["linear_crack", "alligator_crack", "pothole"]


class Report:
    def __init__(self, root: Path):
        self.root = root
        self.lines: list[str] = []

    def add(self, *lines: str) -> None:
        self.lines.extend(lines)

    def para(self, text: str) -> None:
        self.add(text, "")

    def load(self, rel: str):
        return load_json(self.root / rel)

    def table(self, head: list[str], rows: list[list], sources: list[str]) -> None:
        self.add(
            "| " + " | ".join(head) + " |",
            "|" + "|".join("---" for _ in head) + "|",
            *("| " + " | ".join(str(c) for c in r) + " |" for r in rows),
            "",
            "Source: " + ", ".join(f"`{s}`" for s in sources),
            "",
        )

    def not_run(self, what: str, missing: str) -> None:
        self.add(
            "| Result | Status |",
            "|---|---|",
            f"| {what} | not run |",
            "",
            f"Source: `{missing}` (missing)",
            "",
        )

    def need(self, what: str, *rels: str):
        """Load every input, or emit one not-run row naming the first missing one."""
        data = [self.load(r) for r in rels]
        for r, d in zip(rels, data, strict=True):
            if isinstance(d, NotRun):
                self.not_run(what, r)
                return None
        return data


def f4(x) -> str:
    return "–" if x is None else f"{x:.4f}"


def pct(x, digits: int = 1) -> str:
    return "–" if x is None else f"{x * 100:.{digits}f}%"


# --- sections ---------------------------------------------------------------


def data_audit(r: Report) -> None:
    r.add("## Data audit (T1/T2)", "")
    got = r.need("Raw dataset audit", "results/T1/raw_audit.json")
    if got:
        rows = [
            [
                c["country"],
                f"{c['images']:,}",
                f"{c['boxes_total']:,}",
                f"{c['raw_classes'].get('D40', 0):,}",
                c["parse_errors"],
                c["degenerate_boxes"] + c["out_of_bounds_boxes"],
            ]
            for c in got[0]["countries"]
        ]
        r.table(
            ["Country", "Images", "Boxes", "D40 (pothole) boxes", "Parse errors", "Bad boxes"],
            rows,
            ["results/T1/raw_audit.json"],
        )
    got = r.need("Split audit", "results/T2/split_audit.json")
    if got:
        rows = [
            [
                name,
                f"{s['images']:,}",
                f"{s['backgrounds']:,}",
                *(f"{s['instances'][c]:,}" for c in CLASSES),
            ]
            for name, s in got[0]["splits"].items()
        ]
        r.table(["Split", "Images", "Backgrounds", *CLASSES], rows, ["results/T2/split_audit.json"])
    got = r.need(
        "Exhaustive leak checks",
        "results/T2/exhaustive_leak.json",
        "results/T2/exhaustive_india_vs_nonindia_val.json",
        "results/T9/bharatpothole_overlap.json",
    )
    if got:
        leak, nv, bph = got
        t = leak["same_scene_corr"]
        rows = [
            [
                f"India x India (same scene, {t})",
                f"{leak['india_internal']['pairs']:,}",
                leak["india_internal"]["max_corr"],
                leak["india_internal"]["count_over_threshold"],
            ],
            [
                f"India x non-India train ({t})",
                f"{leak['india_vs_nonindia']['pairs']:,}",
                leak["india_vs_nonindia"]["max_corr"],
                leak["india_vs_nonindia"]["count_over_threshold"],
            ],
            [
                "India x non-India val (same-scene threshold; not recorded in this file)",
                f"{nv['pairs']:,}",
                nv["max_corr"],
                nv["count_over"],
            ],
        ]
        rows += [
            [
                f"BharatPotHole {k} x India held-out ({bph['threshold']})",
                f"{v['pairs']:,}",
                v["max_corr"],
                v["duplicate_count"],
            ]
            for k, v in bph["splits"].items()
        ]
        r.para(
            "Pairs over the same-scene threshold between India and non-India validation are "
            "same-scene look-alikes, not copies: cross-country checks test for copies at the "
            "stricter copy threshold (D066)."
        )
        r.table(
            ["Comparison (threshold)", "Pairs", "Max correlation", "Over threshold"],
            rows,
            [
                "results/T2/exhaustive_leak.json",
                "results/T2/exhaustive_india_vs_nonindia_val.json",
                "results/T9/bharatpothole_overlap.json",
            ],
        )


def model_a(r: Report) -> None:
    r.add("## Model A: non-India validation against India (T6)", "")
    srcs = ["results/T6_A_nonindia_val/metrics.json", "results/LOCKED/A_india_full.json"]
    got = r.need("Model A per-class AP50", *srcs)
    if got:
        non, ind = (g["pycocotools_metrics"] for g in got)
        rows = [
            [
                c,
                f4(non["per_class"][c]["ap50"]),
                f4(ind["per_class"][c]["ap50"]),
                f4(non["per_class"][c]["ap50"] - ind["per_class"][c]["ap50"]),
            ]
            for c in CLASSES
        ]
        rows.append(
            ["**mAP50**", f4(non["map50"]), f4(ind["map50"]), f4(non["map50"] - ind["map50"])]
        )
        r.table(["Class", "AP50 non-India val", "AP50 India (locked)", "Gap"], rows, srcs)
    got = r.need("Model A recall at the report threshold", "results/T6/localisation.json")
    if got:
        loc = got[0]
        rows = []
        for name in ("nonindia_val", "india_full"):
            rec = loc[name]["recall"]["conf_0.25"]
            rows += [
                [name, c, pct(rec[c]["iou_0.5"]), pct(rec[c]["centre"]), f"{rec[c]['total']:,}"]
                for c in CLASSES
            ]
        r.table(
            ["Set", "Class", "Recall @IoU 0.5", "Recall, centre inside box", "GT boxes"],
            rows,
            ["results/T6/localisation.json"],
        )


def a_vs_b(r: Report) -> None:
    r.add("## Model A vs Model B on india_test (T7)", "")
    got = r.need("A vs B on india_test", "results/T7/A_vs_B_india_test.json")
    if got:
        d = got[0]
        rows = [
            [c, f4(d["A"]["per_class_ap50"][c]), f4(d["B"]["per_class_ap50"][c])] for c in CLASSES
        ]
        rows.append(["**mAP50**", f4(d["A"]["map50"]), f4(d["B"]["map50"])])
        for m in ("precision", "recall"):
            rows.append(
                [
                    f"{m} @conf {d['eval_settings']['report_conf']}",
                    f4(d["A"]["pr_at_report_conf"][m]),
                    f4(d["B"]["pr_at_report_conf"][m]),
                ]
            )
        r.table(["Class", "Model A", "Model B"], rows, ["results/T7/A_vs_B_india_test.json"])


def external(r: Report) -> None:
    r.add("## External data: BharatPotHole and Model P (T9), Chennai (T15)", "")
    got = r.need("BharatPotHole internal leakage", "results/T9/bph_internal_leakage.json")
    if got:
        d = got[0]
        rows = [
            [
                e["split"],
                e["videos"],
                e["shared_video_ids"],
                f"{e['frames_from_shared_videos']:,} of {e['frames']:,}",
                pct(e["share_of_frames_from_shared_videos"]),
            ]
            for e in d["eval_splits"]
        ]
        rows.append(
            [
                "all splits",
                d["distinct_videos_all_splits"],
                "–",
                f"{d['frames_all_splits']:,} frames",
                f"{d['frames_per_video']} frames/video",
            ]
        )
        r.table(
            ["BPH split", "Videos", "Also in BPH train", "Frames from shared videos", "Share"],
            rows,
            ["results/T9/bph_internal_leakage.json"],
        )
    srcs = ["results/T9/B_vs_P_india_val.json", "results/T9/B_vs_P_india_test_LOCKED.json"]
    got = r.need("Model B vs Model P on potholes", *srcs)
    if got:
        val, test = got
        rows = []
        for m in ("B", "P"):
            t = test["models"][m]
            rows.append(
                [
                    f"Model {m}",
                    f4(val["models"][m]["pothole_ap50"]),
                    f4(t["pothole_ap50"]),
                    f4(t["pothole_ap50_95"]),
                    f4(t["at_conf_0.25"]["recall"]),
                    f4(t["at_conf_0.25"]["false_alarms_per_image"]),
                ]
            )
        def ci(d: dict) -> str:
            lo, hi = d["bootstrap_P_minus_B"]["pothole_ap50"]["ci95"]
            return f"[{lo:+.4f}, {hi:+.4f}] ({d['bootstrap_units']['count']:,} groups)"

        rows.append(["P − B AP50, 95% CI over scene groups", ci(val), ci(test), "", "", ""])
        r.para(
            "Pothole-only ground truth, one scorer. `india_val` is the selection set (D074); "
            "locked `india_test` is the unbiased check."
        )
        r.table(
            [
                "",
                "AP50 india_val",
                "AP50 india_test",
                "AP50-95 india_test",
                "Recall @0.25",
                "False alarms/img @0.25",
            ],
            rows,
            srcs,
        )
    got = r.need("Model P locked held-out evaluation", "results/LOCKED/P_india_heldout.json")
    if got:
        d = got[0]
        pc = d["pycocotools_metrics"]["per_class"]["pothole"]
        r.table(
            ["Model", "Set", "Images", "Pothole AP50", "Pothole instances", "Cross-check delta"],
            [
                [
                    "P",
                    d["set"],
                    f"{d['images']:,}",
                    f4(pc["ap50"]),
                    f"{pc['instances']:,}",
                    d["cross_check"]["map50_abs_delta"],
                ]
            ],
            ["results/LOCKED/P_india_heldout.json"],
        )
    r.not_run("Chennai test set (T15)", "results/T15")


def conformal(r: Report) -> None:
    r.add("## Conformal risk control (T10)", "")
    got = r.need("Miss-rate floors", "results/T10/feasibility.json")
    if got:
        d = got[0]
        rows = [
            [
                k,
                v["images_with_pothole"],
                f4(v["miss_rate_floor"]),
                f4(v["min_certifiable_alpha"]),
                v.get("feasible_from_alpha", "–"),
            ]
            for k, v in d["sources"].items()
        ]
        r.table(
            [
                "Model · set",
                "Images with a pothole",
                "Miss-rate floor",
                "Min certifiable α",
                "Feasible from α",
            ],
            rows,
            ["results/T10/feasibility.json"],
        )
    got = r.need("Certified thresholds", "results/T10/conformal.json")
    if not got:
        return
    d = got[0]
    r.para(
        f"Image-level pothole miss rate at IoU {d['iou']}; mean over {d['n_resamples']} "
        f"re-partitions by {d['resampling_unit']}. Under D082 the survey's potholes come from "
        "Model P, so P's rows are the operative certificate; Model B's are shown because T12 "
        "ran on B. The certificate controls misses, not false alarms."
    )
    means = {c: {x["alpha"]: x for x in rows} for c, rows in d["resampling"]["cases"].items()}
    for case, label in (
        ("P_india_cal_to_test", "Model P, calibrated on india_cal"),
        ("B_india_cal_to_test", "Model B, calibrated on india_cal"),
        ("A_india_cal_to_test", "Model A, calibrated on india_cal"),
        ("A_nonindia_to_test", "Model A, calibrated on non-India (the shift)"),
    ):
        rows = []
        for x in d["cases"][case]["table"]:
            m = means[case].get(x["alpha"], {})
            k = m.get("feasible_draws", 0)
            mean = "–" if not k else f4(m["mean_test_risk"]) + (
                "" if k == d["n_resamples"] else f" ({k} of {d['n_resamples']} feasible)")
            if not x["feasible"]:
                rows.append([x["alpha"], "infeasible", "–", mean, "–"])
            else:
                rows.append(
                    [
                        x["alpha"],
                        x["tau"],
                        f4(x["test_risk"]),
                        mean,
                        f"{x['false_alarms_per_image']:.2f}",
                    ]
                )
        r.add(f"**{label}**", "")
        r.table(
            [
                "Certified α",
                "Threshold",
                "Miss rate, india_test",
                "Mean over re-partitions",
                "False alarms/img",
            ],
            rows,
            ["results/T10/conformal.json"],
        )


def drift(r: Report) -> None:
    r.add("## Drift alarm (T11)", "")
    got = r.need("Drift alarm", "results/T11/drift.json")
    if got:
        d = got[0]
        rows = []
        for k in ("plain", "cusum"):
            s = d[k]["shift"]
            f = s["delay_frames"]
            rows.append(
                [
                    d[k]["statistic"],
                    f"{d[k]['alarm_threshold']:g}",
                    f"{d[k]['null_false_alarm_rate']:.3f}",
                    f"{s['detected']} of {d['n_streams']}",
                    s["alarmed_in_null_prefix"],
                    s["never_alarmed"],
                    f"{f['median']:g}" if f else "–",
                ]
            )
        r.para(
            f"Model A frame scores: {d['null_prefix']} non-India frames, then India. "
            f"Same null false-alarm budget ({d['false_alarm_budget']:.3f}) for both statistics."
        )
        r.table(
            [
                "Statistic",
                "Threshold",
                "Null false alarms",
                "Detected after shift",
                "Alarmed early",
                "Never",
                "Median delay, frames",
            ],
            rows,
            ["results/T11/drift.json"],
        )


def allocation(r: Report) -> None:
    r.add("## Allocation (T12)", "")
    got = r.need("Repair allocation", "results/T12/allocation.json")
    if not got:
        return
    d = got[0]
    src = ["results/T12/allocation.json"]
    r.para(
        "**Every number in this section comes from a simulation that detected every class, "
        "potholes included, at Model B's recall — not Model P's (D082).** False alarms are "
        "not simulated."
    )
    rows = [
        [
            p["role"],
            p["alpha"],
            p["tau"],
            p["false_alarms_per_image"],
            *(p["recall"][c] for c in CLASSES),
        ]
        for p in d["operating_points"]
    ]
    r.table(
        [
            "Role",
            "Certified α",
            "Threshold",
            "False alarms/img",
            *(f"Recall, {c}" for c in CLASSES),
        ],
        rows,
        src,
    )
    head = next(p for p in d["operating_points"] if p["role"] == "headline")
    fracs = sorted({x["budget_fraction"] for x in d["rows"]})
    for regime in ("uniform_traffic", "varying_traffic"):
        rows = []
        for pol in ("oracle", "nominal", "robust", "greedy", "random"):
            cells = [pol]
            for f in fracs:
                x = next(
                    x
                    for x in d["rows"]
                    if x["regime"] == regime
                    and x["alpha"] == head["alpha"]
                    and x["budget_fraction"] == f
                    and x["policy"] == pol
                )
                cells.append(
                    f"{pct(x['benefit_vs_oracle'], 0)} · {pct(x['mean_worst20_share'], 0)}"
                )
            rows.append(cells)
        r.add(
            f"**{regime.replace('_', ' ')}, certified α {head['alpha']}** — each cell: share of "
            "oracle benefit · share of the true worst 20 repaired. Nominal is the optimiser on "
            "observed condition, robust on conformal robust condition, greedy is worst-first.",
            "",
        )
        r.table(["Policy", *(f"{round(f * 100)}% budget" for f in fracs)], rows, src)
    rows = [
        [
            x["regime"].replace("_", " "),
            x["alpha"],
            f"{round(x['budget_fraction'] * 100)}%",
            pct(x["identical_choice_share"]),
            f"{x['benefit_robust_minus_nominal']:+.1f} [{x['benefit_ci95'][0]:+.1f}, "
            f"{x['benefit_ci95'][1]:+.1f}]",
            f"{x['worst20_robust_minus_nominal']:+.4f} [{x['worst20_ci95'][0]:+.4f}, "
            f"{x['worst20_ci95'][1]:+.4f}]",
        ]
        for x in d["robust_vs_nominal"]
        if x["alpha"] == head["alpha"]
    ]
    r.add(
        f"**Robust minus nominal at α {head['alpha']}, paired over "
        f"{d['generator']['n_trials']:,} networks**",
        "",
    )
    r.table(
        [
            "Regime",
            "α",
            "Budget",
            "Identical repair set",
            "Benefit [95% CI]",
            "Worst-20 share [95% CI]",
        ],
        rows,
        src,
    )


def simulation(r: Report) -> None:
    r.add("## Simulation (T13)", "")
    r.not_run("Detect-and-avoid simulation", "results/T13")


def edge(r: Report) -> None:
    r.add("## Edge latency, FPS and v_max (T14)", "")
    r.not_run("Edge pipeline on target hardware", "results/T14")
    r.para(
        "The video section below reports timings measured on a Mac (MPS). They are not "
        "edge-hardware numbers and do not stand in for T14."
    )


def annotator(root: Path, gt_path: str) -> str:
    """The 'Annotator:' line of a ground-truth CSV header, with its continuation lines."""
    p = root / gt_path
    if not p.exists():
        return "not recorded (ground-truth file missing)"
    out, on = [], False
    for line in p.read_text().splitlines():
        if not line.startswith("#"):
            break
        body = line.lstrip("#").strip()
        if body.startswith("Annotator:"):
            out, on = [body[len("Annotator:") :].strip()], True
        elif on and not re.match(r"^[A-Z][\w ]*:\s", body):
            out.append(body)
        else:
            on = False
    return " ".join(out) if out else "not recorded in the file header"


def video(r: Report) -> None:
    r.add("## Video (read-only: the video-evaluation session's lane)", "")
    r.para(
        "Counts are tracks, not potholes (D075). Results, settings and ground truth below are "
        "read from that session's files and are not regenerated here."
    )
    clips = (
        sorted(p for p in (r.root / "results/video").glob("*") if p.is_dir())
        if (r.root / "results/video").exists()
        else []
    )
    if not clips:
        r.not_run("Video evaluation", "results/video")
        return
    for clip in clips:
        rel = clip.relative_to(r.root).as_posix()
        r.add(f"### Clip `{clip.name}`", "")
        srcs = [f"{rel}/B/summary.json", f"{rel}/P/summary.json"]
        got = r.need(f"Track counts, {clip.name}", *srcs)
        if got:
            rows = []
            for m, s in zip(("B", "P"), got, strict=True):
                res, perf = s["result"], s["performance"]
                rows.append(
                    [
                        m,
                        res["unique_confirmed_tracks"],
                        f"{res['raw_detections']:,}",
                        res["tracks_seen_below_horizon"],
                        f"{perf['processing_fps']:.1f}",
                        f"{perf['latency_ms']['p50']:.1f} / {perf['latency_ms']['p95']:.1f}",
                    ]
                )
            st, v = got[0]["settings"], got[0]["video"]
            r.para(
                f"{v['duration_s']:g} s at {v['fps']:g} fps, {v['width']}x{v['height']}; "
                f"conf {st['conf']}, tracker `{st['tracker']}`, horizon {st['horizon_frac']}, "
                f"confirm {st['confirm']['required']} of {st['confirm']['window']} frames, "
                f"device {st['device']}."
            )
            r.table(
                [
                    "Model",
                    "Confirmed tracks",
                    "Raw detections",
                    "Tracks seen",
                    "Processing FPS (Mac)",
                    "Latency p50 / p95 ms (Mac)",
                ],
                rows,
                srcs,
            )
        gt_rel = f"{rel}/gt_score.json"
        got = r.need(f"Ground-truth scoring, {clip.name}", gt_rel)
        if got:
            g = got[0]
            n = g["gt"]["potholes"]
            rows = [
                [
                    m,
                    f"{x['hit']} of {x['potholes']}",
                    x["tracks_in_window"],
                    x["duplicates"],
                    f"{x['false_alarms_per_min']:g}",
                    f"{x['median_frames_per_hit']:g}",
                ]
                for m, x in g["models"].items()
            ]
            who = annotator(r.root, g["gt"]["path"])
            r.para(
                f"Window {g['window_s'][0]:g}–{g['window_s'][1]:g} s, {n} annotated potholes. "
                f"**Annotator, from the ground-truth file: {who}**"
            )
            r.table(
                [
                    "Model",
                    "Potholes hit",
                    "Tracks in window",
                    "Duplicate tracks",
                    "False alarms/min",
                    "Median frames per hit",
                ],
                rows,
                [gt_rel, g["gt"]["path"]],
            )
            if g.get("caveats"):
                r.add(
                    "Caveats recorded with the scores:", "", *(f"- {c}" for c in g["caveats"]), ""
                )
        ext = r.load(f"{rel}/extent.json")
        if not isinstance(ext, NotRun) and "scale" in ext:
            sc = ext["scale"]
            rows = [
                [
                    k,
                    f"{v['frames_with_any_box']} of {v['frames']}",
                    v["boxes"],
                    v["pothole_boxes"],
                    "–" if v["max_conf"] is None else v["max_conf"],
                ]
                for k, v in sc["by_factor"].items()
            ]
            r.add(
                f"**Scale test (D080): Model {ext['model']} at conf {sc['conf']} on the degraded "
                "stretch**",
                "",
            )
            r.table(
                ["Condition", "Frames with any box", "Boxes", "Pothole boxes", "Max conf"],
                rows,
                [f"{rel}/extent.json"],
            )


def decisions(r: Report) -> None:
    r.add("## Decision log status", "")
    path = r.root / "docs/DECISIONS.md"
    index: dict[str, tuple[str, str]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            m = re.match(r"^\| (D\d{3}) \| (.*) \| ([^|]*) \|$", line)
            if m:
                index[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    if "D082" not in index:
        r.para(
            "**D082 is cited but not yet written in `docs/DECISIONS.md`.** The attribution "
            "it is cited for — potholes from Model P, cracks from Model B, never summed — is "
            "applied in this report as the user's instruction. D082 is reserved for the "
            "video-evaluation session. **D083 was taken by the session that ran T10–T17**, "
            "for T16."
        )
    rows = [[d, *index.get(d, ("not yet written", "–"))] for d in CITED]
    if not index:
        r.not_run("Decision index", "docs/DECISIONS.md")
    else:
        r.table(["Decision", "Index entry", "Status"], rows, ["docs/DECISIONS.md"])


def build_report(root: Path, stamp: dict) -> str:
    r = Report(root)
    r.add(
        "# Results",
        "",
        f"Generated by `scripts/make_report.py` from `results/` at {stamp['utc']}, commit "
        f"{stamp['commit']}. **Do not edit by hand** — rerun the script.",
        "",
        "Model attribution (D082): potholes come from Model P and cracks from Model B; their "
        "pothole outputs are never summed. Every table names the file it was read from, and a "
        'missing input is a "not run" row.',
        "",
    )
    for section in (
        data_audit,
        model_a,
        a_vs_b,
        external,
        conformal,
        drift,
        allocation,
        simulation,
        edge,
        video,
        decisions,
    ):
        section(r)
    return "\n".join(r.lines).rstrip() + "\n"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    commit = (
        subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root
        ).stdout.strip()
        or "unknown"
    )
    stamp = {"utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "commit": commit}
    out = root / "results" / "RESULTS.md"
    out.write_text(build_report(root, stamp))
    print(f"wrote {out} ({len(out.read_text().splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
