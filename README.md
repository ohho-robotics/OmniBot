<div align="center">
  <h1>OmniBot</h1>
  <p>Mecanum mobile manipulator: ROS 2 Jazzy drivers, kinematics, and a CPU-side agent loop.</p>

  <p align="center">
    <img src="assets/PXL_20260505_121303728.jpg" width="49%" alt="OmniBot base and arm" />
    <img src="assets/PXL_20260505_121328008.jpg" width="49%" alt="OmniBot side view" />
  </p>

  <p align="center">
    <img src="assets/Omnibot_demo1.gif" width="49%" alt="OmniBot driving" />
    <img src="assets/Omnibot_demo2.gif" width="49%" alt="OmniBot arm motion" />
  </p>

  <p align="center">
    <a href="https://github.com/ohho-robotics/OmniBot/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/ohho-robotics/OmniBot/ci.yml?branch=main&label=CI" alt="CI status for the main branch"/></a>
    &nbsp;
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue" alt="Apache-2.0"/></a>
  </p>
</div>

OmniBot is the public robot repo for OhhO. The photos and GIFs above are the physical robot. The commands below are what a fresh clone can run without that robot.

## CPU-only demo

About five minutes. No ROS, no GPU, no robot. CI runs this block on every pull request.

<!-- ci-commands: cpu -->
```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e mecanum-kinematics -e omnibot-ai-engines/learning_engine -e omnibot-ai-engines/agent_engine -e yahboom-python-driver pytest numpy
pytest mecanum-kinematics/tests yahboom-python-driver/tests ros2-bev-stitcher/tests omnibot-ros2/omnibot_arm/test -q
python -m unittest discover -s omnibot-ai-engines/learning_engine/tests -t omnibot-ai-engines
python -m unittest discover -s omnibot-ai-engines/agent_engine/tests -t omnibot-ai-engines
PYTHONPATH=omnibot-ai-engines pytest omnibot-ai-engines/data_engine/tests -q
python scripts/cpu_demo.py
```
<!-- /ci-commands -->

`scripts/cpu_demo.py` drives the mecanum model forward at 0.30 m/s, encodes a Yahboom motion packet, and completes one scripted agent goal ("go to the kitchen"). It does not talk to hardware.

### Roadmap: `ohho-os`

`pip install ohho-os` and `ohho sim` are not on PyPI. That install is waiting on OHH-20. Do not treat it as a working command.

## ROS 2 path

Ubuntu 24.04 with ROS 2 Jazzy already installed. `src/` is 13 symlinks to the packages in this repo. CI runs this block in `ros:jazzy-ros-base-noble`.

<!-- ci-commands: ros -->
```bash
sudo apt-get update
sudo apt-get install -y python3-colcon-common-extensions python3-rosdep python3-pytest
sudo rosdep init || true
rosdep update
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -y --rosdistro jazzy \
  --dependency-types=build \
  --dependency-types=buildtool \
  --dependency-types=build_export \
  --dependency-types=buildtool_export \
  --dependency-types=exec \
  --dependency-types=test
colcon build --symlink-install
source install/setup.bash
colcon test --event-handlers console_direct+ --return-code-on-test-failure
colcon test-result --verbose
```
<!-- /ci-commands -->

## Needs hardware or a GPU

These trees are in the repo. They are not started by the commands above.

| What | Where | Needs |
|---|---|---|
| Base driver and Xbox teleop | `omnibot-ros2/omnibot_bringup` | Raspberry Pi, Yahboom board on serial, controller |
| Arm and LeRobot episode recording | `omnibot-ros2/omnibot_arm`, `omnibot-ai-ros2/omnibot_lerobot` | SO-101 arm, cameras. A public recording video is Roadmap |
| Nav2 and SLAM | `omnibot-ros2/omnibot_navigation` | Robot or Gazebo, plus the apt packages the ROS block installs |
| Gazebo compose | `omnibot-digital-twin/docker/docker-compose.yml` | Docker. There is no `.devcontainer` in this repo |
| OpenVLA server | `omnibot-ai-engines/vla_engine` | NVIDIA GPU and model weights. Not installed by the CPU demo |
| Isaac RL training | `omnibot-ai-engines/rl_engine` | Isaac Sim and a GPU |
| Android controller | `omnibot-android/` | Android SDK, JDK 17, a device, ROSBridge on the robot |
| Quest teleop | `omnibot-vr/` | Unity `6000.5.2f1` (see `ProjectSettings/ProjectVersion.txt`), a headset |

ONNX policy playback and a LeRobot record session are not part of CI. Code for both is in the tree. A video of them running is Roadmap.

## Layout

| Directory | What it is |
|---|---|
| `src/` | Colcon workspace (symlinks) |
| `omnibot-ros2/` | Driver, arm, description, bringup, Nav2, hybrid mux |
| `omnibot-ai-ros2/` | VLA, LeRobot, RL, and orchestration nodes |
| `omnibot-ai-engines/` | Numpy learning and agent engines, plus GPU training code |
| `mecanum-kinematics/` | Wheel inverse and forward kinematics |
| `yahboom-python-driver/` | Yahboom serial protocol |
| `ros2-bev-stitcher/` | Bird's-eye homography |
| `omnibot-digital-twin/` | Gazebo world and compose files |
| `omnibot-android/` | Kotlin controller |
| `omnibot-vr/` | Unity Quest project |

## License

[Apache-2.0](LICENSE) for OhhO code in this repository. Vendored Meta XR SDK and CoplayDev unity-mcp packages keep their own licences. See [NOTICE](NOTICE).
