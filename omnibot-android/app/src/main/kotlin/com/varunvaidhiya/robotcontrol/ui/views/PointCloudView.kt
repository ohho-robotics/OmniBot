package com.varunvaidhiya.robotcontrol.ui.views

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.ScaleGestureDetector
import android.view.View
import kotlin.math.max
import kotlin.math.min

/**
 * Renders a top-down 2D projection of a ROS PointCloud2 message.
 * Points are coloured by depth (Z) using a Jet-like colormap:
 *   near → blue   mid → green/yellow   far → red
 *
 * Supports pinch-to-zoom.
 */
class PointCloudView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    data class Point3D(val x: Float, val y: Float, val z: Float)

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val robotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        style = Paint.Style.STROKE
        strokeWidth = 3f
    }
    private val gridPaint = Paint().apply {
        color = Color.argb(40, 255, 255, 255)
        strokeWidth = 1f
        style = Paint.Style.STROKE
    }

    private var points: List<Point3D> = emptyList()
    private var minZ = 0f
    private var maxZ = 5f

    private var scaleFactor = 60f          // pixels per metre
    private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            scaleFactor *= detector.scaleFactor
            scaleFactor = scaleFactor.coerceIn(10f, 300f)
            invalidate()
            return true
        }
    })

    override fun onTouchEvent(ev: android.view.MotionEvent): Boolean {
        scaleDetector.onTouchEvent(ev)
        return true
    }

    fun updatePoints(newPoints: List<Point3D>) {
        if (newPoints.isEmpty()) return
        points = newPoints
        minZ = newPoints.minOf { it.z }
        maxZ = max(newPoints.maxOf { it.z }, minZ + 0.01f)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val cx = width / 2f
        val cy = height / 2f

        // Draw grid
        val gridStep = scaleFactor
        var gx = cx % gridStep
        while (gx < width) { canvas.drawLine(gx, 0f, gx, height.toFloat(), gridPaint); gx += gridStep }
        var gy = cy % gridStep
        while (gy < height) { canvas.drawLine(0f, gy, width.toFloat(), gy, gridPaint); gy += gridStep }

        // Draw points
        for (pt in points) {
            val sx = cx + pt.x * scaleFactor
            val sy = cy - pt.y * scaleFactor   // Y flipped (ROS Y = left)
            if (sx < 0 || sx > width || sy < 0 || sy > height) continue

            val t = ((pt.z - minZ) / (maxZ - minZ)).coerceIn(0f, 1f)
            paint.color = jetColor(t)
            canvas.drawCircle(sx, sy, 2.5f, paint)
        }

        // Robot marker (cross at centre)
        canvas.drawLine(cx - 10, cy, cx + 10, cy, robotPaint)
        canvas.drawLine(cx, cy - 10, cx, cy + 10, robotPaint)
        canvas.drawCircle(cx, cy, 6f, robotPaint)
    }

    /** Jet-like colormap: t=0→blue, t=0.5→green, t=1→red */
    private fun jetColor(t: Float): Int {
        val r = (255 * min(1f, max(0f, 1.5f - kotlin.math.abs(4f * t - 3f)))).toInt()
        val g = (255 * min(1f, max(0f, 1.5f - kotlin.math.abs(4f * t - 2f)))).toInt()
        val b = (255 * min(1f, max(0f, 1.5f - kotlin.math.abs(4f * t - 1f)))).toInt()
        return Color.rgb(r, g, b)
    }
}
