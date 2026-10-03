"""Episode quality filtering logic for OmniBot demonstrations.

Detects and rejects corrupted or flawed demonstrations:
  1. Identical consecutive frames for > 0.5 s (frozen video)
  2. Wrist vs bird's-eye view camera timestamp delta > 50 ms (timestamp skew)
  3. Joint step > 0.5 rad between consecutive frames (joint jump)
  4. Episode duration shorter than 2.0 s (short / abortive take)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Iterator, Sequence

import numpy as np
import pyarrow.parquet as pq

from data_engine.schema.camera_keys import (
    LEROBOT_IMAGE_KEYS,
    OBSERVATION_IMAGE_BEV,
    OBSERVATION_IMAGE_WRIST,
)
from data_engine.schema.constants import ARM_JOINT_NAMES

# ---------------------------------------------------------------------------
# Thresholds and Result Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FilterThresholds:
    """Thresholds for episode quality filtering."""

    max_frozen_s: float = 0.5
    max_camera_skew_s: float = 0.05
    max_joint_step_rad: float = 0.5
    min_duration_s: float = 2.0
    frame_diff_threshold: float = 0.0


@dataclass
class EpisodeMetrics:
    """Computed quality metrics for an episode."""

    duration_s: float = 0.0
    max_frozen_duration_s: float = 0.0
    max_camera_skew_s: float = 0.0
    max_joint_step_rad: float = 0.0
    frame_count: int = 0
    fps: float = 30.0
    frozen_camera_durations: dict[str, float] = field(default_factory=dict)


@dataclass
class EpisodeScore:
    """Evaluation result for a single demonstration episode."""

    episode_index: int
    passed: bool
    status: str  # "keep" or "reject"
    reasons: list[str]
    metrics: EpisodeMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_index": self.episode_index,
            "passed": self.passed,
            "status": self.status,
            "reasons": self.reasons,
            "metrics": {
                "duration_s": round(self.metrics.duration_s, 4),
                "max_frozen_duration_s": round(self.metrics.max_frozen_duration_s, 4),
                "max_camera_skew_s": round(self.metrics.max_camera_skew_s, 4),
                "max_joint_step_rad": round(self.metrics.max_joint_step_rad, 4),
                "frame_count": self.metrics.frame_count,
                "fps": round(self.metrics.fps, 2),
                "frozen_camera_durations": {
                    k: round(v, 4)
                    for k, v in self.metrics.frozen_camera_durations.items()
                },
            },
        }


@dataclass
class DatasetFilterResult:
    """Summary and details for an entire dataset filtering run."""

    dataset_path: str
    thresholds: FilterThresholds
    summary: dict[str, Any]
    kept: list[int]
    rejected: list[int]
    episodes: dict[int, EpisodeScore]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "thresholds": {
                "max_frozen_s": self.thresholds.max_frozen_s,
                "max_camera_skew_s": self.thresholds.max_camera_skew_s,
                "max_joint_step_rad": self.thresholds.max_joint_step_rad,
                "min_duration_s": self.thresholds.min_duration_s,
                "frame_diff_threshold": self.thresholds.frame_diff_threshold,
            },
            "kept": self.kept,
            "rejected": self.rejected,
            "episodes": {
                str(ep_idx): ep.to_dict() for ep_idx, ep in self.episodes.items()
            },
        }

    def save_json(self, output_path: str | Path) -> Path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2))
        return out


# ---------------------------------------------------------------------------
# Frame Source Abstractions
# ---------------------------------------------------------------------------


class FrameSource(ABC):
    """Abstract interface for supplying camera frames to the quality filter."""

    @abstractmethod
    def get_frames(
        self, ep_idx: int, cam_key: str
    ) -> Iterator[np.ndarray] | Sequence[np.ndarray]:
        """Return or yield frames for a given episode index and camera key."""
        pass


class InMemoryFrameSource(FrameSource):
    """Frame source backed by in-memory numpy arrays or callables.

    Useful for tests and synthetic demonstrations without writing video files.
    """

    def __init__(
        self,
        frames: (
            dict[int, dict[str, Sequence[np.ndarray]]]
            | dict[str, Sequence[np.ndarray]]
            | Callable[[int, str], Sequence[np.ndarray]]
            | None
        ) = None,
    ):
        self._frames = frames or {}

    def set_frames(
        self, cam_key: str, frames: Sequence[np.ndarray], ep_idx: int = 0
    ) -> None:
        if isinstance(self._frames, dict):
            if ep_idx not in self._frames or not isinstance(
                self._frames[ep_idx], dict
            ):
                self._frames[ep_idx] = {}
            self._frames[ep_idx][cam_key] = frames

    def get_frames(
        self, ep_idx: int, cam_key: str
    ) -> Iterator[np.ndarray] | Sequence[np.ndarray]:
        if callable(self._frames):
            return self._frames(ep_idx, cam_key)
        if isinstance(self._frames, dict):
            # Nested: {ep_idx: {cam_key: [...]}}
            if ep_idx in self._frames and isinstance(self._frames[ep_idx], dict):
                return self._frames[ep_idx].get(cam_key, [])
            # Flat: {cam_key: [...]} for single episode
            if cam_key in self._frames:
                return self._frames[cam_key]
        return []


class DiskFrameSource(FrameSource):
    """Frame source reading from dataset disk storage.

    Prioritizes .npy / .npz arrays (codec-free, ideal for tests/CPU),
    then falls back to .mp4 videos via OpenCV when available.
    """

    def __init__(self, dataset_root: str | Path, chunks_size: int = 1000):
        self.dataset_root = Path(dataset_root)
        self.chunks_size = chunks_size

    def _chunk(self, ep_idx: int) -> str:
        return f"chunk-{ep_idx // self.chunks_size:03d}"

    def get_frames(
        self, ep_idx: int, cam_key: str
    ) -> Iterator[np.ndarray] | Sequence[np.ndarray]:
        chunk = self._chunk(ep_idx)
        ep_str = f"episode_{ep_idx:06d}"
        cam_dir = self.dataset_root / "videos" / chunk / cam_key

        # 1. Check for .npy array (synthetic / codec-free)
        npy_path = cam_dir / f"{ep_str}.npy"
        if npy_path.exists():
            arr = np.load(npy_path)
            return (arr[i] for i in range(len(arr)))

        # 2. Check for .npz array
        npz_path = cam_dir / f"{ep_str}.npz"
        if npz_path.exists():
            data = np.load(npz_path)
            key = list(data.keys())[0]
            arr = data[key]
            return (arr[i] for i in range(len(arr)))

        # 3. Check for .mp4 video file
        mp4_path = cam_dir / f"{ep_str}.mp4"
        if mp4_path.exists():
            return self._iter_mp4(mp4_path)

        return []

    @staticmethod
    def _iter_mp4(path: Path) -> Iterator[np.ndarray]:
        try:
            import cv2
        except ImportError:
            raise RuntimeError(
                f"Found video file {path} but OpenCV (cv2) is not installed. "
                "Install opencv-python or provide frames via FrameSource / .npy arrays."
            )
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {path}")
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                yield frame
        finally:
            cap.release()


# ---------------------------------------------------------------------------
# Individual Quality Rule Checkers
# ---------------------------------------------------------------------------


def check_duration(
    timestamps: Sequence[float] | np.ndarray | None,
    frame_count: int,
    fps: float = 30.0,
    min_duration_s: float = 2.0,
) -> tuple[float, bool, str | None]:
    """Check if episode duration meets minimum length.

    Returns:
        (duration_s, is_rejected, reason_if_rejected)
    """
    if timestamps is not None and len(timestamps) > 1:
        ts = np.asarray(timestamps, dtype=np.float64)
        if np.median(ts) > 1e12 or np.max(ts) > 1e12:
            ts = ts * 1e-9
        duration = float(ts[-1] - ts[0])
    elif timestamps is not None and len(timestamps) == 1:
        duration = 0.0
    elif frame_count > 0 and fps > 0:
        duration = float((frame_count - 1) / fps) if frame_count > 1 else 0.0
    else:
        duration = 0.0

    if duration < min_duration_s:
        reason = (
            f"episode_too_short: episode duration {duration:.2f}s is shorter "
            f"than {min_duration_s:.2f}s ({frame_count} frames at {fps:.1f} fps)"
        )
        return duration, True, reason
    return duration, False, None


def check_joint_jump(
    states: np.ndarray,
    max_joint_step_rad: float = 0.5,
    joint_indices: Sequence[int] | None = None,
) -> tuple[float, bool, str | None]:
    """Check for discontinuous joint jumps between consecutive frames.

    Args:
        states: Array of robot states shape (N, D).
        max_joint_step_rad: Max allowed change in radians in one step.
        joint_indices: Optional indices in state vector corresponding to arm joints.
                       Defaults to the first len(ARM_JOINT_NAMES) columns (6).

    Returns:
        (max_step_rad, is_rejected, reason_if_rejected)
    """
    arr = np.asarray(states, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)

    if arr.shape[0] < 2:
        return 0.0, False, None

    if joint_indices is not None:
        joints = arr[:, joint_indices]
        names = [
            ARM_JOINT_NAMES[idx] if idx < len(ARM_JOINT_NAMES) else f"joint_{idx}"
            for idx in joint_indices
        ]
    else:
        n_joints = min(len(ARM_JOINT_NAMES), arr.shape[1])
        joints = arr[:, :n_joints]
        names = ARM_JOINT_NAMES[:n_joints]

    if joints.shape[1] == 0:
        return 0.0, False, None

    diffs = np.abs(np.diff(joints, axis=0))
    max_step = float(np.max(diffs))

    if max_step > max_joint_step_rad:
        frame_idx, joint_idx = np.unravel_index(np.argmax(diffs), diffs.shape)
        joint_name = names[joint_idx] if joint_idx < len(names) else f"joint_{joint_idx}"
        reason = (
            f"joint_jump: joint step {max_step:.3f} rad exceeds threshold "
            f"{max_joint_step_rad:.3f} rad between frames {frame_idx} and "
            f"{frame_idx + 1} ({joint_name})"
        )
        return max_step, True, reason
    return max_step, False, None


def check_camera_skew(
    wrist_timestamps: Sequence[float] | np.ndarray | None,
    bev_timestamps: Sequence[float] | np.ndarray | None,
    max_camera_skew_s: float = 0.05,
) -> tuple[float, bool, str | None]:
    """Check timestamp skew between wrist and bird's-eye view cameras.

    Args:
        wrist_timestamps: Timestamps of wrist camera frames.
        bev_timestamps: Timestamps of BEV camera frames.
        max_camera_skew_s: Max allowed delta in seconds (default: 50 ms = 0.05 s).

    Returns:
        (max_skew_s, is_rejected, reason_if_rejected)
    """
    if wrist_timestamps is None or bev_timestamps is None:
        return 0.0, False, None

    t_w = np.asarray(wrist_timestamps, dtype=np.float64)
    t_b = np.asarray(bev_timestamps, dtype=np.float64)

    if len(t_w) == 0 or len(t_b) == 0:
        return 0.0, False, None

    if np.median(t_w) > 1e12 or np.max(t_w) > 1e12:
        t_w = t_w * 1e-9
    if np.median(t_b) > 1e12 or np.max(t_b) > 1e12:
        t_b = t_b * 1e-9

    common_len = min(len(t_w), len(t_b))
    deltas = np.abs(t_w[:common_len] - t_b[:common_len])
    max_skew = float(np.max(deltas))

    if max_skew > max_camera_skew_s:
        frame_idx = int(np.argmax(deltas))
        reason = (
            f"camera_timestamp_skew: wrist vs bev timestamp delta "
            f"{max_skew * 1000.0:.1f} ms exceeds {max_camera_skew_s * 1000.0:.1f} ms "
            f"threshold at frame {frame_idx}"
        )
        return max_skew, True, reason
    return max_skew, False, None


def check_frozen_frames(
    frames: Iterable[np.ndarray],
    timestamps: Sequence[float] | np.ndarray | None = None,
    fps: float = 30.0,
    max_frozen_s: float = 0.5,
    frame_diff_threshold: float = 0.0,
    cam_key: str = "camera",
) -> tuple[float, bool, str | None]:
    """Check if camera stream has identical consecutive frames for longer than max_frozen_s.

    Args:
        frames: Iterable yielding 2D/3D numpy arrays.
        timestamps: Optional per-frame timestamps.
        fps: Frame rate if timestamps are omitted.
        max_frozen_s: Max allowable frozen duration in seconds (default: 0.5 s).
        frame_diff_threshold: Mean absolute pixel difference to consider identical (default: 0.0).
        cam_key: Camera name for reporting.

    Returns:
        (max_frozen_duration_s, is_rejected, reason_if_rejected)
    """
    prev_frame = None
    streak_start_idx = 0
    streak_start_time = 0.0
    max_frozen_duration = 0.0
    rejected = False
    reason = None

    ts_arr = None
    if timestamps is not None and len(timestamps) > 0:
        ts_arr = np.asarray(timestamps, dtype=np.float64)
        if np.median(ts_arr) > 1e12 or np.max(ts_arr) > 1e12:
            ts_arr = ts_arr * 1e-9

    for idx, frame in enumerate(frames):
        t_curr = (
            ts_arr[idx]
            if ts_arr is not None and idx < len(ts_arr)
            else (idx / fps)
        )
        if idx == 0:
            prev_frame = frame
            streak_start_idx = 0
            streak_start_time = t_curr
            continue

        if frame_diff_threshold <= 0.0:
            is_identical = np.array_equal(frame, prev_frame)
        else:
            diff = float(
                np.mean(
                    np.abs(frame.astype(np.float32) - prev_frame.astype(np.float32))
                )
            )
            is_identical = bool(diff <= frame_diff_threshold)

        if is_identical:
            duration = t_curr - streak_start_time
            if duration > max_frozen_duration:
                max_frozen_duration = duration
            if duration > max_frozen_s and not rejected:
                rejected = True
                reason = (
                    f"frozen_video: camera '{cam_key}' has identical frames for "
                    f"{duration:.2f}s (> {max_frozen_s:.2f}s) from frame {streak_start_idx} "
                    f"(t={streak_start_time:.2f}s) to frame {idx} (t={t_curr:.2f}s)"
                )
        else:
            prev_frame = frame
            streak_start_idx = idx
            streak_start_time = t_curr

    return max_frozen_duration, rejected, reason


# ---------------------------------------------------------------------------
# Episode & Dataset Scorers
# ---------------------------------------------------------------------------


def score_episode(
    episode_index: int,
    states: np.ndarray,
    timestamps: Sequence[float] | np.ndarray | None = None,
    wrist_timestamps: Sequence[float] | np.ndarray | None = None,
    bev_timestamps: Sequence[float] | np.ndarray | None = None,
    frame_source: FrameSource | None = None,
    camera_keys: Sequence[str] = LEROBOT_IMAGE_KEYS,
    thresholds: FilterThresholds | None = None,
    fps: float = 30.0,
) -> EpisodeScore:
    """Score a single demonstration episode against all 4 quality rules."""
    thresh = thresholds or FilterThresholds()
    reasons: list[str] = []

    frame_count = len(states) if states is not None else 0
    if timestamps is not None:
        frame_count = max(frame_count, len(timestamps))

    # 1. Rule 1: Episode shorter than 2 s
    duration_s, dur_rej, dur_reason = check_duration(
        timestamps=timestamps,
        frame_count=frame_count,
        fps=fps,
        min_duration_s=thresh.min_duration_s,
    )
    if dur_rej and dur_reason:
        reasons.append(dur_reason)

    # 2. Rule 2: Joint step > 0.5 rad between frames
    max_step_rad, jump_rej, jump_reason = check_joint_jump(
        states=states,
        max_joint_step_rad=thresh.max_joint_step_rad,
    )
    if jump_rej and jump_reason:
        reasons.append(jump_reason)

    # 3. Rule 3: Wrist vs BEV camera timestamp delta > 50 ms
    max_camera_skew_s, skew_rej, skew_reason = check_camera_skew(
        wrist_timestamps=wrist_timestamps,
        bev_timestamps=bev_timestamps,
        max_camera_skew_s=thresh.max_camera_skew_s,
    )
    if skew_rej and skew_reason:
        reasons.append(skew_reason)

    # 4. Rule 4: Identical frames for > 0.5 s (per camera)
    max_frozen_duration_s = 0.0
    frozen_camera_durations: dict[str, float] = {}

    if frame_source is not None:
        for cam in camera_keys:
            # Determine appropriate timestamps for this camera
            cam_ts = timestamps
            if cam == OBSERVATION_IMAGE_WRIST and wrist_timestamps is not None:
                cam_ts = wrist_timestamps
            elif cam == OBSERVATION_IMAGE_BEV and bev_timestamps is not None:
                cam_ts = bev_timestamps

            cam_frames = frame_source.get_frames(episode_index, cam)
            cam_frozen_s, cam_rej, cam_reason = check_frozen_frames(
                frames=cam_frames,
                timestamps=cam_ts,
                fps=fps,
                max_frozen_s=thresh.max_frozen_s,
                frame_diff_threshold=thresh.frame_diff_threshold,
                cam_key=cam,
            )
            frozen_camera_durations[cam] = cam_frozen_s
            max_frozen_duration_s = max(max_frozen_duration_s, cam_frozen_s)
            if cam_rej and cam_reason:
                reasons.append(cam_reason)

    passed = len(reasons) == 0
    status = "keep" if passed else "reject"

    metrics = EpisodeMetrics(
        duration_s=duration_s,
        max_frozen_duration_s=max_frozen_duration_s,
        max_camera_skew_s=max_camera_skew_s,
        max_joint_step_rad=max_step_rad,
        frame_count=frame_count,
        fps=fps,
        frozen_camera_durations=frozen_camera_durations,
    )

    return EpisodeScore(
        episode_index=episode_index,
        passed=passed,
        status=status,
        reasons=reasons,
        metrics=metrics,
    )


def filter_dataset(
    dataset_root: str | Path,
    thresholds: FilterThresholds | None = None,
    frame_source: FrameSource | None = None,
    verbose: bool = False,
) -> DatasetFilterResult:
    """Filter an entire LeRobot dataset on disk and generate a keep/reject report."""
    root = Path(dataset_root)
    thresh = thresholds or FilterThresholds()

    # Read info.json if present
    info_path = root / "meta" / "info.json"
    fps = 30.0
    chunks_size = 1000
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
            fps = float(info.get("fps", 30.0))
            chunks_size = int(info.get("chunks_size", 1000))
        except Exception:
            pass

    # Find declared episodes
    episodes_path = root / "meta" / "episodes.jsonl"
    ep_indices: list[int] = []
    if episodes_path.exists():
        for line in episodes_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ep_indices.append(rec["episode_index"])
            except Exception:
                pass

    # Fallback to parquet scanning if episodes.jsonl is not present or empty
    if not ep_indices:
        data_dir = root / "data"
        if data_dir.exists():
            for pq_file in sorted(data_dir.glob("chunk-*/episode_*.parquet")):
                match = re.search(r"episode_(\d+)\.parquet", pq_file.name)
                if match:
                    ep_indices.append(int(match.group(1)))

    ep_indices = sorted(set(ep_indices))

    # Initialize disk frame source if none provided
    source = frame_source or DiskFrameSource(root, chunks_size=chunks_size)

    kept: list[int] = []
    rejected: list[int] = []
    episode_scores: dict[int, EpisodeScore] = {}

    for ep_idx in ep_indices:
        chunk = f"chunk-{ep_idx // chunks_size:03d}"
        ep_str = f"episode_{ep_idx:06d}"
        pq_path = root / "data" / chunk / f"{ep_str}.parquet"

        if not pq_path.exists():
            metrics = EpisodeMetrics(frame_count=0, fps=fps)
            score = EpisodeScore(
                episode_index=ep_idx,
                passed=False,
                status="reject",
                reasons=[f"missing_parquet: {pq_path} does not exist"],
                metrics=metrics,
            )
            episode_scores[ep_idx] = score
            rejected.append(ep_idx)
            continue

        table = pq.read_table(pq_path)
        col_names = set(table.schema.names)

        # Observation state
        state_col = "observation.state" if "observation.state" in col_names else "state"
        if state_col in col_names:
            states = np.array(table[state_col].to_pylist(), dtype=np.float32)
        else:
            states = np.zeros((len(table), len(ARM_JOINT_NAMES)), dtype=np.float32)

        # Timestamps
        if "timestamp" in col_names:
            timestamps = np.array(table["timestamp"].to_pylist(), dtype=np.float64)
        else:
            timestamps = np.arange(len(table), dtype=np.float64) / fps

        # Per-camera timestamps
        wrist_cols = [
            "observation.images.wrist.timestamp",
            "observation.images.wrist_timestamp",
            "wrist_timestamp",
            "camera_wrist_timestamp",
            "timestamp_wrist",
            "wrist_ts",
        ]
        bev_cols = [
            "observation.images.bev.timestamp",
            "observation.images.bev_timestamp",
            "bev_timestamp",
            "camera_bev_timestamp",
            "timestamp_bev",
            "bev_ts",
        ]

        wrist_ts = None
        bev_ts = None

        for col in wrist_cols:
            if col in col_names:
                wrist_ts = np.array(table[col].to_pylist(), dtype=np.float64)
                break

        for col in bev_cols:
            if col in col_names:
                bev_ts = np.array(table[col].to_pylist(), dtype=np.float64)
                break

        # Check for sidecar timestamp array files
        if wrist_ts is None:
            w_ts_path = (
                root
                / "videos"
                / chunk
                / OBSERVATION_IMAGE_WRIST
                / f"{ep_str}_timestamps.npy"
            )
            if w_ts_path.exists():
                wrist_ts = np.load(w_ts_path)

        if bev_ts is None:
            b_ts_path = (
                root
                / "videos"
                / chunk
                / OBSERVATION_IMAGE_BEV
                / f"{ep_str}_timestamps.npy"
            )
            if b_ts_path.exists():
                bev_ts = np.load(b_ts_path)

        score = score_episode(
            episode_index=ep_idx,
            states=states,
            timestamps=timestamps,
            wrist_timestamps=wrist_ts,
            bev_timestamps=bev_ts,
            frame_source=source,
            camera_keys=LEROBOT_IMAGE_KEYS,
            thresholds=thresh,
            fps=fps,
        )

        episode_scores[ep_idx] = score
        if score.passed:
            kept.append(ep_idx)
        else:
            rejected.append(ep_idx)

    total = len(ep_indices)
    summary = {
        "total_episodes": total,
        "kept_episodes": len(kept),
        "rejected_episodes": len(rejected),
        "keep_ratio": round(len(kept) / total, 4) if total > 0 else 0.0,
    }

    return DatasetFilterResult(
        dataset_path=str(root),
        thresholds=thresh,
        summary=summary,
        kept=kept,
        rejected=rejected,
        episodes=episode_scores,
    )


class EpisodeQualityFilter:
    """Configurable quality filter instance."""

    def __init__(
        self,
        thresholds: FilterThresholds | None = None,
        frame_source: FrameSource | None = None,
    ):
        self.thresholds = thresholds or FilterThresholds()
        self.frame_source = frame_source

    def filter_dataset(
        self, dataset_root: str | Path, verbose: bool = False
    ) -> DatasetFilterResult:
        return filter_dataset(
            dataset_root=dataset_root,
            thresholds=self.thresholds,
            frame_source=self.frame_source,
            verbose=verbose,
        )

    def score_episode(
        self,
        episode_index: int,
        states: np.ndarray,
        timestamps: Sequence[float] | np.ndarray | None = None,
        wrist_timestamps: Sequence[float] | np.ndarray | None = None,
        bev_timestamps: Sequence[float] | np.ndarray | None = None,
        fps: float = 30.0,
    ) -> EpisodeScore:
        return score_episode(
            episode_index=episode_index,
            states=states,
            timestamps=timestamps,
            wrist_timestamps=wrist_timestamps,
            bev_timestamps=bev_timestamps,
            frame_source=self.frame_source,
            thresholds=self.thresholds,
            fps=fps,
        )
