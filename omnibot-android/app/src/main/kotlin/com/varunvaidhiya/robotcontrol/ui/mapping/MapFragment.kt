package com.varunvaidhiya.robotcontrol.ui.mapping

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.viewpager2.adapter.FragmentStateAdapter
import com.google.android.material.tabs.TabLayoutMediator
import com.varunvaidhiya.robotcontrol.R
import com.varunvaidhiya.robotcontrol.databinding.FragmentMapBinding
import com.varunvaidhiya.robotcontrol.ui.slam.SlamMapFragment
import com.varunvaidhiya.robotcontrol.ui.viewer.RobotViewerFragment
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MapFragment : Fragment() {

    private var _binding: FragmentMapBinding? = null
    private val binding get() = _binding!!

    private val tabs = listOf(
        TabInfo("2D SLAM",   R.drawable.ic_map)       { SlamMapFragment() },
        TabInfo("3D Cloud",  R.drawable.ic_3d_map)    { PointCloudFragment() },
        TabInfo("3D Robot",  R.drawable.ic_omnibot_logo) { RobotViewerFragment() }
    )

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentMapBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        binding.viewPagerMap.adapter = object : FragmentStateAdapter(this) {
            override fun getItemCount() = tabs.size
            override fun createFragment(position: Int) = tabs[position].factory()
        }

        // Disable swipe on all tabs — each tab uses its own gestures (pinch-zoom etc.)
        binding.viewPagerMap.isUserInputEnabled = false

        TabLayoutMediator(binding.tabLayoutMap, binding.viewPagerMap) { tab, pos ->
            tab.text = tabs[pos].label
            tab.icon = requireContext().getDrawable(tabs[pos].iconRes)
        }.attach()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    private data class TabInfo(
        val label: String,
        val iconRes: Int,
        val factory: () -> Fragment
    )
}
