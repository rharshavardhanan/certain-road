"""available_device: the configured device where it exists, else this machine's accelerator."""

import pytest

torch = pytest.importorskip("torch")

from certain_road.core.device import available_device  # noqa: E402


def machine(monkeypatch, *, cuda: bool, mps: bool) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: cuda)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: mps)


@pytest.mark.parametrize(
    ("preferred", "cuda", "mps", "expected"),
    [
        ("mps", False, True, "mps"),  # the MacBook, as configured
        ("mps", True, False, "cuda:0"),  # the Jetson, given the Mac's config
        ("mps", False, False, "cpu"),
        ("cuda:0", True, False, "cuda:0"),
        ("cuda:0", False, True, "mps"),
        ("cpu", True, True, "cpu"),  # cpu is honoured: reproducible evaluation needs it
    ],
)
def test_available_device(monkeypatch, preferred, cuda, mps, expected):
    machine(monkeypatch, cuda=cuda, mps=mps)
    assert available_device(preferred) == expected
