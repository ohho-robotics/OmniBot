"""Tests for episode quality filter (OHH-99).

Verifies the four reject rules on synthetic episodes:
  1. Identical frames for >0.5 s (frozen video)
  2. Wrist vs bird's-eye view camera timestamp delta >50 ms (skew)
  3. Joint step >0.5 rad between frames (joint jump)
  4. Episode shorter than 2 s (short take)

Also tests CLI invocation, custom threshold flags, FrameSource abstraction,
and OHH-49 demonstration count filtering.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_engine.quality.episode_filter import (
    DatasetFilterResult,
    DiskFrameSource,
    EpisodeQualityFilter,
    FilterThresholds,
    InMemoryFrameSource,
    check_camera_skew,
    check_duration,
    check_frozen_frames,
    check_joint_jump,
    filter_dataset,
    score_episode,
)
from data_engine.schema.camera_keys import (
    LEROBOT_IMAGE_KEYS,
    OBSERVATION_IMAGE_BEV,
    OBSERVATION_IMAGE_WRIST,
)
from data_engine.schema.constants import ARM_JOINT_NAMES

ENGINES = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Unit tests: Rule 1 — Episode duration
# ---------------------------------------------------------------------------


def test_duration_rule_rejects_under_two_seconds():
    # 45 frames at 30 fps = 1.467 s (< 2.0 s)
    t = np.linspace(0.0, 1.467, 45)
    duration, rejected, reason = check_duration(t, len(t), fps=30.0, min_duration_s=2.0)
    assert rejected is True
    assert duration < 2.0
    assert reason is not None
    assert "episode_too_short" in reason


def test_duration_rule_keeps_over_two_seconds():
    # 75 frames at 30 fps = 2.467 s (>= 2.0 s)
    t = np.linspace(0.0, 2.5, 75)
    duration, rejected, reason = check_duration(t, len(t), fps=30.0, min_duration_s=2.0)
    assert rejected is False
    assert duration >= 2.0
    assert reason is None


def test_duration_threshold_boundary():
    # Exactly 2.0 s -> keep
    t_exact = np.array([0.0, 2.0])
    dur, rej, _ = check_duration(t_exact, 2, min_duration_s=2.0)
    assert rej is False
    assert dur == 2.0

    # 1.99 s -> reject
    t_short = np.array([0.0, 1.99])
    dur, rej, _ = check_duration(t_short, 2, min_duration_s=2.0)
    assert rej is True


# ---------------------------------------------------------------------------
# Unit tests: Rule 2 — Joint step between frames
# ---------------------------------------------------------------------------


def test_joint_jump_rule_rejects_step_over_half_radian():
    # 60 frames, 6 joints. Frame 20 jumps by 0.6 rad on shoulder_lift (joint 1).
    states = np.zeros((60, 9), dtype=np.float32)
    states[20:, 1] = 0.6  # step from 0.0 to 0.6 > 0.5 rad

    max_step, rejected, reason = check_joint_jump(states, max_joint_step_rad=0.5)
    assert rejected is True
    assert max_step == pytest.approx(0.6, abs=1e-4)
    assert reason is not None
    assert "joint_jump" in reason
    assert "shoulder_lift" in reason


def test_joint_jump_rule_keeps_smooth_trajectories():
    # Smooth sine wave trajectory, max step ~0.05 rad
    t = np.linspace(0, 1, 60)
    states = np.zeros((60, 9), dtype=np.float32)
    for j in range(6):
        states[:, j] = 0.2 * np.sin(2 * np.pi * t + j)

    max_step, rejected, reason = check_joint_jump(states, max_joint_step_rad=0.5)
    assert rejected is False
    assert max_step < 0.5
    assert reason is None


def test_joint_jump_threshold_boundary():
    # Step of exactly 0.5 rad -> keep
    states_exact = np.array([[0.0] * 6, [0.5] + [0.0] * 5], dtype=np.float32)
    _, rej, _ = check_joint_jump(states_exact, max_joint_step_rad=0.5)
    assert rej is False

    # Step of 0.51 rad -> reject
    states_jump = np.array([[0.0] * 6, [0.51] + [0.0] * 5], dtype=np.float32)
    _, rej, _ = check_joint_jump(states_jump, max_joint_step_rad=0.5)
    assert rej is True


# ---------------------------------------------------------------------------
# Unit tests: Rule 3 — Wrist vs BEV timestamp skew
# ---------------------------------------------------------------------------


def test_camera_skew_rule_rejects_skew_over_50ms():
    # 60 frames at 30 fps
    t_wrist = np.linspace(0.0, 2.0, 60)
    t_bev = t_wrist.copy()
    # Introduce 60 ms delta at frame 15
    t_bev[15] += 0.060

    max_skew, rejected, reason = check_camera_skew(
        t_wrist, t_bev, max_camera_skew_s=0.05
    )
    assert rejected is True
    assert max_skew == pytest.approx(0.060, abs=1e-4)
    assert reason is not None
    assert "camera_timestamp_skew" in reason
    assert "60.0 ms" in reason


def test_camera_skew_rule_keeps_aligned_timestamps():
    t_wrist = np.linspace(0.0, 2.0, 60)
    t_bev = t_wrist + 0.010  # 10 ms jitter <= 50 ms

    max_skew, rejected, reason = check_camera_skew(
        t_wrist, t_bev, max_camera_skew_s=0.05
    )
    assert rejected is False
    assert max_skew == pytest.approx(0.010, abs=1e-4)
    assert reason is None


def test_camera_skew_threshold_boundary():
    t_w = np.array([0.0, 0.1])
    # Exactly 50 ms -> keep
    t_b_exact = np.array([0.05, 0.15])
    _, rej, _ = check_camera_skew(t_w, t_b_exact, max_camera_skew_s=0.05)
    assert rej is False

    # 51 ms -> reject
    t_b_skew = np.array([0.051, 0.151])
    _, rej, _ = check_camera_skew(t_w, t_b_skew, max_camera_skew_s=0.05)
    assert rej is True


# ---------------------------------------------------------------------------
# Unit tests: Rule 4 — Frozen video (identical frames > 0.5 s)
# ---------------------------------------------------------------------------


def test_frozen_camera_rule_rejects_identical_frames_over_half_second():
    # At 30 fps, 17 identical frames = 16 intervals * 0.0333 s = 0.533 s (> 0.5 s)
    fps = 30.0
    frames = [np.full((4, 4, 3), 42, dtype=np.uint8) for _ in range(17)]
    timestamps = np.arange(17) / fps

    max_frozen, rejected, reason = check_frozen_frames(
        frames=frames,
        timestamps=timestamps,
        fps=fps,
        max_frozen_s=0.5,
        cam_key="observation.images.wrist",
    )
    assert rejected is True
    assert max_frozen > 0.5
    assert reason is not None
    assert "frozen_video" in reason
    assert "observation.images.wrist" in reason


def test_frozen_camera_rule_keeps_dynamic_video():
    fps = 30.0
    n = 60
    # Every frame has a different pixel value
    frames = [np.full((4, 4, 3), i % 256, dtype=np.uint8) for i in range(n)]
    timestamps = np.arange(n) / fps

    max_frozen, rejected, reason = check_frozen_frames(
        frames=frames,
        timestamps=timestamps,
        fps=fps,
        max_frozen_s=0.5,
    )
    assert rejected is False
    assert max_frozen == 0.0
    assert reason is None


def test_frozen_camera_threshold_boundary():
    fps = 30.0
    # 15 frames = 14 intervals * (1/30) = 0.467 s <= 0.5 s -> keep
    frames_short = [np.full((2, 2, 3), 1, dtype=np.uint8) for _ in range(15)]
    ts_short = np.arange(15) / fps
    dur, rej, _ = check_frozen_frames(frames_short, ts_short, fps=fps, max_frozen_s=0.5)
    assert rej is False
    assert dur <= 0.5

    # 17 frames = 16 intervals * (1/30) = 0.533 s > 0.5 s -> reject
    frames_long = [np.full((2, 2, 3), 1, dtype=np.uint8) for _ in range(17)]
    ts_long = np.arange(17) / fps
    dur, rej, _ = check_frozen_frames(frames_long, ts_long, fps=fps, max_frozen_s=0.5)
    assert rej is True
    assert dur > 0.5


# ---------------------------------------------------------------------------
# Score episode with FrameSource abstraction
# ---------------------------------------------------------------------------


def test_score_episode_with_in_memory_frame_source():
    fps = 30.0
    n = 90  # 3.0 s
    t = np.arange(n) / fps
    states = np.zeros((n, 9), dtype=np.float32)

    # Clean frames for wrist and BEV
    source = InMemoryFrameSource(
        {
            OBSERVATION_IMAGE_WRIST: [
                np.full((4, 4, 3), i, dtype=np.uint8) for i in range(n)
            ],
            OBSERVATION_IMAGE_BEV: [
                np.full((4, 4, 3), i, dtype=np.uint8) for i in range(n)
            ],
        }
    )

    score = score_episode(
        episode_index=0,
        states=states,
        timestamps=t,
        wrist_timestamps=t,
        bev_timestamps=t,
        frame_source=source,
        fps=fps,
    )
    assert score.passed is True
    assert score.status == "keep"
    assert len(score.reasons) == 0
    assert score.metrics.duration_s == pytest.approx(3.0 - (1.0 / 30.0), abs=0.1)


def test_score_episode_collects_multiple_reasons():
    # Episode with BOTH joint jump and short duration
    t = np.array([0.0, 0.5, 1.0])  # 1.0 s < 2.0 s
    states = np.zeros((3, 9), dtype=np.float32)
    states[1, 0] = 0.8  # 0.8 rad jump > 0.5 rad

    score = score_episode(
        episode_index=1,
        states=states,
        timestamps=t,
    )
    assert score.passed is False
    assert score.status == "reject"
    assert len(score.reasons) == 2
    rule_tags = [r.split(":")[0] for r in score.reasons]
    assert "episode_too_short" in rule_tags
    assert "joint_jump" in rule_tags


# ---------------------------------------------------------------------------
# Synthetic Dataset on Disk: test all rules via filter_dataset & CLI
# ---------------------------------------------------------------------------


def _write_synthetic_dataset_with_cases(root: Path) -> dict[str, int]:
    """Build a synthetic dataset on disk containing 5 episodes:
    ep 0: CLEAN (keep)
    ep 1: SHORT DURATION (reject: duration 1.0 s < 2.0 s)
    ep 2: JOINT JUMP (reject: step 0.7 rad > 0.5 rad)
    ep 3: CAMERA SKEW (reject: wrist vs bev delta 70 ms > 50 ms)
    ep 4: FROZEN VIDEO (reject: wrist identical frames for 0.7 s > 0.5 s)
    """
    meta = root / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    fps = 30

    episodes_meta = []
    cases = {
        "clean": 0,
        "short": 1,
        "joint_jump": 2,
        "camera_skew": 3,
        "frozen_video": 4,
    }

    # Episode definitions:
    # 0: Clean: 90 frames (3.0 s), smooth motion, aligned timestamps, distinct frames
    # 1: Short: 30 frames (1.0 s)
    # 2: Joint jump: 90 frames, frame 30 jumps 0.7 rad
    # 3: Skew: 90 frames, wrist vs bev delta 70 ms
    # 4: Frozen: 90 frames, wrist identical for 25 frames (25/30 = 0.83 s)

    total_frames = 0
    for name, ep_idx in cases.items():
        n = 30 if name == "short" else 90
        total_frames += n
        episodes_meta.append({"episode_index": ep_idx, "tasks": [0], "length": n})

        t = np.arange(n, dtype=np.float64) / fps
        t_wrist = t.copy()
        t_bev = t.copy()

        states = np.zeros((n, 9), dtype=np.float32)
        # Small continuous ramp so steps are ~0.005 rad
        for j in range(6):
            states[:, j] = np.linspace(0.0, 0.4, n)

        if name == "joint_jump":
            states[30:, 2] += 0.7  # elbow_flex jump

        if name == "camera_skew":
            t_bev[20:] += 0.070  # 70 ms skew

        table = pa.table(
            {
                "observation.state": [states[i].tolist() for i in range(n)],
                "action": [[0.0] * 9 for _ in range(n)],
                "timestamp": t.tolist(),
                "observation.images.wrist.timestamp": t_wrist.tolist(),
                "observation.images.bev.timestamp": t_bev.tolist(),
                "frame_index": list(range(n)),
                "episode_index": [ep_idx] * n,
                "index": list(range(n)),
                "task_index": [0] * n,
                "next.done": [i == n - 1 for i in range(n)],
            }
        )

        chunk = f"chunk-{ep_idx // 1000:03d}"
        data_dir = root / "data" / chunk
        data_dir.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, data_dir / f"episode_{ep_idx:06d}.parquet")

        # Save synthetic camera frames as .npy (DiskFrameSource reads these without codecs)
        wrist_frames = np.zeros((n, 8, 8, 3), dtype=np.uint8)
        bev_frames = np.zeros((n, 8, 8, 3), dtype=np.uint8)

        for i in range(n):
            bev_frames[i] = (i * 3) % 256
            if name == "frozen_video" and 20 <= i <= 45:
                # 26 identical frames (25/30 = 0.83 s > 0.5 s)
                wrist_frames[i] = wrist_frames[20]
            else:
                wrist_frames[i] = (i * 2) % 256

        for cam_key, frames_arr in [
            (OBSERVATION_IMAGE_WRIST, wrist_frames),
            (OBSERVATION_IMAGE_BEV, bev_frames),
        ]:
            cam_dir = root / "videos" / chunk / cam_key
            cam_dir.mkdir(parents=True, exist_ok=True)
            np.save(cam_dir / f"episode_{ep_idx:06d}.npy", frames_arr)
            # Write dummy .mp4 file to verify validator compatibility
            (cam_dir / f"episode_{ep_idx:06d}.mp4").write_bytes(b"dummy-mp4")

    # Meta
    info = {
        "codebase_version": "v2.0",
        "fps": fps,
        "total_episodes": len(cases),
        "total_frames": total_frames,
        "features": {key: {"dtype": "video"} for key in LEROBOT_IMAGE_KEYS},
    }
    (meta / "info.json").write_text(json.dumps(info, indent=2))
    (meta / "tasks.jsonl").write_text(
        json.dumps({"task_index": 0, "task": "cube pick"}) + "\n"
    )
    (meta / "episodes.jsonl").write_text(
        "\n".join(json.dumps(e) for e in episodes_meta) + "\n"
    )
    (meta / "stats.json").write_text("{}\n")

    return cases


def test_filter_dataset_on_synthetic_data(tmp_path: Path):
    root = tmp_path / "dataset"
    cases = _write_synthetic_dataset_with_cases(root)

    result = filter_dataset(root, verbose=True)

    assert result.summary["total_episodes"] == 5
    assert result.summary["kept_episodes"] == 1
    assert result.summary["rejected_episodes"] == 4
    assert result.summary["keep_ratio"] == 0.2

    # Episode 0 (clean) must be KEPT
    assert cases["clean"] in result.kept
    assert result.episodes[cases["clean"]].status == "keep"
    assert len(result.episodes[cases["clean"]].reasons) == 0

    # Episode 1 (short) must be REJECTED for duration
    assert cases["short"] in result.rejected
    assert result.episodes[cases["short"]].status == "reject"
    assert any("episode_too_short" in r for r in result.episodes[cases["short"]].reasons)

    # Episode 2 (joint jump) must be REJECTED for joint step
    assert cases["joint_jump"] in result.rejected
    assert any("joint_jump" in r for r in result.episodes[cases["joint_jump"]].reasons)

    # Episode 3 (skew) must be REJECTED for camera skew
    assert cases["camera_skew"] in result.rejected
    assert any(
        "camera_timestamp_skew" in r
        for r in result.episodes[cases["camera_skew"]].reasons
    )

    # Episode 4 (frozen) must be REJECTED for frozen camera
    assert cases["frozen_video"] in result.rejected
    assert any(
        "frozen_video" in r for r in result.episodes[cases["frozen_video"]].reasons
    )

    # Test JSON output writing
    out_file = tmp_path / "filter_results.json"
    saved = result.save_json(out_file)
    assert saved.exists()

    data = json.loads(out_file.read_text())
    assert data["summary"]["kept_episodes"] == 1
    assert data["summary"]["rejected_episodes"] == 4
    assert data["kept"] == [cases["clean"]]
    assert data["rejected"] == [
        cases["short"],
        cases["joint_jump"],
        cases["camera_skew"],
        cases["frozen_video"],
    ]


# ---------------------------------------------------------------------------
# CLI Execution via subprocess
# ---------------------------------------------------------------------------


def test_filter_episodes_cli_default(tmp_path: Path):
    root = tmp_path / "cli_dataset"
    _write_synthetic_dataset_with_cases(root)

    out_json = tmp_path / "cli_out.json"

    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ENGINES) + (os.pathsep + prev if prev else "")

    cmd = [
        sys.executable,
        "-m",
        "data_engine.scripts.filter_episodes",
        "--dataset",
        str(root),
        "--output",
        str(out_json),
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(ENGINES),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Filter Summary:" in proc.stdout
    assert "Kept episodes:     1" in proc.stdout
    assert "Rejected episodes: 4" in proc.stdout

    assert out_json.exists()
    payload = json.loads(out_json.read_text())
    assert payload["summary"]["kept_episodes"] == 1
    assert payload["kept"] == [0]


def test_filter_episodes_cli_custom_threshold_flags(tmp_path: Path):
    root = tmp_path / "custom_thresh"
    _write_synthetic_dataset_with_cases(root)

    out_json = tmp_path / "custom_out.json"

    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ENGINES) + (os.pathsep + prev if prev else "")

    # Relax thresholds so that:
    # - min duration 0.5 s (episode 1 passes)
    # - max joint step 1.0 rad (episode 2 passes)
    # - max skew 100 ms (episode 3 passes)
    # - max frozen 1.0 s (episode 4 passes)
    cmd = [
        sys.executable,
        "-m",
        "data_engine.scripts.filter_episodes",
        "--dataset",
        str(root),
        "--output",
        str(out_json),
        "--min-duration-s",
        "0.5",
        "--max-joint-step-rad",
        "1.0",
        "--max-camera-skew-ms",
        "100",
        "--max-frozen-s",
        "1.0",
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(ENGINES),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Kept episodes:     5" in proc.stdout
    assert "Rejected episodes: 0" in proc.stdout

    payload = json.loads(out_json.read_text())
    assert payload["summary"]["kept_episodes"] == 5
    assert len(payload["rejected"]) == 0


# ---------------------------------------------------------------------------
# OHH-49 Demo Counting Criteria Test
# ---------------------------------------------------------------------------


def test_ohh_49_demo_count_only_uses_kept_episodes(tmp_path: Path):
    """OHH-49 demonstration collection count must strictly reflect kept episodes."""
    root = tmp_path / "ohh49_dataset"
    _write_synthetic_dataset_with_cases(root)

    result = filter_dataset(root)

    # Raw total is 5 episodes
    assert result.summary["total_episodes"] == 5

    # OHH-49 clean demonstration count:
    ohh_49_demonstration_count = len(result.kept)
    assert ohh_49_demonstration_count == 1
    assert ohh_49_demonstration_count != result.summary["total_episodes"]
