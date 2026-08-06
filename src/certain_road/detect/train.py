"""YOLOv8n training on Apple Silicon MPS.

Training happens here and only here. The Jetson is an inference target, never a
training device.
"""

import tempfile
from pathlib import Path

import yaml

from certain_road.core.paths import repo_root

# Keys that must never appear in a data yaml handed to the detector trainer.
# `configs/dataset/*.yaml` is a checked-in, hand-editable file with no other
# validation before `detect train` consumes it; either key here feeding
# training would silently void every conformal guarantee in the project (D009).
FORBIDDEN_DATA_YAML_KEYS = ("calib", "test")

# Splits `detect train` requires to be present under the resolved data root
# before handing anything to ultralytics.
REQUIRED_SPLITS = ("train", "val")


def load_train_config(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def _check_data_yaml_has_no_calib_firewall_breach(data_yaml: Path) -> None:
    data_cfg = yaml.safe_load(Path(data_yaml).read_text())
    found = [key for key in FORBIDDEN_DATA_YAML_KEYS if key in data_cfg]
    if found:
        raise ValueError(
            f"{data_yaml} contains forbidden key(s) {found}: calib/test must never "
            "reach detector training, or every conformal guarantee is silently voided"
        )


def resolve_data_yaml(data_yaml: Path, tmp_dir: Path) -> Path:
    """Resolve a possibly-relative `path` and write a self-contained copy.

    Ultralytics resolves a relative data-yaml `path` against its own
    `datasets_dir` setting (`~/PROJECTS/datasets` on this machine), never
    against the process working directory or the yaml's own location (D040).
    A committed config must still keep `path` relative for portability, so we
    resolve it here against the repo root and hand ultralytics an absolute,
    disposable copy instead of mutating the committed file.
    """
    data_cfg = yaml.safe_load(Path(data_yaml).read_text())
    raw_path = Path(data_cfg["path"])
    resolved_root = raw_path if raw_path.is_absolute() else repo_root() / raw_path

    for split in REQUIRED_SPLITS:
        split_dir = resolved_root / "images" / split
        if not split_dir.is_dir():
            raise FileNotFoundError(
                f"{data_yaml} declares path={data_cfg['path']!r}, resolved to "
                f"{resolved_root}, but {split_dir} does not exist. Run "
                f"`certain-road dataset split` or fix `path` in {data_yaml}."
            )

    resolved_cfg = data_cfg | {"path": str(resolved_root)}
    resolved_yaml = tmp_dir / f"resolved_{data_yaml.name}"
    resolved_yaml.write_text(yaml.safe_dump(resolved_cfg, sort_keys=False))
    return resolved_yaml


def train(config_path: Path, data_yaml: Path, *, smoke: bool = False) -> Path:
    """Run training. `smoke=True` runs two epochs to prove the setup works."""
    import torch
    from ultralytics import YOLO

    _check_data_yaml_has_no_calib_firewall_breach(data_yaml)
    cfg = load_train_config(config_path)

    if cfg["device"] == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("config requests MPS but it is unavailable")

    model_name = cfg.pop("model")
    if smoke:
        cfg |= {"epochs": 2, "name": f"{cfg['name']}_smoke", "exist_ok": True}

    with tempfile.TemporaryDirectory() as tmp:
        resolved_yaml = resolve_data_yaml(data_yaml, Path(tmp))
        model = YOLO(model_name)
        results = model.train(data=str(resolved_yaml), **cfg)
    return Path(results.save_dir)
