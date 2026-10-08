#!/usr/bin/env bash
# Gazebo Harmonic for ROS 2 Jazzy, and a virtual CAN bus vcan0, on the Jetson.
# Run with:  bash ros/install_gazebo_can.sh   (asks for your sudo password once)
# vcan0 comes back at every boot (systemd unit vcan0.service); this script is needed once.
set -euo pipefail
trap 'echo; echo "!! install_gazebo_can.sh stopped at line $LINENO: $BASH_COMMAND" >&2' ERR
step() { echo; echo "==> $*"; }

sudo -v

step "installing Gazebo Harmonic and ros_gz (several hundred MB)"
sudo apt update
sudo apt install -y ros-jazzy-ros-gz ffmpeg

step "virtual CAN bus vcan0 (real CAN frames, no hardware), brought up at every boot"
sudo tee /etc/systemd/system/vcan0.service >/dev/null <<'UNIT'
[Unit]
Description=Virtual CAN bus vcan0 for the certain-road demo
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/modprobe vcan
ExecStart=/bin/sh -c 'ip link show vcan0 >/dev/null 2>&1 || ip link add dev vcan0 type vcan'
ExecStart=/usr/sbin/ip link set up vcan0

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now vcan0.service
ip -brief link show vcan0

echo
echo "Done. Check with:  gz sim --version   and   candump vcan0"
