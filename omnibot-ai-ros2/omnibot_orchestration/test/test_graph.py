"""
Unit tests for the LangGraph mission state machine nodes.

Nodes are tested in isolation — no live ROS context, no LLM calls.
The mock node stub satisfies the interface expected by all graph nodes.
"""

import pytest

pytest.importorskip(
    "langgraph", reason="langgraph not installed — skipping graph tests"
)


# ── Shared mock ───────────────────────────────────────────────────────────────


class _MockNode:
    """Minimal stub satisfying the ros_node interface used by graph nodes."""

    def __init__(self):
        self._locations = {
            "kitchen": {"x": 3.5, "y": 1.2, "yaw": 1.5708},
            "home": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            "workspace": {"x": 2.0, "y": -1.5, "yaw": -1.5708},
        }
        self._api_key = ""
        self._published_missions = []
        self._published_cancels = []
        self._published_statuses = []
        self._published_responses = []
        self._vision = None

        import threading

        self._image_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._latest_mission_status = "phase=idle mission={}"

    def _publish_mission(self, cmd: str) -> None:
        self._published_missions.append(cmd)

    def _publish_cancel(self, reason: str) -> None:
        self._published_cancels.append(reason)

    def _publish_ai_status(self, status: str) -> None:
        self._published_statuses.append(status)

    @property
    def _response_needed_pub(self):
        class _Pub:
            def __init__(self, node):
                self._node = node

            def publish(self, msg):
                self._node._published_responses.append(msg.data)

        return _Pub(self)

    def get_logger(self):
        class _Logger:
            def info(self, *a):
                pass

            def warn(self, *a):
                pass

            def error(self, *a):
                pass

        return _Logger()


def _config(node=None):
    """Build a RunnableConfig carrying the mock node."""
    return {"configurable": {"ros_node": node or _MockNode(), "thread_id": "test"}}


def _base_state(**kwargs):
    """Return a minimal MissionState dict."""
    from omnibot_orchestration.graph.state import initial_state

    s = dict(initial_state("test"))
    s.update(kwargs)
    return s


# ── navigate_node ─────────────────────────────────────────────────────────────


def test_navigate_node_publishes_command():
    from omnibot_orchestration.graph.nodes import navigate_node

    node = _MockNode()
    state = _base_state(nav_location="kitchen")
    result = navigate_node(state, _config(node))

    assert result["phase"] == "navigating"
    assert node._published_missions == ["navigate:kitchen"]


def test_navigate_node_no_ros(monkeypatch):
    from omnibot_orchestration.graph.nodes import navigate_node

    state = _base_state(nav_location="kitchen")
    result = navigate_node(state, _config(node=None))
    assert result["phase"] == "navigating"


# ── execute_vla_node ──────────────────────────────────────────────────────────


def test_execute_vla_node_publishes_command():
    from omnibot_orchestration.graph.nodes import execute_vla_node

    node = _MockNode()
    state = _base_state(vla_task="pick up the red cup")
    result = execute_vla_node(state, _config(node))

    assert result["phase"] == "vla"
    assert node._published_missions == ["vla:pick up the red cup"]


# ── observe_node ──────────────────────────────────────────────────────────────


def test_observe_node_no_vision():
    from omnibot_orchestration.graph.nodes import observe_node

    node = _MockNode()
    node._vision = None
    state = _base_state()
    result = observe_node(state, _config(node))

    assert result["phase"] == "observing"
    assert "No camera" in result["response"]


def test_observe_node_with_vision():
    from omnibot_orchestration.graph.nodes import observe_node

    class _FakeVision:
        def describe_scene(self, camera="front"):
            return "A red cup on the kitchen counter."

    node = _MockNode()
    node._vision = _FakeVision()
    state = _base_state()
    result = observe_node(state, _config(node))

    assert "red cup" in result["response"]
    assert result["phase"] == "observing"


# ── human_checkpoint_node ─────────────────────────────────────────────────────


def test_human_checkpoint_publishes_question():
    from omnibot_orchestration.graph.nodes import human_checkpoint_node

    node = _MockNode()

    class _FakeString:
        data = ""

    # Patch std_msgs import inside the node function
    import sys
    import types

    fake_std = types.ModuleType("std_msgs")
    fake_msgs = types.ModuleType("std_msgs.msg")
    fake_msgs.String = _FakeString
    fake_std.msg = fake_msgs
    sys.modules.setdefault("std_msgs", fake_std)
    sys.modules.setdefault("std_msgs.msg", fake_msgs)

    state = _base_state(human_question="Which table do you mean?")
    result = human_checkpoint_node(state, _config(node))

    assert result["requires_human"] is True
    assert result["phase"] == "waiting_human"
    assert "Which table" in result["response"]


# ── finalize_node ─────────────────────────────────────────────────────────────


def test_finalize_node_uses_existing_response():
    from omnibot_orchestration.graph.nodes import finalize_node

    node = _MockNode()
    state = _base_state(response="Fetched the cup from kitchen.")
    result = finalize_node(state, _config(node))

    assert result["phase"] == "done"
    assert result["response"] == "Fetched the cup from kitchen."
    assert any("DONE" in s for s in node._published_statuses)


def test_finalize_node_builds_response_from_state():
    from omnibot_orchestration.graph.nodes import finalize_node

    node = _MockNode()
    state = _base_state(
        response="",
        nav_location="kitchen",
        vla_task="pick up the cup",
    )
    result = finalize_node(state, _config(node))

    assert "kitchen" in result["response"]
    assert "pick up the cup" in result["response"]
    assert result["phase"] == "done"


def test_finalize_node_observe_sentinel_excluded():
    from omnibot_orchestration.graph.nodes import finalize_node

    node = _MockNode()
    state = _base_state(response="", vla_task="__observe__")
    result = finalize_node(state, _config(node))
    # __observe__ sentinel must not appear in user-visible response
    assert "__observe__" not in result["response"]


# ── recover_node (no LLM) ─────────────────────────────────────────────────────


def test_recover_node_increments_retry_count(monkeypatch):
    from omnibot_orchestration.graph import nodes as nodes_mod

    # Stub out LLM so no API call is made
    class _FakeLLM:
        def invoke(self, messages):
            class R:
                content = (
                    '{"action": "retry", "refined_task": "pick up the large red cup"}'
                )

            return R()

    monkeypatch.setattr(nodes_mod, "_llm", _FakeLLM())

    from omnibot_orchestration.graph.nodes import recover_node

    node = _MockNode()
    state = _base_state(
        retry_count=0,
        phase="vla",
        last_error="timeout",
        vla_task="pick up cup",
    )
    result = recover_node(state, _config(node))

    assert result["retry_count"] == 1
    assert node._published_cancels == ["recover"]


def test_recover_node_escalates_after_retries(monkeypatch):
    from omnibot_orchestration.graph import nodes as nodes_mod

    class _FakeLLM:
        def invoke(self, messages):
            class R:
                content = '{"action": "escalate", "question": "What should I do?"}'

            return R()

    monkeypatch.setattr(nodes_mod, "_llm", _FakeLLM())

    from omnibot_orchestration.graph.nodes import recover_node

    node = _MockNode()
    state = _base_state(
        retry_count=2,
        phase="navigating",
        last_error="nav2 timeout",
        vla_task="pick up cup",
        nav_location="kitchen",
    )
    result = recover_node(state, _config(node))

    assert result["requires_human"] is True
    assert "human_question" in result


# ── route functions ───────────────────────────────────────────────────────────


def test_route_after_parse_observe():
    from omnibot_orchestration.graph.mission_graph import route_after_parse

    state = _base_state(vla_task="__observe__", nav_location=None)
    assert route_after_parse(state) == "observe"


def test_route_after_parse_navigate_and_vla():
    from omnibot_orchestration.graph.mission_graph import route_after_parse

    state = _base_state(nav_location="kitchen", vla_task="pick up cup")
    assert route_after_parse(state) == "navigate"


def test_route_after_parse_vla_only():
    from omnibot_orchestration.graph.mission_graph import route_after_parse

    state = _base_state(nav_location=None, vla_task="open the drawer")
    assert route_after_parse(state) == "execute_vla"


def test_route_after_parse_fallback_finalize():
    from omnibot_orchestration.graph.mission_graph import route_after_parse

    state = _base_state(nav_location=None, vla_task=None)
    assert route_after_parse(state) == "finalize"


def test_route_after_navigate_with_error():
    from omnibot_orchestration.graph.mission_graph import route_after_navigate

    state = _base_state(last_error="nav2 failed")
    assert route_after_navigate(state) == "recover"


def test_route_after_vla_return_home():
    from omnibot_orchestration.graph.mission_graph import route_after_vla

    state = _base_state(return_home=True, phase="vla", last_error=None)
    assert route_after_vla(state) == "navigate"


def test_route_after_recover_requires_human():
    from omnibot_orchestration.graph.mission_graph import route_after_recover

    state = _base_state(requires_human=True)
    assert route_after_recover(state) == "human_checkpoint"


# ── graph construction ────────────────────────────────────────────────────────


def test_build_mission_graph_compiles():
    from omnibot_orchestration.graph.mission_graph import build_mission_graph

    graph = build_mission_graph(ros_node=None)
    assert graph is not None
    node_names = set(graph.nodes)
    for expected in [
        "parse_intent",
        "navigate",
        "execute_vla",
        "observe",
        "recover",
        "human_checkpoint",
        "finalize",
    ]:
        assert expected in node_names, f"Missing node: {expected}"
