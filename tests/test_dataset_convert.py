from pathlib import Path

import pytest

from certain_road.perception.dataset.convert import SOURCE_TO_ID, convert_directory, to_yolo_lines
from certain_road.perception.dataset.voc import VocAnnotation, VocObject, class_census, parse_voc

XML_TEMPLATE = """<annotation>
  <size><width>{w}</width><height>{h}</height><depth>3</depth></size>
  {objects}
</annotation>"""

OBJ = """<object><name>{name}</name>
  <bndbox><xmin>{xmin}</xmin><ymin>{ymin}</ymin><xmax>{xmax}</xmax><ymax>{ymax}</ymax></bndbox>
</object>"""


def write_xml(path, objects, w=600, h=600):
    body = "\n".join(OBJ.format(**o) for o in objects)
    path.write_text(XML_TEMPLATE.format(w=w, h=h, objects=body))
    return path


def test_parses_size_and_objects(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=10, ymin=20, xmax=110, ymax=120)])
    ann = parse_voc(p)
    assert (ann.width, ann.height) == (600, 600)
    assert len(ann.objects) == 1
    assert ann.objects[0].name == "D40"


def test_converts_to_normalised_centre_format(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D00", xmin=100, ymin=200, xmax=200, ymax=400)])
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert rejected.total() == 0
    cls, cx, cy, w, h = lines[0].split()
    assert int(cls) == SOURCE_TO_ID["D00"]
    assert float(cx) == pytest.approx(150 / 600, abs=1e-6)
    assert float(cy) == pytest.approx(300 / 600, abs=1e-6)
    assert float(w) == pytest.approx(100 / 600, abs=1e-6)
    assert float(h) == pytest.approx(200 / 600, abs=1e-6)


def test_longitudinal_and_transverse_merge_to_one_class_id(tmp_path):
    """D00 (longitudinal) and D10 (transverse) share one ASTM D6433 deduct curve,
    so both must collapse to the same class id."""
    p = write_xml(
        tmp_path / "a.xml",
        [
            dict(name="D00", xmin=10, ymin=10, xmax=50, ymax=50),
            dict(name="D10", xmin=60, ymin=60, xmax=100, ymax=100),
        ],
    )
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert rejected.total() == 0
    assert len(lines) == 2
    ids = {int(line.split()[0]) for line in lines}
    assert ids == {SOURCE_TO_ID["D00"]}
    assert SOURCE_TO_ID["D00"] == SOURCE_TO_ID["D10"] == 0


def test_unknown_class_is_dropped_and_counted(tmp_path):
    p = write_xml(
        tmp_path / "a.xml",
        [
            dict(name="D40", xmin=10, ymin=10, xmax=50, ymax=50),
            dict(name="D43", xmin=10, ymin=10, xmax=50, ymax=50),
        ],
    )
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert len(lines) == 1
    assert rejected["unknown_class:D43"] == 1


def test_degenerate_box_is_dropped_and_counted(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=50, ymin=50, xmax=50, ymax=90)])
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert lines == []
    assert rejected["degenerate_box"] == 1


def test_inverted_box_is_normalised_not_dropped(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=200, ymin=300, xmax=100, ymax=150)])
    lines, rejected = to_yolo_lines(parse_voc(p))
    assert len(lines) == 1
    assert rejected.total() == 0


def test_out_of_bounds_box_is_clamped(tmp_path):
    p = write_xml(tmp_path / "a.xml", [dict(name="D40", xmin=-30, ymin=10, xmax=900, ymax=200)])
    lines, _ = to_yolo_lines(parse_voc(p))
    _, cx, cy, w, h = (float(v) for v in lines[0].split())
    assert 0.0 <= cx <= 1.0 and 0.0 <= w <= 1.0


def test_census_counts_every_class_string(tmp_path):
    d = tmp_path / "xmls"
    d.mkdir()
    write_xml(d / "a.xml", [dict(name="D00", xmin=1, ymin=1, xmax=9, ymax=9)])
    write_xml(
        d / "b.xml",
        [
            dict(name="D00", xmin=1, ymin=1, xmax=9, ymax=9),
            dict(name="D43", xmin=1, ymin=1, xmax=9, ymax=9),
        ],
    )
    counts = class_census(d)
    assert counts["D00"] == 2
    assert counts["D43"] == 1


def test_malformed_xml_is_skipped_not_fatal(tmp_path):
    """A single unparseable annotation must not abort the whole conversion."""
    d = tmp_path / "xmls"
    d.mkdir()
    write_xml(d / "good.xml", [dict(name="D00", xmin=1, ymin=1, xmax=9, ymax=9)])
    (d / "bad.xml").write_text("<annotation><unclosed>")
    label_dir = tmp_path / "labels"

    files, boxes, rejected = convert_directory(d, label_dir)

    assert files == 1
    assert boxes == 1
    assert rejected["PARSE_ERROR:ParseError"] == 1
    assert (label_dir / "good.txt").exists()
    assert not (label_dir / "bad.txt").exists()


def test_annotation_missing_size_is_skipped_not_fatal(tmp_path):
    """VocAnnotation parsing raises ValueError for a missing <size>; same handling."""
    d = tmp_path / "xmls"
    d.mkdir()
    (d / "nosize.xml").write_text("<annotation><object><name>D00</name></object></annotation>")
    label_dir = tmp_path / "labels"

    files, boxes, rejected = convert_directory(d, label_dir)

    assert files == 0
    assert boxes == 0
    assert rejected["PARSE_ERROR:ValueError"] == 1
    assert not (label_dir / "nosize.txt").exists()


# --- T2 extensions: real-size override and min_box_px (D055/D057) -------------


def _ann(width, height, boxes):
    """VocAnnotation with `boxes` as (name, xmin, ymin, xmax, ymax)."""
    return VocAnnotation(
        path=Path("x.xml"),
        width=width,
        height=height,
        objects=[VocObject(name=n, xmin=a, ymin=b, xmax=c, ymax=d) for n, a, b, c, d in boxes],
    )


def test_size_override_renormalises_against_the_real_image():
    """The same pixel box is a larger fraction of a smaller real image.

    The box is kept well inside 500px so this isolates renormalisation; clipping
    against the real size is covered by the next test.
    """
    ann = _ann(1000, 1000, [("D40", 200, 200, 300, 300)])
    declared, _ = to_yolo_lines(ann)
    overridden, _ = to_yolo_lines(ann, size=(500, 500))

    assert declared == ["2 0.250000 0.250000 0.100000 0.100000"]
    assert overridden == ["2 0.500000 0.500000 0.200000 0.200000"]


def test_size_override_clips_to_the_real_image_not_the_declared_one():
    ann = _ann(1000, 1000, [("D40", 400, 400, 900, 900)])
    lines, rejected = to_yolo_lines(ann, size=(500, 500))
    # xmax/ymax clip from 900 to 500, so the box becomes 100x100 centred at 450.
    assert lines == ["2 0.900000 0.900000 0.200000 0.200000"]
    assert not rejected


def test_min_box_px_drops_thin_boxes_and_counts_them():
    ann = _ann(100, 100, [("D40", 10, 10, 11, 30), ("D40", 10, 10, 30, 30)])
    lines, rejected = to_yolo_lines(ann, min_box_px=2)
    assert len(lines) == 1  # the 1px-wide box is gone
    assert rejected["below_min_box_px"] == 1


def test_min_box_px_default_preserves_historical_behaviour():
    """Default 0.0 must not reclassify anything that used to pass."""
    ann = _ann(100, 100, [("D40", 10, 10, 11, 30)])
    lines, rejected = to_yolo_lines(ann)
    assert len(lines) == 1
    assert "below_min_box_px" not in rejected


def test_degenerate_is_reported_separately_from_min_box_px():
    """Japan_001265's real shape: zero width. Not a thin box - a broken one."""
    ann = _ann(600, 600, [("D20", 198, 474, 198, 475)])
    lines, rejected = to_yolo_lines(ann, min_box_px=2)
    assert lines == []
    assert rejected["degenerate_box"] == 1
    assert "below_min_box_px" not in rejected
