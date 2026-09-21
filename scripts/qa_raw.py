"""T1 step 5 — draw ground-truth boxes on raw images so they can be eyeballed.

Counts can be right while boxes sit in the wrong place: a transposed axis or a
pixel/normalised mix-up produces a perfectly plausible audit table. This is the
only check in T1 that would catch that, so it renders the boxes as the source
actually states them, with no conversion in between.

Colour follows the D038/D055 merge so the taxonomy is visible at a glance:
D00/D10 green (linear_crack), D20 orange (alligator_crack), D40 red (pothole),
and every class the converter drops in grey.
"""

import random
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import raw_dir, repo_root  # noqa: E402
from certain_road.perception.dataset.voc import parse_voc  # noqa: E402

COUNTRIES = ["India", "Japan", "Norway", "United_States", "Czech",
             "China_MotorBike", "China_Drone"]
SAMPLE_PER_COUNTRY = 8
CELL = 420
COLS, ROWS = 4, 2
SEED = 0

COLOURS = {"D00": (0, 200, 0), "D10": (0, 200, 0),
           "D20": (0, 165, 255), "D40": (0, 0, 255)}
DROPPED = (150, 150, 150)


def letterbox(img, size):
    h, w = img.shape[:2]
    s = size / max(h, w)
    out = cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))))
    canvas = cv2.copyMakeBorder(
        out, (size - out.shape[0]) // 2, size - out.shape[0] - (size - out.shape[0]) // 2,
        (size - out.shape[1]) // 2, size - out.shape[1] - (size - out.shape[1]) // 2,
        cv2.BORDER_CONSTANT, value=(30, 30, 30))
    return canvas


def render(country, out_dir):
    root = raw_dir() / "RDD2022" / country / "train"
    xmls = sorted((root / "annotations" / "xmls").glob("*.xml"))
    # Prefer annotated frames: a grid of empty roads shows nothing about boxes.
    rng = random.Random(f"{SEED}:{country}")
    with_boxes = [x for x in xmls if parse_voc(x).objects]
    picks = rng.sample(with_boxes, min(SAMPLE_PER_COUNTRY, len(with_boxes)))

    cells, notes = [], []
    for xml_path in picks:
        ann = parse_voc(xml_path)
        img = cv2.imread(str(root / "images" / f"{xml_path.stem}.jpg"))
        if img is None:
            continue
        for o in ann.objects:
            colour = COLOURS.get(o.name, DROPPED)
            p1, p2 = (int(o.xmin), int(o.ymin)), (int(o.xmax), int(o.ymax))
            thick = max(2, round(max(img.shape[:2]) / 400))
            cv2.rectangle(img, p1, p2, colour, thick)
            cv2.putText(img, o.name, (p1[0], max(14, p1[1] - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, max(0.5, thick * 0.25), colour, thick)
        notes.append(f"{xml_path.stem} {ann.width}x{ann.height} "
                     f"{len(ann.objects)}box {sorted({o.name for o in ann.objects})}")
        cv2.imwrite(str(out_dir / f"{country}__{xml_path.stem}.jpg"), img)
        cell = letterbox(img, CELL)
        cv2.putText(cell, xml_path.stem, (6, CELL - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cells.append(cell)

    while len(cells) < COLS * ROWS:
        cells.append(letterbox(cv2.imread(str(root / "images" / f"{picks[0].stem}.jpg")), CELL) * 0)
    grid = cv2.vconcat([cv2.hconcat(cells[r * COLS:(r + 1) * COLS]) for r in range(ROWS)])
    banner = grid[:0].copy()
    grid = cv2.copyMakeBorder(grid, 34, 0, 0, 0, cv2.BORDER_CONSTANT, value=(20, 20, 20))
    cv2.putText(grid, f"{country}  |  green D00/D10  orange D20  red D40  grey dropped",
                (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    del banner
    cv2.imwrite(str(out_dir / f"_montage_{country}.jpg"), grid)
    return notes


def main():
    out_dir = repo_root() / "results" / "T1" / "qa"
    out_dir.mkdir(parents=True, exist_ok=True)
    for c in COUNTRIES:
        notes = render(c, out_dir)
        print(f"=== {c} ===")
        for n in notes:
            print("   ", n)
    print(f"\nwrote {out_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
