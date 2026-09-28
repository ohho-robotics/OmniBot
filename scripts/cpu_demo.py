#!/usr/bin/env python3
"""CPU demo: mecanum round-trip, one Yahboom packet, one agent goal.

No ROS, no GPU, no robot. Exits 0 on success.
"""

import struct

from agent_engine.core.blackboard import WorldState
from agent_engine.core.harness import AgentHarness
from agent_engine.core.tools import ToolParam, ToolRegistry, ToolSpec
from agent_engine.core.types import Plan, ToolCall, ToolResult
from agent_engine.reasoners.scripted import ScriptedReasoner
from mecanum_drive_ros2 import (
    RobotGeometry,
    forward_kinematics,
    integrate_pose,
    inverse_kinematics,
)
from yahboom_ros2.protocol import (
    HEAD_RX,
    HEAD_TX,
    TYPE_VELOCITY,
    VelocityPacket,
    packet_motion,
    parse_rx_buffer,
)


def main() -> None:
    geom = RobotGeometry(
        wheel_radius=0.04,
        wheel_separation_width=0.215,
        wheel_separation_length=0.165,
    )
    wheels = inverse_kinematics(0.30, 0.0, 0.0, geom)
    vx, vy, omega = forward_kinematics(wheels, geom)
    x, y, _theta = integrate_pose(0.0, 0.0, 0.0, vx, vy, omega, dt=1.0)
    print(f"mecanum wheels rad/s: {tuple(round(w, 4) for w in wheels)}")
    print(f"pose after 1s at 0.30 m/s: x={x:.4f} y={y:.4f}")
    if abs(x - 0.30) > 1e-6:
        raise SystemExit("mecanum pose did not match 0.30 m")

    tx = packet_motion(0.2, 0.0, 0.0)
    payload = struct.pack("<hhh", 200, 0, 0)
    length = 3 + len(payload)
    body = bytes([length, TYPE_VELOCITY]) + payload
    rx = bytes([HEAD_TX, HEAD_RX]) + body + bytes([sum(body) & 0xFF])
    parsed = parse_rx_buffer(rx)[0][1]
    if not isinstance(parsed, VelocityPacket) or abs(parsed.vx - 0.2) > 1e-9:
        raise SystemExit("Yahboom velocity packet did not round-trip")
    print(f"yahboom TX {tx.hex()} RX vx={parsed.vx:.3f}")

    log: list[str] = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "navigate_to",
            "Drive to a named location.",
            lambda location: log.append(location)
            or ToolResult(True, f"navigating to {location}"),
            [ToolParam("location", "named location")],
        )
    )

    class _Perceptor:
        def perceive(self) -> WorldState:
            return WorldState()

    harness = AgentHarness(
        _Perceptor(),
        ScriptedReasoner(
            [
                Plan(calls=[ToolCall("navigate_to", {"location": "kitchen"})]),
                Plan(goal_complete=True),
            ]
        ),
        registry,
    )
    goal = harness.submit_goal("go to the kitchen")
    harness.run_until_idle()
    print(f"agent status={goal.status.value} tools={log}")
    if log != ["kitchen"] or goal.status.value != "succeeded":
        raise SystemExit("agent harness did not complete the kitchen goal")
    print("CPU_DEMO_OK")


if __name__ == "__main__":
    main()
