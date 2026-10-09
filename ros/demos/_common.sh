# Shared by the demo scripts: run from the repo root with ROS, the venv and the overlay.
# Environment overrides:  RVIZ=false (no RViz)   CAN_WINDOW=0 (no CAN terminal)
#                         DURATION=<s> (stop by itself after that many seconds)
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
REPO=$PWD
source ros/env.sh
export DISPLAY=${DISPLAY:-:1}
RVIZ=${RVIZ:-true}
# Two harmless warnings, silenced so the terminal stays readable in front of the mentor:
# OpenCV's bundled Qt looks for fonts it does not ship (only its window chrome uses them),
# and the venv sees Ubuntu's own matplotlib too, which only breaks 3D plots (never used).
export QT_QPA_FONTDIR=${QT_QPA_FONTDIR:-/usr/share/fonts/truetype/dejavu}
export PYTHONWARNINGS=${PYTHONWARNINGS:-"ignore:Unable to import Axes3D"}

can_window() {  # a second terminal showing every CAN frame decoded, live
  [ "${CAN_WINDOW:-1}" = 1 ] || return 0
  ip link show vcan0 >/dev/null 2>&1 || { echo "!! vcan0 is down: bash ros/install_gazebo_can.sh"; return 0; }
  gnome-terminal --title "CAN frames on vcan0 (decoded)" -- bash -c \
    "cd '$REPO' && source ros/env.sh && echo 'CAN 0x101 decoded (raw: candump -td vcan0)'; ros2 topic echo /can/decoded; exec bash" \
    >/dev/null 2>&1 &
}

run_launch() {  # run_launch <ros2 launch args...>: in front, or for DURATION seconds
  if [ -z "${DURATION:-}" ]; then ros2 launch "$@"; return; fi
  setsid ros2 launch "$@" & local l=$!
  sleep "$DURATION"; kill -TERM -- -"$l" 2>/dev/null
  for _ in $(seq 20); do kill -0 "$l" 2>/dev/null || break; sleep 1; done
  kill -KILL -- -"$l" 2>/dev/null; wait "$l" 2>/dev/null; return 0
}
