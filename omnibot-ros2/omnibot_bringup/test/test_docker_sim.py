# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""Test Docker sim, devcontainer, docker-compose, and workflow configurations (OHH-33).

Validates Dockerfile.sim, docker-compose.yml, .devcontainer/devcontainer.json,
and .github/workflows/docker-sim.yml without requiring Docker daemon or ROS runtime.
"""

import json
from pathlib import Path
import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]


def test_dockerfile_sim_exists_and_configured():
    dockerfiles = [
        REPO / "Dockerfile.sim",
        REPO / "omnibot-digital-twin" / "docker" / "Dockerfile.sim",
    ]
    for df in dockerfiles:
        assert df.is_file(), f"Missing {df}"
        content = df.read_text(encoding="utf-8")
        assert "FROM ros:jazzy-ros-base-noble" in content
        assert "ros-jazzy-desktop" in content
        assert "ros-jazzy-ros-gz" in content
        assert "ros-jazzy-nav2-bringup" in content
        assert "ros-jazzy-foxglove-bridge" in content
        assert "LIBGL_ALWAYS_SOFTWARE=1" in content
        assert "GALLIUM_DRIVER=llvmpipe" in content
        assert "colcon build" in content
        assert "/opt/omnibot/install" in content
        assert "ENTRYPOINT [\"/omnibot_entrypoint.sh\"]" in content


def test_docker_compose_files_valid_and_configured():
    compose_paths = [
        REPO / "docker-compose.yml",
        REPO / "omnibot-digital-twin" / "docker" / "docker-compose.yml",
    ]
    for cp in compose_paths:
        assert cp.is_file(), f"Missing {cp}"
        data = yaml.safe_load(cp.read_text(encoding="utf-8"))
        assert "services" in data
        assert "sim" in data["services"]
        assert "foxglove" in data["services"]

        sim = data["services"]["sim"]
        assert "ghcr.io/ohho-robotics/omnibot-sim" in sim["image"]
        assert "autonavigate:=true" in sim["command"]
        assert "sim_navigation.launch.py" in sim["command"]
        assert sim.get("depends_on") == ["foxglove"] or "foxglove" in sim.get("depends_on", {})

        foxglove = data["services"]["foxglove"]
        assert "ghcr.io/ohho-robotics/omnibot-sim" in foxglove["image"]
        assert "foxglove_bridge" in foxglove["command"]
        assert "8765:8765" in foxglove["ports"]


def test_devcontainer_json_valid():
    dc_path = REPO / ".devcontainer" / "devcontainer.json"
    assert dc_path.is_file(), f"Missing {dc_path}"
    data = json.loads(dc_path.read_text(encoding="utf-8"))
    assert "name" in data
    assert "Dockerfile.sim" in data.get("build", {}).get("dockerfile", "")
    assert 8765 in data.get("forwardPorts", [])
    assert 9090 in data.get("forwardPorts", [])
    assert "post_create.sh" in data.get("postCreateCommand", "")
    assert data.get("containerEnv", {}).get("LIBGL_ALWAYS_SOFTWARE") == "1"


def test_docker_workflow_exists_and_configured():
    wf_path = REPO / ".github" / "workflows" / "docker-sim.yml"
    assert wf_path.is_file(), f"Missing {wf_path}"
    data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    triggers = data.get("on") if "on" in data else data.get(True, {})
    assert "pull_request" in triggers
    assert "push" in triggers
    assert "v*" in triggers["push"]["tags"]

    job = data["jobs"]["docker-sim"]
    steps = job["steps"]
    step_names = [s.get("name", "") for s in steps]
    assert any("GitHub Container Registry" in n for n in step_names)
    assert any("Build Docker image" in n for n in step_names)
    assert any("Smoke test container" in n for n in step_names)
    assert any("Docker compose" in n for n in step_names)


def test_dockerignore_excludes_heavy_artifacts():
    di_path = REPO / ".dockerignore"
    assert di_path.is_file(), f"Missing {di_path}"
    content = di_path.read_text(encoding="utf-8")
    assert ".git" in content
    assert "install/" in content
    assert "build/" in content
    assert "omnibot-vr/" in content
    assert "omnibot-android/" in content


def test_sim_navigation_launch_has_autonavigate_args():
    launch_file = REPO / "omnibot-ros2" / "omnibot_navigation" / "launch" / "sim_navigation.launch.py"
    assert launch_file.is_file()
    content = launch_file.read_text(encoding="utf-8")
    assert "autonavigate" in content
    assert "foxglove" in content
    assert "route" in content
    assert "waypoint_navigator.py" in content
