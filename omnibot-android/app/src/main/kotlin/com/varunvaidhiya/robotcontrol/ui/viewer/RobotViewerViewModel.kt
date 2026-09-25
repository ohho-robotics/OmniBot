package com.varunvaidhiya.robotcontrol.ui.viewer

import androidx.lifecycle.ViewModel
import com.varunvaidhiya.robotcontrol.data.repository.RobotRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class RobotViewerViewModel @Inject constructor(
    private val repository: RobotRepository
) : ViewModel() {

    val connectionState   = repository.connectionState
    val odomData          = repository.odomData
    val mapData           = repository.mapData
    val armJointPositions = repository.armJointPositions  // DoubleArray, 6 joints

    /** Publish a NavigateToPose goal by routing through the mission planner. */
    fun sendNavigationGoal(worldX: Float, worldY: Float) {
        repository.sendMissionCommand("navigate:pose:${worldX},${worldY},0.0")
    }
}
