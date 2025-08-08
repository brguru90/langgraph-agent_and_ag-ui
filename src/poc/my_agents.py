import asyncio,json
from typing import Annotated, NotRequired,Dict,Optional,Any
from langgraph.prebuilt import InjectedState,InjectedStore, create_react_agent
from typing import TypedDict, Literal,List
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool
from langchain_core import messages
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from fastmcp.client.transports import StdioTransport
from fastmcp import Client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from langchain_core.runnables.config import RunnableConfig
from langchain_core.runnables.base import RunnableBindingBase
from langchain_core.tracers.schemas import Run
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately
from langmem.short_term import SummarizationNode,summarize_messages,RunningSummary
from langgraph.func import entrypoint, task
import uuid
from langgraph.checkpoint.base import Checkpoint, BaseCheckpointSaver
from langchain_core.prompts.chat import ChatPromptTemplate, ChatPromptValue
from langchain_core.messages.utils import get_buffer_string
from langgraph.store.base import BaseStore,SearchItem
from langgraph.store.sqlite import SqliteStore
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import traceback


import warnings
warnings.filterwarnings(
    "ignore",
    message=r"datetime\.datetime\.utcnow",
    category=DeprecationWarning
)
warnings.filterwarnings(
    "ignore", 
    message=r"`config_type` is deprecated",
    category=UserWarning
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module="langgraph"
)
warnings.filterwarnings(
    "ignore",
    message=r"The `copy` method is deprecated; use `model_copy` instead",
    category=DeprecationWarning
)
warnings.filterwarnings(
    "ignore", 
    message=r"The `schema` method is deprecated; use `model_json_schema` instead",
    category=DeprecationWarning
)

# claude-sonnet-4 -> supports upto 200k tokens

max_tokens = 65536
END_CONV="end_conv"

def get_aws_modal():
    return ChatBedrockConverse(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", 
        region_name="us-west-2", 
        credentials_profile_name="llm-sandbox",
        temperature=0.0,
        max_tokens=max_tokens,         
    )

INITIAL_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("placeholder", "{messages}"),
        ("user", "Create a summary of the conversation and also summaries the user query at the beginning of summary for above:"),
    ]
)


EXISTING_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("placeholder", "{messages}"),
        (
            "user",
            "This is summary of the conversation so far: {existing_summary}\n\n"
            "Extend this summary by taking into account the new messages and also summaries the user query at the beginning of summary above:",
        ),
    ]
)

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


class ChatState(TypedDict):
    messages: List[BaseMessage]
    tool_call_count: int
    thread_id: str 
    summary:RunningSummary | None
    last_store_id: str | None
    updated_log_term_memory: bool
    messages_history: List[BaseMessage]




async def query_memories(
        query: str, 
        record_limit: Optional[int] = 10,
        record_offset: Optional[int] = 0,
        *,
        config: RunnableConfig, 
        store: BaseStore,
        get_recent: bool
    ) -> str:
    namespace = (
        "long_term_memories",
        config["configurable"]["user_id"],
        config["configurable"]["thread_id"],
    )
    group_id=config["configurable"].get("group_id",None)
    if group_id:
        namespace=namespace+(group_id,)

    if config["configurable"].get("context_scope", None) == "thread":
        namespace = (
            "long_term_memories",
            config["configurable"]["user_id"],
            config["configurable"]["thread_id"],
        )
    elif config["configurable"].get("context_scope", None) == "user":
        namespace = (
            "long_term_memories",
            config["configurable"]["user_id"],
        )
    if get_recent:
        query+="Today is "+datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    #     namespace=namespace+(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),)
    # print("\n--------- namespace -------------",namespace)
    memories = await store.asearch(namespace, query=query, limit=record_limit, offset=record_offset)
    formatted = "\n".join(f"[{mem.key}]: {mem.value} (similarity: {mem.score})" for mem in memories)
    if formatted:
        return f"""
<memories>
record_limit: {record_limit}
record_offset: {record_offset}

Here are the relevant memories found for query: `{query}`:
{formatted}
</memories>"""
    else:
        return f"""No relevant memories found for query: `{query}`"""
        


@tool(description="Store important information from the conversation in long-term memory. ALWAYS analyze the conversation to extract meaningful content and context before calling this tool. Do NOT call with empty parameters and don't call it if enough information is not available.")
async def store_messages(
    content: str,
    context: str,
    user_queries: List[str],
    *,
    memory_id: Optional[str] = None,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Stores important information from the conversation in long-term memory.

    IMPORTANT: Before calling this tool, you MUST:
    1. Analyze the recent conversation messages
    2. Extract key user queries, information, decisions, or insights
    3. Provide meaningful content and context parameters
    4. Do NOT call with empty or generic parameters

    If a memory conflicts with an existing one, then just UPDATE the
    existing one by passing in memory_id - don't create two memories
    that are the same. If the user corrects a memory, UPDATE it.

    Args:
        content: The main content of the memory. For example:
            "User expressed interest in learning about French."
        context: Additional context for the memory. For example:
            "This was mentioned while discussing career options in Europe."
        user_query: combine all the user queries for the conversation which you want to store in the memory.
        memory_id: ONLY PROVIDE IF UPDATING AN EXISTING MEMORY.
        The memory to overwrite.
    """
    # Validate parameters
    if not content or content.strip() == "" or len(content.strip()) < 10:
        return "Error: Content parameter must be meaningful and at least 10 characters long. Please analyze the conversation and provide specific information to store."
    
    if not context or context.strip() == "" or len(context.strip()) < 10:
        return "Error: Context parameter must be meaningful and at least 10 characters long. Please provide specific situational context for this memory."
    
    # Check for generic/placeholder content
    generic_phrases = ["conversation summary", "general conversation", "user input", "discussion"]
    if any(phrase in content.lower() for phrase in generic_phrases):
        return f"Error: Content appears to be generic ('{content}'). Please provide specific, meaningful information from the conversation."
    
    key = memory_id or str(uuid.uuid4())
    group_id=config["configurable"].get("group_id",None)
    namespace = (
        "long_term_memories",
        config["configurable"]["user_id"],
        config["configurable"]["thread_id"],
    )
    if group_id:
        namespace=namespace+(group_id,)
    await store.aput(
        namespace=namespace,
        key=key,
        value={"content": content, "context": context,"user_queries":user_queries,"last_updated":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
    return f"Summarized with {key}"


@tool
async def query_memory_id(
    context: str,
    record_limit: Optional[int] = 10,
    record_offset: Optional[int] = 0,
    *,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Query memory id by its context.

    Args:
        context: Provide the relevant context to get corresponding memory id/key
    """
    # namespace = (
    #     "long_term_memories",
    # )
    # context=store.aget(namespace=namespace, key=memory_id)
    return await query_memories(context,record_limit,record_offset, config=config, store=store, get_recent=False)




@tool
async def relevant_memory(
    context: str,
    record_limit: Optional[int] =10,
    record_offset: Optional[int] = 0,
    *,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Provide Relevant memories from long term memory.

    Args:
        context: last user query or relevant memory for the current context.
        record_limit: Maximum number of records to return. Defaults to 10.
        record_offset: Offset for pagination. Defaults to 0.
    """
    return await query_memories(context,record_limit,record_offset, config=config, store=store, get_recent=False)
        
@tool
async def recent_memory(
    context: str,
    record_limit: Optional[int] =10,
    record_offset: Optional[int] = 0,
    *,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Provide recent memories from long term memory.

    Args:
        context: last user query or relevant memory for the current context.
        record_limit: Maximum number of records to return. Defaults to 10.
        record_offset: Offset for pagination. Defaults to 0.
    """
    return await query_memories(context,record_limit,record_offset, config=config, store=store, get_recent=True)
 

class MyAgent:   
    def __init__(self):
        print("__MyAgent__")
        self.llm = None
        self.client = None
        self.client_session_ctx = None
        self.client_session = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.max_tool_calls = 5
        self.store = None

    def get_state(self, config:RunnableConfig) -> ChatState:
        """Get the current state of the agent"""
        if not self.graph.get_state(config).values:
            print("\n\n~~~~~~~~~~~~ Init ~~~~~~~~~~~~~~\n\n")
            self.graph.update_state(
                config, 
                values={
                    'messages': [],
                    "tool_call_count": 0,
                    "thread_id": config["configurable"]["thread_id"],
                    "summary": None,
                    "messages_history": []
                },
                as_node="tools"
            )
        return self.graph.get_state(config).values
    
    def set_state(self, config:RunnableConfig, new_state:ChatState,as_node:str='tools'):
        """Set the current state of the agent"""
        self.graph.update_state(config, values=new_state,as_node=as_node)

        
    def filter_visible_messages(self,messages: List[BaseMessage]) -> List[BaseMessage]:
        """Filter out messages marked as hidden from chat display"""
        visible_messages = []
        for msg in messages:
            # Check if message should be hidden
            additional_kwargs = getattr(msg, 'additional_kwargs', {})
            if not additional_kwargs.get('hidden_from_chat', False):
                visible_messages.append(msg)
        return visible_messages


    def mark_tool_messages_as_hidden(self,messages: List[BaseMessage], tool_names: set) -> List[BaseMessage]:
        """Mark tool call and tool result messages as hidden for specific tools"""
        processed_messages = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls: # todo: also handle `tool_use`
                # Check if any tool call is for memory-related tools
                should_hide = any(tool_call.get('name') in tool_names for tool_call in msg.tool_calls)
                if should_hide:
                    msg.additional_kwargs = msg.additional_kwargs or {}
                    msg.additional_kwargs.update({
                        'hidden_from_chat': True, 
                        'message_type': 'tool_call',
                        'hidden_tools': [tc.get('name') for tc in msg.tool_calls if tc.get('name') in tool_names]
                    })
            elif hasattr(msg, 'name') and msg.name in tool_names:
                # Tool result message
                msg.additional_kwargs = msg.additional_kwargs or {}
                msg.additional_kwargs.update({
                    'hidden_from_chat': True, 
                    'message_type': 'tool_result',
                    'tool_name': msg.name
                })
            processed_messages.append(msg)
        return processed_messages

    def update_messages_history(self, config: RunnableConfig, existing_history: List[BaseMessage], messages: List[BaseMessage]):
        """
        Update messages_history with all messages except those marked as hidden_from_chat.
        This method is thread-safe using synchronous graph state operations.
        
        Args:
            config: The RunnableConfig for the current thread
            messages: List of messages to potentially add to history
        """
        
        # Filter messages to exclude those with hidden_from_chat = True
        visible_messages = []
        
        for msg in messages:
            additional_kwargs = getattr(msg, 'additional_kwargs', msg.additional_kwargs or {})
            if not additional_kwargs.get('hidden_from_chat', False) and len(msg.content) > 0:
                # Ensure message has an ID
                if not hasattr(msg, 'id') or msg.id is None:
                    msg.id = str(uuid.uuid4())
                visible_messages.append(msg)
        

        # Only update if there are new visible messages
        if visible_messages:
            # Create a set of existing message IDs to avoid duplicates
            existing_ids = {msg.id for msg in existing_history if hasattr(msg, 'id') and msg.id}
            
            # Add only new messages (not already in history)
            new_messages = [msg for msg in visible_messages if msg.id not in existing_ids]
            
            if new_messages:
                updated_history = existing_history + new_messages
                
                # # Update the state synchronously (thread-safe)
                # self.graph.update_state(
                #     config, 
                #     {"messages_history": updated_history},
                #     as_node="tools"  # Use as_node to control the update origin
                # )
                
                print(f"------ Added {len(new_messages)} new messages to history. Total history: {len(updated_history)} messages")
                return updated_history

        return existing_history


    def decide_store_messages(self,state:ChatState,config: RunnableConfig, store: BaseStore,override_decision:bool=False) -> bool: 
        # additional_kwargs       
        chat_messages=state["messages"]
        if override_decision or count_tokens_approximately(chat_messages) > max_tokens:
            # Instead of calling with empty args, let the LLM analyze and decide
            msg="""The conversation has reached a point where important information should be stored in long-term memory. 

Please analyze the recent conversation and identify:
1. Key information, decisions, or insights that should be remembered
2. The specific context in which this information was discussed
3. Provide memory_id for the conversation if its relevant to update existing memory with the additional information, if available. But make sure you combine both the existing memory and new information to create a meaningful memory and don't loose any information.

Then call the store_messages tool with meaningful content and context parameters. Do NOT call it with empty or generic parameters."""
            analysis_prompt = messages.AIMessage(
                content=[{
                    "type": "text",
                    "text": msg,
                    "index": 0
                }],
                id=str(uuid.uuid4()),
                additional_kwargs={"hidden_from_chat": True, "message_type": "memory_trigger"},
                usage_metadata={
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "input_token_details": {
                        "cache_creation": 0,
                        "cache_read": 0
                    }
                }
            )
            state["messages"].append(analysis_prompt)
            return True
        return False
            

    def init_conversation(self, state: ChatState, config: RunnableConfig, *, store: BaseStore): # get_state won't  work properly in initial conv
        """Initialize the conversation state"""
        # Initialize messages if not already set
        print("\n--state--", state)

        if not state.get("messages"):
            state["messages"] = []
        
        # Initialize messages_history if not already set
        if not state.get("messages_history"):
            state["messages_history"] = []
            
        def llm_studio_fix():
            if os.environ.get("USING_LLM_STUDIO", "false").lower() == "true":
                if state["messages"]:  # Check if messages list is not empty
                    last = state["messages"][-1]
                    if isinstance(last, dict):
                        state["messages"][-1] = messages.HumanMessage(content=last["content"],id=str(uuid.uuid4()))

        llm_studio_fix()  

        state["messages_history"]=self.update_messages_history(config, state['messages_history'], [state["messages"][-1]])

        # Return command to route to LLM node
        return Command(
            update={
                'messages': state["messages"],
                'tool_call_count': 0,
                'thread_id': config["configurable"]["thread_id"],
                "updated_log_term_memory":False,
                "summary": state.get("summary",None),
                "messages_history": state.get("messages_history", [])
            },
            goto="llm"
        )
    
    async def before_conversation_end(self, state:ChatState,config: RunnableConfig, *, store: BaseStore):
        """Handle any cleanup before conversation ends"""

        if not state.get("updated_log_term_memory",False) and self.decide_store_messages(state, config, store,True):
            state["updated_log_term_memory"] = True
            return Command(
                update=state,
                goto="llm"
            )

        if os.environ.get("USING_LLM_STUDIO", "true").lower() == "true":
            self.sql_lite_conn.commit() 
            self.store_conn.commit()  
        
        # Return command to route to END node
        return Command(
            update={},
            goto=END
        )

    async def llm_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """LLM node - only responsible for calling llm.invoke"""

        for msg in state["messages"]:
            msg.id = msg.id or str(uuid.uuid4()) # Ensure all messages have IDs
        chat_messages= state["messages"]
        if not state.get("summary") or len(state.get("summary").summarized_message_ids.intersection(set([msg.id for msg in chat_messages]))) == 0:
            chat_messages = summarize_messages(
                messages=chat_messages,
                running_summary=state["summary"],
                model=self.llm,
                max_tokens=max_tokens/1.33,
                max_tokens_before_summary=max_tokens/3.33,
                max_summary_tokens=max_tokens/3.34,
                token_counter=count_tokens_approximately,
                initial_summary_prompt=INITIAL_SUMMARY_PROMPT,
                existing_summary_prompt=EXISTING_SUMMARY_PROMPT
            ).messages # if context exceeds its summarize initial messages and slices it off
        running_summary_msg=""
        summarized_message_ids={}
        if chat_messages and isinstance(chat_messages[0], messages.SystemMessage): # first message is system message means its summary
            if self.decide_store_messages(state, config, store):
                chat_messages.append(state["messages"][-1])
            running_summary_msg = get_buffer_string([chat_messages[0]])
            summarized_message_ids = set([msg.id for msg in chat_messages])
            chat_messages[0]=messages.AIMessage(content=running_summary_msg,id=chat_messages[0].id) # ag-ui don't want first message to be system message
        for msg in chat_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())
        try:
            response = self.llm.invoke(chat_messages)
        except Exception as e:
            print(f"Error invoking LLM: {e}\n",chat_messages,traceback.print_exc())
            response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}",id=str(uuid.uuid4()))
        
        # Update messages_history with the new LLM response and chat messages
        updated_messages = chat_messages + [response]
        
        
        # Always go to router after LLM response
        return Command(
            update={
                'messages': updated_messages,
                'tool_call_count': state['tool_call_count'],
                'thread_id': state['thread_id'],
                'messages_history': self.update_messages_history(config, state['messages_history'], updated_messages),
                "summary": RunningSummary(summary=running_summary_msg,summarized_message_ids=summarized_message_ids,last_summarized_message_id=None) if running_summary_msg else state["summary"]
            },
            goto="route"
        )

    async def tools_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """Tools node - only responsible for calling tool_node.ainvoke"""    
        ai_msg:messages.AIMessage=state["messages"][-1]
        print(
            "---tool_calls: ", 
            list(map(lambda x: f"{x['name']}({x['args']})", ai_msg.tool_calls)),
            ", count=",state["tool_call_count"],
            "thread_id",state['thread_id'],
            "\n\n"
        )
        result = await self.tool_node.ainvoke(state)

        # Mark memory-related tool messages as hidden
        memory_tool_names = {'store_messages', 'relevant_memory', 'recent_memory', 'query_memory_id'}
        result['messages'] = self.mark_tool_messages_as_hidden(result['messages'], memory_tool_names)
        
        # Also mark the AI message that made the tool calls as hidden if it called memory tools
        updated_state_messages = self.mark_tool_messages_as_hidden(state['messages'], memory_tool_names)

        # Combine all messages for the updated state
        all_updated_messages = updated_state_messages + result['messages']
        
        # Update messages_history with all new messages (filtering will be done in update_messages_history)
       

        # print("---tools_node: ",result,"\n\n")
        # Always go to router after tools execution
        return Command(
            update={
                'messages': all_updated_messages,
                'tool_call_count': state['tool_call_count']+1,
                'messages_history': self.update_messages_history(config,state["messages_history"], all_updated_messages)
            },
            goto="route"
        )

    def route_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal["tools", "llm","end_conv"]]:
        """Route node - handles all routing logic using Command pattern"""
        # !!! Command pattern allows us to define custom logic and state can be update during routing
        
        # Get the last message to determine routing
        last_message = state['messages'][-1]
        
        print(f"--route_node: message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}")
        
        # Check if we've exceeded tool call limit
        if state['tool_call_count'] >= self.max_tool_calls:
            print(f">>> Interrupting for human input... on thread_id={state['thread_id']}")
            user_answer = interrupt("Tool call exceeded limit, please reply:\n 1. 'yes' to continue\n 2. 'no' to exit\n 3. any other input will be treated as feedback prompt")
            print(f"User answer: '{user_answer}'",end="\n\n")
            
            if user_answer == 'no':
                # Explicitly end the graph
                return Command(
                    update={},  # No state update needed
                    goto=END_CONV  # End the conversation
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
                
                # Update messages_history with the new human message
                
                
                # Reset tool count and restart LLM processing
                return Command(
                    update={
                        'messages': updated_messages, 
                        'tool_call_count': 0,
                        'messages_history': self.update_messages_history(config,state['messages_history'], [new_human_message])
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
                goto=END_CONV
            )     

    def on_start(self, run:Run, config:RunnableConfig):
        print("\n\ninitial state:", json.dumps(self.get_state(config),default=str))
        self.get_state(config)

    async def init(self):
        """Initialize the agent with MCP tools and LLM"""

        # Initialize LLMs
        self.llm = get_aws_modal()

        self.client = MultiServerMCPClient(
            {
                "fds": {
                    "command": "uvx",
                    "args": ["fds-mcp-server"],
                    "transport": "stdio",
                }
            }
        )

        # Store the context manager and enter it properly
        self.client_session_ctx = self.client.session("fds")
        self.client_session = await self.client_session_ctx.__aenter__()
        
        # print("Available tools:", await self.client_session.list_tools())
        self.tools = await load_mcp_tools(self.client_session)
        
        if self.tools:
            print(f"Successfully loaded {len(self.tools)} MCP tools")
        else:
            print("No tools loaded, returning...")
            return
        
        self.tools.append(store_messages) 
        self.tools.append(relevant_memory) 
        self.tools.append(recent_memory)
        self.tools.append(query_memory_id) 

        self.llm = self.llm.bind_tools(self.tools)            
        self.tool_node = ToolNode(self.tools)
        
        builder = StateGraph(ChatState)
        builder.add_node('start_conv', self.init_conversation)
        builder.add_node('llm', self.llm_node)
        builder.add_node('tools', self.tools_node)
        builder.add_node('route', self.route_node)
        builder.add_node('end_conv', self.before_conversation_end)

        # builder.add_edge(START, 'start_conv')
        builder.set_entry_point('start_conv')
        builder.add_edge('start_conv', 'llm')
        builder.add_edge('end_conv', END)
            
        
        # memory = InMemorySaver()
        # wrapped = SummarizingSaver(memory, memory, threshold=5000)        
        # self._base_graph = builder.compile(checkpointer=wrapped, debug=False, name="fds_agent")
        os.makedirs("data", exist_ok=True)
        sql_file= "data/graph_data.sqlite"
        if os.environ.get("USING_LLM_STUDIO", "false").lower() == "true":
            sql_file= "data/graph_studio_data.sqlite"

        self.sql_lite_conn = sqlite3.connect(sql_file,check_same_thread=False)
        sqlite_saver = SqliteSaver(self.sql_lite_conn)
        self.checkpointer = AsyncSqliteSaverWrapper(sqlite_saver, max_workers=4)
        
        # Initialize SQLite store for long-term memory
        store_sql_file = sql_file.replace("graph_data.sqlite", "store_data.sqlite").replace("graph_studio_data.sqlite", "store_studio_data.sqlite")
        self.store_conn = sqlite3.connect(store_sql_file, check_same_thread=False)
        self.store = SqliteStore(self.store_conn)
        
        self._base_graph = builder.compile(checkpointer=self.checkpointer, store=self.store, debug=False, name="fds_agent")

        # Create the graph with listeners for actual execution
        self.graph = self._base_graph.with_listeners(
            on_start=self.on_start,
            on_end=lambda run, config: print("-------------------------- Agent run ended --------------------------")
        )     

        self.graph.get_graph().print_ascii()
        
        # async for event in self.graph.astream(self.state, stream_mode=["updates","messages"]):
        #     pass

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

            if self.sql_lite_conn:
                try:
                    print("Closing SqlLite Conn...")
                    self.sql_lite_conn.close()
                except Exception as e:
                    print(f"Error closing SQLite connection: {e}")
            
            if self.store_conn:
                try:
                    print("Closing Store SqlLite Conn...")
                    self.store_conn.close()
                except Exception as e:
                    print(f"Error closing store SQLite connection: {e}")
            
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
                try:
                    print("Cleaning up main client...")
                    # MultiServerMCPClient doesn't have __aexit__, just clear the reference
                    self.client = None
                    print("Main client cleaned up successfully")
                except Exception as e:
                    print(f"Error cleaning up main client: {e}")
                    self.client = None
        
        print("Agent cleanup completed")
    
    def get_base_graph(self):
        """Return the base compiled graph without listeners for LangGraph Studio API access"""
        return self._base_graph

