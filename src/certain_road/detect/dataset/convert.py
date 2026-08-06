"""VOC -> YOLO label conversion.

Only the four CRDDC2022 source classes survive, merged into three output classes
(D00/D10 share one id per ASTM D6433). Everything dropped is counted, so the gap
between annotation count and label count is always explainable.
"""

import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from certain_road.detect.dataset.voc import VocAnnotation, parse_voc

# RDD2022 source annotation label -> our class id.
# D00 (longitudinal) and D10 (transverse) collapse to one id: ASTM D6433 treats
# longitudinal and transverse cracking as a single distress sharing one deduct
# curve, and D10 alone has too few instances in the India subset to learn.
SOURCE_TO_ID = {"D00": 0, "D10": 0, "D20": 1, "D40": 2}

ID_TO_CLASS = {0: "linear_crack", 1: "alligator_crack", 2: "pothole"}


def to_yolo_lines(ann: VocAnnotation) -> tuple[list[str], Counter]:
    """Return YOLO label lines plus a counter of everything rejected and why."""
    rejected: Counter = Counter()
    lines: list[str] = []

    if ann.width <= 0 or ann.height <= 0:
        rejected["bad_image_size"] += len(ann.objects)
        return lines, rejected

    for obj in ann.objects:
        if obj.name not in SOURCE_TO_ID:
            rejected[f"unknown_class:{obj.name}"] += 1
            continue

        # Some annotations have the corners transposed; that is a recoverable
        # ordering problem, not a bad box.
        xmin, xmax = sorted((obj.xmin, obj.xmax))
        ymin, ymax = sorted((obj.ymin, obj.ymax))

        xmin = max(0.0, min(xmin, ann.width))
        xmax = max(0.0, min(xmax, ann.width))
        ymin = max(0.0, min(ymin, ann.height))
        ymax = max(0.0, min(ymax, ann.height))

        if xmax - xmin <= 0 or ymax - ymin <= 0:
            rejected["degenerate_box"] += 1
            continue

        cx = (xmin + xmax) / 2 / ann.width
        cy = (ymin + ymax) / 2 / ann.height
        w = (xmax - xmin) / ann.width
        h = (ymax - ymin) / ann.height

        lines.append(f"{SOURCE_TO_ID[obj.name]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

    return lines, rejected


def convert_directory(xml_dir: Path, label_dir: Path) -> tuple[int, int, Counter]:
    """Convert every XML in `xml_dir`. Returns (files, boxes, rejections).

    A file that fails to parse is counted under the same `PARSE_ERROR:<Type>`
    key `class_census` uses, and produces no label file — it must not abort
    conversion of the remaining ~7,706 real annotations.
    """
    label_dir.mkdir(parents=True, exist_ok=True)
    rejected: Counter = Counter()
    files = boxes = 0

    for xml_path in sorted(Path(xml_dir).glob("*.xml")):
        try:
            annotation = parse_voc(xml_path)
        except (ET.ParseError, ValueError) as exc:
            rejected[f"PARSE_ERROR:{type(exc).__name__}"] += 1
            continue
        lines, dropped = to_yolo_lines(annotation)
        rejected.update(dropped)
        # An empty label file is meaningful: it marks a genuine negative frame.
        (label_dir / f"{xml_path.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        files += 1
        boxes += len(lines)

    return files, boxes, rejected
