import pytest

from certain_road.core.paths import repo_root
from certain_road.detect.train import (
    _check_data_yaml_has_no_calib_firewall_breach,
    load_train_config,
)

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


def test_data_yaml_with_calib_key_is_rejected(tmp_path):
    """calib feeding detector training would silently void every conformal guarantee."""
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("path: data\ntrain: images/train\nval: images/val\ncalib: images/calib\n")
    with pytest.raises(ValueError, match="calib"):
        _check_data_yaml_has_no_calib_firewall_breach(data_yaml)


def test_data_yaml_with_test_key_is_rejected(tmp_path):
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("path: data\ntrain: images/train\nval: images/val\ntest: images/test\n")
    with pytest.raises(ValueError, match="test"):
        _check_data_yaml_has_no_calib_firewall_breach(data_yaml)


def test_data_yaml_without_calib_or_test_is_accepted(tmp_path):
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("path: data\ntrain: images/train\nval: images/val\n")
    _check_data_yaml_has_no_calib_firewall_breach(data_yaml)  # must not raise
