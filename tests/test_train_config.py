from certain_road.core.paths import repo_root
from certain_road.detect.train import load_train_config

CONFIG = repo_root() / "configs" / "train" / "yolov8n.yaml"


def test_config_loads_and_targets_mps():
    cfg = load_train_config(CONFIG)
    assert cfg["device"] == "mps", "must not silently train on CPU"
    assert cfg["model"] == "yolov8n.pt"


def test_required_keys_present():
    cfg = load_train_config(CONFIG)
    for key in ("epochs", "patience", "imgsz", "batch", "seed", "project", "name"):
        assert key in cfg, f"missing {key}"


def test_vertical_flip_is_disabled():
    """Road scenes have a fixed orientation; flipud would fabricate impossible views."""
    assert load_train_config(CONFIG)["flipud"] == 0.0
