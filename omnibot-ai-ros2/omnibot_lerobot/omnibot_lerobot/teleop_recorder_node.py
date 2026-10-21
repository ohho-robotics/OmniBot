#!/usr/bin/env python3
"""
Teleoperation + dataset recording node for OmniBot mobile manipulation.

Records synchronized arm + base demonstrations for SmolVLA fine-tuning.

Leader arm (SO-101) provides arm action commands.
Xbox controller drives the base and triggers recording.

State machine:
  IDLE      → waiting for RB button press
  RECORDING → accumulating frames
  SAVING    → writing episode to disk

Topics subscribed:
  /arm/leader_states           (sensor_msgs/JointState) - leader arm (arm actions)
  /arm/joint_states            (sensor_msgs/JointState) - follower arm (arm observations)
  /joy                         (sensor_msgs/Joy)         - Xbox controller
  /camera/wrist/image_raw      (sensor_msgs/Image)  → observation.images.wrist
  /camera/base/bev/image_raw   (sensor_msgs/Image)  → observation.images.bev (BEV mosaic from 4 base cameras)
  /odom                        (nav_msgs/Odometry)       - base velocity

Unified 9D action:  [arm(6), base_vx, base_vy, base_vz]
Unified 9D state:   [arm(6), base_vx, base_vy, base_vz]

Services (std_srvs/Trigger), plus /ohho/record/task and /ohho/record/episode_index:
  /ohho/record/start     begin one episode (refused if already recording)
  /ohho/record/stop      save the in-progress episode
  /ohho/record/discard   drop the in-progress episode; nothing is written

Topic:
  /ohho/record/state     std_msgs/String JSON, transient-local, 2 Hz and on each phase change
"""

import json
import os
import time
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState, Joy, Image
from nav_msgs.msg import Odometry
from std_msgs.msg import Int32, String
from std_srvs.srv import Trigger
from enum import Enum, auto

try:
    from cv_bridge import CvBridge

    CV_BRIDGE_AVAILABLE = True
except ImportError:
    CV_BRIDGE_AVAILABLE = False

try:
    import cv2  # noqa: F401

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# ---------------------------------------------------------------------------
# Optional LeRobot import
# ---------------------------------------------------------------------------
try:
    from lerobot.common.datasets.lerobot_dataset import LeRobotDataset

    LEROBOT_AVAILABLE = True
except ImportError:
    LEROBOT_AVAILABLE = False

try:
    from omnibot_lerobot.ohho_teleop_recorder import (
        OHHO_AVAILABLE,
        WRITER_AVAILABLE,
        OhhoTeleopRecorder,
    )
except ImportError:
    OHHO_AVAILABLE = False
    WRITER_AVAILABLE = False
    OhhoTeleopRecorder = None  # type: ignore[misc, assignment]

OHHO_RECORDING = OHHO_AVAILABLE and WRITER_AVAILABLE

try:
    from omnibot_lerobot.record_session import RecordPhase, RecordSession, commit_stop
except ImportError:
    from record_session import RecordPhase, RecordSession, commit_stop

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
JOINT_NAMES = [
    "arm_shoulder_pan",
    "arm_shoulder_lift",
    "arm_elbow_flex",
    "arm_wrist_flex",
    "arm_wrist_roll",
    "arm_gripper",
]
MAX_LINEAR = 0.2  # m/s safe recording speed
MAX_ANGULAR = 1.0  # rad/s
STATE_TOPIC = "/ohho/record/state"
STATE_HZ = 2.0


class RecordState(Enum):
    IDLE = auto()
    RECORDING = auto()
    SAVING = auto()


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------
class TeleopRecorderNode(Node):
    """Records teleoperation episodes in LeRobot HF dataset format."""

    def __init__(self):
        super().__init__("teleop_recorder_node")

        # ------------------------------------------------------------------
        # Parameters
        # ------------------------------------------------------------------
        self.declare_parameter("output_dir", "~/datasets/mobile_manipulation")
        self.declare_parameter("repo_id", "local/mobile_manipulation")
        self.declare_parameter("record_hz", 30.0)
        self.declare_parameter("episode_timeout_s", 60.0)
        self.declare_parameter("joy_record_button", 7)  # Xbox RB
        self.declare_parameter("joy_discard_button", 6)  # Xbox LB
        self.declare_parameter("task_name", "mobile manipulation task")
        # -1 means "use the recorder's next index". >= 0 pins that index on every start.
        self.declare_parameter("episode_index", -1)

        self.output_dir = os.path.expanduser(self.get_parameter("output_dir").value)
        self.repo_id = self.get_parameter("repo_id").value
        self.record_hz = self.get_parameter("record_hz").value
        self.episode_timeout_s = self.get_parameter("episode_timeout_s").value
        self.joy_record_button = self.get_parameter("joy_record_button").value
        self.joy_discard_button = self.get_parameter("joy_discard_button").value

        os.makedirs(self.output_dir, exist_ok=True)

        # ------------------------------------------------------------------
        # Runtime state
        # ------------------------------------------------------------------
        task_name = self.get_parameter("task_name").value
        self.session = RecordSession(
            task=task_name if isinstance(task_name, str) else "mobile manipulation task"
        )
        self._topic_task: str | None = None
        # One-shot index from /ohho/record/episode_index. Cleared after a successful start.
        self._pending_episode_index: int | None = None
        self._mirror_session()

        # Sensor cache
        self.leader_positions = np.zeros(len(JOINT_NAMES), dtype=np.float32)
        self.follower_positions = np.zeros(len(JOINT_NAMES), dtype=np.float32)
        self.base_vel = np.zeros(3, dtype=np.float32)
        self.joy_axes = [0.0] * 8
        self.joy_buttons = [0] * 16
        self.prev_joy_buttons = [0] * 16
        self.wrist_image = None  # numpy HxWx3 uint8 RGB
        self.bev_image = None  # numpy HxWx3 uint8 RGB — BEV mosaic from 4 base cameras
        self.wrist_msg_time = None
        self.bev_msg_time = None

        self._ohho_rec = (
            OhhoTeleopRecorder(self.repo_id, self.record_hz)
            if OHHO_RECORDING and OhhoTeleopRecorder is not None
            else None
        )

        # ------------------------------------------------------------------
        # cv_bridge
        # ------------------------------------------------------------------
        if CV_BRIDGE_AVAILABLE:
            self.bridge = CvBridge()
        else:
            self.bridge = None
            self.get_logger().warn("cv_bridge not available — images will be zeros.")

        # ------------------------------------------------------------------
        # Subscribers
        # ------------------------------------------------------------------
        self.create_subscription(
            JointState, "/arm/leader_states", self.leader_state_cb, 10
        )
        self.create_subscription(
            JointState, "/arm/joint_states", self.follower_state_cb, 10
        )
        self.create_subscription(Joy, "/joy", self.joy_cb, 10)
        self.create_subscription(
            Image, "/camera/wrist/image_raw", self.wrist_image_cb, 10
        )
        self.create_subscription(
            Image, "/camera/base/bev/image_raw", self.bev_image_cb, 10
        )
        self.create_subscription(Odometry, "/odom", self.odom_cb, 10)

        # ------------------------------------------------------------------
        # Record timer
        # ------------------------------------------------------------------
        timer_period = 1.0 / self.record_hz
        self.create_timer(timer_period, self.record_timer_cb)

        if self._ohho_rec is not None:
            writer = "ohho-os+data_engine"
        elif LEROBOT_AVAILABLE:
            writer = "lerobot"
        else:
            writer = "numpy fallback"
        self.get_logger().info(
            f"TeleopRecorderNode started | hz={self.record_hz} | "
            f"output={self.output_dir} | writer={writer}"
        )
        self.get_logger().info(
            f"Press button {self.joy_record_button} (RB) to start/stop recording. "
            f"Button {self.joy_discard_button} (LB) discards the current episode."
        )

        state_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._state_pub = self.create_publisher(String, STATE_TOPIC, state_qos)
        self.create_subscription(String, "/ohho/record/task", self._task_cb, 10)
        self.create_subscription(
            Int32, "/ohho/record/episode_index", self._episode_index_cb, 10
        )
        self.create_service(Trigger, "/ohho/record/start", self._on_start_service)
        self.create_service(Trigger, "/ohho/record/stop", self._on_stop_service)
        self.create_service(Trigger, "/ohho/record/discard", self._on_discard_service)
        self.create_timer(1.0 / STATE_HZ, self._publish_state)
        self._publish_state()
        self.get_logger().info(
            "Recording services: /ohho/record/start /ohho/record/stop "
            "/ohho/record/discard ; state on /ohho/record/state"
        )

    # ------------------------------------------------------------------
    # Image helpers
    # ------------------------------------------------------------------

    def _ros_image_to_numpy_rgb(self, msg: Image):
        """Convert ROS Image to numpy HxWx3 uint8 RGB."""
        if self.bridge is not None:
            try:
                return np.array(
                    self.bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8"),
                    dtype=np.uint8,
                )
            except Exception as exc:
                self.get_logger().warn(
                    f"Image conversion error: {exc}", throttle_duration_sec=5.0
                )
        return np.zeros((240, 320, 3), dtype=np.uint8)

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------

    def leader_state_cb(self, msg: JointState):
        name_to_pos = dict(zip(msg.name, msg.position))
        self.leader_positions = np.array(
            [name_to_pos.get(n, 0.0) for n in JOINT_NAMES], dtype=np.float32
        )

    def follower_state_cb(self, msg: JointState):
        name_to_pos = dict(zip(msg.name, msg.position))
        self.follower_positions = np.array(
            [name_to_pos.get(n, 0.0) for n in JOINT_NAMES], dtype=np.float32
        )

    def odom_cb(self, msg: Odometry):
        self.base_vel = np.array(
            [
                msg.twist.twist.linear.x,
                msg.twist.twist.linear.y,
                msg.twist.twist.angular.z,
            ],
            dtype=np.float32,
        )

    def joy_cb(self, msg: Joy):
        self.prev_joy_buttons = list(self.joy_buttons)
        self.joy_axes = list(msg.axes)
        self.joy_buttons = list(msg.buttons)
        self._handle_button_events()

    def _image_stamp_s(self, msg: Image) -> float:
        if msg.header.stamp.sec or msg.header.stamp.nanosec:
            return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        return time.time()

    def wrist_image_cb(self, msg: Image):
        self.wrist_image = self._ros_image_to_numpy_rgb(msg)
        self.wrist_msg_time = self._image_stamp_s(msg)

    def bev_image_cb(self, msg: Image):
        self.bev_image = self._ros_image_to_numpy_rgb(msg)
        self.bev_msg_time = self._image_stamp_s(msg)

    # ------------------------------------------------------------------
    # Button handling
    # ------------------------------------------------------------------

    def _button_just_pressed(self, idx: int) -> bool:
        """True if button transitioned 0→1 this tick."""
        if idx >= len(self.joy_buttons) or idx >= len(self.prev_joy_buttons):
            return False
        return self.joy_buttons[idx] == 1 and self.prev_joy_buttons[idx] == 0

    def _handle_button_events(self):
        if self._button_just_pressed(self.joy_record_button):
            self._on_record_button()

        if self._button_just_pressed(self.joy_discard_button):
            self._on_discard_button()

    def _on_record_button(self):
        if self.session.state is RecordPhase.IDLE:
            result = self._begin_recording()
            if result.success:
                self.get_logger().info(
                    f"Recording episode {result.episode_index} ... "
                    f"Press RB again to save, LB to discard."
                )
            else:
                self.get_logger().warn(result.message)
        elif self.session.state is RecordPhase.RECORDING:
            self.get_logger().info(
                f"Stopping recording. Saving {self.session.frame_count} frames..."
            )
            self._stop_and_save()

    def _on_discard_button(self):
        if self.session.state is not RecordPhase.RECORDING:
            return
        frames_recorded = self.session.frame_count
        index = self.session.episode_index
        result = self.session.discard()
        if result.success:
            self._discard_ohho_episode()
        self._mirror_session()
        self._publish_state()
        self.get_logger().warn(
            f"Discarding episode {index} ({frames_recorded} frames recorded)."
        )
        if not result.success:
            self.get_logger().warn(result.message)

    # ------------------------------------------------------------------
    # Record timer
    # ------------------------------------------------------------------

    def record_timer_cb(self):
        # Check timeout
        if self.session.state is RecordPhase.RECORDING:
            elapsed = time.time() - self.session.started_at
            if elapsed > self.episode_timeout_s:
                self.get_logger().warn(
                    f"Episode timeout ({self.episode_timeout_s}s). Auto-saving..."
                )
                self._stop_and_save()
                return

            self._record_frame()

    def _record_frame(self):
        """Capture and append one frame to the episode buffer."""
        # Base action from joy axes (standard Xbox mapping)
        base_vx = (
            float(self.joy_axes[1]) * MAX_LINEAR if len(self.joy_axes) > 1 else 0.0
        )
        base_vy = (
            float(self.joy_axes[0]) * MAX_LINEAR if len(self.joy_axes) > 0 else 0.0
        )
        base_vz = (
            float(self.joy_axes[3]) * MAX_ANGULAR if len(self.joy_axes) > 3 else 0.0
        )

        # 9D action: [arm(6), base_vx, base_vy, base_vz]
        arm_action = self.leader_positions.copy()
        base_action = np.array([base_vx, base_vy, base_vz], dtype=np.float32)
        full_action = np.concatenate([arm_action, base_action])

        # 9D state: [follower_arm(6), base_vx, base_vy, base_vz]
        full_state = np.concatenate(
            [self.follower_positions.copy(), self.base_vel.copy()]
        )

        # Images (copy to avoid mutation)
        wrist_img = (
            self.wrist_image.copy()
            if self.wrist_image is not None
            else np.zeros((240, 320, 3), dtype=np.uint8)
        )
        bev_img = (
            self.bev_image.copy()
            if self.bev_image is not None
            else np.zeros((240, 320, 3), dtype=np.uint8)
        )

        wall_t = time.time()
        frame = {
            "state": full_state.astype(np.float32),
            "action": full_action.astype(np.float32),
            "wrist_image": wrist_img,
            "bev_image": bev_img,  # BEV mosaic from 4 base cameras
            "timestamp": wall_t,
        }
        if self.session.append_frame(frame) and self._ohho_rec is not None:
            self._ohho_rec.capture_frame(
                full_state,
                full_action,
                wrist_img,
                bev_img,
                wall_timestamp=wall_t,
                wrist_timestamp=self.wrist_msg_time,
                bev_timestamp=self.bev_msg_time,
            )
            self.session.note_frame_count(self._ohho_rec.frame_count)
        self.frame_count = self.session.frame_count
        self.episode_buffer = self.session.live_frames

    # ------------------------------------------------------------------
    # Services and state topic
    # ------------------------------------------------------------------

    def _mirror_session(self) -> None:
        """Copy session fields onto the attributes the episode writer reads."""
        self.record_state = {
            RecordPhase.IDLE: RecordState.IDLE,
            RecordPhase.RECORDING: RecordState.RECORDING,
            RecordPhase.SAVING: RecordState.SAVING,
        }[self.session.state]
        self.episode_index = self.session.episode_index
        self.frame_count = self.session.frame_count
        self.task_description = self.session.task
        self.recording_start_time = self.session.started_at or None
        self.episode_buffer = self.session.live_frames

    def _task_for_start(self) -> str | None:
        if self._topic_task is not None and self._topic_task.strip():
            return self._topic_task.strip()
        value = self.get_parameter("task_name").value
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _episode_index_for_start(self) -> int | None:
        if self._pending_episode_index is not None:
            if self._pending_episode_index < 0:
                return None
            return self._pending_episode_index
        value = self.get_parameter("episode_index").value
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        if isinstance(value, bool) or index < 0:
            return None
        return index

    def _begin_recording(self):
        result = self.session.start(
            task=self._task_for_start(),
            episode_index=self._episode_index_for_start(),
        )
        if result.success:
            self._pending_episode_index = None
        self._mirror_session()
        if result.success:
            self._start_ohho_episode()
        self._publish_state()
        return result

    def _start_ohho_episode(self) -> None:
        if self._ohho_rec is None:
            return
        # discard_episode is a no-op when nothing is open. It clears a leftover
        # episode so start_episode cannot raise after an empty stop.
        self._ohho_rec.discard_episode()
        self._ohho_rec.start_episode(self.task_description)

    def _discard_ohho_episode(self) -> None:
        if self._ohho_rec is None:
            return
        self._ohho_rec.discard_episode()

    def _stop_and_save(self):
        def write(frames):
            self.episode_buffer = frames
            self.frame_count = len(frames)
            self.episode_index = self.session.episode_index
            self.task_description = self.session.task
            self.record_state = RecordState.SAVING
            self.recording_start_time = self.session.started_at or None
            self._publish_state()
            self._save_episode()

        result = commit_stop(self.session, write)
        if not result.success and "no frames to save" in result.message:
            self._discard_ohho_episode()
        self._mirror_session()
        self._publish_state()
        if not result.success:
            self.get_logger().warn(result.message)
        return result

    def _publish_state(self) -> None:
        msg = String()
        msg.data = json.dumps(self.session.snapshot(), separators=(",", ":"))
        self._state_pub.publish(msg)

    def _task_cb(self, msg: String) -> None:
        self._topic_task = msg.data

    def _episode_index_cb(self, msg: Int32) -> None:
        self._pending_episode_index = int(msg.data)

    def _fill_trigger(self, response, result):
        response.success = result.success
        response.message = result.message
        return response

    def _on_start_service(self, _request, response):
        result = self._begin_recording()
        if result.success:
            self.get_logger().info(result.message)
        else:
            self.get_logger().warn(result.message)
        return self._fill_trigger(response, result)

    def _on_stop_service(self, _request, response):
        result = self._stop_and_save()
        return self._fill_trigger(response, result)

    def _on_discard_service(self, _request, response):
        result = self.session.discard()
        if result.success:
            self._discard_ohho_episode()
        self._mirror_session()
        self._publish_state()
        self.get_logger().warn(result.message)
        return self._fill_trigger(response, result)

    # ------------------------------------------------------------------
    # Episode saving
    # ------------------------------------------------------------------

    def _save_episode(self):
        """Write the current episode buffer. Does not change recording state.

        The episode index advances in ``RecordSession.complete_save`` only
        after this returns. Discard never calls this method.
        """
        if not self.episode_buffer:
            raise RuntimeError("no frames to save")

        if self._ohho_rec is not None:
            self._ohho_rec.save_episode(
                self.output_dir,
                self.task_description,
                self.record_hz,
                self.repo_id,
            )
        elif LEROBOT_AVAILABLE:
            self._save_lerobot_format()
        else:
            self._save_numpy_format()

        self.get_logger().info(
            f"Episode {self.episode_index} saved "
            f"({self.frame_count} frames @ {self.record_hz:.0f} Hz, "
            f"{self.frame_count / self.record_hz:.1f}s)."
        )

    def _save_lerobot_format(self):
        """Save episode using LeRobot HuggingFace dataset format."""
        features = {
            "observation.state": {
                "dtype": "float32",
                "shape": (9,),
                "names": {"joints": JOINT_NAMES + ["base_vx", "base_vy", "base_vz"]},
            },
            "action": {
                "dtype": "float32",
                "shape": (9,),
                "names": {"joints": JOINT_NAMES + ["base_vx", "base_vy", "base_vz"]},
            },
            "observation.images.wrist": {
                "dtype": "video",
                "shape": (3, 240, 320),
                "names": ["channels", "height", "width"],
            },
            "observation.images.bev": {
                "dtype": "video",
                "shape": (3, 240, 320),
                "names": ["channels", "height", "width"],
            },
        }

        dataset = LeRobotDataset.create(
            repo_id=self.repo_id,
            fps=int(self.record_hz),
            root=self.output_dir,
            features=features,
            image_writer_threads=4,
        )

        for frame in self.episode_buffer:
            dataset.add_frame(
                {
                    "observation.state": frame["state"],
                    "action": frame["action"],
                    "observation.images.wrist": frame["wrist_image"],
                    "observation.images.bev": frame["bev_image"],
                }
            )

        dataset.save_episode(task=self.task_description)

    def _save_numpy_format(self):
        """Fallback: save episode as .npz file."""
        states = np.stack([f["state"] for f in self.episode_buffer])
        actions = np.stack([f["action"] for f in self.episode_buffer])
        wrist_imgs = np.stack([f["wrist_image"] for f in self.episode_buffer])
        bev_imgs = np.stack([f["bev_image"] for f in self.episode_buffer])
        timestamps = np.array([f["timestamp"] for f in self.episode_buffer])

        ep_dir = os.path.join(self.output_dir, f"episode_{self.episode_index:05d}")
        os.makedirs(ep_dir, exist_ok=True)

        np.savez_compressed(
            os.path.join(ep_dir, "data.npz"),
            states=states,
            actions=actions,
            wrist_images=wrist_imgs,
            bev_images=bev_imgs,
            timestamps=timestamps,
            joint_names=np.array(JOINT_NAMES),
            task=np.array([self.task_description]),
            fps=np.array([self.record_hz]),
        )
        self.get_logger().info(
            f"Saved numpy episode to {ep_dir}/data.npz "
            "(pip install ohho-os and set PYTHONPATH to omnibot-ai-engines for LeRobot v2, "
            "or install lerobot for the HF writer)"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(args=None):
    rclpy.init(args=args)
    node = TeleopRecorderNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
