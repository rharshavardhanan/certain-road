"""PASCAL VOC annotation parsing for RDD2022."""

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VocObject:
    name: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float


@dataclass(frozen=True)
class VocAnnotation:
    path: Path
    width: int
    height: int
    objects: list[VocObject]


def _text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    if found is None or found.text is None:
        raise ValueError(f"missing <{tag}>")
    return found.text.strip()


def parse_voc(xml_path: Path) -> VocAnnotation:
    root = ET.parse(xml_path).getroot()

    size = root.find("size")
    if size is None:
        raise ValueError(f"{xml_path}: missing <size>")
    width, height = int(_text(size, "width")), int(_text(size, "height"))

    objects = []
    for obj in root.findall("object"):
        box = obj.find("bndbox")
        if box is None:
            continue
        objects.append(
            VocObject(
                name=_text(obj, "name"),
                xmin=float(_text(box, "xmin")),
                ymin=float(_text(box, "ymin")),
                xmax=float(_text(box, "xmax")),
                ymax=float(_text(box, "ymax")),
            )
        )

    return VocAnnotation(path=xml_path, width=width, height=height, objects=objects)


def class_census(xml_dir: Path) -> Counter:
    """Count every class string present, including ones we will later drop."""
    counts: Counter = Counter()
    for xml_path in sorted(Path(xml_dir).glob("*.xml")):
        try:
            annotation = parse_voc(xml_path)
        except (ET.ParseError, ValueError) as exc:
            counts[f"PARSE_ERROR:{type(exc).__name__}"] += 1
            continue
        for obj in annotation.objects:
            counts[obj.name] += 1
    return counts
