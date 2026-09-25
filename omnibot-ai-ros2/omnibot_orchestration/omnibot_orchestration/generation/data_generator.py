"""
AutoGen offline data generator for OmniBot.

Generates training artefacts for SmolVLA fine-tuning, named_location YAML
entries, and mission script drafts. A human reviews all outputs before they
touch the robot.

NEVER publishes to ROS topics. Output is text / YAML / JSON only.

Requires `pyautogen` (pip install pyautogen). Falls back gracefully if absent.

Usage (standalone, no ROS required):
    from omnibot_orchestration.generation.data_generator import OmniBotDataGenerator

    gen = OmniBotDataGenerator(api_key="sk-ant-...")

    tasks = gen.generate_task_descriptions(
        scenario="kitchen countertop with various objects",
        count=10,
    )
    entry = gen.generate_location_config(
        description="The charging dock is in the corner near the window."
    )
    script = gen.generate_mission_script(goal="Clean up the workspace")
"""

import json
import re
from typing import Any, Dict, List, Optional


def _make_config(api_key: str) -> Dict:
    return {
        "config_list": [
            {
                "model": "claude-sonnet-4-6",
                "api_key": api_key or "ANTHROPIC_API_KEY_NOT_SET",
                "api_type": "anthropic",
            }
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }


class OmniBotDataGenerator:
    """
    AutoGen-based offline generator for OmniBot training data.

    Uses an AssistantAgent + UserProxyAgent pair to iteratively refine outputs.
    Human review is always required before feeding outputs to the robot.
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._autogen_available = self._check_autogen()

    @staticmethod
    def _check_autogen() -> bool:
        try:
            import autogen  # noqa: F401

            return True
        except ImportError:
            try:
                import pyautogen  # noqa: F401

                return True
            except ImportError:
                return False

    def generate_task_descriptions(
        self,
        scenario: str,
        count: int = 10,
        object_types: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Generate SmolVLA task description strings for a given scenario.

        Each description is a short imperative sentence:
        "pick up the red cup", "open the top drawer", "place the bottle upright".
        """
        objects_hint = (
            f"Focus on these object types: {', '.join(object_types)}. "
            if object_types
            else ""
        )
        prompt = (
            f"Generate {count} diverse, realistic manipulation task descriptions "
            f"for a mobile robot arm operating in this scene: {scenario}.\n"
            f"{objects_hint}"
            "Requirements:\n"
            "- Each task is a short imperative sentence (≤12 words)\n"
            "- Tasks must be physically feasible for a 6-DOF arm\n"
            "- Vary the actions: pick, place, open, close, push, pull, pour\n"
            "- Be specific about objects and their positions\n"
            "- Output ONLY the numbered list, no preamble\n"
            "Example: 1. Pick up the blue bottle from the left shelf"
        )

        if not self._autogen_available:
            return self._llm_fallback(prompt, parse_numbered_list=True)

        return self._autogen_generate(
            system="You are a robotics dataset curator specialising in VLA training data.",
            prompt=prompt,
            parse_fn=self._parse_numbered_list,
        )

    def generate_location_config(
        self,
        description: str,
        location_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a named_locations.yaml entry from a natural language description.

        Returns dict with: name, x, y, yaw (floats), notes (str).
        Always verify coordinates before deployment.
        """
        name_hint = (
            f"Use '{location_name}' as the location name. " if location_name else ""
        )
        prompt = (
            f"Generate a location config entry for OmniBot's named_locations.yaml.\n"
            f"Description: {description}\n"
            f"{name_hint}"
            "Output format (JSON):\n"
            '{"name": "location_key", "x": 0.0, "y": 0.0, "yaw": 0.0, '
            '"notes": "human-readable description"}\n'
            "Rules:\n"
            "- name: lowercase snake_case, ≤20 chars\n"
            "- x, y: estimate metres from robot origin; positive x=forward, y=left\n"
            "- yaw: radians, 0=facing +x, π/2=facing +y\n"
            "- notes: one sentence for human reviewers\n"
            "- Output ONLY the JSON object, no preamble\n"
            "IMPORTANT: These are estimates — a human MUST verify coordinates."
        )

        if not self._autogen_available:
            results = self._llm_fallback(prompt, parse_numbered_list=False)
            return self._parse_location_json(results[0] if results else "{}")

        raw = self._autogen_generate(
            system="You are a robotics configuration assistant for a ROS 2 robot.",
            prompt=prompt,
            parse_fn=lambda r: [r],
        )
        return self._parse_location_json(raw[0] if raw else "{}")

    def generate_mission_script(
        self,
        goal: str,
        known_locations: Optional[List[str]] = None,
    ) -> str:
        """
        Draft a multi-step mission script as YAML for human review.

        Returns a YAML string with navigate/vla steps that can be adapted
        into LangGraph initial state or /mission/command messages.
        """
        locs = ", ".join(known_locations) if known_locations else "none specified"
        prompt = (
            f"Draft a multi-step mission script for OmniBot.\n"
            f"Goal: {goal}\n"
            f"Available locations: {locs}\n\n"
            "Output a YAML mission script with this structure:\n"
            "mission:\n"
            "  goal: <goal>\n"
            "  steps:\n"
            "    - action: navigate\n"
            "      location: <name>\n"
            "    - action: vla\n"
            "      task: <description>\n\n"
            "Rules:\n"
            "- Only use locations from the available list\n"
            "- VLA task descriptions: ≤15 words each\n"
            "- Add a 'notes' field to steps that need human verification\n"
            "- End with navigate: home if robot should return\n"
            "Output ONLY the YAML, no explanation."
        )

        if not self._autogen_available:
            results = self._llm_fallback(prompt, parse_numbered_list=False)
            return results[0] if results else f"# Could not generate script for: {goal}"

        raw = self._autogen_generate(
            system="You are a robotics mission planner that writes executable YAML scripts.",
            prompt=prompt,
            parse_fn=lambda r: [r],
        )
        return raw[0] if raw else f"# Generation failed for: {goal}"

    # ── AutoGen conversation driver ────────────────────────────────────────

    def _autogen_generate(
        self,
        system: str,
        prompt: str,
        parse_fn,
    ) -> List[Any]:
        try:
            import autogen
        except ImportError:
            import pyautogen as autogen

        llm_config = _make_config(self._api_key)

        assistant = autogen.AssistantAgent(
            name="omnibot_generator",
            system_message=system,
            llm_config=llm_config,
        )

        proxy = autogen.UserProxyAgent(
            name="human_reviewer",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=1,
            code_execution_config=False,
        )

        proxy.initiate_chat(assistant, message=prompt, silent=True)

        messages = assistant.chat_messages.get(proxy, [])
        for m in reversed(messages):
            if m.get("role") == "assistant":
                return parse_fn(m.get("content", ""))

        return []

    # ── LLM fallback (no AutoGen) ──────────────────────────────────────────

    def _llm_fallback(self, prompt: str, parse_numbered_list: bool = True) -> List[str]:
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = ChatAnthropic(
                model="claude-sonnet-4-6",
                anthropic_api_key=self._api_key or None,
                max_tokens=2048,
                temperature=0.3,
            )
            response = llm.invoke(
                [
                    SystemMessage(
                        content="You are a helpful robotics data generation assistant."
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            raw = response.content
            if parse_numbered_list:
                return self._parse_numbered_list(raw)
            return [raw]
        except Exception as e:
            return [f"# Generation failed: {e}"]

    # ── Parsers ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_numbered_list(raw: str) -> List[str]:
        results = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line) if line[0].isdigit() else line
            if cleaned:
                results.append(cleaned)
        return results

    @staticmethod
    def _parse_location_json(raw: str) -> Dict[str, Any]:
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"name": "unknown", "x": 0.0, "y": 0.0, "yaw": 0.0, "notes": raw}

    @property
    def is_available(self) -> bool:
        return self._autogen_available
