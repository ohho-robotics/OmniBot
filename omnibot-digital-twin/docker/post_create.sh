#!/bin/bash
# Runs once after the DevContainer is created (postCreateCommand).
# Installs workspace dependencies and builds the ROS 2 workspace.
set -e

cd /workspaces/OmniBot

echo "=== Installing rosdep dependencies ==="
source /opt/ros/jazzy/setup.bash
cd robot_ws
rosdep install --from-paths src --ignore-src -y --rosdistro jazzy

echo "=== Installing standalone Python packages ==="
cd /workspaces/OmniBot
pip3 install -e packages/yahboom_ros2 \
             -e packages/vla_serve \
             -e packages/robot_episode_dataset \
             -e packages/ros2_bev_stitcher \
             -e packages/mecanum_drive_ros2

echo "=== Building ROS 2 workspace ==="
cd /workspaces/OmniBot/robot_ws
colcon build --symlink-install

echo "=== Done! Source the workspace: ==="
echo "  source /workspaces/OmniBot/robot_ws/install/setup.bash"
