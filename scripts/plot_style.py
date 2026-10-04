"""Shared chart style for the static result figures (dataviz reference palette).

Categorical hues are assigned in the palette's validated order and follow the
*entity*, never its rank, so a model keeps its colour across every figure.
Text is set in ink, not series colour; grid and axes stay recessive.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]


def figure(width: float = 8.0, height: float = 5.0, **kw):
    fig, ax = plt.subplots(figsize=(width, height), facecolor=SURFACE, **kw)
    for a in ax if hasattr(ax, "__iter__") else [ax]:
        style_axes(a)
    return fig, ax


def style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK_2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)
    ax.title.set_color(INK)


def title(ax, text: str, sub: str | None = None) -> None:
    ax.set_title(text, loc="left", fontsize=12, color=INK, pad=22 if sub else 10)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK_2, va="bottom")


def save(fig, path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
