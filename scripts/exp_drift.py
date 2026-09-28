"""T11 — does the drift alarm notice when Model A leaves its domain?

T10 showed the failure: calibrate on non-India, deploy on India, and the promised
20% miss rate becomes 70%. Nothing in the certificate announces this. The drift
alarm is the runtime answer — a signal, computed from the detector's own output
with no labels, that the stream has stopped looking like the data the
certificate was issued on.

Model A's predictions only, because A is the model with a real shift to detect:
it never saw India. Nothing is re-run; nothing is decided.

**Null.** `nonindia_val` is split 50/50 at random into a reference bag and a null
pool. Each null stream is a fresh shuffle of the pool. Ville's inequality bounds
the chance a stream *ever* alarms at 1/threshold, so the measured rate is checked
against that, not against a hand-tuned window.

**Shift.** Each stream is `null_prefix` null frames, then shuffled India frames.
Delay is counted from the first India frame. An alarm inside the null prefix is a
false alarm, and is counted as one rather than as an early detection.

**Two statistics (D078).** The spec's plain power martingale sinks ~0.19 nats per
in-domain frame and has to repay that before it can alarm, so its delay grows
with uptime. The CUSUM reset floors log M at zero and does not. Its threshold is
picked by a rule fixed in config before any shift stream was run: the smallest
grid value whose null false-alarm rate is within the spec's budget. The CUSUM
trace does not depend on the threshold, so each stream is run once and every
threshold is read off the same trace.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from certain_road.assess.drift import frame_score, run_stream  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
D = CFG["drift"]
EPS, THRESHOLD, TOPK = float(D["eps"]), float(D["alarm_threshold"]), int(D["topk"])
N_STREAMS, PREFIX = int(D["n_streams"]), int(D["null_prefix"])
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
OUT = repo_root() / "results" / "T11"
N_TRACES = 10


def frame_scores(pred_json: Path, split: str) -> np.ndarray:
    """One score per image in `split`, including images with no detection at all.

    Every class counts: the score asks how sure the detector is about anything,
    and a detector out of its domain is unsure about everything.
    """
    confs: dict[str, list[float]] = defaultdict(list)
    for r in json.loads(pred_json.read_text()):
        confs[Path(str(r["image_id"])).stem].append(float(r["score"]))
    stems = [Path(x).stem for x in (YOLO_DIR / f"{split}.txt").read_text().split() if x.strip()]
    return np.array([frame_score(confs.get(s, []), topk=TOPK) for s in stems])


def first_crossing(trace: list[float], log_c: float) -> int | None:
    hit = np.nonzero(np.asarray(trace) >= log_c)[0]
    return int(hit[0]) if hit.size else None


def classify(alarms: list[int | None]) -> dict:
    """Shift-stream outcomes: early (inside the null prefix), missed, or a delay."""
    delays = [a - PREFIX + 1 for a in alarms if a is not None and a >= PREFIX]
    d = np.array(delays)
    return {"detected": len(delays),
            "alarmed_in_null_prefix": sum(1 for a in alarms if a is not None and a < PREFIX),
            "never_alarmed": sum(1 for a in alarms if a is None),
            "delay_frames": {"median": float(np.median(d)), "mean": round(float(d.mean()), 2),
                             "p90": float(np.percentile(d, 90)), "min": int(d.min()),
                             "max": int(d.max())} if len(d) else None,
            "delays": [int(x) for x in d]}


def main() -> int:
    non = frame_scores(repo_root() / "results/T6_A_nonindia_val/val/predictions.json",
                       "nonindia_val")
    india = frame_scores(repo_root() / "results/LOCKED/A_india_full_run/val/predictions.json",
                         "india_full")
    rng = np.random.default_rng(0)
    order = rng.permutation(len(non))
    half = len(non) // 2
    reference, null_pool = non[order[:half]], non[order[half:]]
    print(f"reference {len(reference)}, null pool {len(null_pool)}, India {len(india)}; "
          f"median score non-India {np.median(non):.3f} vs India {np.median(india):.3f}",
          flush=True)
    budget = 1.0 / THRESHOLD
    grid = [float(c) for c in D["cusum_threshold_grid"]]

    # --- null ----------------------------------------------------------------
    plain_null, cusum_null = [], {c: [] for c in grid}
    for k in range(N_STREAMS):
        stream = null_pool[np.random.default_rng(1000 + k).permutation(len(null_pool))]
        alarm, _ = run_stream(reference, stream, eps=EPS, alarm_threshold=THRESHOLD, seed=k)
        plain_null.append(alarm)
        _, tr = run_stream(reference, stream, eps=EPS, alarm_threshold=THRESHOLD, seed=k,
                           cusum=True)
        for c in grid:
            cusum_null[c].append(first_crossing(tr, np.log(c)))
    plain_far = sum(a is not None for a in plain_null) / N_STREAMS
    cusum_far = {c: sum(a is not None for a in v) / N_STREAMS for c, v in cusum_null.items()}
    chosen = next((c for c in grid if cusum_far[c] <= budget), None)
    print(f"null, plain: rate {plain_far:.3f} (Ville bound {budget:.3f})")
    for c in grid:
        print(f"null, CUSUM C={c:g}: rate {cusum_far[c]:.3f}"
              f"{'   <- chosen' if c == chosen else ''}")
    if chosen is None:
        raise SystemExit("no CUSUM threshold in the grid meets the null budget; widen the grid")

    # --- shift -------------------------------------------------------------
    plain_alarms, cusum_alarms, traces = [], [], {"plain": [], "cusum": []}
    for k in range(N_STREAMS):
        r = np.random.default_rng(5000 + k)
        prefix = null_pool[r.choice(len(null_pool), PREFIX, replace=False)]
        stream = np.concatenate([prefix, india[r.permutation(len(india))]])
        a_plain, tr_plain = run_stream(reference, stream, eps=EPS, alarm_threshold=THRESHOLD,
                                       seed=10_000 + k)
        _, tr_cusum = run_stream(reference, stream, eps=EPS, alarm_threshold=chosen,
                                 seed=10_000 + k, cusum=True)
        plain_alarms.append(a_plain)
        cusum_alarms.append(first_crossing(tr_cusum, np.log(chosen)))
        if k < N_TRACES:
            traces["plain"].append(tr_plain)
            traces["cusum"].append(tr_cusum)

    report = {
        "model": "A", "eps": EPS, "topk": TOPK, "n_streams": N_STREAMS, "null_prefix": PREFIX,
        "reference_frames": len(reference), "null_pool_frames": len(null_pool),
        "india_frames": len(india), "false_alarm_budget": budget,
        "median_frame_score": {"nonindia": round(float(np.median(non)), 4),
                               "india": round(float(np.median(india)), 4)},
        "plain": {"statistic": "power martingale (spec)", "alarm_threshold": THRESHOLD,
                  "null_false_alarm_rate": plain_far, "shift": classify(plain_alarms)},
        "cusum": {"statistic": "power martingale with CUSUM reset (D078)",
                  "null_false_alarm_rate_by_threshold": {f"{c:g}": v for c, v in cusum_far.items()},
                  "alarm_threshold": chosen, "null_false_alarm_rate": cusum_far[chosen],
                  "shift": classify(cusum_alarms)},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "drift.json").write_text(json.dumps(report, indent=2))
    write_markdown(report)
    plot(report, traces)

    for key in ("plain", "cusum"):
        sh = report[key]["shift"]
        f = sh["delay_frames"]
        tail = (f"; delay median {f['median']:g}, p90 {f['p90']:g}, range {f['min']}-{f['max']}"
                if f else "")
        print(f"shift, {key}: detected {sh['detected']}/{N_STREAMS}, early "
              f"{sh['alarmed_in_null_prefix']}, never {sh['never_alarmed']}{tail}")
    return 0


def write_markdown(report: dict) -> None:
    md = ["# T11 - drift alarm (conformal test martingale), Model A", "",
          f"eps {report['eps']}; frame score 1 - mean(top-{report['topk']} confidences); "
          f"reference bag {report['reference_frames']} non-India frames; shift streams are "
          f"{report['null_prefix']} null frames then India. False-alarm budget "
          f"{report['false_alarm_budget']:.3f}.", "",
          "| statistic | threshold | null false-alarm rate | detected | early | never | "
          "median delay | p90 delay |", "|---|---|---|---|---|---|---|---|"]
    for key in ("plain", "cusum"):
        r, sh = report[key], report[key]["shift"]
        f = sh["delay_frames"]
        md.append(f"| {r['statistic']} | {r['alarm_threshold']:g} | "
                  f"{r['null_false_alarm_rate']:.3f} | {sh['detected']}/{report['n_streams']} | "
                  f"{sh['alarmed_in_null_prefix']} | {sh['never_alarmed']} | "
                  f"{f['median']:g} | {f['p90']:g} |" if f else
                  f"| {r['statistic']} | {r['alarm_threshold']:g} | "
                  f"{r['null_false_alarm_rate']:.3f} | 0/{report['n_streams']} | "
                  f"{sh['alarmed_in_null_prefix']} | {sh['never_alarmed']} | - | - |")
    md += ["", "CUSUM null false-alarm rate by threshold (selection rule: smallest within budget):",
           "", "| threshold | rate |", "|---|---|"]
    md += [f"| {c} | {v:.3f} |" for c, v in
           report["cusum"]["null_false_alarm_rate_by_threshold"].items()]
    md += ["", "Generated by `scripts/exp_drift.py`; interpretation in `docs/DECISIONS.md`."]
    (OUT / "drift.md").write_text("\n".join(md) + "\n")


def plot(report: dict, traces: dict) -> None:
    import matplotlib.pyplot as plt
    from plot_style import INK_2, MUTED, SLOTS, SURFACE, figure, save, style_axes, title

    delay = report["cusum"]["shift"]["delay_frames"]
    horizon = PREFIX + 1500

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), facecolor=SURFACE, sharex=True)
    panels = (("plain", report["plain"]["alarm_threshold"], "Spec: plain power martingale"),
              ("cusum", report["cusum"]["alarm_threshold"], "D078: with CUSUM reset"))
    for ax, (key, c, name) in zip(axes, panels, strict=True):
        style_axes(ax)
        for tr in traces[key]:
            ax.plot(range(1, min(len(tr), horizon) + 1), tr[:horizon], color=SLOTS[0],
                    linewidth=1.1, alpha=0.7)
        log_c = float(np.log(c))
        ax.axvline(PREFIX + 0.5, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
        ax.axhline(log_c, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
        lo, hi = ax.get_ylim()
        ax.text(PREFIX + 15, hi - 0.07 * (hi - lo), "India begins", color=MUTED, fontsize=8)
        ax.text(horizon * 0.98, log_c + 0.02 * (hi - lo), f"alarm at M = {c:g}", color=MUTED,
                fontsize=8, ha="right", va="bottom")
        ax.set_xlim(0, horizon)
        ax.set_xlabel("frame")
        ax.set_title(name, loc="left", fontsize=10, color=INK_2)
    axes[0].set_ylabel("log martingale")
    fig.suptitle(f"{N_TRACES} streams of Model A scores: {PREFIX} non-India frames, then India",
                 x=0.01, ha="left", fontsize=12)
    save(fig, OUT / "martingale_traces.png")

    if not delay:
        return
    fig, ax = figure()
    d = report["cusum"]["shift"]["delays"]
    counts, _, _ = ax.hist(d, bins=range(0, max(d) + 11, 10), color=SLOTS[0],
                           edgecolor="#fcfcfb", linewidth=1.5)
    ax.axvline(delay["median"], color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.set_ylim(0, max(counts) * 1.12)
    ax.text(delay["median"] + 3, max(counts) * 1.04, f"median {delay['median']:g} frames",
            color=INK_2, fontsize=8)
    ax.set_xlabel("India frames seen before the alarm")
    ax.set_ylabel("streams")
    sh = report["cusum"]["shift"]
    title(ax, f"CUSUM detection delay over {report['n_streams']} shifted streams",
          f"Threshold {report['cusum']['alarm_threshold']:g}. "
          f"{sh['alarmed_in_null_prefix']} alarmed inside the null prefix, "
          f"{sh['never_alarmed']} never.")
    save(fig, OUT / "delay_hist.png")


if __name__ == "__main__":
    raise SystemExit(main())
