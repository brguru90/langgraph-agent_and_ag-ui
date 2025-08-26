import uuid
from typing import Literal
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


class ResearchAgent:

    def __init__(self, return_to_supervisor=False):
        print("__ResearchAgent__")
        self.return_to_supervisor = return_to_supervisor
        self.base_llm = None
        self.llm = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.max_tool_calls = 6
        self.client = None
        self.client_session = None
        self.client_session_ctx = None

    def get_steering_tool(self):
        return create_handoff_tool(agent_name=SupervisorNode.RESEARCH_AGENT_VAL, description="Assign task to a researcher agent.")

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

    def route_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["tools", "llm"]]:
        """Route node - handles all routing logic using Command pattern"""
        
        last_message = state['messages'][-1]

        print(f"--route_node research_agent: message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}, len={len(state['messages'])}", last_message)

        # Check if we've exceeded tool call limit
        if state['tool_call_count'] >= self.max_tool_calls:
            print(f">>> Tool call limit exceeded for research agent on thread_id={state['thread_id']}")
            # For research agent, we'll just end gracefully instead of interrupting
            return Command(
                update={},
                goto=END
            )
        
        # Normal flow routing logic:
        # 1. If last message is AIMessage with tool_calls → go to tools
        # 2. If last message is ToolMessage → go to LLM (to process tool results)
        # 3. If last message is AIMessage without tool_calls → end (LLM finished)
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
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

        mcp_config={
                "context7": {
                    "url": "https://mcp.context7.com/mcp",
                    "transport": "http",
                }
        }
        self.client=Client(mcp_config,sampling_handler=mcp_sampling_handler)        
        self.client_session = (await self.client.__aenter__()).session
        self.tools = await load_mcp_tools(self.client_session)        
        if self.tools:
            print(f"Successfully loaded {len(self.tools)} MCP tools")
        else:
            raise ValueError("No tools loaded, returning...")
        
        # Bind tools to LLM and create tool node
        self.llm = self.base_llm.bind_tools(self.tools)
        self.tool_node = ToolNode(self.tools)

        # Build the graph using StateGraph
        builder = StateGraph(ChatState)
        builder.add_node('llm', self.llm_node)
        builder.add_node('tools', self.tools_node)
        builder.add_node('route', self.route_node)        

        builder.add_edge(START, 'llm')
        builder.add_edge("route", END)

        self.graph = builder.compile(name=SupervisorNode.RESEARCH_AGENT_VAL)
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
        import asyncio
        import warnings
        
        # Suppress warnings during cleanup
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            # Close client session first
            if self.client_session_ctx:
                try:
                    print("Closing client session...")
                    await asyncio.wait_for(
                        self.client_session_ctx.__aexit__(exc_type, exc_val, exc_tb),
                        timeout=2.0  # Give it 2 seconds to close gracefully
                    )
                    print("Client session closed successfully")
                except asyncio.TimeoutError:
                    print("Client session close timed out, forcing cleanup")
                except Exception as e:
                    print(f"Error closing client session: {e}")
                finally:
                    self.client_session_ctx = None
                    self.client_session = None
            
            # Clean up the main client (no __aexit__ method available)
            if self.client:
                self.client = None
        
        print("Agent cleanup completed")