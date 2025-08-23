from typing import TypedDict,List,Literal,get_args
from enum import Enum
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


class SupervisorNode:
    START_CONV = Literal["start_conv"]
    END_CONV = Literal["end_conv"]
    TOOLS = Literal["tools"]
    LLM = Literal["llm"]
    ROUTE = Literal["route"]
    SUPERVISOR = Literal["supervisor"]
    CODING_AGENT = Literal["coding_agent"]
    RESEARCH_AGENT = Literal["research_agent"]

    START_CONV_VAL = "start_conv"
    END_CONV_VAL = "end_conv"
    TOOLS_VAL = "tools"
    LLM_VAL = "llm"
    ROUTE_VAL = "route"
    SUPERVISOR_VAL = "supervisor"
    CODING_AGENT_VAL = "coding_agent"
    RESEARCH_AGENT_VAL = "research_agent"