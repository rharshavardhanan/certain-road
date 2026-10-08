# Source once per terminal, from anywhere:  source ros/env.sh
# ROS 2 Jazzy, then the project's uv venv (certain_road, torch, ultralytics), then this
# workspace's overlay once `colcon build` has made one. Order matters: the venv's python3
# must come first on PATH, because the nodes' shebang is `env python3` (setup.cfg).
_cr_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
source "$_cr_root/.venv/bin/activate"
if [ -f "$_cr_root/ros/install/setup.bash" ]; then
  source "$_cr_root/ros/install/setup.bash"
fi
unset _cr_root
