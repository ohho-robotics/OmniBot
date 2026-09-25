"""
CrewAI offline mission planner for OmniBot.

Runs OFFLINE — never in the live robot control loop. Call plan_mission() to
get a validated, structured mission plan from a natural language request, then
feed the result into the LangGraph state machine for execution.

Three-agent crew:
  Observer   — analyses scene context and prerequisites
  Navigator  — plans optimal location visit sequence
  Manipulator — writes precise VLA task descriptions per stop

Usage (standalone, no ROS required):
    from omnibot_orchestration.planning.crew_planner import OmniBotMissionPlanner

    planner = OmniBotMissionPlanner(
        known_locations=["kitchen", "workspace", "home"],
        entity_memory_summary="Red cup last seen on kitchen counter.",
        api_key="sk-ant-...",
    )
    steps = planner.plan_mission("Fetch the red cup from the kitchen")
    # steps → [
    #   {"action": "navigate", "location": "kitchen"},
    #   {"action": "vla",      "task": "pick up the red cup"},
    #   {"action": "navigate", "location": "home"},
    # ]
"""

import json
import re
from typing import Any, Dict, List, Optional


def _make_llm(api_key: str = "") -> Any:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model="claude-sonnet-4-6",
        anthropic_api_key=api_key or None,
        max_tokens=2048,
        temperature=0.2,
    )


class OmniBotMissionPlanner:
    """
    Offline CrewAI planner for complex multi-step missions.

    Requires `crewai` to be installed. Falls back gracefully if absent.
    """

    def __init__(
        self,
        known_locations: List[str],
        entity_memory_summary: str = "",
        api_key: str = "",
    ):
        self._locations = known_locations
        self._memory_summary = entity_memory_summary
        self._api_key = api_key
        self._crew_available = self._check_crewai()

    @staticmethod
    def _check_crewai() -> bool:
        try:
            import crewai  # noqa: F401

            return True
        except ImportError:
            return False

    def plan_mission(self, user_request: str) -> List[Dict]:
        """
        Plan a multi-step mission from a natural language request.

        Returns a list of step dicts:
            [{"action": "navigate", "location": "kitchen"},
             {"action": "vla",      "task": "pick up the red cup"},
             {"action": "navigate", "location": "home"}]

        Falls back to a single-step VLA plan if crewai is unavailable.
        """
        if not self._crew_available:
            return self._fallback_plan(user_request)

        try:
            return self._crew_plan(user_request)
        except Exception as e:
            return [{"action": "vla", "task": user_request, "error": str(e)}]

    def _crew_plan(self, user_request: str) -> List[Dict]:
        from crewai import Agent, Crew, Process, Task

        llm = _make_llm(self._api_key)
        locs = ", ".join(self._locations) or "none defined"

        observer = Agent(
            role="Scene Intelligence Officer",
            goal=(
                "Determine what objects and conditions are relevant to the mission. "
                "Identify prerequisites and potential obstacles."
            ),
            backstory=(
                "Expert at reading environment descriptions and identifying objects, "
                "their locations, and task prerequisites. Known entity state: "
                + (self._memory_summary or "none")
            ),
            llm=llm,
            verbose=False,
        )

        navigator = Agent(
            role="Route Planner",
            goal=(
                f"Plan the optimal sequence of locations to visit. "
                f"Known locations: {locs}. "
                "Only use locations from this list — never invent new ones."
            ),
            backstory=(
                "Expert at multi-stop route optimisation. The robot navigates "
                "via Nav2 to any named location. Always end at 'home' if the "
                "user wants the robot to return after the task."
            ),
            llm=llm,
            verbose=False,
        )

        manipulator = Agent(
            role="Manipulation Strategist",
            goal="Define precise VLA task descriptions for each manipulation stop.",
            backstory=(
                "Expert at writing clear, concise task descriptions for a "
                "vision-language-action model (SmolVLA). Tasks must be under "
                "20 words and describe the physical action: 'pick up the red cup', "
                "'open the drawer', 'place the cup on the table'."
            ),
            llm=llm,
            verbose=False,
        )

        analyse_task = Task(
            description=(
                f"Analyse this mission request: '{user_request}'\n"
                f"Known entity state: {self._memory_summary or 'none'}\n"
                "List: (1) objects needed, (2) their likely locations, "
                "(3) any prerequisites the robot must satisfy first."
            ),
            agent=observer,
            expected_output="Bullet-point analysis of objects, locations, prerequisites.",
        )

        route_task = Task(
            description=(
                f"Using the analysis, plan the location visit sequence.\n"
                f"Available locations: {locs}\n"
                "Output a numbered list of locations to visit, in order. "
                "If no navigation is needed (object already in front of robot), "
                "output 'No navigation required'."
            ),
            agent=navigator,
            expected_output="Ordered list of location names or 'No navigation required'.",
            context=[analyse_task],
        )

        vla_task = Task(
            description=(
                "For each navigation stop that requires manipulation, write a "
                "precise VLA task description (≤20 words each).\n"
                "Format each as: LOCATION: task description\n"
                "If a stop is navigation-only, write: LOCATION: navigate only"
            ),
            agent=manipulator,
            expected_output="LOCATION: task description pairs, one per line.",
            context=[analyse_task, route_task],
        )

        synthesise_task = Task(
            description=(
                "Combine the route and VLA tasks into a final JSON mission plan.\n"
                "Output ONLY a valid JSON array with objects of the form:\n"
                '  {"action": "navigate", "location": "<name>"}\n'
                '  {"action": "vla",      "task": "<description>"}\n'
                "Rules:\n"
                "- Every navigate step must use a location from the known list\n"
                "- Interleave navigate + vla steps correctly\n"
                "- If the user wants the robot to return, add a final navigate:home\n"
                "- Do NOT wrap in markdown fences"
            ),
            agent=navigator,
            expected_output="JSON array of mission step objects.",
            context=[route_task, vla_task],
        )

        crew = Crew(
            agents=[observer, navigator, manipulator],
            tasks=[analyse_task, route_task, vla_task, synthesise_task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff(inputs={"request": user_request})
        return self._parse_plan(str(result))

    def _parse_plan(self, raw: str) -> List[Dict]:
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
        try:
            steps = json.loads(raw)
            if isinstance(steps, list):
                return [s for s in steps if isinstance(s, dict) and "action" in s]
        except (json.JSONDecodeError, ValueError):
            pass
        # Graceful degradation: return raw as a single VLA task
        return [{"action": "vla", "task": raw[:200]}]

    def _fallback_plan(self, user_request: str) -> List[Dict]:
        """Simple single-step plan used when crewai is not installed."""
        return [{"action": "vla", "task": user_request}]

    @property
    def is_available(self) -> bool:
        return self._crew_available


def plan_mission_simple(
    user_request: str,
    known_locations: Optional[List[str]] = None,
    entity_memory_summary: str = "",
    api_key: str = "",
) -> List[Dict]:
    """Convenience function — creates a planner and runs it in one call."""
    planner = OmniBotMissionPlanner(
        known_locations=known_locations or [],
        entity_memory_summary=entity_memory_summary,
        api_key=api_key,
    )
    return planner.plan_mission(user_request)
