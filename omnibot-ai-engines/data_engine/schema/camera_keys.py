"""Canonical LeRobot camera keys for this robot.

Wrist close-up plus the stitched bird's-eye view. Dataset writers, the
validator, the visualizer, recorders, and the policy must use these two
keys. The physical front camera is an input to the BEV stitcher, not a
dataset feature — do not add ``observation.images.front``.
"""

OBSERVATION_IMAGE_WRIST = "observation.images.wrist"
OBSERVATION_IMAGE_BEV = "observation.images.bev"

# Stable order: wrist, then bird's-eye view.
LEROBOT_IMAGE_KEYS = (
    OBSERVATION_IMAGE_WRIST,
    OBSERVATION_IMAGE_BEV,
)
