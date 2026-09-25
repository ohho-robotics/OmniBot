"""
LangChain Agent Launch — starts the AI orchestration layer for OmniBot.

Must be run on the AI desktop PC alongside vla_serve and the VLA nodes.
The Raspberry Pi base must be reachable on the same ROS_DOMAIN_ID (30).

Quick-start:
  # 1. Set your API key
  export ANTHROPIC_API_KEY=sk-ant-...

  # 2. Launch standalone (alongside hybrid_robot.launch.py)
  ros2 launch omnibot_orchestration langchain_agent.launch.py

  # 3. Send a natural language command
  ros2 topic pub --once /ai/command std_msgs/msg/String \\
    "data: 'Fetch the coffee cup from the kitchen and bring it to me'"

  # 4. Watch AI reasoning and status
  ros2 topic echo /ai/status

  # 5. Watch the resulting structured mission commands
  ros2 topic echo /mission/command
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory("omnibot_orchestration")
    config_file = os.path.join(pkg, "config", "langchain_agent.yaml")

    use_sim_time = LaunchConfiguration("use_sim_time", default="false")
    vla_serve_url = LaunchConfiguration(
        "vla_serve_url", default="http://localhost:8000"
    )

    agent_node = Node(
        package="omnibot_orchestration",
        executable="langchain_agent_node",
        name="langchain_agent_node",
        output="screen",
        parameters=[
            config_file,
            {
                "use_sim_time": use_sim_time,
                "vla_serve_url": vla_serve_url,
                # Pass credentials from shell environment — never hard-code
                "anthropic_api_key": EnvironmentVariable(
                    "ANTHROPIC_API_KEY", default_value=""
                ),
                "langchain_api_key": EnvironmentVariable(
                    "LANGCHAIN_API_KEY", default_value=""
                ),
                "langchain_project": EnvironmentVariable(
                    "LANGCHAIN_PROJECT", default_value="omnibot"
                ),
            },
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="false",
                description="Use simulation clock (set true when running with Gazebo)",
            ),
            DeclareLaunchArgument(
                "vla_serve_url",
                default_value="http://localhost:8000",
                description="Base URL of the vla_serve FastAPI inference server",
            ),
            agent_node,
        ]
    )
