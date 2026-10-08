#!/usr/bin/env bash
# Backups for the review: record a demo's screen, or gather every recording into one folder.
#
#   bash ros/record_backup.sh video [start end]   ROS real-road video + CAN in RViz (default 150-170 s)
#   bash ros/record_backup.sh sim [seconds]       ROS 2D closed loop in RViz (default 60 s)
#   bash ros/record_backup.sh gazebo [metres]     Gazebo closed loop in RViz, CAN on (default 230 m)
#   bash ros/record_backup.sh collect             copy all recordings, reports and run logs
#                                                 into review_backup/<date>/ (plays offline)
#
# Recordings land in runs/backup/. Uses the shared heavy lock, so it waits for other GPU jobs.
cd "$(dirname "$0")/.." || exit 1
mode=${1:-collect}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p runs/backup
export DISPLAY=${DISPLAY:-:1} XAUTHORITY=${XAUTHORITY:-/run/user/1000/gdm/Xauthority}

record() {  # record <mp4> <command...>: screen capture for as long as the command runs
  local mp4=$1; shift
  setsid gst-launch-1.0 -e ximagesrc display-name="$DISPLAY" use-damage=false \
    ! video/x-raw,framerate=15/1 ! videoconvert ! x264enc speed-preset=ultrafast \
    tune=zerolatency bitrate=6000 ! h264parse ! mp4mux ! filesink location="$mp4" \
    > "${mp4%.mp4}.gst.log" 2>&1 &
  local g=$!
  "$@"
  sleep 2
  kill -INT -- -"$g" 2>/dev/null
  for _ in $(seq 20); do kill -0 "$g" 2>/dev/null || break; sleep 1; done
  kill -TERM -- -"$g" 2>/dev/null
  echo "recording -> $mp4"
}

launch_for() {  # launch_for <seconds|""> <ros2 launch args...>: stop by process group
  local secs=$1; shift
  setsid ros2 launch "$@" &
  local l=$!
  if [ -n "$secs" ]; then sleep "$secs"; kill -TERM -- -"$l" 2>/dev/null; fi
  wait "$l" 2>/dev/null
}

case "$mode" in
  video)
    source ros/env.sh
    record "runs/backup/ros_video_can_$stamp.mp4" flock /tmp/certain-road-heavy.lock \
      bash -c "$(declare -f launch_for); launch_for '' certain_road_ros video.launch.py \
      start:=${2:-150} end:=${3:-170} can:=auto rviz:=true"
    ;;
  sim)
    source ros/env.sh
    record "runs/backup/ros_sim_$stamp.mp4" flock /tmp/certain-road-heavy.lock \
      bash -c "$(declare -f launch_for); launch_for ${2:-60} certain_road_ros demo.launch.py"
    ;;
  gazebo)
    record "runs/backup/gazebo_closed_loop_$stamp.mp4" flock /tmp/certain-road-heavy.lock \
      bash runs/gazebo/closed_loop.sh "runs/gazebo/poor_seed0/backup_$stamp" "${2:-230}" \
      rtf:=0.3 can:=auto rviz:=true
    ;;
  collect)
    out="review_backup/$(date +%F)"
    mkdir -p "$out"
    for f in runs/demo_capture/*.mp4 runs/demo_capture/*.png runs/ros/capture/*.mp4 \
             runs/backup/*.mp4 runs/survey_environments/report.html \
             runs/gazebo/evidence_poor_seed0*/clip.mp4 runs/gazebo/poor_seed0/avoidance.json \
             results/dashboard/index.html ros/MENTOR-DEMO.md; do
      [ -e "$f" ] && cp -n "$f" "$out/$(echo "$f" | tr / _)"
    done
    du -sh "$out"; ls "$out" | wc -l | xargs echo "files:"
    ;;
  *) echo "usage: bash ros/record_backup.sh video|sim|gazebo|collect"; exit 2 ;;
esac
