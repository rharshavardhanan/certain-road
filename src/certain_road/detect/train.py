"""YOLOv8n training on Apple Silicon MPS.

Training happens here and only here. The Jetson is an inference target, never a
training device.
"""

from pathlib import Path

import yaml


def load_train_config(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def train(config_path: Path, data_yaml: Path, *, smoke: bool = False) -> Path:
    """Run training. `smoke=True` runs two epochs to prove the setup works."""
    import torch
    from ultralytics import YOLO

    cfg = load_train_config(config_path)

    if cfg["device"] == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("config requests MPS but it is unavailable")

    model_name = cfg.pop("model")
    if smoke:
        cfg |= {"epochs": 2, "name": f"{cfg['name']}_smoke", "exist_ok": True}

    model = YOLO(model_name)
    results = model.train(data=str(data_yaml), **cfg)
    return Path(results.save_dir)
