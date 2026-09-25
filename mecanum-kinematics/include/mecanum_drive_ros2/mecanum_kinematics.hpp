#pragma once
/**
 * mecanum_drive_ros2 — Generic Mecanum Wheel Kinematics
 *
 * Header-only C++17 library providing forward and inverse kinematics for
 * a 4-wheeled mecanum robot.  No ROS dependency in this header.
 *
 * Wheel layout (standard X-configuration, 45° rollers):
 *
 *        front
 *    FL ──── FR
 *    │        │
 *    BL ──── BR
 *        rear
 *
 * Sign conventions (ROS REP 103):
 *   vx  — forward (+x)
 *   vy  — left    (+y)
 *   omega — CCW  (+z)
 */

#include <array>
#include <cmath>

namespace mecanum_drive {

/**
 * Robot geometry parameters.
 */
struct RobotGeometry {
  double wheel_radius;          ///< metres
  double wheel_separation_width;   ///< metres, distance between left & right wheels (full track)
  double wheel_separation_length;  ///< metres, distance between front & rear wheels (full wheelbase)
};

/**
 * Four wheel angular velocities (rad/s).
 * Order: [front_left, front_right, rear_left, rear_right]
 */
using WheelVelocities = std::array<double, 4>;

/**
 * Inverse kinematics: body twist → wheel angular velocities.
 *
 * @param vx     Forward body velocity (m/s)
 * @param vy     Lateral body velocity (m/s)
 * @param omega  Angular body velocity (rad/s)
 * @param geom   Robot geometry
 * @return WheelVelocities [FL, FR, BL, BR] in rad/s
 */
inline WheelVelocities inverseKinematics(
    double vx, double vy, double omega,
    const RobotGeometry & geom)
{
  const double L = geom.wheel_separation_length / 2.0;
  const double W = geom.wheel_separation_width  / 2.0;
  const double k = L + W;  // combined half-geometry for rotation
  const double r = geom.wheel_radius;

  return {
    (vx - vy - k * omega) / r,  // FL
    (vx + vy + k * omega) / r,  // FR
    (vx + vy - k * omega) / r,  // BL
    (vx - vy + k * omega) / r,  // BR
  };
}

/**
 * Forward kinematics: wheel angular velocities → body twist.
 *
 * @param w    WheelVelocities [FL, FR, BL, BR] in rad/s
 * @param geom Robot geometry
 * @return {vx, vy, omega} body twist (m/s, m/s, rad/s)
 */
struct BodyTwist { double vx, vy, omega; };

inline BodyTwist forwardKinematics(
    const WheelVelocities & w,
    const RobotGeometry & geom)
{
  const double L = geom.wheel_separation_length / 2.0;
  const double W = geom.wheel_separation_width  / 2.0;
  const double k = L + W;
  const double r = geom.wheel_radius;

  const double fl = w[0], fr = w[1], bl = w[2], br = w[3];

  return {
    /* vx    */ r * (fl + fr + bl + br) / 4.0,
    /* vy    */ r * (-fl + fr + bl - br) / 4.0,
    /* omega */ r * (-fl + fr - bl + br) / (4.0 * k),
  };
}

/**
 * Integrate body twist into 2-D pose over time dt.
 *
 * @param x       Current X position (m)      [in/out]
 * @param y       Current Y position (m)      [in/out]
 * @param theta   Current heading (rad)       [in/out]
 * @param vx      Forward velocity (m/s)
 * @param vy      Lateral velocity (m/s)
 * @param omega   Angular velocity (rad/s)
 * @param dt      Time step (s)
 */
inline void integratePose(
    double & x, double & y, double & theta,
    double vx, double vy, double omega,
    double dt)
{
  const double cos_th = std::cos(theta);
  const double sin_th = std::sin(theta);
  x     += (vx * cos_th - vy * sin_th) * dt;
  y     += (vx * sin_th + vy * cos_th) * dt;
  theta += omega * dt;
  // Normalize to [-pi, pi]
  theta = std::atan2(std::sin(theta), std::cos(theta));
}

}  // namespace mecanum_drive
