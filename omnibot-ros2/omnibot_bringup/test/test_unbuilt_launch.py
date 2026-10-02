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
