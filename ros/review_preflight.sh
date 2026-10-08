#!/usr/bin/env bash
# Review-day check: everything the demos need is on this Jetson. No GPU, ~5 s, no sudo.
# Run with:  bash ros/review_preflight.sh      Then follow ros/MENTOR-DEMO.md.
cd "$(dirname "$0")/.." || exit 1
ok=0; bad=0
check() {  # check "label" command...
  if eval "$2" >/dev/null 2>&1; then echo "  OK    $1"; ok=$((ok + 1)); else echo "  FAIL  $1"; bad=$((bad + 1)); fi
}

echo "certain-road review pre-flight ($(date +%F\ %H:%M))"
echo "-- system"
check "ROS 2 Jazzy installed" "test -f /opt/ros/jazzy/setup.bash"
check "Gazebo (ros_gz) installed" "test -d /opt/ros/jazzy/share/ros_gz_sim"
check "CAN bus vcan0 up (else: bash ros/install_gazebo_can.sh)" "ip link show vcan0 | grep -q UP"
check "project venv with CUDA torch" ".venv/bin/python -c 'import torch; assert torch.cuda.is_available()'"
echo "-- data and models"
check "Model P weights (sha256 = results/LOCKED)" "sha256sum runs/kaggle/roadsight-train-p/export/model_p/best.pt | grep -q b336e44c5ba4d230106a561b9b1940d6898925d99aab31ea96572e3155329618"
check "Model B weights (sha256 = results/LOCKED)" "sha256sum runs/kaggle/roadsight-train-b/export/model_b/best.pt | grep -q f6177e36b75506de788536932b6e20a50216ebafe575fa8a761ce01cb29e6147"
check "real road video" "test -s data/video/2DV-cYmIvT4.mp4"
check "49 MuJoCo textures" "test \$(find data/raw/trial_textures -name '*.jpg' | wc -l) -eq 49"
check "drift reference list" "test -s data/yolo/india_val.txt"
check "Gazebo world poor_seed0" "test -s runs/gazebo/poor_seed0/world.sdf"
echo "-- builds"
check "ROS package certain_road_ros built" "test -d ros/install/certain_road_ros"
check "ROS package certain_road_gz built" "test -d ros/install/certain_road_gz"
echo "-- recordings (the backup if anything live is slow)"
check "MuJoCo survey drive" "test -s runs/demo_capture/mujoco_poor_seed0.mp4"
check "real road, Model P + B live" "test -s runs/demo_capture/real_road_120-180s.mp4"
check "ROS 2D closed loop" "ls runs/ros/capture/demo_*.mp4"
check "ROS real video + CAN in RViz" "ls runs/ros/capture/video_rviz_*.mp4"
check "Gazebo closed loop" "compgen -G 'runs/ros/capture/gazebo_closed_loop_*.mp4'"
echo "-- survey report"
check "three-road survey report (HTML)" "test -n \"\$(find runs/survey_environments -name '*.html' 2>/dev/null)\""

echo
echo "$ok passed, $bad failed"
[ "$bad" -eq 0 ] && echo "Ready. Open ros/MENTOR-DEMO.md for the order and commands."
exit "$bad"
