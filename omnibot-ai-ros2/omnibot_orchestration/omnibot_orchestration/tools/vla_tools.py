from typing import TYPE_CHECKING, List

from langchain.tools import tool

if TYPE_CHECKING:
    from omnibot_orchestration.langchain_agent_node import LangchainAgentNode


def make_vla_tools(node: "LangchainAgentNode") -> List:

    @tool
    def execute_vla_task(task_description: str) -> str:
        """Execute a vision-language manipulation task at the robot's current location.

        Use this when the robot is already at the right place and needs to
        perform manipulation: picking up objects, opening drawers, placing
        items, etc. Do NOT use this if the robot first needs to travel somewhere
        — use navigate_then_execute instead.

        Args:
            task_description: Natural language description of the task
                              (e.g. 'pick up the blue bottle',
                               'open the cabinet door').

        Returns:
            Confirmation that the VLA task prompt was sent.
        """
        cmd = f"vla:{task_description}"
        node._publish_mission(cmd)
        node.get_logger().info(f'[Tool] execute_vla_task → "{cmd}"')
        return f"VLA task sent: '{task_description}'."

    return [execute_vla_task]
