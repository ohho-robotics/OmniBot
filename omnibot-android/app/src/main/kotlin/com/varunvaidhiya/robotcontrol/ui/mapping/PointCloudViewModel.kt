package com.varunvaidhiya.robotcontrol.ui.mapping

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.varunvaidhiya.robotcontrol.data.repository.RobotRepository
import com.varunvaidhiya.robotcontrol.ui.views.PointCloudView
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class PointCloudViewModel @Inject constructor(
    private val repository: RobotRepository
) : ViewModel() {

    private val _points = MutableStateFlow<List<PointCloudView.Point3D>>(emptyList())
    val points: StateFlow<List<PointCloudView.Point3D>> = _points.asStateFlow()

    private val _pointCount = MutableStateFlow(0)
    val pointCount: StateFlow<Int> = _pointCount.asStateFlow()

    private val _maxRange = MutableStateFlow(0f)
    val maxRange: StateFlow<Float> = _maxRange.asStateFlow()

    private var lastFrameMs = 0L
    private val _fps = MutableStateFlow(0f)
    val fps: StateFlow<Float> = _fps.asStateFlow()

    init {
        viewModelScope.launch {
            repository.pointCloud.collect { pts ->
                val now = System.currentTimeMillis()
                if (lastFrameMs > 0) {
                    val dt = (now - lastFrameMs) / 1000f
                    _fps.value = if (dt > 0) 1f / dt else 0f
                }
                lastFrameMs = now
                _points.value = pts
                _pointCount.value = pts.size
                _maxRange.value = pts.maxOfOrNull { kotlin.math.sqrt((it.x * it.x + it.y * it.y).toDouble()).toFloat() } ?: 0f
            }
        }
    }
}
