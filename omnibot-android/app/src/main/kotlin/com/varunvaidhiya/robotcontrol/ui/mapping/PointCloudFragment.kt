package com.varunvaidhiya.robotcontrol.ui.mapping

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.varunvaidhiya.robotcontrol.databinding.FragmentPointCloudBinding
import com.varunvaidhiya.robotcontrol.ui.common.BaseFragment
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

@AndroidEntryPoint
class PointCloudFragment : BaseFragment<FragmentPointCloudBinding>() {

    private val viewModel: PointCloudViewModel by viewModels()

    override fun inflateBinding(inflater: LayoutInflater, container: ViewGroup?): FragmentPointCloudBinding =
        FragmentPointCloudBinding.inflate(inflater, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setupObservers()
    }

    private fun setupObservers() {
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {

                launch {
                    viewModel.points.collectLatest { pts ->
                        val hasData = pts.isNotEmpty()
                        binding.layoutNoData.visibility = if (hasData) View.GONE else View.VISIBLE
                        if (hasData) binding.pointCloudView.updatePoints(pts)
                    }
                }

                launch {
                    viewModel.pointCount.collectLatest { n ->
                        binding.textPointCount.text = "Points: $n"
                    }
                }

                launch {
                    viewModel.maxRange.collectLatest { r ->
                        binding.textCloudRange.text = "Range: %.1f m".format(r)
                    }
                }

                launch {
                    viewModel.fps.collectLatest { f ->
                        binding.textCloudFps.text = "FPS:   %.1f".format(f)
                    }
                }
            }
        }
    }
}
