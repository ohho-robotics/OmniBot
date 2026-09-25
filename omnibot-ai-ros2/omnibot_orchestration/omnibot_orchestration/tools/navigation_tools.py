from typing import TYPE_CHECKING, List

from langchain.tools import tool

if TYPE_CHECKING:
    from omnibot_orchestration.langchain_agent_node import LangchainAgentNode


def make_navigation_tools(node: "LangchainAgentNode") -> List:

    @tool
    def navigate_to_location(location: str) -> str:
        """Navigate the robot to a named location using Nav2.

        Use this when the user wants the robot to move somewhere without
        performing any manipulation at the destination.

        Args:
            location: The name of the destination. Must be one of the known
                      locations. Call list_available_locations first if unsure.

        Returns:
            Confirmation that the navigation command was sent.
        """
        known = sorted(node._locations.keys())
        if location not in known:
            return (
                f"ERROR: '{location}' is not a known location. "
                f"Known locations: {known}. "
                "Use list_available_locations() or ask_human_for_clarification()."
            )
        cmd = f"navigate:{location}"
        node._publish_mission(cmd)
        node.get_logger().info(f'[Tool] navigate_to_location → "{cmd}"')
        return f"Navigation command sent. Robot is moving to '{location}'."

    @tool
    def navigate_then_execute(location: str, task: str) -> str:
        """Navigate to a location and then execute a VLA manipulation task there.

        Use this for any task that requires travel AND manipulation:
        fetch-and-place, pick-up at a destination, etc.

        Args:
            location: Named destination to travel to first.
            task: Natural language description of the manipulation task to
                  execute once at the destination (e.g. 'pick up the red cup').

        Returns:
            Confirmation that the combined mission was sent.
        """
        known = sorted(node._locations.keys())
        if location not in known:
            return (
                f"ERROR: '{location}' is not a known location. "
                f"Known locations: {known}. "
                "Use list_available_locations() or ask_human_for_clarification()."
            )
        cmd = f"navigate:{location},vla:{task}"
        node._publish_mission(cmd)
        node.get_logger().info(f'[Tool] navigate_then_execute → "{cmd}"')
        return (
            f"Hybrid mission sent: navigate to '{location}', "
            f"then execute VLA task '{task}'."
        )

    return [navigate_to_location, navigate_then_execute]
