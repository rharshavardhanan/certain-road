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
    from certain_road.detect.dataset.convert import SOURCE_TO_ID
    from certain_road.detect.dataset.voc import class_census

    xml_dir = raw_dir() / "RDD2022" / country / "train" / "annotations" / "xmls"
    counts = class_census(xml_dir)

    print(f"{'class':<24} {'count':>8}   status")
    for name, count in counts.most_common():
        status = "KEEP" if name in SOURCE_TO_ID else "DROP"
        print(f"{name:<24} {count:>8}   {status}")

    kept = sum(c for n, c in counts.items() if n in SOURCE_TO_ID)
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


@dataset_app.command("split")
def dataset_split(country: str = "India") -> None:
    """Build the deterministic four-way split and the ultralytics data yaml."""
    import yaml

    from certain_road.core.paths import processed_dir, raw_dir, repo_root
    from certain_road.detect.dataset.convert import ID_TO_CLASS
    from certain_road.detect.dataset.split import build_splits, materialise, write_manifest

    root = processed_dir() / country.lower()
    label_src = root / "labels_all"
    image_src = raw_dir() / "RDD2022" / country / "train" / "images"

    stems = sorted(p.stem for p in label_src.glob("*.txt"))
    if not stems:
        raise SystemExit(f"no labels in {label_src}; run `dataset convert` first")

    splits = build_splits(stems)
    reports = materialise(splits, image_src, label_src, root)
    write_manifest(splits, root / "splits.json")

    for name, names in splits.items():
        print(f"{name:<6} {len(names):>6}")

    print("\nmaterialised (requested vs. linked to disk):")
    any_skipped = False
    for name, report in reports.items():
        line = (
            f"  {name:<6} requested={report.requested:>6} "
            f"linked={report.linked:>6} skipped_missing_image={report.skipped_missing_image:>6}"
        )
        if report.skipped_missing_image:
            any_skipped = True
            line += "  <-- MISSING IMAGES ON DISK"
        print(line)
    if any_skipped:
        print(
            "\nsome stems had no matching image on disk; this is expected for RDD2022 "
            "(images without annotations) but confirm the counts above look right"
        )

    data_yaml = repo_root() / "configs" / "dataset" / f"rdd2022_{country.lower()}.yaml"
    data_yaml.parent.mkdir(parents=True, exist_ok=True)
    data_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(root),
                "train": "images/train",
                "val": "images/val",
                "names": {i: ID_TO_CLASS[i] for i in sorted(ID_TO_CLASS)},
            },
            sort_keys=False,
        )
    )
    print(f"\nwrote {data_yaml}")
    print("calib and test are deliberately absent from the yaml: ultralytics must never see them")


@STAGE_APPS["detect"].command("train")
def detect_train(smoke: bool = False, country: str = "India") -> None:
    """Train YOLOv8n. Use --smoke for a two-epoch setup check."""
    from certain_road.core.paths import repo_root
    from certain_road.detect.train import train

    save_dir = train(
        repo_root() / "configs" / "train" / "yolov8n.yaml",
        repo_root() / "configs" / "dataset" / f"rdd2022_{country.lower()}.yaml",
        smoke=smoke,
    )
    print(f"results -> {save_dir}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
