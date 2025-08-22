from typing import TypedDict,List
from langchain_core.messages.base import BaseMessage
from langmem.short_term import RunningSummary
from langgraph.prebuilt.chat_agent_executor import AgentState

class ChatState(AgentState):
    messages: List[BaseMessage]
    tool_call_count: int
    thread_id: str 
    summary:RunningSummary | None
    updated_log_term_memory: bool
    messages_history: List[BaseMessage]