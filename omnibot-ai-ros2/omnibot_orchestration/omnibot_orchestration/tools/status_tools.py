from typing import TYPE_CHECKING, List

from langchain.tools import tool

if TYPE_CHECKING:
    from omnibot_orchestration.langchain_agent_node import LangchainAgentNode


def make_status_tools(node: "LangchainAgentNode") -> List:

    @tool
    def get_robot_status() -> str:
        """Get the current mission status of the robot.

        Returns the current phase (idle, navigating, vla, done) and the
        active mission details. Call this before issuing a new mission if
        you are unsure whether the robot is busy, or after a task to confirm
        completion.

        Returns:
            A string describing the robot's current phase and mission.
        """
        with node._status_lock:
            status = node._latest_mission_status
        if status is None:
            return (
                "No status received yet. The mission_planner node may not be running."
            )
        return f"Robot status: {status}"

    @tool
    def cancel_current_mission() -> str:
        """Cancel the currently running mission immediately.

        Safe to call even when no mission is active. Use this before issuing
        a new mission if the robot appears stuck, or if the user explicitly
        requests a stop.

        Returns:
            Confirmation that the cancel command was sent.
        """
        node._publish_cancel("cancel")
        node.get_logger().info("[Tool] cancel_current_mission called")
        return "Cancel command sent. Robot returning to idle mode."

    return [get_robot_status, cancel_current_mission]
