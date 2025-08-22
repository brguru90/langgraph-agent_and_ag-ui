
from langchain_aws import ChatBedrockConverse
from langchain_core import messages
from fastmcp.client.sampling import (
    SamplingMessage,
    SamplingParams,
    RequestContext,
)
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately
import uuid
from langchain_aws import BedrockEmbeddings


import asyncio,json
from typing import Annotated, NotRequired,Dict,Optional,Any
from langgraph.prebuilt import InjectedState,InjectedStore, create_react_agent
from typing import TypedDict, Literal,List
from langchain_ollama import ChatOllama
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph,MessagesState, START, END
from fastmcp.client.transports import StdioTransport
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.base import Checkpoint, BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import AsyncSqliteStore
from langgraph.store.redis import AsyncRedisStore
from langgraph.store.base import IndexConfig
import sqlite3
import aiosqlite
import asyncio
from concurrent.futures import ThreadPoolExecutor
from langgraph.types import Command, interrupt


# claude-sonnet-4 -> supports upto 200k tokens

# max_tokens = 65536
# max_tokens = 2000
max_tokens = 20000

thinking_params = {
    "thinking": {
        "type": "enabled",
        "budget_tokens": 2000  # Adjust based on your requirements
    }
}

def get_aws_modal(model_max_tokens=max_tokens,temperature=0.5,additional_model_request_fields=thinking_params,**kwargs):
    return ChatBedrockConverse(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", 
        region_name="us-west-2", 
        credentials_profile_name="llm-sandbox",
        temperature=1 if additional_model_request_fields else temperature,
        max_tokens=model_max_tokens, 
        additional_model_request_fields=additional_model_request_fields,
        **kwargs
    )
    # return ChatOllama(
    #     model="llama3.2",
    #     base_url="http://192.168.3.104:11434"
    # )

def get_aws_embed_model():
    return BedrockEmbeddings(
        model_id="amazon.titan-embed-text-v2:0",
        region_name="us-west-2",
        credentials_profile_name="llm-sandbox"
    )


async def mcp_sampling_handler(
    _messages: list[SamplingMessage],
    params: SamplingParams,
    context: RequestContext
) -> BaseMessage:
    print(params)
    print("\n\n---------- mcp_sampling_handler -------------\n\n")
    compatible_messages=[messages.HumanMessage(content=message.content.text, id=str(uuid.uuid4())) for message in _messages]
    if count_tokens_approximately(compatible_messages) > 1000:
        raise ValueError(f"Messages exceed 1000 tokens({count_tokens_approximately(compatible_messages)}), unable to process.")
    response=await get_aws_modal(model_max_tokens=1200,temperature=0.0,additional_model_request_fields=None).ainvoke(compatible_messages) # without any tool
    print("MCP response:", response)
    return response.content



def create_handoff_tool(*, agent_name: str, description: str | None = None):
    name = f"transfer_to_{agent_name}"
    description = description or f"Ask {agent_name} for help."

    @tool(name, description=description)
    def handoff_tool(
        state: Annotated[MessagesState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        # tool_message = {
        #     "role": "tool",
        #     "content": f"Successfully transferred to {agent_name}",
        #     "name": name,
        #     "tool_call_id": tool_call_id,
        # }
        tool_message = messages.ToolMessage(
            role="tool",
            content=f"Successfully transferred to {agent_name}",
            name=name,
            tool_call_id=tool_call_id,
        )
        return Command(
            goto=agent_name,  
            update={**state, "messages": state["messages"] + [tool_message]},  
            graph=Command.PARENT,  
        )

    return handoff_tool


class AsyncSqliteSaverWrapper(BaseCheckpointSaver):
    """
    A wrapper around SqliteSaver that provides full async support while maintaining
    sync compatibility. This wrapper uses a thread pool to execute sync operations
    asynchronously without blocking the event loop.
    """
    
    def __init__(self, sqlite_saver: SqliteSaver, max_workers: int = 4):
        """
        Initialize the async wrapper.
        
        Args:
            sqlite_saver: The SqliteSaver instance to wrap
            max_workers: Maximum number of threads in the thread pool
        """
        self.sqlite_saver = sqlite_saver
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._loop = None
    
    def _ensure_loop(self):
        """Ensure we have access to the current event loop"""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
    
    # Delegate config_specs to inner saver
    @property
    def config_specs(self):
        return self.sqlite_saver.config_specs
    
    # Sync methods - delegate directly to SqliteSaver
    def get_tuple(self, config):
        return self.sqlite_saver.get_tuple(config)
    
    def list(self, config, *, filter=None, before=None, limit=None):
        return self.sqlite_saver.list(config, filter=filter, before=before, limit=limit)
    
    def put(self, config, checkpoint: Checkpoint, metadata, new_versions):
        return self.sqlite_saver.put(config, checkpoint, metadata, new_versions)
    
    def put_writes(self, config, writes, task_id, task_path=""):
        return self.sqlite_saver.put_writes(config, writes, task_id, task_path)
    
    def delete_thread(self, thread_id):
        return self.sqlite_saver.delete_thread(thread_id)
    
    def get_next_version(self, current, channel):
        return self.sqlite_saver.get_next_version(current, channel)
    
    # Async methods - run sync methods in thread pool
    async def aget_tuple(self, config):
        """Async version of get_tuple"""
        self._ensure_loop()
        if self._loop:
            return await self._loop.run_in_executor(
                self._executor, 
                self.sqlite_saver.get_tuple, 
                config
            )
        else:
            # Fallback to sync if no event loop
            return self.sqlite_saver.get_tuple(config)
    
    async def alist(self, config, *, filter=None, before=None, limit=None):
        """Async version of list"""
        self._ensure_loop()
        if self._loop:
            # Since list returns a generator, we need to handle it specially
            items = await self._loop.run_in_executor(
                self._executor,
                lambda: list(self.sqlite_saver.list(config, filter=filter, before=before, limit=limit))
            )
            for item in items:
                yield item
        else:
            # Fallback to sync if no event loop
            for item in self.sqlite_saver.list(config, filter=filter, before=before, limit=limit):
                yield item
    
    async def aput(self, config, checkpoint: Checkpoint, metadata, new_versions):
        """Async version of put"""
        self._ensure_loop()
        if self._loop:
            return await self._loop.run_in_executor(
                self._executor,
                self.sqlite_saver.put,
                config, checkpoint, metadata, new_versions
            )
        else:
            # Fallback to sync if no event loop
            return self.sqlite_saver.put(config, checkpoint, metadata, new_versions)
    
    async def aput_writes(self, config, writes, task_id, task_path=""):
        """Async version of put_writes"""
        self._ensure_loop()
        if self._loop:
            return await self._loop.run_in_executor(
                self._executor,
                self.sqlite_saver.put_writes,
                config, writes, task_id, task_path
            )
        else:
            # Fallback to sync if no event loop
            return self.sqlite_saver.put_writes(config, writes, task_id, task_path)
    
    async def adelete_thread(self, thread_id):
        """Async version of delete_thread"""
        self._ensure_loop()
        if self._loop:
            return await self._loop.run_in_executor(
                self._executor,
                self.sqlite_saver.delete_thread,
                thread_id
            )
        else:
            # Fallback to sync if no event loop
            return self.sqlite_saver.delete_thread(thread_id)
    
    def shutdown(self):
        """Shutdown the thread pool executor"""
        if self._executor:
            self._executor.shutdown(wait=True)
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            self.shutdown()
        except:
            pass


