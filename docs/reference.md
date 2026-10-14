# OmniBot reference

Detailed notes moved from the top-level README. Back to [README](../README.md).

## Needs hardware / needs GPU

| Feature | Needs | Evidence |
|---|---|---|
| `ohho sim --robot omnibot` | Neither | [ohho-os 1.1.2](https://pypi.org/project/ohho-os/1.1.2/) and the docs-test job in [ci.yml](../.github/workflows/ci.yml) |
| Colcon build and test of `src/` | Neither | [src/](../src/) and the `ros` job in [ci.yml](../.github/workflows/ci.yml). That job needs ROS 2 Jazzy. |
| Kinematics, Yahboom codec, BEV homography, arm tick math, arm command safety (joint limits, 0.15 rad/cycle, 200 ms hold, e-stop torque latch), policy inference guards (black/missing frame refusal, latency drop, 0.15 rad/cycle arm clamp), learning engine, agent engine | Neither | The `cpu` job in [ci.yml](../.github/workflows/ci.yml) runs `pytest omnibot-ros2/omnibot_arm/test omnibot-ai-ros2/omnibot_lerobot/test`. Those tests do not start ROS or the arm. |
| Xbox teleop, cameras, arm, LeRobot recording | Robot | [robot_with_joy.launch.py](../omnibot-ros2/omnibot_bringup/launch/robot_with_joy.launch.py), [perception.launch.py](../omnibot-ros2/omnibot_bringup/launch/perception.launch.py), [arm.launch.py](../omnibot-ros2/omnibot_arm/launch/arm.launch.py), [teleop_record.launch.py](../omnibot-ai-ros2/omnibot_lerobot/launch/teleop_record.launch.py) |
| Nav2 and SLAM on the real robot | Robot | [omnibot_navigation](../omnibot-ros2/omnibot_navigation/). Not run on hardware for this change. |
| Nav2 + `slam_toolbox` in the Gazebo apartment world | Neither | [Nav2 + slam_toolbox in Gazebo](../README.md#nav2--slam_toolbox-in-gazebo-ohh-30), the [`nav-sim`](../.github/workflows/nav-sim.yml) workflow, and the committed [run log](../omnibot-ros2/omnibot_navigation/docs/nav_sim_runs_local_log.txt). Needs ROS 2 Jazzy and Gazebo Harmonic. |
| Gazebo compose files | Neither | [docker-compose.yml](../omnibot-digital-twin/docker/docker-compose.yml) runs headless Gazebo. [docker-compose.gpu.yml](../omnibot-digital-twin/docker/docker-compose.gpu.yml) is an optional NVIDIA overlay. The docs-test job does not start compose. |
| Gazebo Harmonic `sim.launch.py` | Neither | [sim.launch.py](../omnibot-ros2/omnibot_bringup/launch/sim.launch.py) and the `sim-smoke` job in [ci.yml](../.github/workflows/ci.yml). That job needs ROS 2 Jazzy and Gazebo Harmonic. The launch does not exit, so docs-test skips it. |
| OpenVLA / SmolVLA weights | GPU | [vla_engine/README.md](../omnibot-ai-engines/vla_engine/README.md) and [requirements.txt](../omnibot-ai-engines/vla_engine/requirements.txt) (`torch`) |
| Isaac Lab RL | GPU | [rl_engine/README.md](../omnibot-ai-engines/rl_engine/README.md) and [requirements.txt](../omnibot-ai-engines/rl_engine/requirements.txt) (`isaaclab`, `onnxruntime-gpu`) |
| Android controller | Robot | [omnibot-android/](../omnibot-android/). Building it needs the Android SDK and JDK 17 ([`build.gradle.kts`](../omnibot-android/build.gradle.kts)), which is separate from a desktop GPU. |
| Quest teleop | Robot | [omnibot-vr/](../omnibot-vr/). Unity **6000.5.2f1** is pinned in [`ProjectSettings/ProjectVersion.txt`](../omnibot-vr/ProjectSettings/ProjectVersion.txt). |


## Gazebo Harmonic simulation

One command starts Gazebo Harmonic, spawns `omnibot_description`, and bridges the base. The default is headless (`gui:=false`), which is what the `sim-smoke` job runs. The launch does not exit, so docs-test skips it.

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch omnibot_bringup sim.launch.py world:=flat
```

`world:=apartment` loads a single room with a kitchen (counter, stove, fridge), a desk, and a door. Launch file: [`omnibot-ros2/omnibot_bringup/launch/sim.launch.py`](../omnibot-ros2/omnibot_bringup/launch/sim.launch.py). The mecanum chassis is driven in the plane (`drive:=planar` by default; `drive:=mecanum` selects the MecanumDrive plugin). Sensors in this launch are a 2D lidar, the front RGB camera, and the IMU.

The VR profile is [`sim_vr.launch.py`](../omnibot-ros2/omnibot_bringup/launch/sim_vr.launch.py). It includes this launch with `world:=apartment` and `vr:=true`, so Gazebo follows `/cmd_vel/out`. rosbridge and `web_video_server` bind `127.0.0.1` unless `rosbridge_address` is set with the gateway off. The shared topic contract is [vr.md](vr.md).

`ros_gz_bridge` topics. `rosbridge:=true` (the default) also starts `rosbridge_websocket` on port 9090. The sim-smoke test passes `rosbridge:=false` and does not start rosbridge:

| Topic | Type |
|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` |
| `/odom` | `nav_msgs/msg/Odometry` |
| `/scan` | `sensor_msgs/msg/LaserScan` |
| `/imu` | `sensor_msgs/msg/Imu` |
| `/camera/front/image_raw` | `sensor_msgs/msg/Image` |
| `/camera/front/camera_info` | `sensor_msgs/msg/CameraInfo` |
| `/tf` (`odom` -> `base_footprint`, added for Nav2 and `slam_toolbox`) | `tf2_msgs/msg/TFMessage` |

Bridge config: [`omnibot-ros2/omnibot_bringup/config/sim_bridge.yaml`](../omnibot-ros2/omnibot_bringup/config/sim_bridge.yaml).

The headless launch test [`omnibot-ros2/omnibot_bringup/test/test_sim_launch.py`](../omnibot-ros2/omnibot_bringup/test/test_sim_launch.py) checks that `/odom`, `/scan`, `/imu`, and `/camera/front/image_raw` publish within 30 s and that `/cmd_vel` moves the robot at least 0.2 m. The `sim-smoke` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs it on `ros:jazzy`.

Eight frames from `/camera/front/image_raw` saved by that test (`OMNIBOT_SIM_FRAME_DIR`) while it published `/cmd_vel` in `world:=flat`. The red box is the `marker` model in [`flat.sdf`](../omnibot-ros2/omnibot_bringup/worlds/flat.sdf):

<p align="center">
  <img src="../assets/omnibot_gazebo_flat.gif" width="320" alt="Front camera frames from the flat Gazebo world while the robot drives"/>
</p>

## Teleop from the website

The OhhO website's Connect page can drive the sim over rosbridge. Start the flat Gazebo world, then open Connect and set the ROSBridge URL to `ws://localhost:9090`. rosbridge listens on localhost only by default; `rosbridge_address:=0.0.0.0` exposes it on the network without authentication. The launch does not exit, so the docs-test job skips this fence.

```bash
ros2 launch omnibot_bringup sim.launch.py world:=flat
```

`/cmd_vel` moves the base, `/odom` publishes, and `/camera/front/image_raw` publishes when the camera sensor starts. `world:=apartment` stays the furnished world.

The requirement files below pull GPU stacks. Docs-test skips them.

```bash
pip install -r omnibot-ai-engines/vla_engine/requirements.txt
pip install -r omnibot-ai-engines/rl_engine/requirements.txt
```

## Bring-up control mode

`mobile_manipulation.launch.py` starts `teleop_safety`, `cmd_vel_mux`, and `arm_cmd_mux` in `teleop`. Clients publish `/cmd_vel/teleop_raw`; `teleop_safety` publishes `/cmd_vel/teleop`, which the mux forwards. Nav2, VLA, and RL base commands are not forwarded until `/control_mode` is `vla`, `nav2`, or `rl_nav`. `/arm/joint_commands/teleop` (Quest VR hand IK and Android joint sliders) is forwarded in `teleop` while `/emergency_stop` is false, and held in `vla`, `nav2`, and `rl_nav`. `/arm/joint_commands/policy` (`policy_node`) and `/arm/joint_commands/rl` stay held in `teleop`. `/arm/joint_commands` is a deprecated alias of the policy input for one release and is held in teleop the same way. Switching `/control_mode` between any two different modes (teleop→autonomous, autonomous→teleop, or autonomous→autonomous) publishes a zero Twist to stop the base on that callback so the previous source's latched velocity does not run away. Setting `/control_mode` back to `teleop` stops the policy and RL arm streams on that callback, forwards `/cmd_vel/teleop`, and forwards `/arm/joint_commands/teleop`. Publishing `/emergency_stop` true stops base and arm outputs, including teleop, on that callback.

| Arm input | Who publishes | Forwarded when |
|---|---|---|
| `/arm/joint_commands/teleop` | `teleop_safety` (clients publish `/arm/joint_commands/teleop_raw`) | `/control_mode` is `teleop` and `/emergency_stop` is false |
| `/arm/joint_commands/policy` | `policy_node` | `vla` or `nav2`, arm source `policy`, e-stop clear |
| `/arm/joint_commands` | deprecated alias of the policy input (one release) | same gate as `/arm/joint_commands/policy` |
| `/arm/joint_commands/rl` | `rl_arm_node` | `rl_nav`, arm source `rl_arm`, e-stop clear |
| `/arm/joint_commands/out` | `arm_cmd_mux` | the selected source above; `arm_driver_node` subscribes |

`hybrid_robot.launch.py` and `omnibot_pi.launch.py` still pass `default_mode:=nav2` for the base mux. This gate was unit-tested here without ROS 2. It was not run with `ros2 launch`, Gazebo, or a robot.
