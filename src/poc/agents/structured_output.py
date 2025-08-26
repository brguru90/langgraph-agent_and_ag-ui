import uuid
from typing import Literal,Annotated, NotRequired,Dict,Optional,Any,cast

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langchain_core import messages
from langchain_core.runnables.config import RunnableConfig
from langgraph.store.base import BaseStore
from .utils import mcp_sampling_handler,get_aws_modal,create_handoff_tool
from fastmcp import Client
from langchain_mcp_adapters.tools import load_mcp_tools
from .state import ChatState,SupervisorNode
import traceback
from langgraph.prebuilt import InjectedState,InjectedStore, create_react_agent
from langchain_core.tools import tool, InjectedToolCallId

@tool
async def combine_responses(
    state: Annotated[ChatState,InjectedState],
) -> str | list[str | dict]:
    """Combine the responses,
    - If the multiple user queries provided or the multiple steps involved with related response, then add one or more steps to combine the response or conclude the response meaningfully into single final response.
    - If the multiple unrelated queries provided or the multiple steps involved with unrelated response, then add one or more steps to combine all the information into different block/sections in the same single final response.
    - Don't summaries and don't loose any information from the final response while combining.
    """

    return ""


class StructuredOutputAgent:

    def __init__(self, return_to_supervisor=False):
        print("__StructuredOutputAgent__")
        self.return_to_supervisor = return_to_supervisor
        self.base_llm = None
        self.llm = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.descriptions="Responsible for generating structured outputs from unstructured inputs and also combining the multiple information from different execution steps."

    def get_steering_tool(self):
        return create_handoff_tool(agent_name=SupervisorNode.STRUCTURED_OUTPUT_AGENT_VAL, description=f"Assign task to a structured output agent ({self.descriptions}).")
    
    def combine_responses(self, state: ChatState, config: RunnableConfig, *, store: BaseStore):
        """Combine responses node - only responsible for calling combine_responses tool"""    
        plans=state["plan"].plan
        combine_response_payload=[]
        for plan in plans:
            if plan.status == "pending":
                instructions=plan.model_dump_json()
                dependent_response=[dependent_plan.response for dependent_plan in plans if dependent_plan.step_uid in plan.response_from_previous_step and dependent_plan.response]
                combine_response_payload.append(    
                    messages.HumanMessage(
                        content=f"complete execution steps with planning and respective responses for the plan:\n {instructions} dependent_response={dependent_response}",
                        id=str(uuid.uuid4())
                    )
                )
        response=self.base_llm.invoke(combine_response_payload)
        
        return Command(
            update={
                'messages': state["messages"] + [response],
                'tool_call_count': state['tool_call_count'] + 1
            },
            goto=END
        )

    async def llm_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """LLM node - only responsible for calling llm.invoke"""
        
        chat_messages = state["messages"]
        for msg in chat_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())
        try:
            response = self.llm.invoke(chat_messages)
        except Exception as e:
            print(f"Error invoking LLM: {e}\n", chat_messages, traceback.print_exc())
            response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}", id=str(uuid.uuid4()))
        
        updated_messages = chat_messages + [response]

        return Command(
            update={
                'messages': updated_messages,
            },
            goto="route"
        )

    async def tools_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """Tools node - only responsible for calling tool_node.ainvoke"""    
        ai_msg: messages.AIMessage = state["messages"][-1]
        result = await self.tool_node.ainvoke(state)

        # Combine all messages for the updated state
        all_updated_messages = state['messages'] + result['messages']
        
        return Command(
            update={
                'messages': all_updated_messages,
                'tool_call_count': state['tool_call_count'] + 1
            },
            goto="route"
        )

    def route_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["tools", "llm","combine_responses"]]:
        """Route node - handles all routing logic using Command pattern"""
        
        last_message = state['messages'][-1]

        print(f"--route_node combine_out_agent: message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}, len={len(state['messages'])}", last_message)
        

        def check_call_to_agent():
            print("\n----- check_call_to_agent ------\n")
            delegate_to_node=["combine_responses"]
            if not isinstance(last_message,messages.AIMessage):
                return False
            is_agent_call = last_message.tool_calls[0]['name'] in delegate_to_node
            if not is_agent_call:
                return False
            
            tool_message = messages.ToolMessage(
                content=f"Successfully transferred to Agent `{last_message.tool_calls[0]["name"]}`",
                name=last_message.tool_calls[0]['name'],
                tool_call_id=last_message.tool_calls[0]["id"]
            )

            print("\n------check_plan_executer------\n")
            return Command(
                update={
                    'messages':  state['messages'] + [tool_message]
                },
                goto=last_message.tool_calls[0]['name']
            )  

        # Normal flow routing logic:
        # 1. If last message is AIMessage with tool_calls → go to tools
        # 2. If last message is ToolMessage → go to LLM (to process tool results)
        # 3. If last message is AIMessage without tool_calls → end (LLM finished)
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            forward_to_agent=check_call_to_agent()
            if forward_to_agent:
                return forward_to_agent
            # LLM wants to use tools
            return Command(
                update={},
                goto="tools"
            )
        elif last_message.type == 'tool':
            # Tool message completed, let LLM process the results
            return Command(
                update={},
                goto="llm"
            )
        else:
            # LLM finished without tool calls - end execution
            return Command(
                update={},
                goto=END
            )

    async def init(self):
        """Initialize the agent with MCP tools and LLM"""
        
        # Initialize LLMs
        self.base_llm = get_aws_modal(additional_model_request_fields=None, temperature=0)

        self.tools = []
        self.tools.append(combine_responses)        
        self.llm = self.base_llm.bind_tools(self.tools)
        self.tool_node = ToolNode(self.tools)

        # Build the graph using StateGraph
        builder = StateGraph(ChatState)
        builder.add_node('llm', self.llm_node)
        builder.add_node('tools', self.tools_node)
        builder.add_node('combine_responses', self.combine_responses)
        builder.add_node('route', self.route_node)        

        builder.add_edge(START, 'llm')
        builder.add_edge("combine_responses", END)
        builder.add_edge("route", END)

        self.graph = builder.compile(name=SupervisorNode.STRUCTURED_OUTPUT_AGENT)
        self.graph.get_graph().print_ascii()

    async def close(self):
        """Clean up resources and close connections"""
        print("Closing agent resources...")
        await self.__aexit__(None, None, None)

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources and close connections"""

        print("Agent cleanup completed")