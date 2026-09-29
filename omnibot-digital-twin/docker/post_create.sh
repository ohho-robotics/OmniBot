#!/bin/bash
# Runs once after the DevContainer is created (postCreateCommand).
# Installs workspace dependencies and builds the ROS 2 workspace.
set -e

cd /workspaces/OmniBot

echo "=== Installing rosdep dependencies ==="
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -y --rosdistro jazzy \
  --dependency-types=build \
  --dependency-types=buildtool \
  --dependency-types=build_export \
  --dependency-types=buildtool_export \
  --dependency-types=exec \
  --dependency-types=test

echo "=== Installing standalone Python packages that live in this repo ==="
pip3 install -e mecanum-kinematics -e yahboom-python-driver

echo "=== Building ROS 2 workspace ==="
colcon build --symlink-install

echo "=== Done! Source the workspace: ==="
echo "  source /workspaces/OmniBot/install/setup.bash"
