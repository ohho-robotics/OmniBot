^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package yahboom_ros2
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1.0.0 (2026-03-15)
-------------------
* Initial release: ROS 2 Jazzy driver for the Yahboom ROS Robot Expansion Board
  (Rosmaster series — X3, R2, and compatible variants)
* Extracted from the OmniBot monorepo; standalone, hardware-agnostic packaging
* ``protocol.py``: pure-Python encoder/decoder for the reverse-engineered
  Rosmaster serial protocol (0xFF 0xFC framing, FUNC_MOTION 0x12,
  checksum = (sum+5)&0xFF) — no ROS dependency, usable standalone
* ``driver_node.py``: full ROS 2 node

  * Subscribes ``/cmd_vel`` (geometry_msgs/Twist) and ``/joy`` (sensor_msgs/Joy)
  * Publishes ``/odom`` (nav_msgs/Odometry) and ``/imu/data`` (sensor_msgs/Imu)
  * Broadcasts ``odom → base_link`` TF transform
  * Velocity ramping (configurable ``ramp_step`` parameter)
  * IMU data from on-board MPU9250 (accel, gyro, Euler attitude)
  * Automatic serial reconnect on cable unplug
  * ``debug_serial`` parameter to log unknown RX packet types

* All hardware-specific values removed from source (serial port, baud rate,
  wheel geometry, velocity limits now ROS 2 parameters)
* Launch file: ``yahboom_driver.launch.py``
* Param YAML: ``config/yahboom_params.yaml``
* Contributors: Varun Vaidhiya
