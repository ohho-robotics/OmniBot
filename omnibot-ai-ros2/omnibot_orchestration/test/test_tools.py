"""
Unit tests for LangChain tools.

Tools are closures that capture a node reference. These tests use a minimal
stub to avoid requiring a live ROS 2 context.
"""

import pytest

pytest.importorskip("langchain", reason="langchain not installed — skipping tool tests")


class _MockNode:
    """Minimal stub mimicking the parts of LangchainAgentNode that tools access."""

    def __init__(self, locations=None):
        self._locations = locations or {
            "kitchen": {"x": 3.5, "y": 1.2, "yaw": 1.5708},
            "home": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            "workspace": {"x": 2.0, "y": -1.5, "yaw": -1.5708},
        }
        self._published_missions = []
        self._published_cancels = []
        self._published_responses = []
        self._latest_mission_status = "phase=idle mission={}"
        import threading

        self._status_lock = threading.Lock()

    def _publish_mission(self, cmd):
        self._published_missions.append(cmd)

    def _publish_cancel(self, reason):
        self._published_cancels.append(reason)

    def get_logger(self):
        class _Logger:
            def info(self, *a):
                pass

            def warn(self, *a):
                pass

            def error(self, *a):
                pass

        return _Logger()

    @property
    def _response_needed_pub(self):
        class _Pub:
            def __init__(self, node):
                self._node = node

            def publish(self, msg):
                self._node._published_responses.append(msg.data)

        return _Pub(self)


# ── Navigation tools ──────────────────────────────────────────────────────────


def _nav_tools(locations=None):
    from omnibot_orchestration.tools.navigation_tools import make_navigation_tools

    node = _MockNode(locations)
    tools = {t.name: t for t in make_navigation_tools(node)}
    return node, tools


def test_navigate_to_known_location():
    node, tools = _nav_tools()
    result = tools["navigate_to_location"].invoke({"location": "kitchen"})
    assert "kitchen" in result
    assert node._published_missions == ["navigate:kitchen"]


def test_navigate_to_unknown_location_returns_error():
    node, tools = _nav_tools()
    result = tools["navigate_to_location"].invoke({"location": "mars"})
    assert "ERROR" in result
    assert node._published_missions == []


def test_navigate_then_execute_known():
    node, tools = _nav_tools()
    result = tools["navigate_then_execute"].invoke(
        {"location": "kitchen", "task": "pick up the red cup"}
    )
    assert "kitchen" in result
    assert node._published_missions == ["navigate:kitchen,vla:pick up the red cup"]


def test_navigate_then_execute_unknown_location():
    node, tools = _nav_tools()
    result = tools["navigate_then_execute"].invoke(
        {"location": "moon", "task": "pick up rock"}
    )
    assert "ERROR" in result
    assert node._published_missions == []


# ── VLA tools ─────────────────────────────────────────────────────────────────


def test_execute_vla_task():
    from omnibot_orchestration.tools.vla_tools import make_vla_tools

    node = _MockNode()
    tools = {t.name: t for t in make_vla_tools(node)}
    result = tools["execute_vla_task"].invoke({"task_description": "open the drawer"})
    assert "open the drawer" in result
    assert node._published_missions == ["vla:open the drawer"]


# ── Status tools ──────────────────────────────────────────────────────────────


def test_get_robot_status():
    from omnibot_orchestration.tools.status_tools import make_status_tools

    node = _MockNode()
    tools = {t.name: t for t in make_status_tools(node)}
    result = tools["get_robot_status"].invoke({})
    assert "idle" in result


def test_cancel_mission():
    from omnibot_orchestration.tools.status_tools import make_status_tools

    node = _MockNode()
    tools = {t.name: t for t in make_status_tools(node)}
    result = tools["cancel_current_mission"].invoke({})
    assert "Cancel" in result
    assert node._published_cancels == ["cancel"]


# ── Query tools ───────────────────────────────────────────────────────────────


def test_list_available_locations():
    from omnibot_orchestration.tools.query_tools import make_query_tools

    node = _MockNode()
    # Patch out vision and entity memory deps (not needed for this tool)
    node._vision = None
    node._entity_memory = None
    tools = {t.name: t for t in make_query_tools(node)}
    result = tools["list_available_locations"].invoke({})
    assert "kitchen" in result
    assert "home" in result
    assert "workspace" in result


# ── Human tools ───────────────────────────────────────────────────────────────


def test_ask_human_for_clarification():
    from omnibot_orchestration.tools.human_tools import make_human_tools

    node = _MockNode()
    tools = {t.name: t for t in make_human_tools(node)}
    result = tools["ask_human_for_clarification"].invoke(
        {"question": "Which table do you mean?"}
    )
    assert "Which table" in result
    assert node._published_responses == ["Which table do you mean?"]
