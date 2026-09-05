"""Top-down render of a scenario run, beside the camera view the robot saw.

Two panels on purpose. The left panel is world truth; the right is what
`driving/corridor.py` actually reasoned over. Showing both is what makes the
projection auditable rather than something to take on faith.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: no display on the Jetson or in CI
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from certain_road.driving.corridor import Corridor, corridor_polygon  # noqa: E402
from certain_road.sim.model import Robot  # noqa: E402
from certain_road.sim.scenario import Scenario, Trace  # noqa: E402

_URGENCY_COLOUR = {"far": "#4C9F70", "near": "#E8A33D", "imminent": "#C8433B"}


def render(scenario: Scenario, trace: Trace, robot: Robot, corridor: Corridor, out: Path) -> Path:
    """Write a two-panel PNG. Returns the path written."""
    fig, (world, cam) = plt.subplots(1, 2, figsize=(13, 6))

    # ---- left: world, top-down -------------------------------------------
    for p in scenario.potholes:
        world.add_patch(mpatches.Circle((p.x, p.y), p.radius, color="#333", alpha=0.85))

    xs = [s.x for s in trace.states]
    ys = [s.y for s in trace.states]
    world.plot(xs, ys, "-", color="#888", lw=1, zorder=1)
    for s, ip, urg in zip(trace.states, trace.in_path, trace.urgency, strict=True):
        world.plot(
            s.x,
            s.y,
            "o",
            ms=5,
            color=_URGENCY_COLOUR.get(urg, "#BBB") if ip else "#BBB",
            zorder=2,
        )

    last = trace.states[-1]
    world.add_patch(
        mpatches.Rectangle(
            (last.x - robot.length_m / 2, last.y - robot.width_m / 2),
            robot.length_m,
            robot.width_m,
            color="#2B5FA8",
            alpha=0.9,
        )
    )
    world.set_aspect("equal")
    world.set_xlabel("x forward (m)")
    world.set_ylabel("y left (m)")
    world.set_title(f"world — scenario '{scenario.name}'")
    world.grid(alpha=0.25)
    world.legend(
        handles=[
            mpatches.Patch(color="#BBB", label="not in path"),
            mpatches.Patch(color=_URGENCY_COLOUR["far"], label="in path · far"),
            mpatches.Patch(color=_URGENCY_COLOUR["near"], label="in path · near"),
            mpatches.Patch(color=_URGENCY_COLOUR["imminent"], label="in path · imminent"),
        ],
        loc="upper left",
        fontsize=8,
    )

    # ---- right: the camera frame the corridor actually judged -------------
    idx = next((i for i, v in enumerate(trace.in_path) if v), len(trace.states) - 1)
    det = trace.detections[idx]
    poly = corridor_polygon(corridor, robot.camera.img_w, robot.camera.img_h)
    cam.add_patch(mpatches.Polygon(poly, closed=True, alpha=0.20, color="#2B5FA8"))
    if det is not None:
        cam.add_patch(
            mpatches.Rectangle(
                (det.x1, det.y1),
                det.x2 - det.x1,
                det.y2 - det.y1,
                fill=False,
                lw=2,
                color=_URGENCY_COLOUR.get(trace.urgency[idx], "#C8433B"),
            )
        )
    cam.set_xlim(0, robot.camera.img_w)
    cam.set_ylim(robot.camera.img_h, 0)  # image coords: y grows downward
    cam.set_aspect("equal")
    cam.set_title(f"camera frame {idx} — in_path={trace.in_path[idx]} urgency={trace.urgency[idx]}")
    cam.set_xlabel("u (px)")
    cam.set_ylabel("v (px)")

    fig.suptitle(scenario.description, fontsize=9, y=0.02)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out
