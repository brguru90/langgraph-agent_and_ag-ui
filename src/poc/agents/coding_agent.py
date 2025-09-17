import asyncio,json
from typing import Annotated, NotRequired,Dict,Optional,Any
from langgraph.prebuilt import InjectedState,InjectedStore, create_react_agent
from typing import TypedDict, Literal,List,get_args
from langchain_ollama import ChatOllama
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool
from langchain_core import messages
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from fastmcp.client.transports import StdioTransport
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastmcp import Client
from fastmcp.client.sampling import (
    SamplingMessage,
    SamplingParams,
    RequestContext,
)
from mcp import ClientSession
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from langchain_core.runnables.config import RunnableConfig
from langchain_core.runnables.base import RunnableBindingBase
from langchain_core.tracers.schemas import Run
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.modifier import RemoveMessage
from langchain_core.messages.utils import count_tokens_approximately
from langmem.short_term import SummarizationNode,summarize_messages,RunningSummary
from langgraph.func import entrypoint, task
import uuid
from langgraph.checkpoint.base import Checkpoint, BaseCheckpointSaver
from langchain_core.prompts.chat import ChatPromptTemplate, ChatPromptValue
from langchain_core.messages.utils import get_buffer_string
from langgraph.store.base import BaseStore,SearchItem
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import AsyncSqliteStore
from langgraph.store.redis import AsyncRedisStore
from langgraph.store.base import IndexConfig
from langchain_aws import BedrockEmbeddings
import sqlite3
import aiosqlite
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import traceback

from .utils import max_tokens,thinking_params,mcp_sampling_handler,get_aws_modal,create_handoff_tool
from .state import ChatState,SupervisorNode

class CodingAgent:   
    def __init__(self):
        print("__CodingAgent__")
        self.base_llm = None
        self.llm = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.max_tool_calls = 4
        self.client:Client = None
        self.client_session:ClientSession = None
        self.name:str=SupervisorNode.CODING_AGENT_VAL
        self.descriptions="Provides documentation for the vue3 with the FDS(Fabric Design system) components"

    def get_steering_tool(self):
        return create_handoff_tool(agent_name=self.name, description=f"Assign task to a coding/programming Agent ({self.descriptions}")
    
    

    async def llm_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """LLM node - only responsible for calling llm.invoke"""

        chat_messages =state["messages"]
        for msg in chat_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())
        try:
            response = await self.llm.ainvoke(chat_messages)
        except Exception as e:
            print(f"Error invoking LLM: {e}\n",chat_messages,traceback.print_exc())
            response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}",id=str(uuid.uuid4()))
        
        updated_messages = chat_messages + [response]

        return Command(
            update={
                'messages': updated_messages,
            },
            goto="route"
        )

    async def tools_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """Tools node - only responsible for calling tool_node.ainvoke"""    
        ai_msg:messages.AIMessage=state["messages"][-1]
        result = await self.tool_node.ainvoke(state)

        # Combine all messages for the updated state
        all_updated_messages = state['messages'] + result['messages']
        
        return Command(
            update={
                'messages': all_updated_messages,
                'tool_call_count': state['tool_call_count']+1
            },
            goto="route"
        )

    def route_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal["tools", "llm"]]:
        """Route node - handles all routing logic using Command pattern"""
        # !!! Command pattern allows us to define custom logic and state can be update during routing

        last_message = state['messages'][-1]

        print(f"--route_node coding_agent: message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}, len={len(state['messages'])}",last_message)


        # Check if we've exceeded tool call limit
        if state['tool_call_count'] >= self.max_tool_calls:
            print(f">>> Interrupting for human input... on thread_id={state['thread_id']}")
            user_answer = interrupt("Tool call exceeded limit, please reply:\n 1. 'yes' to continue\n 2. 'no' to exit\n 3. any other input will be treated as feedback prompt")
            print(f"User answer: '{user_answer}'",end="\n\n")
            
            if user_answer == 'no':
                # Explicitly end the graph
                return Command(
                    update={},  # No state update needed
                    goto=END  # End the conversation
                )
            elif user_answer == 'yes':
                # Reset tool count and continue with tools if LLM wants to use them
                if getattr(last_message, 'tool_calls', None):
                    return Command(
                        update={'tool_call_count': 0},
                        goto="tools"
                    )
                else:
                    return Command(
                        update={'tool_call_count': 0},
                        goto="llm"
                    )
            else:
                # User provided new input i.e., its neither yes nor no - this becomes a new human message
                new_human_message = messages.HumanMessage(content=user_answer, id=str(uuid.uuid4()))
                updated_messages = state['messages'] + [new_human_message]
                                
                
                # Reset tool count and restart LLM processing
                return Command(
                    update={
                        'messages': updated_messages, 
                        'tool_call_count': 0,
                    },
                    goto="llm"
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
        self.base_llm = get_aws_modal()

        mcp_config={
                "fds": {
                    "command": "uvx",
                    "args": ["fds-mcp-server"],
                    "transport": "stdio",
                }
        }
        self.client=Client(mcp_config,sampling_handler=mcp_sampling_handler)        
        self.client_session = (await self.client.__aenter__()).session
        self.tools = await load_mcp_tools(self.client_session)
        
        if self.tools:
            print(f"Successfully loaded {len(self.tools)} MCP tools")
        else:
            raise ValueError("No tools loaded, returning...")

        for tool in self.tools:
            tool.name=self.name+"_"+tool.name
        self.llm = self.base_llm.bind_tools(self.tools)            
        self.tool_node = ToolNode(self.tools)

        builder = StateGraph(ChatState)
        builder.add_node('llm', self.llm_node)
        builder.add_node('tools', self.tools_node)
        builder.add_node('route', self.route_node)        

        builder.add_edge(START, 'llm')
        builder.add_edge("route", END)

        self.graph = builder.compile(name=self.name)
        self.graph.get_graph().print_ascii()
        


    async def close(self):
        """Clean up resources and close connections"""
        print("Closing agent resources...")
        await self.__aexit__(None, None, None)

    # Keep the async context manager methods for backward compatibility
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
            if self.client_session:
                try:
                    print("Closing client session...")
                    await asyncio.wait_for(
                        self.client_session.__aexit__(exc_type, exc_val, exc_tb),
                        timeout=2.0  # Give it 2 seconds to close gracefully
                    )
                    print("Client session closed successfully")
                except asyncio.TimeoutError:
                    print("Client session close timed out, forcing cleanup")
                except Exception as e:
                    print(f"Error closing client session: {e}")
                finally:
                    self.client_session = None
                    self.client_session = None
            
            # Clean up the main client (no __aexit__ method available)
            if self.client:
                self.client.close()
                self.client = None
        
        print("Agent cleanup completed")
    

