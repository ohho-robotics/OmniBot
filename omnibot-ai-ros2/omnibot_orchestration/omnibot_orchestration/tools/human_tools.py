from typing import TYPE_CHECKING, List

from langchain.tools import tool

if TYPE_CHECKING:
    from omnibot_orchestration.langchain_agent_node import LangchainAgentNode


def make_human_tools(node: "LangchainAgentNode") -> List:

    @tool
    def ask_human_for_clarification(question: str) -> str:
        """Ask the human operator for clarification when a request is ambiguous.

        Use this when:
        - The user refers to a location that is not in the known locations list.
        - The instruction is vague and could mean multiple things.
        - A task has failed twice and you need guidance.
        - You cannot determine the correct action without more information.

        The question is published to /ai/response_needed so the Android app or
        operator can see and respond to it. The operator should reply by
        publishing a new message to /ai/command.

        Args:
            question: A clear, specific question for the operator.

        Returns:
            Acknowledgment that the question was sent.
        """
        try:
            from std_msgs.msg import String as RosString

            msg = RosString()
        except ImportError:

            class _Msg:
                data: str = ""

            msg = _Msg()
        msg.data = question
        node._response_needed_pub.publish(msg)
        node.get_logger().info(f"[Tool] Clarification needed: {question}")
        return (
            f"Clarification request sent to operator: '{question}'. "
            "Waiting for response via /ai/command."
        )

    return [ask_human_for_clarification]
