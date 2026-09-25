package com.varunvaidhiya.robotcontrol.ui.controls

import androidx.lifecycle.ViewModel
import com.varunvaidhiya.robotcontrol.data.models.RobotMode
import com.varunvaidhiya.robotcontrol.data.models.VelocityCommand
import com.varunvaidhiya.robotcontrol.data.repository.RobotRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class ControlsViewModel @Inject constructor(
    private val repository: RobotRepository
) : ViewModel() {

    val robotStatus      = repository.robotStatus
    val armJointPositions = repository.armJointPositions

    fun sendVelocity(linearX: Float, linearY: Float, angular: Float) {
        repository.sendVelocity(VelocityCommand(linearX, linearY, angular))
    }

    fun triggerEmergencyStop() {
        repository.sendEmergencyStop()
    }

    fun setMode(mode: RobotMode) {
        repository.sendMode(mode)
    }

    /**
     * Command all 6 arm joints at once.
     * [positions] is ordered by Constants.ARM_JOINT_NAMES:
     *   [shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper] in radians.
     */
    fun sendArmPositions(positions: DoubleArray) {
        repository.sendArmJointCommand(positions)
    }

    /** Set a single arm joint by index (0=shoulder_pan … 5=gripper). */
    fun sendArmJoint(index: Int, radians: Double) {
        val current = armJointPositions.value.copyOf()
        if (index in current.indices) {
            current[index] = radians
            repository.sendArmJointCommand(current)
        }
    }

    fun setArmEnabled(enabled: Boolean) {
        repository.setArmEnabled(enabled)
    }
}
