"""D073 — are BharatPotHole's own eval splits held out, and how diverse is it?

Roboflow exports name files `<videoID>_frame_<index>_jpg.rf.<hash>.jpg`, so the
source video and frame number survive in the filename. Two questions fall out of
that, and they are different questions.

**Is either eval split held out?** If the same video appears in train and in
valid or test - worse, adjacent frames of it - then that split measures
memorisation of footage the model trained on, not generalization.

**How much does BharatPotHole actually contain?** An image count answers the
wrong question when the images are sampled video frames. Frames of one drive
share vehicle, camera, mount, weather, surface and often the same physical
potholes. The honest unit is the drive, so this counts distinct videos too.

Neither question touches india_val, india_cal or india_test, and neither says
anything about BharatPotHole's *annotation convention* - whether its boxes are
drawn like RDD2022's. That is a separate risk, judged on india_val.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

BPH = repo_root() / "data/raw/bharatpothole/BharatPotHole/BharatPotHole"
ADJACENT = 10
PATTERN = re.compile(r"^(?P<video>.+?)_frame_(?P<frame>\d+)_jpg\.rf\.[0-9a-f]+$")


def parse(split):
    """video id -> sorted frame indices."""
    out = defaultdict(list)
    unparsed = []
    for p in sorted((BPH / split / "images").glob("*.jpg")):
        m = PATTERN.match(p.stem)
        if not m:
            unparsed.append(p.stem)
            continue
        out[m.group("video")].append(int(m.group("frame")))
    for v in out.values():
        v.sort()
    return out, unparsed


def against_train(train, split, name):
    """How much of `split` is footage the model already trained on?"""
    shared = sorted(set(train) & set(split))
    adjacent = []
    for v in shared:
        sf = set(split[v])
        for f in train[v]:
            for g in sf:
                if abs(g - f) <= ADJACENT:
                    adjacent.append({"video": v, "train_frame": f,
                                     "eval_frame": g, "delta": abs(g - f)})
    frames_in_shared = sum(len(split[v]) for v in shared)
    total = sum(len(v) for v in split.values())
    return {
        "split": name,
        "videos": len(split), "frames": total,
        "shared_video_ids": len(shared),
        "shared_video_examples": shared[:10],
        "frames_from_shared_videos": frames_in_shared,
        "share_of_frames_from_shared_videos": round(
            frames_in_shared / total, 4) if total else 0.0,
        "near_adjacent_pairs": len(adjacent),
        "near_adjacent_examples": adjacent[:10],
        "held_out": not shared,
    }


def main() -> int:
    train, un_tr = parse("train")
    valid, un_va = parse("valid")
    test, un_te = parse("test")
    for name, d, un in (("train", train, un_tr), ("valid", valid, un_va),
                        ("test", test, un_te)):
        print(f"{name}: {len(d)} videos, {sum(len(v) for v in d.values())} frames "
              f"({len(un)} unparsed)")

    evals = [against_train(train, valid, "valid"), against_train(train, test, "test")]
    all_videos = set(train) | set(valid) | set(test)
    all_frames = sum(sum(len(v) for v in d.values()) for d in (train, valid, test))
    leaky = [e for e in evals if not e["held_out"]]

    report = {
        "adjacent_window": ADJACENT,
        "train_videos": len(train),
        "train_frames": sum(len(v) for v in train.values()),
        # The honest size of this dataset. Frames of one drive are not
        # independent images, so an image count overstates what it contains.
        "distinct_videos_all_splits": len(all_videos),
        "frames_all_splits": all_frames,
        "frames_per_video": round(all_frames / len(all_videos), 1) if all_videos else 0.0,
        "eval_splits": evals,
        "verdict": (
            f"{'/'.join(e['split'] for e in leaky)} not held out; "
            f"excluded from all evaluation" if leaky
            else "disjoint videos; BPH eval splits are fair held-out sets"),
    }
    out = repo_root() / "results" / "T9"
    out.mkdir(parents=True, exist_ok=True)
    (out / "bph_internal_leakage.json").write_text(json.dumps(report, indent=2))
    for e in evals:
        print(f"\n{e['split']}: {e['shared_video_ids']}/{e['videos']} videos also in train")
        print(f"  frames from shared videos: {e['frames_from_shared_videos']}/{e['frames']} "
              f"({e['share_of_frames_from_shared_videos']:.1%})")
        print(f"  near-adjacent pairs (|delta| <= {ADJACENT}): {e['near_adjacent_pairs']}")
    print(f"\neffective diversity: {len(all_videos)} distinct videos across "
          f"{all_frames} frames ({report['frames_per_video']} frames/video)")
    print(f"\nVERDICT: {report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
