package com.varunvaidhiya.robotcontrol.data.models

/**
 * Occupancy grid map from /map (nav_msgs/OccupancyGrid)
 * Cell values: -1 = unknown, 0 = free, 100 = occupied
 */
data class MapData(
    val width: Int = 0,
    val height: Int = 0,
    val resolution: Float = 0.05f,  // meters per cell
    val originX: Float = 0f,        // map origin in meters
    val originY: Float = 0f,
    val cells: IntArray = IntArray(0),
    val timestamp: Long = System.currentTimeMillis()
) {
    /** Convert a pose in meters to map pixel coordinates */
    fun metersToPixel(worldX: Float, worldY: Float): Pair<Float, Float> {
        val px = (worldX - originX) / resolution
        val py = height - (worldY - originY) / resolution  // flip Y axis
        return Pair(px, py)
    }
}
