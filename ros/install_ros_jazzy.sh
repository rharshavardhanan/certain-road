#!/usr/bin/env bash
# ROS 2 Jazzy install for the Jetson (Ubuntu 24.04 / JetPack 7.2), following
# docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html (ros2-apt-source method).
# Run with:  bash ros/install_ros_jazzy.sh   (asks for your sudo password once)
set -euo pipefail
trap 'echo; echo "!! install_ros_jazzy.sh stopped at line $LINENO: $BASH_COMMAND" >&2' ERR
step() { echo; echo "==> $*"; }

sudo -v

# 1. 8 GB swapfile: the Orin Nano has 7.3 GB RAM and no swap, and RViz + torch + VS Code
#    will run it out. Remove later with: sudo swapoff /swapfile && sudo rm /swapfile
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 8G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 2. ROS apt source (official ros2-apt-source package)
step "apt update"
sudo apt update
sudo apt install -y software-properties-common curl

# The docs read the version from api.github.com, but this network is over GitHub's
# unauthenticated API rate limit ("API rate limit exceeded"), which made the old line
# fail silently. The releases/latest redirect gives the same tag without the API.
step "finding the latest ros2-apt-source release"
ROS_APT_SOURCE_VERSION=$(curl -fsI https://github.com/ros-infrastructure/ros-apt-source/releases/latest \
  | grep -i '^location:' | tr -d '\r' | sed 's#.*/tag/##')
if [ -z "$ROS_APT_SOURCE_VERSION" ]; then
  echo "!! could not read the ros2-apt-source version from GitHub" >&2; exit 1
fi
echo "ros2-apt-source $ROS_APT_SOURCE_VERSION"
CODENAME=$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})
step "downloading ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${CODENAME}_all.deb"
curl -fL -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${CODENAME}_all.deb"
dpkg-deb --info /tmp/ros2-apt-source.deb >/dev/null   # a real .deb, not an error page
sudo dpkg -i /tmp/ros2-apt-source.deb
sudo apt update

# 3. ROS 2 Jazzy desktop (rclpy, rviz2, rqt_graph, demo nodes) + colcon + the message
#    packages the demo needs. No Gazebo today.
step "installing ROS 2 Jazzy (a few GB; 10-20 minutes)"
sudo apt install -y \
  ros-jazzy-desktop \
  ros-dev-tools \
  ros-jazzy-vision-msgs \
  ros-jazzy-cv-bridge \
  python3-opencv

# 4. Source ROS in every new shell
grep -qxF 'source /opt/ros/jazzy/setup.bash' ~/.bashrc || echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc

echo
echo "ROS 2 Jazzy installed. Open a NEW terminal, then test:"
echo "  ros2 run demo_nodes_cpp talker      # terminal 1"
echo "  ros2 run demo_nodes_py listener     # terminal 2"
