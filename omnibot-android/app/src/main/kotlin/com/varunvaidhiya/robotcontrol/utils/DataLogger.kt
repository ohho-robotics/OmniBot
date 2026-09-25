package com.varunvaidhiya.robotcontrol.utils

import android.content.Context
import android.os.Environment
import com.varunvaidhiya.robotcontrol.data.models.MotorData
import com.varunvaidhiya.robotcontrol.data.models.RobotStatus
import com.varunvaidhiya.robotcontrol.data.models.WheelSpeed
import timber.log.Timber
import java.io.File
import java.io.FileWriter
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class DataLogger(private val context: Context) {

    private var currentLogFile: File? = null
    private var writer: FileWriter? = null
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
    private val fileDateFormat = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US)

    // Check if logging is enabled (can be controlled by settings)
    var isLoggingEnabled = false

    fun startNewSession() {
        if (!isLoggingEnabled) return
        
        try {
            val fileName = "robot_log_${fileDateFormat.format(Date())}.csv"
            val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS)
            currentLogFile = File(dir, fileName)
            
            writer = FileWriter(currentLogFile, true)
            // Header — shared columns for all row types:
            // SPEED/MOTOR_*: FL,FR,RL,RR hold per-wheel values
            // STATUS:        FL=connected, FR=signal, RL=rosNodes, RR=eStop, Extra1=mode, Extra2=ip
            writer?.append("Timestamp,Type,FL,FR,RL,RR,Extra1,Extra2\n")
            writer?.flush()
            Timber.i("Started logging to: ${currentLogFile?.absolutePath}")
            
        } catch (e: IOException) {
            Timber.e(e, "Failed to start logging")
        }
    }

    fun stopSession() {
        try {
            writer?.close()
            writer = null
            Timber.i("Stopped logging")
        } catch (e: IOException) {
            Timber.e(e, "Failed to stop logging")
        }
    }

    fun logWheelSpeeds(speeds: WheelSpeed) {
        if (!isLoggingEnabled || writer == null) return
        
        try {
            val timestamp = dateFormat.format(Date())
            val line = "$timestamp,SPEED,${speeds.frontLeft},${speeds.frontRight},${speeds.backLeft},${speeds.backRight}\n"
            writer?.append(line)
            writer?.flush()
        } catch (e: Exception) {
            Timber.e(e, "Error logging speeds")
        }
    }

    /**
     * Logs all four wheels' motor telemetry as five CSV rows (one per metric),
     * each following the same FL,FR,RL,RR column layout as [logWheelSpeeds].
     *
     * Row types emitted: MOTOR_PWM, MOTOR_RPM, MOTOR_CURRENT, MOTOR_TEMP, MOTOR_HEALTH
     */
    fun logMotorData(data: MotorData) {
        if (!isLoggingEnabled || writer == null) return

        try {
            val ts = dateFormat.format(Date(data.timestamp))
            val fl = data.frontLeft
            val fr = data.frontRight
            val rl = data.backLeft
            val rr = data.backRight

            writer?.append("$ts,MOTOR_PWM,${fl.pwmValue},${fr.pwmValue},${rl.pwmValue},${rr.pwmValue},,\n")
            writer?.append("$ts,MOTOR_RPM,${fl.rpm},${fr.rpm},${rl.rpm},${rr.rpm},,\n")
            writer?.append("$ts,MOTOR_CURRENT,${fl.current},${fr.current},${rl.current},${rr.current},,\n")
            writer?.append("$ts,MOTOR_TEMP,${fl.temperature},${fr.temperature},${rl.temperature},${rr.temperature},,\n")
            writer?.append("$ts,MOTOR_HEALTH,${fl.health},${fr.health},${rl.health},${rr.health},,\n")
            writer?.flush()
        } catch (e: Exception) {
            Timber.e(e, "Error logging motor data")
        }
    }

    /**
     * Logs a single robot-status snapshot.
     *
     * Column mapping (reuses the shared header):
     *   FL=connected, FR=signalStrength, RL=rosNodesActive, RR=emergencyStopActive,
     *   Extra1=currentMode, Extra2=ipAddress
     */
    fun logRobotStatus(status: RobotStatus) {
        if (!isLoggingEnabled || writer == null) return

        try {
            val ts = dateFormat.format(Date(status.timestamp))
            writer?.append(
                "$ts,STATUS,${status.isConnected},${status.signalStrength}," +
                "${status.rosNodesActive},${status.emergencyStopActive}," +
                "${status.currentMode},${status.ipAddress}\n"
            )
            writer?.flush()
        } catch (e: Exception) {
            Timber.e(e, "Error logging robot status")
        }
    }

    fun getLogFiles(): List<File> {
        val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS)
        return dir?.listFiles()?.sortedDescending()?.toList() ?: emptyList()
    }
}
