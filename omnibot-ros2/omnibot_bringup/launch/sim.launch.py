# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""Headless Gazebo Harmonic bringup for OmniBot.

    ros2 launch omnibot_bringup sim.launch.py world:=flat
    ros2 launch omnibot_bringup sim.launch.py world:=apartment

Spawns omnibot_description (mecanum chassis) with a planar-move drive
(gz-sim VelocityControl + OdometryPublisher on /cmd_vel and /odom), a 2D
lidar, the front RGB camera, and the IMU. ros_gz_bridge bridges:

    /cmd_vel  /odom  /scan  /imu  /camera/front/image_raw
    /camera/front/camera_info  /clock

`rosbridge:=true` (the default) also starts rosbridge_websocket on port 9090
bound to 127.0.0.1 so a browser on this machine can drive this stack.
`rosbridge_address:=0.0.0.0` exposes it on the network without authentication.
The sim-smoke test passes `rosbridge:=false` and does not start rosbridge.
This launch does not start foxglove or the arm driver.

`vr:=true` is the sim VR profile. It starts teleop_safety, cmd_vel_mux, and
arm_cmd_mux, and bridges Gazebo's /cmd_vel from /cmd_vel/out. Clients publish
/cmd_vel/teleop_raw and /arm/joint_commands/teleop_raw. The default `vr:=false`
path is unchanged and still drives Gazebo on /cmd_vel.

`record_vr_session:=true` is opt-in and only applies with `vr:=true`. It includes
omnibot_hybrid/launch/vr_session_recorder.launch.py, which records the VR
session topics to MCAP. The default is false, so sim-smoke does not record.
OHH-198 sim_vr.launch.py should forward `record_vr_session` into this file
and should not include the recorder launch itself.

`drive:=mecanum` selects the gz-sim MecanumDrive plugin instead of planar move.
`gui:=true` opens the Gazebo client; the default is server-only so CI has no display.
"""

import os

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def _world_path(bringup_share, world):
    known = {
        "flat": os.path.join(bringup_share, "worlds", "flat.sdf"),
        "apartment": os.path.join(bringup_share, "worlds", "apartment.sdf"),
    }
    if world in known:
        return known[world]
    if os.path.isfile(world):
        return world
    candidate = os.path.join(bringup_share, "worlds", world)
    if os.path.isfile(candidate):
        return candidate
    if not world.endswith(".sdf"):
        with_suffix = candidate + ".sdf"
        if os.path.isfile(with_suffix):
            return with_suffix
    raise FileNotFoundError(
        f"world {world!r} is not flat, apartment, or an existing SDF path"
    )


def _launch_sim(context, *args, **kwargs):
    del args, kwargs
    world_key = LaunchConfiguration("world").perform(context)
    drive = LaunchConfiguration("drive").perform(context)
    gui = LaunchConfiguration("gui").perform(context).lower() in ("1", "true", "yes")

    bringup = FindPackageShare("omnibot_bringup").perform(context)
    description = FindPackageShare("omnibot_description").perform(context)
    ros_gz_sim = FindPackageShare("ros_gz_sim").perform(context)

    vr = LaunchConfiguration("vr").perform(context).lower() in (
        "1",
        "true",
        "yes",
    )
    record_vr_session = LaunchConfiguration("record_vr_session").perform(context).lower() in (
        "1",
        "true",
        "yes",
    )
    world_path = _world_path(bringup, world_key)
    xacro_file = os.path.join(description, "urdf", "omnibot.urdf.xacro")
    bridge_name = "sim_bridge_vr.yaml" if vr else "sim_bridge.yaml"
    bridge_config = os.path.join(bringup, "config", bridge_name)

    robot_desc = ParameterValue(
        Command(
            [
                "xacro ",
                xacro_file,
                f" drive:={drive}",
                " lidar:=true",
                " minimal_sensors:=true",
            ]
        ),
        value_type=str,
    )

    # -s is server-only. --headless-rendering lets the lidar and camera
    # render without a window (Gazebo Harmonic / gz-sim 8).
    if gui:
        gz_args = f"-r {world_path}"
    else:
        gz_args = f"-r -s --headless-rendering {world_path}"

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, "launch", "gz_sim.launch.py")
        ),
        launch_arguments={"gz_args": gz_args}.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[{"robot_description": robot_desc, "use_sim_time": True}],
    )

    spawn = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="ros_gz_sim",
                executable="create",
                output="screen",
                arguments=[
                    "-name",
                    "omnibot",
                    "-topic",
                    "robot_description",
                    "-x",
                    "0",
                    "-y",
                    "0",
                    "-z",
                    "0.05",
                ],
            )
        ],
    )

    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="ros_gz_bridge",
        output="screen",
        parameters=[{"config_file": bridge_config, "use_sim_time": False}],
    )

    actions = [gazebo, robot_state_publisher, spawn, bridge]
    rosbridge_on = LaunchConfiguration("rosbridge").perform(context).lower() in (
        "1",
        "true",
        "yes",
    )
    if rosbridge_on:
        address = LaunchConfiguration("rosbridge_address").perform(context)
        actions.append(
            Node(
                package="rosbridge_server",
                executable="rosbridge_websocket",
                name="rosbridge_websocket",
                output="screen",
                parameters=[{"port": 9090, "address": address}],
            )
        )
    if vr:
        hybrid = FindPackageShare("omnibot_hybrid").perform(context)
        actions.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(hybrid, "launch", "teleop_safety.launch.py")
                )
            )
        )
        actions.append(
            Node(
                package="omnibot_hybrid",
                executable="cmd_vel_mux",
                name="cmd_vel_mux",
                output="screen",
                parameters=[{"default_mode": "teleop", "use_sim_time": False}],
            )
        )
        actions.append(
            Node(
                package="omnibot_rl",
                executable="arm_cmd_mux",
                name="arm_cmd_mux",
                output="screen",
                parameters=[{"default_mode": "teleop", "use_sim_time": False}],
            )
        )
        if record_vr_session:
            actions.append(
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        os.path.join(hybrid, "launch", "vr_session_recorder.launch.py")
                    )
                )
            )
    elif record_vr_session:
        actions.append(
            LogInfo(
                msg=(
                    "record_vr_session is ignored unless vr:=true. "
                    "Not recording."
                )
            )
        )
    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "world",
                default_value="flat",
                description="flat, apartment, or a path to an SDF world",
            ),
            DeclareLaunchArgument(
                "drive",
                default_value="planar",
                description="planar (velocity control) or mecanum (MecanumDrive)",
            ),
            DeclareLaunchArgument(
                "gui",
                default_value="false",
                description="Open the Gazebo GUI. Default is headless.",
            ),
            DeclareLaunchArgument(
                "rosbridge",
                default_value="true",
                description=(
                    "Start rosbridge_websocket on port 9090, bound to "
                    "rosbridge_address (127.0.0.1 by default). "
                    "The sim-smoke test sets this false."
                ),
            ),
            DeclareLaunchArgument(
                "vr",
                default_value="false",
                description=(
                    "Sim VR profile. Start teleop_safety plus the base and arm "
                    "muxes, and drive Gazebo from /cmd_vel/out. Clients publish "
                    "/cmd_vel/teleop_raw and /arm/joint_commands/teleop_raw. "
                    "Default false keeps the /cmd_vel smoke-test path."
                ),
            ),
            DeclareLaunchArgument(
                "record_vr_session",
                default_value="false",
                description=(
                    "With vr:=true, record the VR session topics to MCAP "
                    "(teleop commands, heartbeat, telemetry, safety state, "
                    "control mode) with file rotation and a size cap. "
                    "Default false records nothing. OHH-198 sim_vr.launch.py "
                    "should forward this argument into sim.launch.py."
                ),
            ),
            DeclareLaunchArgument(
                "rosbridge_address",
                default_value="127.0.0.1",
                description=(
                    "Interface rosbridge_websocket binds. "
                    "127.0.0.1 is loopback only. "
                    "0.0.0.0 exposes it on the network without authentication."
                ),
            ),
            OpaqueFunction(function=_launch_sim),
        ]
    )
