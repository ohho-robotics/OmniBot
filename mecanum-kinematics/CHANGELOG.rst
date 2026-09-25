^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package mecanum_drive_ros2
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1.0.0 (2026-03-15)
-------------------
* Initial release: generic mecanum wheel kinematics library for ROS 2
* Extracted from the OmniBot omnibot_driver package; no hardware dependency
* ``include/mecanum_drive_ros2/mecanum_kinematics.hpp``: header-only C++17 library

  * ``inverseKinematics(vx, vy, omega, geom)`` → (FL, FR, BL, BR) rad/s
  * ``forwardKinematics(wheels, geom)`` → (vx, vy, omega) body twist
  * ``integratePose(x, y, theta, vx, vy, omega, dt)`` → updated 2-D pose
  * Zero runtime dependencies — drop into any C++ ROS 2 package via ``find_package``

* ``mecanum_drive_ros2/kinematics.py``: pure-Python mirror of the C++ library

  * ``RobotGeometry`` dataclass (wheel_radius, separation_width, separation_length)
  * ``inverse_kinematics()``, ``forward_kinematics()``, ``integrate_pose()``
  * No ROS dependency — use in scripts, unit tests, and Jupyter notebooks

* Sign conventions follow ROS REP 103 (+x forward, +y left, +z CCW)
* Wheel layout: FL, FR, BL, BR with standard 45° roller X-configuration
* Param YAML: ``config/mecanum_params.yaml``
* Contributors: Varun Vaidhiya
