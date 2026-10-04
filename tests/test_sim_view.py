"""`render`: the two-panel image `certain-road sim run` writes.

Nothing else calls it, and no test ran the CLI, so a broken render surfaced only when
someone ran a scenario by hand. This renders a real scenario run headless.
"""

from PIL import Image

from certain_road.core.paths import repo_root
from certain_road.driving.corridor import load_corridor
from certain_road.driving.decision import load_policy
from certain_road.sim.model import load_robot
from certain_road.sim.run import run_scenario
from certain_road.sim.scenario import SCENARIOS
from certain_road.sim.view import render

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_a_scenario_run_renders_to_a_two_panel_png(tmp_path):
    configs = repo_root() / "configs"
    robot = load_robot(configs / "sim" / "robot.yaml")
    corridor = load_corridor(configs / "driving" / "corridor.yaml")
    policy = load_policy(configs / "driving" / "decision.yaml")
    scenario = SCENARIOS["centre"]
    trace = run_scenario(scenario, robot, corridor, policy)

    out = render(scenario, trace, robot, corridor, tmp_path / "centre.png")

    assert out.read_bytes()[: len(PNG_SIGNATURE)] == PNG_SIGNATURE
    with Image.open(out) as image:
        width, height = image.size
    assert width > height  # world view and camera view side by side
