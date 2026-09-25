package com.varunvaidhiya.robotcontrol.ui.slam

import android.animation.ObjectAnimator
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.varunvaidhiya.robotcontrol.databinding.FragmentSlamMapBinding
import com.varunvaidhiya.robotcontrol.ui.common.BaseFragment
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@AndroidEntryPoint
class SlamMapFragment : BaseFragment<FragmentSlamMapBinding>() {

    private val slamViewModel: SlamViewModel by viewModels()

    override fun inflateBinding(inflater: LayoutInflater, container: ViewGroup?): FragmentSlamMapBinding =
        FragmentSlamMapBinding.inflate(inflater, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        fadeOutHint()
        setupObservers()
    }

    private fun fadeOutHint() {
        binding.textZoomHint.postDelayed({
            ObjectAnimator.ofFloat(binding.textZoomHint, "alpha", 1f, 0f).apply {
                duration = 1200
                start()
            }
        }, 3000)
    }

    private fun setupObservers() {
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {

                launch {
                    slamViewModel.mapData.collectLatest { data ->
                        if (data != null) {
                            val w = slamViewModel.mapWidth.value
                            val h = slamViewModel.mapHeight.value
                            binding.slamMapView.updateMap(w, h, data)
                            updateMapStats(w, h, data)
                        }
                    }
                }

                launch {
                    slamViewModel.robotPoseX.collectLatest { _ ->
                        val x = slamViewModel.robotPoseX.value
                        val y = slamViewModel.robotPoseY.value
                        val yaw = slamViewModel.robotYaw.value
                        binding.slamMapView.updateRobotPose(x, y, yaw)
                    }
                }

                // Odom pose display (meters, not pixels)
                launch {
                    slamViewModel.odomMeters.collectLatest { odom ->
                        binding.textPoseX.text = "X:    %.2f m".format(odom.x)
                        binding.textPoseY.text = "Y:    %.2f m".format(odom.y)
                        val deg = Math.toDegrees(odom.yaw.toDouble()).roundToInt()
                        binding.textPoseYaw.text = "θ:    ${deg}°"
                    }
                }

                launch {
                    slamViewModel.mapResolution.collectLatest { res ->
                        binding.textMapRes.text = "Res:  %.3f m/cell".format(res)
                    }
                }
            }
        }
    }

    private fun updateMapStats(width: Int, height: Int, cells: IntArray) {
        binding.textMapSize.text = "Size: ${width}×${height}"
        if (cells.isNotEmpty()) {
            val known = cells.count { it >= 0 }
            val pct = (known * 100f / cells.size).roundToInt()
            binding.textMapExplored.text = "Known: ${pct}%"
        }
    }
}
