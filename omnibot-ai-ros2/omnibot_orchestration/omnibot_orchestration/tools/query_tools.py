from typing import TYPE_CHECKING, List

from langchain.tools import tool

if TYPE_CHECKING:
    from omnibot_orchestration.langchain_agent_node import LangchainAgentNode


def make_query_tools(node: "LangchainAgentNode") -> List:

    @tool
    def list_available_locations() -> str:
        """List all named locations the robot can navigate to.

        Call this when the user refers to a place that might not be in the
        map, or before constructing any navigation command to validate the
        location name.

        Returns:
            A sorted list of location names the robot knows about.
        """
        locs = sorted(node._locations.keys())
        return f"Available locations: {locs}"

    @tool
    def describe_current_scene(camera: str = "front") -> str:
        """Get a natural language description of what the robot's camera sees.

        Use this to answer questions like 'what do you see?', locate objects,
        check task completion, or make conditional decisions based on the
        environment.

        After calling this tool, extract any object names and their positions
        mentioned in the description and remember them using the entity memory
        (the memory is updated automatically).

        Args:
            camera: Which camera to use. 'front' for the forward-facing base
                    camera (default). 'wrist' for the gripper camera (better
                    for close-up manipulation context).

        Returns:
            Natural language scene description from the robot's camera.
        """
        description = node._vision.describe_scene(camera=camera)

        # Auto-update entity memory: record that this location was observed.
        # The LLM will still interpret and act on the description itself.
        try:
            with node._status_lock:
                status = node._latest_mission_status or ""
            # Extract current location from status string if present
            # e.g. "phase=idle mission={'navigate': 'kitchen', ...}"
            import re

            match = re.search(r"'navigate':\s*'([^']+)'", status)
            location_hint = match.group(1) if match else "unknown"
            node._entity_memory.remember_object(
                object_name=f"scene_at_{location_hint}_{camera}",
                location=location_hint,
                description=description[:200],
            )
        except Exception:
            pass  # Memory update is best-effort; never block scene description

        return description

    return [list_available_locations, describe_current_scene]
