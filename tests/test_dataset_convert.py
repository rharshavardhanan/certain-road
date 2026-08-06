import pytest

from certain_road.detect.dataset.convert import CLASS_TO_ID, to_yolo_lines
from certain_road.detect.dataset.voc import class_census, parse_voc

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
    assert int(cls) == CLASS_TO_ID["D00"]
    assert float(cx) == pytest.approx(150 / 600, abs=1e-6)
    assert float(cy) == pytest.approx(300 / 600, abs=1e-6)
    assert float(w) == pytest.approx(100 / 600, abs=1e-6)
    assert float(h) == pytest.approx(200 / 600, abs=1e-6)


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
