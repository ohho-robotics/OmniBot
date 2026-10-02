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

That topic set is what a later rosbridge client needs (OHH-92). This launch
does not start rosbridge_server, foxglove, or the arm driver.

`drive:=mecanum` selects the gz-sim MecanumDrive plugin instead of planar move.
`gui:=true` opens the Gazebo client; the default is server-only so CI has no display.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction
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

    world_path = _world_path(bringup, world_key)
    xacro_file = os.path.join(description, "urdf", "omnibot.urdf.xacro")
    bridge_config = os.path.join(bringup, "config", "sim_bridge.yaml")

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

    return [gazebo, robot_state_publisher, spawn, bridge]


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
            OpaqueFunction(function=_launch_sim),
        ]
    )
