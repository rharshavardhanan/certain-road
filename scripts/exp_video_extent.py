"""Why Model B is silent on the degraded stretch of the Bengaluru clip.

Three measurements. Nothing is re-decided (D074 stands) and nothing is tuned.

**Scale.** Ten frames from t=100-109 s, where the road is broken and
water-filled and B returns nothing even at conf 0.05. Each frame is padded into
a grey canvas 1.5x/2x/3x its size, which shrinks the damage relative to the
image, and separately cropped to the lower-centre half-frame, which magnifies it
~2x. "The damage is too large to read as one object" predicts detections rise
with padding; "the defects are too small" predicts they rise with the zoom;
neither rising points at appearance.

**Extent.** india_train GT relative box areas (normalised w*h), against two
extents drawn by eye on the t=105 s frame: the whole degraded stretch and one
discrete pothole.

**Drift.** D078's monitor over every frame of the clip: Model B's scores against
B's own india_val predictions. The video is scored exactly as the bag was — the
frozen eval block, plus the multi-label NMS that `model.val` uses and `predict`
does not — and that equivalence is checked on india_val images before the
stream is trusted.

    uv run python scripts/exp_video_extent.py data/video/2DV-cYmIvT4.mp4

Per-frame video scores are cached in `runs/video/<stem>/frame_scores.npz`;
delete it to force fresh inference.
"""

import argparse
import json
import sys
from functools import partial
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from exp_drift import frame_scores  # noqa: E402  (the reference bag, built as T11 builds it)

from certain_road.assess.drift import frame_score, run_stream  # noqa: E402
from certain_road.core.device import available_device  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402

ROOT = repo_root()
CFG = yaml.safe_load((ROOT / "configs" / "project.yaml").read_text())
EVAL, DR = CFG["eval"], CFG["drift"]
VCFG = yaml.safe_load((ROOT / "configs" / "eval" / "video.yaml").read_text())
VCFG["device"] = available_device(VCFG["device"])  # mps on the Mac, cuda on the Jetson
X, DV = VCFG["extent"], VCFG["drift"]
YOLO_DIR = ROOT / CFG["paths"]["yolo"]

# dataviz reference palette: categorical slots 1-2, chart chrome
BLUE, ORANGE, INK, MUTED, GRID, SURFACE = (
    "#2a78d6",
    "#eb6834",
    "#2b2b2a",
    "#8a8a86",
    "#e4e4e0",
    "#fcfcfb",
)
HAND_BGR = (180, 60, 230)
TRACE_NAMES = {"cusum": "CUSUM reset (D078, headline)", "plain": "plain power martingale (spec)"}


def read_frame(cap: cv2.VideoCapture, t_s: float) -> np.ndarray:
    cap.set(cv2.CAP_PROP_POS_MSEC, t_s * 1000)
    ok, frame = cap.read()
    if not ok:
        sys.exit(f"cannot read a frame at {t_s} s")
    return frame


def pad(img: np.ndarray, factor: float) -> np.ndarray:
    """Centre `img` on a grey canvas `factor` times its size (114 = ultralytics' fill)."""
    h, w = img.shape[:2]
    big_h, big_w = round(h * factor), round(w * factor)
    canvas = np.full((big_h, big_w, 3), 114, np.uint8)
    y0, x0 = (big_h - h) // 2, (big_w - w) // 2
    canvas[y0 : y0 + h, x0 : x0 + w] = img
    return canvas


def crop(img: np.ndarray, box: list[float]) -> np.ndarray:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    return img[round(y1 * h) : round(y2 * h), round(x1 * w) : round(x2 * w)]


def scale_diagnostic(model, video: Path, pothole: int, conditions: dict) -> tuple[dict, dict]:
    cap = cv2.VideoCapture(str(video))
    frames = {t: read_frame(cap, t) for t in X["times_s"]}

    by_factor, per_frame, panels = {}, {}, {}
    for name, transform in conditions.items():
        rows = []
        for t, frame in frames.items():
            r = model.predict(
                transform(frame),
                conf=X["conf"],
                imgsz=EVAL["imgsz"],
                device=VCFG["device"],
                verbose=False,
            )[0]
            d = r.boxes.data.cpu().numpy()
            pot = d[d[:, 5] == pothole]
            rows.append(
                {
                    "t_s": t,
                    "boxes": len(d),
                    "pothole_boxes": len(pot),
                    "max_conf": round(float(d[:, 4].max()), 4) if len(d) else None,
                    "max_pothole_conf": round(float(pot[:, 4].max()), 4) if len(pot) else None,
                }
            )
            if t == X["figure_time_s"]:
                panels[name] = r.plot(line_width=2)
        per_frame[name] = rows
        confs = [x["max_conf"] for x in rows if x["max_conf"] is not None]
        by_factor[name] = {
            "frames": len(rows),
            "frames_with_any_box": sum(x["boxes"] > 0 for x in rows),
            "frames_with_pothole_box": sum(x["pothole_boxes"] > 0 for x in rows),
            "boxes": sum(x["boxes"] for x in rows),
            "pothole_boxes": sum(x["pothole_boxes"] for x in rows),
            "max_conf": max(confs) if confs else None,
        }
    return {
        "conf": X["conf"],
        "times_s": X["times_s"],
        "by_factor": by_factor,
        "per_frame": per_frame,
    }, panels


def gt_areas(pothole: int) -> dict:
    """Relative area (normalised w*h) of every india_train GT box, against the hand extents."""
    rows = []
    for entry in (YOLO_DIR / "india_train.txt").read_text().split():
        label = YOLO_DIR / "labels" / f"{Path(entry).stem}.txt"
        if label.exists():
            for line in label.read_text().splitlines():
                c, _, _, w, h = line.split()[:5]
                rows.append((int(c), float(w) * float(h)))
    a = np.array(rows)
    if not len(a):
        sys.exit("no india_train labels found")
    every, pots = a[:, 1], a[a[:, 0] == pothole, 1]

    def stats(v: np.ndarray) -> dict:
        q25, med, q75 = np.percentile(v, [25, 50, 75])
        return {
            "n": int(len(v)),
            "median": float(med),
            "q25": float(q25),
            "q75": float(q75),
            "max": float(v.max()),
        }

    hand = {}
    for name, (x1, y1, x2, y2) in X["hand_boxes"].items():
        area = (x2 - x1) * (y2 - y1)
        hand[name] = {
            "box": [x1, y1, x2, y2],
            "relative_area": round(area, 5),
            "percentile_all_classes": round(100 * float((every < area).mean()), 2),
            "percentile_pothole": round(100 * float((pots < area).mean()), 2),
        }
    return {
        "split": "india_train",
        "all_classes": stats(every),
        "pothole": stats(pots),
        "hand_boxes": hand,
    }


def val_mode_scorer(model):
    """Frame -> (frame_score, boxes), scored exactly as `model.val` scored the bag.

    `predict` runs single-label NMS; `model.val` runs multi-label, which keeps a box
    once per class above conf and so changes the top-3. The patch is process-wide,
    which is why the scale diagnostic (plain predict, as in eval_video) runs first.
    """
    import ultralytics.utils.nms as nms

    nms.non_max_suppression = partial(nms.non_max_suppression, multi_label=True)

    def score(img: np.ndarray) -> tuple[float, np.ndarray]:
        r = model.predict(
            img,
            conf=EVAL["conf"],
            iou=EVAL["iou"],
            max_det=EVAL["max_det"],
            imgsz=EVAL["imgsz"],
            rect=EVAL["rect"],
            half=EVAL["half"],
            device=VCFG["device"],
            verbose=False,
        )[0]
        d = r.boxes.data.cpu().numpy()
        # The reference JSON stores scores to 5 dp; ties matter to the p-value.
        return frame_score([round(float(c), 5) for c in d[:, 4]], topk=int(DR["topk"])), d

    return score


def drift(model, video: Path, pothole: int) -> tuple[dict, dict, np.ndarray, float]:
    score = val_mode_scorer(model)
    split = DV["reference_split"]
    entries = [e for e in (YOLO_DIR / f"{split}.txt").read_text().split() if e.strip()]
    reference = frame_scores(ROOT / DV["reference_predictions"], split)
    n = DV["equivalence_images"]
    mine = np.array([score(cv2.imread(str(YOLO_DIR / e)))[0] for e in entries[:n]])
    delta = float(np.abs(mine - reference[:n]).max())
    print(f"equivalence on {n} {split} images: max |delta frame_score| = {delta:.2e}")
    if delta > DV["equivalence_tol"]:
        sys.exit(f"video scoring does not reproduce the reference bag (delta {delta:.2e})")

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cache = ROOT / "runs" / "video" / video.stem / "frame_scores.npz"
    if cache.exists():
        z = np.load(cache)
        scores, counts = z["scores"], z["counts"]
    else:
        s_list, c_list = [], []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            s, d = score(frame)
            keep = d[:, 4] >= DV["count_conf"]
            s_list.append(s)
            c_list.append((int(keep.sum()), int((keep & (d[:, 5] == pothole)).sum())))
        scores, counts = np.array(s_list), np.array(c_list)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, scores=scores, counts=counts)

    runs, traces = {}, {}
    for stride in DV["strides"]:
        stream = scores[::stride]
        for stat, cusum, threshold in (
            ("cusum", True, DV["cusum_threshold"]),
            ("plain", False, DR["alarm_threshold"]),
        ):
            alarm, trace = run_stream(
                reference,
                stream,
                eps=float(DR["eps"]),
                alarm_threshold=float(threshold),
                seed=0,
                cusum=cusum,
            )
            key = f"{stat}_every_{stride}"
            frame_at = None if alarm is None else alarm * stride
            runs[key] = {
                "statistic": stat,
                "stride_frames": stride,
                "stream_len": len(stream),
                "threshold": threshold,
                "alarm_frame": frame_at,
                "alarm_s": None if frame_at is None else round(frame_at / fps, 2),
                "max_log_m": round(max(trace), 3),
                "final_log_m": round(trace[-1], 3),
            }
            traces[key] = np.array(trace)

    # Is the alarm "no damage in view" rather than "out of domain"? RDD images are
    # mostly damaged road, so compare the bag's own frames with and without GT.
    has_gt = np.array(
        [
            bool(
                (lab := YOLO_DIR / "labels" / f"{Path(e).stem}.txt").exists()
                and lab.read_text().strip()
            )
            for e in entries
        ]
    )
    summary = {
        "model": "B",
        "reference": f"B on {split} ({len(reference)} frames)",
        "reference_median_by_gt": {
            "with_gt": {"n": int(has_gt.sum()), "median": float(np.median(reference[has_gt]))},
            "without_gt": {
                "n": int((~has_gt).sum()),
                "median": float(np.median(reference[~has_gt])) if (~has_gt).any() else None,
            },
        },
        "equivalence_max_delta": delta,
        "median_score": {"video": float(np.median(scores)), split: float(np.median(reference))},
        "frames": len(scores),
        "frames_no_box_at_count_conf": int((counts[:, 0] == 0).sum()),
        "frames_no_pothole_at_count_conf": int((counts[:, 1] == 0).sum()),
        "count_conf": DV["count_conf"],
        "runs": runs,
    }
    return summary, traces, counts, fps


def scale_figure(panels: dict, by_factor: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels), 3.2), facecolor=SURFACE)
    for ax, (name, bgr) in zip(axes, panels.items(), strict=True):
        img = bgr.copy()
        if name == "pad 1x":
            h, w = img.shape[:2]
            for x1, y1, x2, y2 in X["hand_boxes"].values():
                cv2.rectangle(
                    img,
                    (round(x1 * w), round(y1 * h)),
                    (round(x2 * w) - 1, round(y2 * h) - 1),
                    HAND_BGR,
                    3,
                )
        ax.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        b = by_factor[name]
        ax.set_title(
            f"{name}\n{b['boxes']} boxes in {b['frames']} frames ({b['pothole_boxes']} pothole)",
            color=INK,
            fontsize=10,
        )
        ax.axis("off")
    fig.suptitle(
        f"Model B at conf {X['conf']}, t={X['figure_time_s']} s shown; counts over "
        f"t={X['times_s'][0]}-{X['times_s'][-1]} s. Magenta on 'pad 1x': hand-drawn extents.",
        color=MUTED,
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def drift_figure(summary: dict, traces: dict, counts: np.ndarray, fps: float, path: Path) -> None:
    t = np.arange(len(counts)) / fps
    fig, (a, b, c) = plt.subplots(
        3,
        1,
        figsize=(11, 7.5),
        sharex=True,
        facecolor=SURFACE,
        gridspec_kw={"height_ratios": [1, 1.4, 1.4]},
    )
    for ax in (a, b, c):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=MUTED, labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.axvspan(X["times_s"][0], X["times_s"][-1] + 1, color=GRID, alpha=0.6, linewidth=0)

    a.plot(t, counts[:, 0], color=BLUE, linewidth=1)
    zero = counts[:, 0] == 0
    a.scatter(t[zero], np.full(zero.sum(), -0.6), marker="|", s=18, color=MUTED, linewidths=0.6)
    a.set_ylim(-1.2, max(3, counts[:, 0].max() + 1))
    a.set_title(
        f"Model B boxes per frame at conf >= {summary['count_conf']} (all classes); "
        f"grey ticks: frames with none ({summary['frames_no_box_at_count_conf']} of "
        f"{summary['frames']})",
        loc="left",
        color=INK,
        fontsize=10,
    )
    a.text(X["times_s"][0], a.get_ylim()[1], " scale window", color=MUTED, fontsize=8, va="top")

    for ax, stat, legend_at in ((b, "cusum", "upper right"), (c, "plain", "lower left")):
        keys = [f"{stat}_every_{stride}" for stride in DV["strides"]]
        for key, stride, colour in zip(keys, DV["strides"], (BLUE, ORANGE), strict=True):
            x = np.arange(len(traces[key])) * stride / fps
            label = "every frame (30 fps)" if stride == 1 else f"every {stride}th frame (~1 fps)"
            ax.plot(x, traces[key], color=colour, linewidth=2 if stride > 1 else 1, label=label)
        threshold = summary["runs"][keys[0]]["threshold"]
        ax.axhline(
            np.log(threshold),
            color=MUTED,
            linewidth=1,
            linestyle="--",
            label=f"alarm threshold, log {threshold:g}",
        )
        lo, hi = ax.get_ylim()
        for i, (key, colour) in enumerate(zip(keys, (BLUE, ORANGE), strict=True)):
            alarm_s = summary["runs"][key]["alarm_s"]
            if alarm_s is not None:
                ax.axvline(alarm_s, color=colour, linewidth=1, linestyle=":")
                ax.text(
                    alarm_s,
                    hi - (0.04 + 0.1 * i) * (hi - lo),
                    f" alarm {alarm_s:.1f} s",
                    color=INK,
                    fontsize=8,
                    va="top",
                )
        name = TRACE_NAMES[stat]
        ax.set_title(f"log M, {name}", loc="left", color=INK, fontsize=10)
        ax.set_ylabel("log M", color=MUTED, fontsize=9)
        ax.legend(frameon=False, fontsize=8, loc=legend_at, labelcolor=INK)
    c.set_xlabel("video time (s)", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description="Scale, extent and drift on one road video")
    ap.add_argument("video", type=Path)
    args = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(ROOT / VCFG["models"]["B"])
    pothole = list(model.names.values()).index("pothole")
    out = ROOT / "results" / "video" / args.video.stem
    out.mkdir(parents=True, exist_ok=True)

    conditions = {f"pad {f:g}x": partial(pad, factor=f) for f in X["pad_factors"]}
    conditions["zoom 2x"] = partial(crop, box=X["zoom_window"])
    scale, panels = scale_diagnostic(model, args.video, pothole, conditions)
    # Control: Model P on the same frames at the same conf, unpadded. Report only (D074).
    p_model = YOLO(ROOT / VCFG["models"]["P"])
    p_pothole = list(p_model.names.values()).index("pothole")
    p_scale, _ = scale_diagnostic(p_model, args.video, p_pothole, {"pad 1x": conditions["pad 1x"]})
    scale["model_p_control"] = {
        **p_scale["by_factor"]["pad 1x"],
        "per_frame": p_scale["per_frame"]["pad 1x"],
    }
    scale_figure(panels, scale["by_factor"], out / "scale.png")
    areas = gt_areas(pothole)
    drift_summary, traces, counts, fps = drift(model, args.video, pothole)
    drift_figure(drift_summary, traces, counts, fps, out / "drift.png")

    result = {
        "video": str(args.video),
        "model": "B",
        "weights": VCFG["models"]["B"],
        "scale": scale,
        "gt_area": areas,
        "drift": drift_summary,
    }
    (out / "extent.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "scale": scale["by_factor"],
                "gt_area": areas,
                "drift": {k: v for k, v in drift_summary.items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
