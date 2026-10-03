#!/usr/bin/env python3
"""
Arm Command Multiplexer for OmniBot.

Selects one arm joint command source and forwards it to /arm/joint_commands/out.
arm_driver_node subscribes to /arm/joint_commands/out.

Topic routing
─────────────
  Inputs (one active at a time):
    /arm/joint_commands        ← policy_node / Android / teleop_recorder
    /arm/joint_commands/rl     ← RL arm policy (rl_arm_node)

  Mode control:
    /control_mode  ← std_msgs/String  "teleop" | "vla" | "nav2" | "rl_nav"
    /arm/cmd_mode  ← std_msgs/String  "policy" | "rl_arm"
    /emergency_stop ← std_msgs/Bool   true holds both arm sources

  Output:
    /arm/joint_commands/out  → arm_driver_node

  Feedback:
    /arm/cmd_mode/active  → currently selected arm source (published at 1 Hz)

Usage
─────
  # Autonomous arm motion stays idle until a human sets /control_mode.
  ros2 topic pub /control_mode std_msgs/msg/String "data: 'vla'"
  ros2 topic pub /arm/cmd_mode std_msgs/msg/String "data: 'policy'"

  ros2 topic pub /control_mode std_msgs/msg/String "data: 'rl_nav'"
  ros2 topic pub /arm/cmd_mode std_msgs/msg/String "data: 'rl_arm'"

  # Hold both arm sources again
  ros2 topic pub /control_mode std_msgs/msg/String "data: 'teleop'"

Startup control mode is teleop, so policy and RL arm commands are not
forwarded until /control_mode is vla, nav2, or rl_nav. /arm/joint_commands
is shared by the visuomotor policy and Android joint teleop, so Android
arm commands are held in teleop as well. Base teleop uses /cmd_vel/teleop
and is not gated here. Not run on hardware in this change.

This mux does not clamp, hold, or drop torque. arm_driver_node applies
those checks on /arm/joint_commands/out (emergency stop, 200 ms silence
hold, joint limits, and MAX_JOINT_DELTA_RAD per cycle).
"""

from omnibot_rl.arm_stream_gate import ArmStreamGate

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, String


class ArmCmdMux(Node):
    """
    Mode-based arm joint command multiplexer.

    Parameters
    ----------
    default_mode : str
        Arm source preferred once /control_mode is autonomous.
        "policy", "rl_arm", or "teleop" (default). Any value still starts
        with control mode teleop, so arm outputs stay idle at startup.
    """

    VALID_MODES = ("policy", "rl_arm")

    def __init__(self):
        super().__init__("arm_cmd_mux")

        self.declare_parameter("default_mode", "teleop")
        requested = self.get_parameter("default_mode").value
        self._gate = ArmStreamGate.from_default_mode(requested)
        self._active_mode: str = self._gate.arm_mode

        # ── Inputs ────────────────────────────────────────────────────────────
        self.create_subscription(JointState, "/arm/joint_commands", self._policy_cb, 10)
        self.create_subscription(
            JointState, "/arm/joint_commands/rl", self._rl_arm_cb, 10
        )
        self.create_subscription(String, "/arm/cmd_mode", self._mode_cb, 10)
        self.create_subscription(String, "/control_mode", self._control_mode_cb, 10)
        self.create_subscription(Bool, "/emergency_stop", self._estop_cb, 10)

        # ── Output ────────────────────────────────────────────────────────────
        self._out_pub = self.create_publisher(JointState, "/arm/joint_commands/out", 10)
        self._active_mode_pub = self.create_publisher(
            String, "/arm/cmd_mode/active", 10
        )

        self.create_timer(1.0, self._publish_active_mode)

        self.get_logger().info(
            f'ArmCmdMux ready. Control mode: "{self._gate.control_mode}" '
            f'(arm outputs held). Arm source preference: "{self._active_mode}". '
            f"Valid arm sources: {self.VALID_MODES}"
        )

    # ── Mode switch ───────────────────────────────────────────────────────────

    def _mode_cb(self, msg: String) -> None:
        if not self._gate.set_arm_mode(msg.data):
            shown = msg.data.strip().lower() if isinstance(msg.data, str) else msg.data
            self.get_logger().warn(
                f'Unknown arm mode "{shown}" ignored. Valid: {self.VALID_MODES}'
            )
            return
        if self._gate.arm_mode != self._active_mode:
            self.get_logger().info(
                f"[ArmCmdMux] Mode: {self._active_mode} → {self._gate.arm_mode}"
            )
            self._active_mode = self._gate.arm_mode
            self._publish_active_mode()

    def _control_mode_cb(self, msg: String) -> None:
        previous = self._gate.control_mode
        if not self._gate.set_control_mode(msg.data):
            shown = msg.data.strip().lower() if isinstance(msg.data, str) else msg.data
            self.get_logger().warn(
                f'Unknown control mode "{shown}" ignored. '
                f"Valid: {ArmStreamGate.VALID_CONTROL_MODES}"
            )
            return
        if self._gate.arm_mode != self._active_mode:
            self._active_mode = self._gate.arm_mode
            self._publish_active_mode()
        if self._gate.control_mode != previous:
            self.get_logger().info(
                f"[ArmCmdMux] Control mode: {previous} → {self._gate.control_mode}"
            )

    def _estop_cb(self, msg: Bool) -> None:
        rising = bool(msg.data) and not self._gate.emergency_stop
        self._gate.set_emergency_stop(msg.data)
        if rising:
            self.get_logger().warn("Emergency stop — arm commands held.")
        elif not msg.data:
            self.get_logger().info("Emergency stop cleared.")

    # ── Source callbacks ──────────────────────────────────────────────────────

    def _policy_cb(self, msg: JointState) -> None:
        if self._gate.allows("policy"):
            self._out_pub.publish(msg)

    def _rl_arm_cb(self, msg: JointState) -> None:
        if self._gate.allows("rl_arm"):
            self._out_pub.publish(msg)

    # ── Periodic feedback ─────────────────────────────────────────────────────

    def _publish_active_mode(self) -> None:
        msg = String()
        msg.data = self._active_mode
        self._active_mode_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ArmCmdMux()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
