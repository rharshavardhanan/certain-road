"""Single entrypoint. One sub-app per pipeline stage.

Stages are wired here and nowhere else; this module is the only place allowed
to know about more than one stage at a time.
"""

from pathlib import Path

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


def _country_stems(country: str, processed_dir, raw_dir) -> tuple[list[str], Path, Path]:
    root = processed_dir() / country.lower()
    label_src = root / "labels_all"
    image_src = raw_dir() / "RDD2022" / country / "train" / "images"
    stems = sorted(p.stem for p in label_src.glob("*.txt"))
    return stems, image_src, label_src


@dataset_app.command("split")
def dataset_split(
    country: str = "India",
    train_only: list[str] = typer.Option(
        [],
        "--train-only",
        help=(
            "Additional country whose annotated images join `train` only "
            "(no calib/test/val); repeatable. Building a multi-country split "
            "this way writes to a new output root and configs/dataset/"
            "rdd2022_multicountry.yaml (D041)."
        ),
    ),
) -> None:
    """Build the deterministic split and the ultralytics data yaml.

    With no `--train-only`, this is the single-country four-way split, exactly
    as before. With one or more `--train-only <Country>`, `country` still gets
    the ordinary four-way split (unchanged) and every `--train-only` country's
    stems join `train` alone — never four-way split, since their calib/test
    portions would never be used (D041).
    """
    from certain_road.core.paths import processed_dir, raw_dir, repo_root
    from certain_road.detect.dataset.split import (
        build_multicountry_splits,
        build_splits,
        materialise,
        materialise_multicountry,
        write_data_yaml,
        write_manifest,
    )

    primary_stems, primary_image_src, primary_label_src = _country_stems(
        country, processed_dir, raw_dir
    )
    if not primary_stems:
        raise SystemExit(f"no labels for {country}; run `dataset convert` first")

    if not train_only:
        splits = build_splits(primary_stems)
        reports = materialise(
            splits, primary_image_src, primary_label_src, processed_dir() / country.lower()
        )
        out_root = processed_dir() / country.lower()
        data_yaml = repo_root() / "configs" / "dataset" / f"rdd2022_{country.lower()}.yaml"
    else:
        stem_sources: dict[str, tuple[Path, Path]] = {
            stem: (primary_image_src, primary_label_src) for stem in primary_stems
        }
        non_primary_stems: list[str] = []
        for extra_country in train_only:
            stems, image_src, label_src = _country_stems(extra_country, processed_dir, raw_dir)
            if not stems:
                raise SystemExit(f"no labels for {extra_country}; run `dataset convert` first")
            non_primary_stems += stems
            stem_sources |= {stem: (image_src, label_src) for stem in stems}

        collisions = sorted(set(primary_stems) & set(non_primary_stems))
        if collisions:
            shown = collisions[:5]
            more = f" (+{len(collisions) - 5} more)" if len(collisions) > 5 else ""
            raise SystemExit(
                f"stem collision between {country} and --train-only countries: {shown}{more}"
            )

        splits = build_multicountry_splits(primary_stems, non_primary_stems)
        out_root = processed_dir() / "multicountry"
        reports = materialise_multicountry(splits, stem_sources, out_root)
        data_yaml = repo_root() / "configs" / "dataset" / "rdd2022_multicountry.yaml"

    write_manifest(splits, out_root / "splits.json")

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

    write_data_yaml(data_yaml, out_root, repo_root())
    print(f"\nwrote {data_yaml}")
    print("calib and test are deliberately absent from the yaml: ultralytics must never see them")


@STAGE_APPS["detect"].command("predict")
def detect_predict(
    weights: Path = typer.Option(..., "--weights", help="YOLO weights (.pt) to run inference with"),
    images: Path = typer.Option(..., "--images", help="Directory of images to run inference over"),
    out: Path = typer.Option(
        ..., "--out", help="Output path for the DetectionRow parquet artifact"
    ),
    class_map: str = typer.Option(
        "identity_3class",
        "--class-map",
        help="Named remap from configs/eval/class_maps.yaml (identity_3class for our own models)",
    ),
    conf: float = typer.Option(
        None,
        "--conf",
        help="Confidence floor; defaults to map_conf_floor in configs/eval/thresholds.yaml",
    ),
    device: str = typer.Option("mps", "--device"),
    imgsz: int = typer.Option(
        None,
        "--imgsz",
        help="Inference image size; defaults to imgsz in configs/eval/thresholds.yaml",
    ),
) -> None:
    """Run detection over a directory of images and write a DetectionRow artifact.

    Applies the named class remap before writing, so a 4-class external
    model's predictions land on our frozen 3-class taxonomy (see
    `configs/eval/class_maps.yaml`) instead of being scored against the wrong
    classes.
    """
    import torch

    from certain_road.artifacts.io import write_artifact
    from certain_road.artifacts.schema import DetectionRow
    from certain_road.detect.predict import load_class_map, load_thresholds, predict_to_detections

    if device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("device=mps requested but MPS is unavailable")

    thresholds = load_thresholds()
    resolved_conf = conf if conf is not None else thresholds["map_conf_floor"]
    resolved_imgsz = imgsz if imgsz is not None else thresholds["imgsz"]

    df = predict_to_detections(
        weights,
        images,
        class_map=load_class_map(class_map),
        conf=resolved_conf,
        device=device,
        imgsz=resolved_imgsz,
    )
    write_artifact(df, out, DetectionRow)
    n_frames_with_detections = df["frame_id"].nunique()
    print(f"{len(df)} detections over {n_frames_with_detections} frames with detections -> {out}")


@STAGE_APPS["detect"].command("eval")
def detect_eval(
    weights: Path = typer.Option(..., "--weights", help="YOLO weights (.pt) to evaluate"),
    split: str = typer.Option("test", "--split", help="Dataset split to evaluate on"),
    class_map: str = typer.Option(
        "identity_3class",
        "--class-map",
        help="Named remap from configs/eval/class_maps.yaml (identity_3class for our own models)",
    ),
    country: str = typer.Option(
        "india",
        "--country",
        help="Processed country whose split to read; only 'india' currently has calib/test (D041)",
    ),
    out: Path = typer.Option(None, "--out", help="Optional path to write the markdown report"),
    device: str = typer.Option("mps", "--device"),
) -> None:
    """Evaluate weights on a processed split: mAP + the operating-threshold sweep + latency.

    One inference pass at `map_conf_floor` (configs/eval/thresholds.yaml)
    feeds both the mAP computation and every row of the operating-point
    sweep -- the sweep filters that single prediction set by score rather
    than re-running inference per threshold. See `certain_road.detect.
    evaluate` for the metric-implementation rationale (D045).
    """
    import torch

    from certain_road.core.paths import processed_dir
    from certain_road.detect.dataset.convert import ID_TO_CLASS
    from certain_road.detect.evaluate import (
        compute_map,
        compute_operating_metrics,
        load_ground_truth,
        measure_latency,
        render_report,
    )
    from certain_road.detect.predict import load_class_map, load_thresholds, predict_to_detections

    if device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("device=mps requested but MPS is unavailable")

    images_dir = processed_dir() / country.lower() / "images" / split
    labels_dir = processed_dir() / country.lower() / "labels" / split
    thresholds = load_thresholds()

    gt = load_ground_truth(labels_dir, images_dir)
    preds = predict_to_detections(
        weights,
        images_dir,
        class_map=load_class_map(class_map),
        conf=thresholds["map_conf_floor"],
        device=device,
        imgsz=thresholds["imgsz"],
    )

    map_metrics = compute_map(preds, gt, num_classes=len(ID_TO_CLASS))
    operating_thresholds = thresholds["operating_thresholds"]
    operating_metrics = [
        compute_operating_metrics(preds, gt, conf=conf) for conf in operating_thresholds
    ]
    latency = measure_latency(
        weights,
        device=device,
        imgsz=thresholds["imgsz"],
        reps=thresholds["latency_reps"],
        warmup=thresholds["latency_warmup"],
    )

    n_images = len(list(labels_dir.glob("*.txt")))
    n_positive = gt["frame_id"].nunique()
    n_empty = n_images - n_positive

    report = render_report(
        weights=weights,
        country=country,
        split=split,
        class_map=class_map,
        n_images=n_images,
        n_positive=n_positive,
        n_empty=n_empty,
        map_metrics=map_metrics,
        operating_thresholds=operating_thresholds,
        operating_metrics=operating_metrics,
        latency=latency,
    )
    print(report)
    if out is not None:
        out.write_text(report)
        print(f"\nwrote {out}")


@STAGE_APPS["detect"].command("train")
def detect_train(
    smoke: bool = False,
    country: str = "India",
    config: Path = Path("configs/train/yolov8n.yaml"),
) -> None:
    """Train YOLOv8. Use --smoke for a two-epoch setup check.

    `--config` selects the training hyperparameter file (model, epochs, batch,
    ...); `--country` selects the dataset yaml, `configs/dataset/rdd2022_
    <country>.yaml` — pass `--country multicountry` for the D041 multi-country
    dataset.
    """
    from certain_road.core.paths import repo_root
    from certain_road.detect.train import train

    config_path = config if config.is_absolute() else repo_root() / config
    save_dir = train(
        config_path,
        repo_root() / "configs" / "dataset" / f"rdd2022_{country.lower()}.yaml",
        smoke=smoke,
    )
    print(f"results -> {save_dir}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
