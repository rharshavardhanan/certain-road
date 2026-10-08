#!/usr/bin/env bash
# Gazebo Harmonic for ROS 2 Jazzy, and a virtual CAN bus vcan0, on the Jetson.
# Run with:  bash ros/install_gazebo_can.sh   (asks for your sudo password once)
# vcan0 does not survive a reboot: run this again after restarting the Jetson.
set -euo pipefail
trap 'echo; echo "!! install_gazebo_can.sh stopped at line $LINENO: $BASH_COMMAND" >&2' ERR
step() { echo; echo "==> $*"; }

sudo -v

step "installing Gazebo Harmonic and ros_gz (several hundred MB)"
sudo apt update
sudo apt install -y ros-jazzy-ros-gz ffmpeg

step "virtual CAN bus vcan0 (real CAN frames, no hardware)"
sudo modprobe vcan
ip link show vcan0 >/dev/null 2>&1 || sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
echo vcan | sudo tee /etc/modules-load.d/vcan.conf >/dev/null   # load the module at boot
ip -brief link show vcan0

echo
echo "Done. Check with:  gz sim --version   and   candump vcan0"
