"""Which torch device this machine can actually run on.

The configs name the MacBook's `mps` (CLAUDE.md). The Jetson has CUDA and no MPS
(D093, D094). Asking for a device the machine lacks falls back to the accelerator it
does have, so one config runs on both, and whatever records the device records the one
that ran. `cpu` is honoured exactly as asked: bit-reproducible evaluation depends on it.
"""

from __future__ import annotations


def available_device(preferred: str) -> str:
    import torch  # imported here: `core` must stay importable without torch

    if preferred == "cpu":
        return "cpu"
    if preferred == "mps" and torch.backends.mps.is_available():
        return "mps"
    if preferred.startswith("cuda") and torch.cuda.is_available():
        return preferred
    if torch.cuda.is_available():
        return "cuda:0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
