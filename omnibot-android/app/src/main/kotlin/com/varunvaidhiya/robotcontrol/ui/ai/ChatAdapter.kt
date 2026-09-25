package com.varunvaidhiya.robotcontrol.ui.ai

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.varunvaidhiya.robotcontrol.R

class ChatAdapter : ListAdapter<ChatMessage, ChatAdapter.MsgVH>(DIFF) {

    inner class MsgVH(view: View) : RecyclerView.ViewHolder(view) {
        val layoutUser: View     = view.findViewById(R.id.layout_user)
        val layoutRobot: View    = view.findViewById(R.id.layout_robot)
        val textUser: TextView   = view.findViewById(R.id.text_user_msg)
        val timeUser: TextView   = view.findViewById(R.id.text_user_time)
        val textRobot: TextView  = view.findViewById(R.id.text_robot_msg)
        val timeRobot: TextView  = view.findViewById(R.id.text_robot_time)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): MsgVH =
        MsgVH(LayoutInflater.from(parent.context).inflate(R.layout.item_chat_message, parent, false))

    override fun onBindViewHolder(holder: MsgVH, position: Int) {
        val msg = getItem(position)
        if (msg.isUser) {
            holder.layoutUser.visibility  = View.VISIBLE
            holder.layoutRobot.visibility = View.GONE
            holder.textUser.text  = msg.text
            holder.timeUser.text  = msg.timestamp
        } else {
            holder.layoutUser.visibility  = View.GONE
            holder.layoutRobot.visibility = View.VISIBLE
            holder.textRobot.text  = msg.text
            holder.timeRobot.text  = msg.timestamp
        }
    }

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<ChatMessage>() {
            override fun areItemsTheSame(a: ChatMessage, b: ChatMessage) =
                a.timestamp == b.timestamp && a.text == b.text
            override fun areContentsTheSame(a: ChatMessage, b: ChatMessage) = a == b
        }
    }
}
