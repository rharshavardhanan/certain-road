import pytest

from certain_road.core.paths import repo_root
from certain_road.detect.train import (
    _check_data_yaml_has_no_calib_firewall_breach,
    load_train_config,
    resolve_data_yaml,
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


def test_relative_data_yaml_path_is_resolved_against_repo_root(tmp_path, monkeypatch):
    """Ultralytics resolves a relative `path` against its own `datasets_dir`,
    not the process cwd or the yaml's location — the repo root resolution
    here is what actually makes a portable, relative `path` work (D040)."""
    fake_repo_root = tmp_path / "fake_repo"
    (fake_repo_root / "data" / "processed" / "india" / "images" / "train").mkdir(parents=True)
    (fake_repo_root / "data" / "processed" / "india" / "images" / "val").mkdir(parents=True)
    monkeypatch.setattr("certain_road.detect.train.repo_root", lambda: fake_repo_root)

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_yaml = config_dir / "data.yaml"
    data_yaml.write_text("path: data/processed/india\ntrain: images/train\nval: images/val\n")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    resolved_yaml = resolve_data_yaml(data_yaml, out_dir)
    resolved_cfg = load_train_config(resolved_yaml)

    assert resolved_cfg["path"] == str(fake_repo_root / "data" / "processed" / "india")


def test_resolve_data_yaml_raises_clear_error_when_split_missing(tmp_path):
    data_yaml = tmp_path / "data.yaml"
    missing_root = tmp_path / "nonexistent" / "dataset"
    data_yaml.write_text(f"path: {missing_root}\ntrain: images/train\nval: images/val\n")

    with pytest.raises(FileNotFoundError) as excinfo:
        resolve_data_yaml(data_yaml, tmp_path)

    assert str(missing_root / "images" / "train") in str(excinfo.value)
