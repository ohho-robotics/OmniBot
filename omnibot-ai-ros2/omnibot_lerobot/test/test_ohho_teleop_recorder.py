"""Headless tests for ohho-os Recorder bridge (no ROS spin)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
ENGINES = REPO / "omnibot-ai-engines"
sys.path.insert(0, str(REPO / "omnibot-ai-ros2" / "omnibot_lerobot"))
if str(ENGINES) not in sys.path:
    sys.path.insert(0, str(ENGINES))

ohho = pytest.importorskip("ohho")

from omnibot_lerobot.ohho_teleop_recorder import OhhoTeleopRecorder
from data_engine.scripts.validate_dataset import validate


def test_ohho_recorder_writes_valid_dataset(tmp_path: Path):
    rec = OhhoTeleopRecorder("local/unit_test", fps=10.0)
    rec.start_episode("test task")
    for i in range(3):
        state = np.linspace(0, 0.1, 9, dtype=np.float32)
        action = state.copy()
        wrist = np.zeros((8, 8, 3), dtype=np.uint8) + i
        bev = np.zeros((8, 8, 3), dtype=np.uint8) + i * 2
        rec.capture_frame(
            state,
            action,
            wrist,
            bev,
            wall_timestamp=float(i) / 10.0,
            wrist_timestamp=float(i) / 10.0,
            bev_timestamp=float(i) / 10.0 + 0.005,
        )
    out = tmp_path / "dataset"
    os.makedirs(out, exist_ok=True)
    rec.save_episode(str(out), "test task", 10.0, "local/unit_test")
    assert validate(out, verbose=False)
