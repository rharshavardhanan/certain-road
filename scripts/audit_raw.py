"""T1 — audit RDD2022 as it ships, before any conversion touches it.

This runs on the **raw** four-class taxonomy (D00, D10, D20, D40) on purpose.
D038 merges D00 and D10 into `linear_crack` and D055 keeps that merge, but the
merge is only auditable if something counts the two classes separately first.
Every other stage in the project sees three classes; this one sees four.

Nothing here filters or repairs. A box outside the image and a `<size>` that
disagrees with the JPEG are both *reported*, because the point is to know what
the source contains before deciding what to do about it.
"""

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import raw_dir, repo_root  # noqa: E402
from certain_road.perception.dataset.voc import parse_voc  # noqa: E402

COUNTRIES = ["India", "Japan", "Norway", "United_States", "Czech",
             "China_MotorBike", "China_Drone"]

# Image counts are exact facts (D036); label counts carry a 1% tolerance (T1.4).
REFERENCE_IMAGES = {"India": 7706, "Japan": 10506, "Norway": 8161,
                    "United_States": 4805, "Czech": 2829,
                    "China_MotorBike": 1977, "China_Drone": 2401}

# D055's merged reference facts: linear_crack / alligator_crack / pothole.
# linear_crack is D00+D10, so the raw audit compares D00+D10 against it.
REFERENCE_MERGED = {
    "Japan": (8028, 6199, 2243), "India": (1623, 2021, 3187),
    "Czech": (1387, 161, 197), "Norway": (10300, 468, 461),
    "United_States": (10045, 834, 135), "China_MotorBike": (3774, 641, 235),
    "China_Drone": (2689, 293, 86),
}
LABEL_TOLERANCE = 0.01


def audit_country(country: str) -> dict:
    root = raw_dir() / "RDD2022" / country / "train"
    img_dir, xml_dir = root / "images", root / "annotations" / "xmls"

    img_stems = {p.stem for p in img_dir.glob("*.jpg")}
    xml_stems = {p.stem for p in xml_dir.glob("*.xml")}

    classes: Counter = Counter()
    degenerate = out_of_bounds = size_mismatch = parse_errors = 0
    mismatch_examples: list[dict] = []

    for xml_path in sorted(xml_dir.glob("*.xml")):
        try:
            ann = parse_voc(xml_path)
        except (ET.ParseError, ValueError) as exc:
            parse_errors += 1
            classes[f"PARSE_ERROR:{type(exc).__name__}"] += 1
            continue

        img_path = img_dir / f"{xml_path.stem}.jpg"
        real_w = real_h = None
        if img_path.exists():
            with Image.open(img_path) as im:      # header only, no decode
                real_w, real_h = im.size
            if (real_w, real_h) != (ann.width, ann.height):
                size_mismatch += 1
                if len(mismatch_examples) < 5:
                    mismatch_examples.append(
                        {"stem": xml_path.stem, "xml": [ann.width, ann.height],
                         "real": [real_w, real_h]})

        # Validate against the real size where we have it: a box is only truly
        # out of bounds relative to the pixels that exist, not to a <size> the
        # file may have got wrong.
        w = real_w if real_w is not None else ann.width
        h = real_h if real_h is not None else ann.height
        for obj in ann.objects:
            classes[obj.name] += 1
            if obj.xmax <= obj.xmin or obj.ymax <= obj.ymin:
                degenerate += 1
            if obj.xmin < 0 or obj.ymin < 0 or obj.xmax > w or obj.ymax > h:
                out_of_bounds += 1

    return {
        "country": country,
        "images": len(img_stems),
        "xmls": len(xml_stems),
        "images_without_xml": sorted(img_stems - xml_stems)[:20],
        "images_without_xml_count": len(img_stems - xml_stems),
        "xmls_without_image": sorted(xml_stems - img_stems)[:20],
        "xmls_without_image_count": len(xml_stems - img_stems),
        "raw_classes": dict(classes.most_common()),
        "boxes_total": sum(v for k, v in classes.items() if not k.startswith("PARSE_ERROR")),
        "degenerate_boxes": degenerate,
        "out_of_bounds_boxes": out_of_bounds,
        "size_mismatches": size_mismatch,
        "size_mismatch_examples": mismatch_examples,
        "parse_errors": parse_errors,
    }


def diff_rows(results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        c = r["country"]
        cls = r["raw_classes"]
        got_linear = cls.get("D00", 0) + cls.get("D10", 0)
        got = (got_linear, cls.get("D20", 0), cls.get("D40", 0))
        want = REFERENCE_MERGED[c]
        deltas = [g - w for g, w in zip(got, want, strict=True)]
        worst = max((abs(d) / w if w else 0.0) for d, w in zip(deltas, want, strict=True))
        rows.append({
            "country": c,
            "images_got": r["images"], "images_want": REFERENCE_IMAGES[c],
            "images_ok": r["images"] == REFERENCE_IMAGES[c],
            "D00": cls.get("D00", 0), "D10": cls.get("D10", 0),
            "linear_got": got_linear, "linear_want": want[0],
            "alligator_got": got[1], "alligator_want": want[1],
            "pothole_got": got[2], "pothole_want": want[2],
            "deltas": deltas, "worst_rel": round(worst, 5),
            "labels_ok": worst <= LABEL_TOLERANCE,
        })
    return rows


def main() -> int:
    out_dir = repo_root() / "results" / "T1"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for country in COUNTRIES:
        print(f"auditing {country} ...", flush=True)
        results.append(audit_country(country))

    rows = diff_rows(results)
    all_classes = sorted({k for r in results for k in r["raw_classes"]})

    payload = {"countries": results, "diff": rows, "class_names_seen": all_classes,
               "reference_images": REFERENCE_IMAGES,
               "reference_merged": {k: list(v) for k, v in REFERENCE_MERGED.items()},
               "label_tolerance": LABEL_TOLERANCE}
    (out_dir / "raw_audit.json").write_text(json.dumps(payload, indent=2))

    md = ["# T1 — RDD2022 raw audit", "",
          "Counts come from the source XML **before** any conversion. The raw",
          "four-class taxonomy is used here on purpose (D055): the D00/D10 merge",
          "is only auditable if something counts them separately first.", "",
          "## Per-country integrity", "",
          "| country | images | xmls | img w/o xml | xml w/o img | boxes |"
          " degenerate | out-of-bounds | size mismatch | parse errors |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['country']} | {r['images']} | {r['xmls']} | "
                  f"{r['images_without_xml_count']} | {r['xmls_without_image_count']} | "
                  f"{r['boxes_total']} | {r['degenerate_boxes']} | {r['out_of_bounds_boxes']} | "
                  f"{r['size_mismatches']} | {r['parse_errors']} |")

    md += ["", "## Every class name present, before filtering", "",
           "| country | " + " | ".join(all_classes) + " |",
           "|---" * (len(all_classes) + 1) + "|"]
    for r in results:
        md.append(f"| {r['country']} | " +
                  " | ".join(str(r["raw_classes"].get(c, 0)) for c in all_classes) + " |")

    md += ["", "## Diff against reference facts", "",
           f"Images must match exactly. Label counts carry a {LABEL_TOLERANCE:.0%} tolerance.",
           "`linear` is D00+D10 (D038/D055).", "",
           "| country | images | D00 | D10 | linear got/want |"
           " alligator got/want | pothole got/want | worst rel | verdict |",
           "|---|---|---|---|---|---|---|---|---|"]
    for d in rows:
        img = f"{d['images_got']}" + ("" if d["images_ok"] else f" ≠ {d['images_want']}")
        verdict = "OK" if d["images_ok"] and d["labels_ok"] else "CHECK"
        md.append(f"| {d['country']} | {img} | {d['D00']} | {d['D10']} | "
                  f"{d['linear_got']}/{d['linear_want']} | "
                  f"{d['alligator_got']}/{d['alligator_want']} | "
                  f"{d['pothole_got']}/{d['pothole_want']} | "
                  f"{d['worst_rel']:.5f} | {verdict} |")
    md += ["", "---", "",
           "Interpretation, image dimensions and the visual-QA notes are in",
           "`findings.md` alongside this file. This file is generated by",
           "`scripts/audit_raw.py` and is overwritten on every run; `findings.md`",
           "is authored and is not."]
    (out_dir / "raw_audit.md").write_text("\n".join(md) + "\n")

    print("\n" + "\n".join(md[-len(rows) - 3:]))
    bad = [d["country"] for d in rows if not (d["images_ok"] and d["labels_ok"])]
    print(f"\nwrote {out_dir}/raw_audit.json and .md")
    print("ALL COUNTRIES WITHIN TOLERANCE" if not bad else f"NEEDS REVIEW: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
