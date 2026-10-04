"""Repository-relative path resolution.

Every path in the project derives from here, so nothing depends on the
current working directory.
"""

from pathlib import Path


def repo_root() -> Path:
    """Walk upward from this file until the directory holding pyproject.toml."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("repository root not found: no pyproject.toml in any parent")


def data_dir() -> Path:
    return repo_root() / "data"


def raw_dir() -> Path:
    return data_dir() / "raw"


def processed_dir() -> Path:
    return data_dir() / "processed"
