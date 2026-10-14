# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""Gazebo VR profile with the same topic contract as the real robot.

    ros2 launch omnibot_bringup sim_vr.launch.py
    ros2 launch omnibot_bringup sim_vr.launch.py nav:=true
    ros2 launch omnibot_bringup sim_vr.launch.py world:=flat

Includes sim.launch.py with world:=apartment and vr:=true. That starts
Gazebo, robot_state_publisher, ros_gz_bridge (/cmd_vel/out -> gz /cmd_vel),
teleop_safety, cmd_vel_mux, and arm_cmd_mux. This file does not start a
second copy of those nodes.

Also starts web_video_server on port 8080 for MJPEG of /camera/front/image_raw.
rosbridge_websocket stays on port 9090. Both bind rosbridge_address, which
defaults to 127.0.0.1. gateway:=true includes ohho_gateway.launch.py when
that file is installed and passes rosbridge:=false into sim.launch.py so
the snippet is the only process on port 9090. The snippet keeps the
upstreams on 127.0.0.1. A missing snippet does not bind 0.0.0.0.

nav:=true starts the apartment Nav2 stack from omnibot_navigation without
a second Gazebo. arm:=true includes omnibot_arm/launch/sim_arm.launch.py,
which mirrors /arm/joint_commands/out onto /arm/joint_states. This profile
does not start OHH-199's arm_sim_driver. cameras:=extra and telemetry:=true
include sim_cameras.launch.py and telemetry_aggregator.launch.py when those
files are installed; a missing include is logged and the profile still starts.
"""

import os

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _load_support():
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_vr_support.py")
    spec = importlib.util.spec_from_file_location("omnibot_sim_vr_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_support = _load_support()


def _include_if(enabled, path, label):
    decision = _support.optional_launch(enabled, os.path.isfile(path))
    if decision == "include":
        return [IncludeLaunchDescription(PythonLaunchDescriptionSource(path))]
    if decision == "missing":
        return [
            LogInfo(
                msg=(
                    f"{label} include point is not installed yet: {path}. "
                    "The sim VR profile is still starting."
                )
            )
        ]
    return []


def _video_node(address):
    return Node(
        package="web_video_server",
        executable="web_video_server",
        name="web_video_server",
        output="screen",
        parameters=[{"port": _support.VIDEO_PORT, "address": address}],
    )


def _navigation():
    """Nav2 on the apartment map. Does not start Gazebo."""
    from ament_index_python.packages import PackageNotFoundError
    from ament_index_python.packages import get_package_share_directory
    from nav2_common.launch import RewrittenYaml

    try:
        nav = get_package_share_directory("omnibot_navigation")
    except PackageNotFoundError as exc:
        raise RuntimeError(
            "nav:=true requires omnibot_navigation on the workspace path"
        ) from exc

    map_yaml = os.path.join(nav, "maps", "apartment.yaml")
    params_file = os.path.join(nav, "config", "nav2_params.yaml")
    # Same headless overrides as sim_navigation.launch.py. bond_timeout 0.0
    # is the Nav2 lifecycle bond, not the teleop or mux watchdog.
    sim_params = RewrittenYaml(
        source_file=params_file,
        param_rewrites={
            "use_sim_time": "true",
            "yaml_filename": map_yaml,
            "observation_sources": "scan",
        },
        convert_types=True,
    )
    map_server = Node(
        package="nav2_map_server",
        executable="map_server",
        name="map_server",
        output="screen",
        parameters=[sim_params],
    )
    amcl = Node(
        package="nav2_amcl",
        executable="amcl",
        name="amcl",
        output="screen",
        parameters=[
            sim_params,
            {
                "set_initial_pose": True,
                "initial_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0},
            },
        ],
    )
    lifecycle_localization = Node(
        package="nav2_lifecycle_manager",
        executable="lifecycle_manager",
        name="lifecycle_manager_localization",
        output="screen",
        parameters=[
            {
                "use_sim_time": True,
                "autostart": True,
                "bond_timeout": 0.0,
                "node_names": ["map_server", "amcl"],
            }
        ],
    )
    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav, "launch", "autonomous_navigation.launch.py")
        ),
        launch_arguments={
            "use_sim_time": "true",
            "params_file": sim_params,
            "autostart": "true",
            "bond_timeout": "0.0",
        }.items(),
    )
    return [map_server, amcl, lifecycle_localization, navigation]


def _launch_vr(context, *args, **kwargs):
    del args, kwargs
    bringup = FindPackageShare("omnibot_bringup").perform(context)

    gateway = LaunchConfiguration("gateway").perform(context)
    rosbridge = LaunchConfiguration("rosbridge").perform(context)
    video = LaunchConfiguration("video").perform(context)
    requested_address = LaunchConfiguration("rosbridge_address").perform(context)
    gateway_path = os.path.join(bringup, "launch", _support.GATEWAY_LAUNCH_NAME)
    gateway_exists = os.path.isfile(gateway_path)
    plan = _support.connectivity(gateway, gateway_exists, rosbridge, video)
    address = _support.upstream_address(gateway, gateway_exists, requested_address)

    actions = []
    if plan["use_gateway_launch"]:
        actions.append(
            LogInfo(
                msg=(
                    "gateway:=true includes ohho_gateway.launch.py. "
                    "rosbridge and web_video_server stay on 127.0.0.1. "
                    "This does not bind 0.0.0.0."
                )
            )
        )
        actions.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(gateway_path),
                launch_arguments={
                    "gateway": "true",
                    "start_rosbridge": "true" if _support.truthy(rosbridge) else "false",
                    "start_web_video": "true" if _support.truthy(video) else "false",
                    "start_foxglove": "true",
                }.items(),
            )
        )
        # The snippet owns rosbridge. sim_starts_rosbridge is false here.
        sim_rosbridge = "false"
    else:
        if plan["gateway_missing"]:
            actions.append(
                LogInfo(
                    msg=(
                        "gateway:=true but ohho_gateway.launch.py is not "
                        f"installed. rosbridge stays on {address}. "
                        "This does not bind 0.0.0.0."
                    )
                )
            )
        elif address != _support.LOOPBACK_ADDRESS:
            actions.append(
                LogInfo(
                    msg=(
                        f"rosbridge_address {address} is not loopback. "
                        "That exposes rosbridge without authentication."
                    )
                )
            )
        sim_rosbridge = "true" if plan["sim_starts_rosbridge"] else "false"
        if plan["sim_starts_video"]:
            actions.append(_video_node(address))

    actions.append(
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(bringup, "launch", "sim.launch.py")
            ),
            launch_arguments={
                "world": LaunchConfiguration("world").perform(context),
                "drive": LaunchConfiguration("drive").perform(context),
                "gui": LaunchConfiguration("gui").perform(context),
                "rosbridge": sim_rosbridge,
                "rosbridge_address": address,
                "vr": "true",
            }.items(),
        )
    )

    if _support.truthy(LaunchConfiguration("arm").perform(context)):
        arm_share = FindPackageShare("omnibot_arm").perform(context)
        actions.extend(
            _include_if(
                True,
                os.path.join(arm_share, "launch", _support.ARM_LAUNCH_NAME),
                "OHH-199 arm_sim_driver",
            )
        )
    cameras = LaunchConfiguration("cameras").perform(context)
    mode = _support.camera_mode(cameras)
    if mode == "extra":
        actions.extend(
            _include_if(
                True,
                os.path.join(bringup, "launch", _support.CAMERA_LAUNCH_NAME),
                "OHH-200 cameras",
            )
        )
    elif mode == "unknown":
        actions.append(
            LogInfo(
                msg=(
                    f"cameras:={cameras} is unknown. "
                    "Keeping the front camera from sim.launch.py."
                )
            )
        )
    actions.extend(
        _include_if(
            LaunchConfiguration("telemetry").perform(context),
            os.path.join(bringup, "launch", _support.TELEMETRY_LAUNCH_NAME),
            "telemetry_aggregator",
        )
    )
    if _support.truthy(LaunchConfiguration("nav").perform(context)):
        actions.extend(_navigation())
    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "world",
                default_value=_support.DEFAULT_WORLD,
                description="flat, apartment, or a path to an SDF world.",
            ),
            DeclareLaunchArgument(
                "drive",
                default_value=_support.DEFAULT_DRIVE,
                description="planar (velocity control) or mecanum (MecanumDrive).",
            ),
            DeclareLaunchArgument(
                "gui",
                default_value=_support.DEFAULT_GUI,
                description="Open the Gazebo GUI. Default is headless.",
            ),
            DeclareLaunchArgument(
                "rosbridge",
                default_value=_support.DEFAULT_ROSBRIDGE,
                description=(
                    "Start rosbridge_websocket on port 9090 when this profile "
                    "owns that port. Ignored when ohho_gateway.launch.py owns it."
                ),
            ),
            DeclareLaunchArgument(
                "rosbridge_address",
                default_value=_support.DEFAULT_BIND,
                description=(
                    "Bind address for rosbridge_websocket and web_video_server. "
                    "Default 127.0.0.1. gateway:=true with ohho_gateway.launch.py "
                    "keeps the upstreams on 127.0.0.1 and does not bind 0.0.0.0."
                ),
            ),
            DeclareLaunchArgument(
                "gateway",
                default_value=_support.DEFAULT_GATEWAY,
                description=(
                    "Include ohho_gateway.launch.py when that file is installed. "
                    "Default false. True does not bind rosbridge to 0.0.0.0."
                ),
            ),
            DeclareLaunchArgument(
                "video",
                default_value=_support.DEFAULT_VIDEO,
                description=(
                    "Start web_video_server on port 8080. "
                    "MJPEG: /stream?topic=/camera/front/image_raw."
                ),
            ),
            DeclareLaunchArgument(
                "nav",
                default_value=_support.DEFAULT_NAV,
                description=(
                    "Start Nav2 on the apartment map. Default false. "
                    "Does not start a second Gazebo."
                ),
            ),
            DeclareLaunchArgument(
                "arm",
                default_value=_support.DEFAULT_ARM,
                description=(
                    "Include omnibot_arm/launch/sim_arm.launch.py when it is "
                    "installed. That file mirrors /arm/joint_commands/out onto "
                    "/arm/joint_states. This profile does not start "
                    "arm_sim_driver itself."
                ),
            ),
            DeclareLaunchArgument(
                "cameras",
                default_value=_support.DEFAULT_CAMERAS,
                description=(
                    "OHH-200 include point. front keeps the camera from "
                    "sim.launch.py. extra includes sim_cameras.launch.py "
                    "when that file is installed."
                ),
            ),
            DeclareLaunchArgument(
                "telemetry",
                default_value=_support.DEFAULT_TELEMETRY,
                description=(
                    "Include telemetry_aggregator.launch.py when that file "
                    "is installed. Default false."
                ),
            ),
            OpaqueFunction(function=_launch_vr),
        ]
    )
