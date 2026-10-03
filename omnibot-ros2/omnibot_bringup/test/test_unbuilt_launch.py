# Copyright 2026 OhhO Robotics
# SPDX-License-Identifier: Apache-2.0
"""CPU checks for the Isaac and MuJoCo launch stubs.

Neither file needs ROS or a GPU. Each must print "not built" and exit 2.
"""

import subprocess
import sys
from pathlib import Path

import pytest

LAUNCH_DIR = Path(__file__).resolve().parents[1] / "launch"


@pytest.mark.parametrize("name", ["isaac.launch.py", "mujoco.launch.py"])
def test_unbuilt_backend_exits_2(name):
    script = LAUNCH_DIR / name
    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stdout.strip() == "not built"
    assert completed.stderr == ""


@pytest.mark.parametrize("name", ["isaac.launch.py", "mujoco.launch.py"])
def test_generate_launch_description_exits_2(name):
    script = LAUNCH_DIR / name
    code = (
        "import importlib.util\n"
        "import sys\n"
        "path = sys.argv[1]\n"
        "spec = importlib.util.spec_from_file_location('launch_stub', path)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "module.generate_launch_description()\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stdout.strip() == "not built"
    assert completed.stderr == ""
