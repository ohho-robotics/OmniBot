# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""Teleop-default gate tests. No ROS 2 install required.

The mux nodes are also imported in a subprocess with stubbed rclpy so the
wrapper wiring is checked on machines that do not have ROS.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
HYBRID_ROOT = REPO / "omnibot-ros2" / "omnibot_hybrid"
RL_ROOT = REPO / "omnibot-ai-ros2" / "omnibot_rl"
LAUNCH = (
    REPO
    / "omnibot-ros2"
    / "omnibot_bringup"
    / "launch"
    / "mobile_manipulation.launch.py"
)
CMD_VEL_MUX = HYBRID_ROOT / "omnibot_hybrid" / "cmd_vel_mux.py"

sys.path.insert(0, str(HYBRID_ROOT))
sys.path.insert(0, str(RL_ROOT))

from omnibot_hybrid.stream_gate import StreamGate  # noqa: E402
from omnibot_rl.arm_stream_gate import ArmStreamGate  # noqa: E402


def test_launch_starts_in_teleop():
    text = LAUNCH.read_text(encoding="utf-8")
    assert 'parameters=[{"default_mode": "teleop"}]' in text
    assert 'parameters=[rl_arm_params, {"default_mode": "teleop"}]' in text
    assert '"default_mode": "vla"' not in text
    assert '"default_mode": "nav2"' not in text


def test_cmd_vel_mux_parameter_default_is_teleop():
    text = CMD_VEL_MUX.read_text(encoding="utf-8")
    assert 'declare_parameter("default_mode", "teleop")' in text


def test_default_holds_autonomous_sources_and_passes_teleop():
    base = StreamGate()
    arm = ArmStreamGate.from_default_mode("policy")
    assert base.mode == "teleop"
    assert arm.control_mode == "teleop"
    assert base.base_allows("teleop") is True
    for source in ("nav2", "vla", "rl_nav"):
        assert base.base_allows(source) is False
    assert arm.allows("policy") is False
    assert arm.allows("rl_arm") is False


@pytest.mark.parametrize("mode", ["vla", "nav2", "rl_nav"])
def test_autonomous_mode_releases_matching_streams(mode):
    base = StreamGate()
    arm = ArmStreamGate.from_default_mode("teleop")
    assert base.set_mode(mode) is True
    assert arm.set_control_mode(mode) is True
    assert base.base_allows(mode) is True
    assert base.base_allows("teleop") is False
    if mode == "rl_nav":
        assert arm.allows("rl_arm") is True
        assert arm.allows("policy") is False
    else:
        assert arm.allows("policy") is True
        assert arm.allows("rl_arm") is False


def test_return_to_teleop_stops_both_streams_within_one_call():
    base = StreamGate()
    arm = ArmStreamGate()
    base.set_mode("vla")
    arm.set_control_mode("vla")
    assert base.base_allows("vla") is True
    assert arm.allows("policy") is True

    assert base.set_mode("teleop") is True
    assert arm.set_control_mode("teleop") is True
    assert base.take_base_stop() is True
    assert base.base_allows("vla") is False
    assert base.base_allows("nav2") is False
    assert base.base_allows("rl_nav") is False
    assert base.base_allows("teleop") is True
    assert arm.allows("policy") is False
    assert arm.allows("rl_arm") is False
    assert base.take_base_stop() is False


def test_emergency_stop_stops_both_streams_within_one_call():
    base = StreamGate()
    arm = ArmStreamGate()
    base.set_mode("nav2")
    arm.set_control_mode("rl_nav")
    base.set_emergency_stop(True)
    arm.set_emergency_stop(True)
    assert base.take_base_stop() is True
    assert base.base_allows("nav2") is False
    assert base.base_allows("teleop") is False
    assert arm.allows("rl_arm") is False
    assert arm.allows("policy") is False

    base.set_emergency_stop(False)
    arm.set_emergency_stop(False)
    assert base.base_allows("nav2") is True
    assert arm.allows("rl_arm") is True


def test_unknown_mode_is_ignored():
    base = StreamGate()
    arm = ArmStreamGate()
    assert base.set_mode("VLA") is True
    assert arm.set_control_mode("  NAV2  ") is True
    assert base.set_mode("nope") is False
    assert arm.set_control_mode("smolvla") is False
    assert base.mode == "vla"
    assert arm.control_mode == "nav2"
    assert arm.set_arm_mode("not-a-mode") is False


def test_invalid_default_falls_back_to_teleop():
    assert StreamGate("nav2-now").mode == "teleop"
    held = ArmStreamGate.from_default_mode("policy")
    assert held.control_mode == "teleop"
    assert held.allows("policy") is False


def test_repeated_teleop_does_not_zero_again():
    base = StreamGate("vla")
    base.set_mode("teleop")
    assert base.take_base_stop() is True
    base.set_mode("teleop")
    assert base.take_base_stop() is False


def _run_stubbed(script):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(HYBRID_ROOT), str(RL_ROOT), env.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_cmd_vel_mux_wrapper_without_ros():
    _run_stubbed(
        """
        import sys
        from types import ModuleType, SimpleNamespace

        def _pkg(name):
            module = ModuleType(name)
            sys.modules[name] = module
            return module

        rclpy = _pkg("rclpy")
        rclpy.init = lambda *a, **k: None
        rclpy.shutdown = lambda *a, **k: None
        rclpy.spin = lambda *a, **k: None
        node_mod = _pkg("rclpy.node")

        class Pub:
            def __init__(self):
                self.msgs = []
            def publish(self, msg):
                self.msgs.append(msg)

        class Node:
            def __init__(self, name):
                self._params = {}
            def declare_parameter(self, name, default):
                self._params[name] = default
            def get_parameter(self, name):
                return SimpleNamespace(value=self._params[name])
            def create_subscription(self, *a, **k):
                return None
            def create_publisher(self, *a, **k):
                return Pub()
            def create_timer(self, *a, **k):
                return None
            def get_logger(self):
                return SimpleNamespace(
                    info=lambda *a, **k: None,
                    warn=lambda *a, **k: None,
                )
            def destroy_node(self):
                return None

        node_mod.Node = Node
        geom = _pkg("geometry_msgs")
        geom_msg = _pkg("geometry_msgs.msg")
        geom.msg = geom_msg

        class Twist:
            def __init__(self):
                self.linear = SimpleNamespace(x=0.0, y=0.0, z=0.0)
                self.angular = SimpleNamespace(x=0.0, y=0.0, z=0.0)

        geom_msg.Twist = Twist
        std = _pkg("std_msgs")
        std_msg = _pkg("std_msgs.msg")
        std.msg = std_msg

        class StringMsg:
            def __init__(self):
                self.data = ""

        class BoolMsg:
            def __init__(self):
                self.data = False

        std_msg.String = StringMsg
        std_msg.Bool = BoolMsg

        from omnibot_hybrid.cmd_vel_mux import CmdVelMux

        node = CmdVelMux()
        assert node._active_mode == "teleop"
        twist = Twist()
        twist.linear.x = 0.5
        node._nav2_cb(twist)
        node._vla_cb(twist)
        node._rl_nav_cb(twist)
        assert node._out_pub.msgs == []
        teleop = Twist()
        teleop.linear.x = 0.2
        node._teleop_cb(teleop)
        assert node._out_pub.msgs[-1].linear.x == 0.2

        mode = StringMsg()
        mode.data = "vla"
        node._mode_cb(mode)
        node._out_pub.msgs.clear()
        node._vla_cb(twist)
        assert node._out_pub.msgs[-1].linear.x == 0.5

        back = StringMsg()
        back.data = "teleop"
        node._mode_cb(back)
        assert node._out_pub.msgs[-1].linear.x == 0.0
        node._out_pub.msgs.clear()
        node._vla_cb(twist)
        assert node._out_pub.msgs == []
        node._teleop_cb(teleop)
        assert len(node._out_pub.msgs) == 1

        stop = BoolMsg()
        stop.data = True
        node._estop_cb(stop)
        assert node._out_pub.msgs[-1].linear.x == 0.0
        node._out_pub.msgs.clear()
        node._teleop_cb(teleop)
        assert node._out_pub.msgs == []
        """
    )


def test_arm_cmd_mux_wrapper_without_ros():
    _run_stubbed(
        """
        import sys
        from types import ModuleType, SimpleNamespace

        def _pkg(name):
            module = ModuleType(name)
            sys.modules[name] = module
            return module

        rclpy = _pkg("rclpy")
        rclpy.init = lambda *a, **k: None
        rclpy.shutdown = lambda *a, **k: None
        rclpy.spin = lambda *a, **k: None
        node_mod = _pkg("rclpy.node")

        class Pub:
            def __init__(self):
                self.msgs = []
            def publish(self, msg):
                self.msgs.append(msg)

        class Node:
            def __init__(self, name):
                self._params = {}
            def declare_parameter(self, name, default):
                self._params[name] = default
            def get_parameter(self, name):
                return SimpleNamespace(value=self._params[name])
            def create_subscription(self, *a, **k):
                return None
            def create_publisher(self, *a, **k):
                return Pub()
            def create_timer(self, *a, **k):
                return None
            def get_logger(self):
                return SimpleNamespace(
                    info=lambda *a, **k: None,
                    warn=lambda *a, **k: None,
                )
            def destroy_node(self):
                return None

        node_mod.Node = Node
        sensor = _pkg("sensor_msgs")
        sensor_msg = _pkg("sensor_msgs.msg")
        sensor.msg = sensor_msg

        class JointState:
            def __init__(self):
                self.position = []

        sensor_msg.JointState = JointState
        std = _pkg("std_msgs")
        std_msg = _pkg("std_msgs.msg")
        std.msg = std_msg

        class StringMsg:
            def __init__(self):
                self.data = ""

        class BoolMsg:
            def __init__(self):
                self.data = False

        std_msg.String = StringMsg
        std_msg.Bool = BoolMsg

        from omnibot_rl.arm_cmd_mux import ArmCmdMux

        node = ArmCmdMux()
        assert node._gate.control_mode == "teleop"
        cmd = JointState()
        cmd.position = [0.1]
        node._policy_cb(cmd)
        node._rl_arm_cb(cmd)
        assert node._out_pub.msgs == []

        mode = StringMsg()
        mode.data = "vla"
        node._control_mode_cb(mode)
        node._policy_cb(cmd)
        assert len(node._out_pub.msgs) == 1
        node._rl_arm_cb(cmd)
        assert len(node._out_pub.msgs) == 1

        back = StringMsg()
        back.data = "teleop"
        node._control_mode_cb(back)
        node._out_pub.msgs.clear()
        node._policy_cb(cmd)
        node._rl_arm_cb(cmd)
        assert node._out_pub.msgs == []

        mode.data = "rl_nav"
        node._control_mode_cb(mode)
        node._rl_arm_cb(cmd)
        assert len(node._out_pub.msgs) == 1
        stop = BoolMsg()
        stop.data = True
        node._estop_cb(stop)
        node._out_pub.msgs.clear()
        node._rl_arm_cb(cmd)
        node._policy_cb(cmd)
        assert node._out_pub.msgs == []
        """
    )
