"""Single entrypoint. One sub-app per pipeline stage.

Stages are wired here and nowhere else; this module is the only place allowed
to know about more than one stage at a time.
"""

import typer

app = typer.Typer(
    name="certain-road",
    help="Road segment repair prioritisation under budget constraint.",
    no_args_is_help=True,
    add_completion=False,
)

STAGE_HELP = {
    "ingest": "Video/camera + track -> frames.parquet",
    "detect": "YOLOv8n training and inference",
    "assess": "Detections -> vision-estimated PCI per segment",
    "calibrate": "Fit or apply conformal intervals on segment vision-estimated PCI",
    "rsl": "Vision-estimated PCI interval -> remaining service life interval",
    "optimize": "Budget-constrained repair selection",
    "report": "Self-contained offline HTML report",
}

# Keep references so later tasks attach commands to the right stage rather than
# inventing parallel top-level apps.
STAGE_APPS: dict[str, typer.Typer] = {}
for _name, _help in STAGE_HELP.items():
    _sub = typer.Typer(name=_name, help=_help, no_args_is_help=True)
    STAGE_APPS[_name] = _sub
    app.add_typer(_sub, name=_name)

dataset_app = typer.Typer(
    name="dataset", help="RDD2022 acquisition and preparation.", no_args_is_help=True
)
app.add_typer(dataset_app, name="dataset")


@dataset_app.command("fetch")
def dataset_fetch(country: str = "India") -> None:
    """Download RDD2022 and extract one country."""
    from certain_road.core.paths import raw_dir
    from certain_road.detect.dataset.fetch import download_rdd2022, extract_country, sha256_of

    zip_path = download_rdd2022(raw_dir())
    checksum = sha256_of(zip_path)

    checks = raw_dir() / "CHECKSUMS.txt"
    checks.write_text(f"{checksum}  {zip_path.name}\n")
    print(f"sha256 {checksum}")
    print(
        "(recorded for our own reproducibility; Figshare publishes no checksum to verify against)"
    )

    out = extract_country(zip_path, country, raw_dir())
    images = len(list((out / "train" / "images").glob("*.jpg")))
    xmls = len(list((out / "train" / "annotations" / "xmls").glob("*.xml")))
    print(f"{country}: {images} train images, {xmls} annotations -> {out}")


@dataset_app.command("census")
def dataset_census(country: str = "India") -> None:
    """Count every class string in the annotations before converting anything."""
    from certain_road.core.paths import raw_dir
    from certain_road.detect.dataset.convert import CLASS_TO_ID
    from certain_road.detect.dataset.voc import class_census

    xml_dir = raw_dir() / "RDD2022" / country / "train" / "annotations" / "xmls"
    counts = class_census(xml_dir)

    print(f"{'class':<24} {'count':>8}   status")
    for name, count in counts.most_common():
        status = "KEEP" if name in CLASS_TO_ID else "DROP"
        print(f"{name:<24} {count:>8}   {status}")

    kept = sum(c for n, c in counts.items() if n in CLASS_TO_ID)
    print(f"\ntotal boxes {counts.total()}, keeping {kept}, dropping {counts.total() - kept}")


@dataset_app.command("convert")
def dataset_convert(country: str = "India") -> None:
    """Convert VOC XML annotations to YOLO label files."""
    from certain_road.core.paths import processed_dir, raw_dir
    from certain_road.detect.dataset.convert import convert_directory

    xml_dir = raw_dir() / "RDD2022" / country / "train" / "annotations" / "xmls"
    label_dir = processed_dir() / country.lower() / "labels_all"

    files, boxes, rejected = convert_directory(xml_dir, label_dir)
    print(f"converted {files} files, {boxes} boxes -> {label_dir}")
    if rejected:
        print("rejected:")
        for reason, count in rejected.most_common():
            print(f"  {reason:<30} {count}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
