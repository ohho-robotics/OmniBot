package com.varunvaidhiya.robotcontrol.ui.slam

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.varunvaidhiya.robotcontrol.data.models.OdomData
import com.varunvaidhiya.robotcontrol.data.repository.RobotRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SlamViewModel @Inject constructor(
    private val repository: RobotRepository
) : ViewModel() {

    val connectionState = repository.connectionState

    private val _mapData = MutableStateFlow<IntArray?>(null)
    val mapData: StateFlow<IntArray?> = _mapData.asStateFlow()

    private val _mapWidth = MutableStateFlow(0)
    val mapWidth: StateFlow<Int> = _mapWidth.asStateFlow()

    private val _mapHeight = MutableStateFlow(0)
    val mapHeight: StateFlow<Int> = _mapHeight.asStateFlow()

    private val _mapResolution = MutableStateFlow(0.05f)
    val mapResolution: StateFlow<Float> = _mapResolution.asStateFlow()

    private val _robotPoseX = MutableStateFlow(0f)
    val robotPoseX: StateFlow<Float> = _robotPoseX.asStateFlow()

    private val _robotPoseY = MutableStateFlow(0f)
    val robotPoseY: StateFlow<Float> = _robotPoseY.asStateFlow()

    private val _robotYaw = MutableStateFlow(0f)
    val robotYaw: StateFlow<Float> = _robotYaw.asStateFlow()

    // Odom in meters for the pose info panel
    private val _odomMeters = MutableStateFlow(OdomData())
    val odomMeters: StateFlow<OdomData> = _odomMeters.asStateFlow()

    init {
        viewModelScope.launch {
            repository.mapData.collect { map ->
                if (map.cells.isNotEmpty()) {
                    _mapWidth.value      = map.width
                    _mapHeight.value     = map.height
                    _mapData.value       = map.cells
                    _mapResolution.value = map.resolution
                }
            }
        }

        viewModelScope.launch {
            combine(repository.odomData, repository.mapData) { odom, map -> Pair(odom, map) }
                .collect { (odom, map) ->
                    _odomMeters.value = odom
                    if (map.resolution > 0f) {
                        val (px, py) = map.metersToPixel(odom.x, odom.y)
                        _robotPoseX.value = px
                        _robotPoseY.value = py
                        _robotYaw.value   = odom.yaw
                    }
                }
        }
    }
}
