"""YOLOv8n training on Apple Silicon MPS.

Training happens here and only here. The Jetson is an inference target, never a
training device.
"""

from pathlib import Path

import yaml

# Keys that must never appear in a data yaml handed to the detector trainer.
# `configs/dataset/*.yaml` is a checked-in, hand-editable file with no other
# validation before `detect train` consumes it; either key here feeding
# training would silently void every conformal guarantee in the project (D009).
FORBIDDEN_DATA_YAML_KEYS = ("calib", "test")


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

    model = YOLO(model_name)
    results = model.train(data=str(data_yaml), **cfg)
    return Path(results.save_dir)
