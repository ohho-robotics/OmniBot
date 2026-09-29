"""Tick and radian conversions for the SO-101 arm.

No ROS imports. The driver node calls these helpers, and the unit tests
import this module directly so they can run without rclpy.
"""


def ticks_to_radians(ticks_list, home_ticks, ticks_per_rad):
    """Convert raw servo ticks to joint angles in radians."""
    return [
        (ticks - home) / ticks_per_rad
        for ticks, home in zip(ticks_list, home_ticks)
    ]


def radians_to_ticks(radians_list, home_ticks, ticks_per_rad):
    """Convert joint angles in radians to servo ticks."""
    return [
        int(round(rad * ticks_per_rad + home))
        for rad, home in zip(radians_list, home_ticks)
    ]


def clamp_radians(radians_list, joint_min, joint_max):
    """Clamp joint angles to declared limits."""
    return [
        max(mn, min(mx, rad))
        for rad, mn, mx in zip(radians_list, joint_min, joint_max)
    ]
