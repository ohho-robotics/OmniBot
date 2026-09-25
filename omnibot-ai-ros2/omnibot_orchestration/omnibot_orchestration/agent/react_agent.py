from typing import List

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def build_agent(
    tools: List,
    system_prompt: str,
    api_key: str = "",
    max_iterations: int = 10,
    timeout: float = 120.0,
) -> AgentExecutor:
    """
    Build a LangChain AgentExecutor backed by Claude with native tool calling.

    Uses create_tool_calling_agent (structured JSON tool calls via Anthropic's
    tool use API) rather than text-based ReAct parsing — critical for robot
    safety since malformed tool calls are caught before any motion is commanded.
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise ImportError(
            "langchain-anthropic is required. Run: pip install langchain-anthropic"
        ) from e

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        anthropic_api_key=api_key or None,  # None → reads ANTHROPIC_API_KEY env var
        max_tokens=4096,
        temperature=0.1,  # Low temperature for deterministic robot action decisions
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=max_iterations,
        max_execution_time=timeout,
        verbose=True,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )
