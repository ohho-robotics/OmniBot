package com.varunvaidhiya.robotcontrol.data.models

/**
 * Odometry data from /odom (nav_msgs/Odometry)
 */
data class OdomData(
    val x: Float = 0f,          // meters, in odom frame
    val y: Float = 0f,
    val yaw: Float = 0f,        // radians
    val vx: Float = 0f,         // m/s, robot frame
    val vy: Float = 0f,
    val vz: Float = 0f,         // rad/s
    val timestamp: Long = System.currentTimeMillis()
)
