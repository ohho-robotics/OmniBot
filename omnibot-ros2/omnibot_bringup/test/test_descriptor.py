# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""Assemble the OmniBot descriptor from YAML. No ROS install required."""

import copy
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from descriptor_assemble import (  # noqa: E402
    MAX_JOINT_STEP_RAD,
    MAX_VX_MPS,
    MAX_WZ_RAD_S,
    assemble_descriptor,
    load_descriptor_yaml,
)

YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "robot_descriptor.yaml"
LAUNCH_DIR = Path(__file__).resolve().parents[1] / "launch"
NODE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "descriptor_node.py"

JOINT_LIMITS = {
    "arm_shoulder_pan": (-3.14, 3.14),
    "arm_shoulder_lift": (-1.57, 1.57),
    "arm_elbow_flex": (-1.57, 1.57),
    "arm_wrist_flex": (-1.57, 1.57),
    "arm_wrist_roll": (-3.14, 3.14),
    "arm_gripper": (-0.1, 0.8),
}


def test_ceilings_match_omnibot():
    assert MAX_VX_MPS == 0.2
    assert MAX_WZ_RAD_S == 1.0
    assert MAX_JOINT_STEP_RAD == 0.15


def test_yaml_assembles_within_ceilings():
    doc = load_descriptor_yaml(YAML_PATH)
    assert doc["id"] == "omnibot"
    assert doc["model"] == "OmniBot"
    assert doc["v"] == "1.0.0"
    assert doc["drive"]["kind"] == "mecanum"
    assert doc["drive"]["holonomic"] is True
    assert doc["drive"]["caps"]["vx_mps"] == 0.2
    assert doc["drive"]["caps"]["vy_mps"] == 0.2
    assert doc["drive"]["caps"]["wz_rad_s"] == 1.0
    hard = doc["safety"]["hard"]
    assert hard["max_vx_mps"] <= MAX_VX_MPS
    assert hard["max_vy_mps"] <= 0.2
    assert hard["max_wz_rad_s"] <= MAX_WZ_RAD_S
    assert hard["max_accel_x_mps2"] <= 0.5
    assert hard["max_accel_y_mps2"] <= 0.5
    assert hard["max_accel_wz_rad_s2"] <= 2.0
    assert hard["max_joint_step_rad"] <= MAX_JOINT_STEP_RAD
    assert hard["max_vx_mps"] == doc["drive"]["caps"]["vx_mps"]
    assert doc["apriltags"] == []
    assert doc["topics"]["cmd"] == "/cmd_vel"
    assert doc["topics"]["state"] == "/odom"
    assert doc["topics"]["estop"] == "/emergency_stop"
    assert doc["topics"]["heartbeat"] == "/ohho/heartbeat"
    assert doc["topics"]["telemetry"] == "/ohho/telemetry"
    assert doc["telemetry"]["schema_id"] == "ohho.telemetry.v1"
    assert doc["telemetry"]["robot_id"] == "omnibot"
    assert doc["telemetry"]["kind"] == "real"
    assert doc["telemetry"]["fields"] == ["base", "joints", "imu"]
    joints = doc["arms"][0]["joints"]
    assert [joint["name"] for joint in joints] == list(JOINT_LIMITS)
    for joint in joints:
        lo, hi = JOINT_LIMITS[joint["name"]]
        assert joint["min"] >= lo
        assert joint["max"] <= hi
        assert lo <= joint["home"] <= hi
    topics = set(doc["topics"]["images"])
    for camera in doc["cameras"]:
        assert camera["topic"] in topics


def test_sim_kind_override_keeps_caps():
    real = load_descriptor_yaml(YAML_PATH)
    sim = load_descriptor_yaml(YAML_PATH, kind="sim")
    assert sim["telemetry"]["kind"] == "sim"
    assert sim["safety"] == real["safety"]
    assert sim["drive"] == real["drive"]


def test_raised_cap_is_refused():
    doc = load_descriptor_yaml(YAML_PATH)
    raised = copy.deepcopy(doc)
    raised["safety"]["hard"]["max_vx_mps"] = 0.21
    with pytest.raises(ValueError, match="ceiling"):
        assemble_descriptor(raised)


def test_drive_cap_above_hard_cap_is_refused():
    doc = load_descriptor_yaml(YAML_PATH)
    wider = copy.deepcopy(doc)
    wider["safety"]["hard"]["max_vx_mps"] = 0.1
    wider["drive"]["caps"]["vx_mps"] = 0.2
    with pytest.raises(ValueError, match="exceeds"):
        assemble_descriptor(wider)


def test_joint_home_outside_limits_is_refused():
    doc = load_descriptor_yaml(YAML_PATH)
    bad = copy.deepcopy(doc)
    bad["arms"][0]["joints"][0]["home"] = 4.0
    with pytest.raises(ValueError, match="home"):
        assemble_descriptor(bad)


def test_descriptor_node_is_executable():
    # colcon --symlink-install keeps this mode. launch's which() skips a
    # non-executable file and reports it missing from libexec.
    root = Path(__file__).resolve().parents[3]
    listed = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-s",
            "--",
            "omnibot-ros2/omnibot_bringup/scripts/descriptor_node.py",
        ],
        cwd=root,
        text=True,
    )
    assert listed.startswith("100755")


def test_publisher_is_latched_on_the_contract_topic():
    text = NODE_PATH.read_text(encoding="utf-8")
    assert "DurabilityPolicy.TRANSIENT_LOCAL" in text
    assert '"/ohho/descriptor"' in text
    assert "descriptor_assemble" in text


def test_so101_arm_only_descriptor_has_no_base_motion():
    path = Path(__file__).resolve().parents[1] / "config" / "so101_arm_only_descriptor.yaml"
    text = path.read_text(encoding="utf-8")
    assert "cmd_vel" not in text
    doc = load_descriptor_yaml(path, kind="sim")
    assert doc["id"] == "so101-arm"
    assert doc["model"] == "SO-101"
    assert doc["v"] == "1.0.0"
    assert doc["drive"]["kind"] == "fixed-base"
    assert doc["drive"]["holonomic"] is False
    assert doc["drive"]["caps"] == {"vx_mps": 0, "vy_mps": 0, "wz_rad_s": 0}
    hard = doc["safety"]["hard"]
    assert hard["max_vx_mps"] == 0
    assert hard["max_vy_mps"] == 0
    assert hard["max_wz_rad_s"] == 0
    assert hard["max_accel_x_mps2"] == 0
    assert hard["max_accel_y_mps2"] == 0
    assert hard["max_accel_wz_rad_s2"] == 0
    assert hard["max_joint_step_rad"] == MAX_JOINT_STEP_RAD
    assert hard["max_joint_step_rad"] <= MAX_JOINT_STEP_RAD
    assert doc["topics"]["cmd"] == "/arm/joint_commands"
    assert doc["topics"]["state"] == "/arm/joint_states"
    assert doc["topics"]["estop"] == "/emergency_stop"
    assert "cmd_vel" not in doc["topics"]["cmd"]
    assert doc["telemetry"]["kind"] == "sim"
    assert doc["telemetry"]["robot_id"] == "so101-arm"
    assert doc["telemetry"]["fields"] == ["joints", "gripper"]
    assert "base" not in doc["telemetry"]["fields"]
    joints = doc["arms"][0]["joints"]
    assert doc["arms"][0]["name"] == "so101"
    assert [joint["name"] for joint in joints] == list(JOINT_LIMITS)
    for joint in joints:
        lo, hi = JOINT_LIMITS[joint["name"]]
        assert joint["min"] >= lo
        assert joint["max"] <= hi
        assert lo <= joint["home"] <= hi
    assert doc["cameras"][0]["topic"] == "/camera/wrist/image_raw"
    assert doc["cameras"][0]["topic"] in doc["topics"]["images"]


def test_so101_arm_sim_launch_publishes_descriptor_without_a_base():
    launch = (LAUNCH_DIR / "so101_arm_sim.launch.py").read_text(encoding="utf-8")
    compile(launch, "so101_arm_sim.launch.py", "exec")
    assert "arm_driver_node.py" in launch
    assert "arm_params.yaml" in launch
    assert "so101_arm_only_descriptor.yaml" in launch
    assert "descriptor_node.py" in launch
    assert '"/ohho/descriptor"' in (NODE_PATH.read_text(encoding="utf-8"))
    assert '{"simulate": True}' in launch
    assert '"kind": "sim"' in launch
    assert '("/arm/joint_commands/out", "/arm/joint_commands")' in launch
    assert "cmd_vel" not in launch
    assert "yahboom" not in launch.lower()
    assert "cmd_vel_mux" not in launch


def test_robot_and_sim_launches_wire_the_publisher():
    robot = (LAUNCH_DIR / "robot.launch.py").read_text(encoding="utf-8")
    sim = (LAUNCH_DIR / "sim.launch.py").read_text(encoding="utf-8")
    for text in (robot, sim):
        assert '"descriptor"' in text
        assert "descriptor_node.py" in text
        assert "robot_descriptor.yaml" in text
        assert "Publish the latched RobotDescriptor JSON on /ohho/descriptor" in text
    assert '"kind": "real"' in robot
    assert '"kind": "sim"' in sim
