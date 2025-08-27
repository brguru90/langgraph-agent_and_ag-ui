import asyncio,json
from typing import Annotated, NotRequired,Dict,Optional,Any,cast
from langgraph.prebuilt import InjectedState,InjectedStore, create_react_agent
from typing import TypedDict, Literal,List
from langchain_ollama import ChatOllama
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core import messages
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph,MessagesState, START, END
from fastmcp.client.transports import StdioTransport
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastmcp import Client
from fastmcp.client.sampling import (
    SamplingMessage,
    SamplingParams,
    RequestContext,
)
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
from .coding_agent import CodingAgent
from .research_agent import ResearchAgent
from .plan_executer import PlanExecuter
from langgraph_supervisor.handoff import create_forward_message_tool
from .state import ChatState,SupervisorNode,PlanOutputModal
from .utils import get_aws_modal,max_tokens,AsyncSqliteSaverWrapper,create_handoff_back_node
from langgraph_supervisor import create_supervisor
from langchain_core.language_models import BaseChatModel, LanguageModelLike
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph.state import CompiledStateGraph
from langchain_core.tools import BaseTool

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






memory_tool_names = {'store_messages':"memorizing", 'relevant_memory':"recalling", 'recent_memory':"recalling recent", 'query_memory_id':"querying memory"}



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
    print("\n\n----------memories----------",namespace,formatted,end="\n\n")
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



@tool
async def get_user_original_queries(
    *,
    config: RunnableConfig,
    state: Annotated[ChatState,InjectedState],
) -> str:
    """ Provides the original query made from the user, which is help full for below reason
        1. it will be help full to steer the conversation back to the original topic to achieve better and accurate results.
        2. it will be help full to call when the agent execution is deviated due to context switching or other interruptions.
        3. it will be help full to provide context when the agent is unsure about the user's intent.

        Note: Periodically call this when switching between the contexts
        Don't miss to call get_user_original_queries when switching between the contexts
    """
    human_messages=[msg.content for msg in state["messages"] if isinstance(msg,messages.HumanMessage)]
    return f"""
        Here is the original query made by the user in current session,
        <initial_user_query>
            {human_messages[0]}
        </initial_user_query>
        <all_the_remaining_user_queries>
            {human_messages[1:]}
        </all_the_remaining_user_queries>
    """


@tool
def plan_executor_agent() -> str:
    """Initiate the execution of the plan executor agent.
        This Plan Executor agent will take care of
        1. Creating the plan 
        2. defining the steps with detailed description
        3. and delegating the execution of each plan to respective agents
        4. Concluding the final response
    """
    return ""

class MyAgent:   
    def __init__(self):
        print("__MyAgent__")
        self.base_llm = None
        self.llm = None
        self.client = None
        self.client_session_ctx = None
        self.client_session = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.plan_executer:PlanExecuter=None
        self.max_tool_calls = 6
        self.store:AsyncRedisStore | AsyncSqliteStore| BaseStore = None
        self.system_message="""
            - You are an supervisor agent, responsible for overseeing and managing other agents.
            - Decide the required tool call to execute agent at the beginning and don't forget to execute planned agents and may be you can understanding each agent by executing first it with dummy query or any /help command like query and list all the available tool for planning then start real execution with real query may be you can retry the original user query usually it will be first message or you can get the user original queries back by calling "get_user_original_queries" tool.
            - Avoid re-executing of same agent unless the some additional information is required
            - Your primary role is to delegate tasks to specialized agents based on the user's requests and the context of the conversation.
            - you can use multiple tools and agents to achieve the desired outcome.
            - you can use tools to decide which agent to delegate a task to.
            - You should also keep track of the overall progress and ensure that all agents are working effectively towards the common goal.
            - Important!, Don't summaries the SubAgents responses

    """

    def get_state(self, config:RunnableConfig) -> ChatState:
        """Get the current state of the agent"""
        if not self.graph.get_state(config).values:
            self.graph.update_state(
                config, 
                values={
                    'messages': [],
                    "tool_call_count": 0,
                    "thread_id": config["configurable"]["thread_id"],
                    "messages_history": [],
                    "plan_executed":False,
                },
                as_node="tools"
            )
        return self.graph.get_state(config).values
    
    def set_state(self, config:RunnableConfig, new_state:ChatState,as_node:str=SupervisorNode.TOOLS_VAL):
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


    def should_hide_message(self,message:BaseMessage) -> bool:
        """Check if a message should be hidden based on tool names"""
        if hasattr(message, 'tool_calls') and message.tool_calls:
            # Check if any tool call is for memory-related tools
            return any(tool_call.get('name') in memory_tool_names for tool_call in message.tool_calls)
        elif hasattr(message, 'name') and message.name in memory_tool_names:
            # Tool result message
            return True
        return False

    def mark_tool_messages_as_hidden(self,chat_messages: List[BaseMessage]) -> List[BaseMessage]:
        """Mark tool call and tool result messages as hidden for specific tools"""
        processed_messages = []
        for msg in chat_messages:
            if self.should_hide_message(msg): # todo: also handle `tool_use`
                msg.additional_kwargs = msg.additional_kwargs or {}
                msg.additional_kwargs.update({
                    'hidden_from_chat': True, 
                })
                tool_name= getattr(msg, 'name', None) 
                if tool_name:
                    processed_messages.append(messages.AIMessage(
                        content=memory_tool_names[tool_name],
                        id=msg.id,
                    ))
                    continue
                tool_names= map(lambda call: call.get('name',None), getattr(msg, 'tool_calls', [{}]))
                if tool_names:
                    for tool_name in tool_names:
                        processed_messages.append(messages.AIMessage(
                            content=memory_tool_names[tool_name],
                            id=f"{tool_name}_{msg.id}",
                        ))               
                    continue
            processed_messages.append(msg)
        return processed_messages

    def update_messages_history(self, config: RunnableConfig, existing_history: List[BaseMessage], chat_messages: List[BaseMessage]):
        """
        Update messages_history with all messages except those marked as hidden_from_chat.
        This method is thread-safe using synchronous graph state operations.
        
        Args:
            config: The RunnableConfig for the current thread
            messages: List of messages to potentially add to history
        """

        messages=self.mark_tool_messages_as_hidden(chat_messages)
        
        # Filter messages to exclude those with hidden_from_chat = True
        visible_messages = []
        
        for msg in messages:
            try:
                additional_kwargs = getattr(msg, 'additional_kwargs', msg.additional_kwargs or {})
                if not additional_kwargs.get('hidden_from_chat', False) and len(msg.content) > 0:
                    # Ensure message has an ID
                    if not hasattr(msg, 'id') or msg.id is None:
                        msg.id = str(uuid.uuid4())
                    visible_messages.append(msg)
            except:
                print(f"Error processing message: {traceback.format_exc()}",msg)
                traceback.print_exc()
                traceback.print_stack()
        

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


    def decide_store_messages(self,state:ChatState,config: RunnableConfig, store: BaseStore) -> bool:       
        msg="""The conversation has reached a point where important information should be stored in long-term memory. 

Please analyze the recent conversation and identify:
1. Key information, decisions, or insights that should be remembered
2. The specific context in which this information was discussed
3. Provide memory_id for the conversation if its relevant to update existing memory with the additional information, if available. But make sure you combine both the existing memory and new information to create a meaningful memory and don't loose any information.

Then call the store_messages tool with meaningful content and context parameters. Do NOT call it with empty or generic parameters."""
        analysis_prompt = messages.SystemMessage(
            content=msg,
            id=str(uuid.uuid4()),
        )
        return analysis_prompt
            

    def init_conversation(self, state: ChatState, config: RunnableConfig, *, store: BaseStore): # get_state won't  work properly in initial conv
        """Initialize the conversation state"""
        # Initialize messages if not already set
        print("\n--state--", state)

        # Initialize messages_history if not already set
        if not state.get("messages_history"):
            state["messages_history"] = []

        if not state.get("messages"):
            state["messages"] = []
        
        def llm_studio_fix():
            if os.environ.get("USING_LLM_STUDIO", "false").lower() == "true":
                if state["messages"]:  # Check if messages list is not empty
                    for i in range(len(state["messages"])):
                        msg = state["messages"][i]
                        if isinstance(msg, dict):
                            state["messages"][i] = messages.HumanMessage(content=msg["content"],id=str(uuid.uuid4()))

        llm_studio_fix()

        if len(state["messages_history"])>0:
            new_messages=[]
            last_finish=state["messages_history"][-1].id
            for msg in state["messages"]:
                if msg.id == last_finish:
                    last_finish=None
                if not last_finish:
                    new_messages.append(msg)
            if not last_finish:
                print(f"----- found {len(new_messages)} new messages since last finish")
                state["messages"] = new_messages

        state["messages_history"]=self.update_messages_history(config, state['messages_history'], [state["messages"][-1]])
        
        # Return command to route to LLM node
        return Command(
            update={
                'messages': state["messages"],
                'tool_call_count': 0,
                'thread_id': config["configurable"]["thread_id"],
                "messages_history": state.get("messages_history", []),
                "plan_executed":False,
                "plan":[]
            },
            goto=SupervisorNode.LLM_VAL
        )
    
    async def before_conversation_end(self, state:ChatState,config: RunnableConfig, *, store: BaseStore):
        """Handle any cleanup before conversation ends"""
        store_recom=self.decide_store_messages(state, config, store)        
        msg = await self.llm.bind_tools([store_messages]).ainvoke(get_buffer_string(state["messages"]+[store_recom]))
        tool_res=await self.tool_node.ainvoke({"messages": state["messages"] + [msg]})

        print("\n\n-----before stop-------\n",type(store),store,json.dumps([msg,tool_res],default=str,indent=2),end="\n\n")


        # chat_messages =state["messages"]
        # for msg in chat_messages:
        #     if not hasattr(msg, 'id') or msg.id is None:
        #         msg.id = str(uuid.uuid4())
        # try:
        #     req=[]
        #     req.append(messages.SystemMessage(content=self.system_message,id=str(uuid.uuid4())))
        #     req.extend(chat_messages)
        #     req.append(messages.HumanMessage(content="Combine all the information and Don't summaries the SubAgents responses", id=str(uuid.uuid4())))
        #     _token=count_tokens_approximately(req)
        #     print(f"----- Aprox input token = {_token} -------")
        #     response = get_aws_modal(model_max_tokens=_token+1000,additional_model_request_fields=None,temperature=0.0).invoke(get_buffer_string(req))
        # except Exception as e:
        #     print(f"Error invoking LLM: {e}\n",chat_messages,traceback.print_exc())
        #     response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}",id=str(uuid.uuid4()))
        
        # updated_messages = chat_messages + [response]

        updated_messages=state["messages"]

        for msg in updated_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())

        return Command(
            update={
                "messages":updated_messages
            },
            goto=END
        )

    async def llm_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal[SupervisorNode.ROUTE]]:
        """LLM node - only responsible for calling llm.invoke"""

        chat_messages =state["messages"]
        token_limit_warning=False
        for msg in chat_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())
        try:
            response = await self.llm.ainvoke([messages.SystemMessage(content=self.system_message,id=str(uuid.uuid4()))]+chat_messages)
        except Exception as e:
            print(f"Error invoking LLM: {e}\n",chat_messages,traceback.print_exc())
            response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}",id=str(uuid.uuid4()))
        
        updated_messages = chat_messages + [response]
        if token_limit_warning:
            updated_messages = chat_messages[0:1]+list(filter(lambda msg: msg.type not in ["human","ai"],chat_messages[1:])) + [response]

        # Always go to router after LLM response
        return Command(
            update={
                'messages': updated_messages,
                'tool_call_count': state['tool_call_count'],
                'thread_id': state['thread_id'],
                'messages_history': self.update_messages_history(config, state['messages_history'], updated_messages),
            },
            goto=SupervisorNode.ROUTE_VAL
        )


    async def tools_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal[SupervisorNode.ROUTE]]:
        """Tools node - only responsible for calling tool_node.ainvoke"""    
        ai_msg:messages.AIMessage=state["messages"][-1]
        print(
            "---tool_calls: ", 
            list(map(lambda x: f"{x['name']}({x['args']})", ai_msg.tool_calls)),
            ", count=",state["tool_call_count"],
            "thread_id",state['thread_id'],
            "\n\n"
        )
        messages.SystemMessage(content=self.system_message,id=str(uuid.uuid4()))
        temp_state={
            **state,
            "messages": [messages.SystemMessage(content=self.system_message,id=str(uuid.uuid4()))]+state["messages"]
        }
        result = await self.tool_node.ainvoke(temp_state)

        

        # Combine all messages for the updated state
        if not isinstance(result,List):
            result=[result]
        tool_messages=[]
        for tool_message in result:
            if isinstance(tool_message,Command):
                tool_messages.extend(tool_message.update.get("messages",[]))
            elif isinstance(tool_message,Dict) and isinstance(tool_message.get("messages",{}),List):
                tool_messages.extend(tool_message.get("messages",[]))
            else:
                tool_messages.append(tool_message)

        all_updated_messages = state['messages'] + tool_messages

        # Update messages_history with all new messages (filtering will be done in update_messages_history)
       

        # print("---tools_node: ",result,"\n\n")
        # Always go to router after tools execution
        return Command(
            update={
                'messages': all_updated_messages,
                'tool_call_count': state['tool_call_count']+1,
                'messages_history': self.update_messages_history(config,state["messages_history"], all_updated_messages)
            },
            goto=SupervisorNode.ROUTE_VAL
        )

    def route_node(self, state:ChatState,config: RunnableConfig, *, store: BaseStore) -> Command[Literal[SupervisorNode.TOOLS, SupervisorNode.LLM,SupervisorNode.END_CONV,SupervisorNode.PLAN_EXECUTER]]:
        """Route node - handles all routing logic using Command pattern"""
        # !!! Command pattern allows us to define custom logic and state can be update during routing

        last_message = state['messages'][-1]


        print(f"--route_node: message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}")

        print(f"\n--route_node(last_message):",json.dumps(last_message,default=str,indent=2),end="\n\n")

        def check_call_to_agent():
            print("\n----- check_call_to_agent ------\n")
            if not isinstance(last_message,messages.AIMessage):
                return False
            is_agent_call = last_message.tool_calls[0]['name']=="plan_executor_agent"
            if not is_agent_call:
                return False
            
            tool_message = messages.ToolMessage(
                content=f"Successfully transferred to Agent `plan_executor_agent`",
                name=last_message.tool_calls[0]['name'],
                tool_call_id=last_message.tool_calls[0]["id"]
            )

            print("\n------check_plan_executer------\n")
            return Command(
                update={
                    'messages':  state['messages'] + [tool_message]
                },
                goto=SupervisorNode.PLAN_EXECUTER_VAL
            )  
        

        # Check if we've exceeded tool call limit
        if state['tool_call_count'] >= self.max_tool_calls:
            print(f">>> Interrupting for human input... on thread_id={state['thread_id']}")
            user_answer = interrupt("Tool call exceeded limit, please reply:\n 1. 'yes' to continue\n 2. 'no' to exit\n 3. any other input will be treated as feedback prompt")
            print(f"User answer: '{user_answer}'",end="\n\n")
            
            if user_answer == 'no':
                # Explicitly end the graph
                return Command(
                    update={},  # No state update needed
                    goto=SupervisorNode.END_CONV_VAL  # End the conversation
                )
            elif user_answer == 'yes':
                # Reset tool count and continue with tools if LLM wants to use them
                if getattr(last_message, 'tool_calls', None):
                    forward_to_agent=check_call_to_agent()
                    if forward_to_agent:
                        return forward_to_agent
                    return Command(
                        update={'tool_call_count': 0},
                        goto=SupervisorNode.TOOLS_VAL
                    )
                else:
                    return Command(
                        update={'tool_call_count': 0},
                        goto=SupervisorNode.LLM_VAL
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
                    goto=SupervisorNode.LLM_VAL
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
                goto=SupervisorNode.TOOLS_VAL
            )
        elif last_message.type == 'tool':
            # Tool message completed, let LLM process the results
            return Command(
                update={},
                goto=SupervisorNode.LLM_VAL
            )
        else:
            # LLM finished without tool calls - end execution
           
            return Command(
                update={},
                goto=SupervisorNode.END_CONV_VAL
            )   

    def on_start(self,run:Run, config:RunnableConfig):
        print("\n\ninitial state:", json.dumps(self.get_state(config),default=str))
        print("\nconfig:", json.dumps(config,default=str))
        self.get_state(config)


    async def init(self):
        """Initialize the agent with MCP tools and LLM"""

        # Initialize LLMs
        self.base_llm = get_aws_modal()
        

        self.tools = []        
        self.tools.append(get_user_original_queries)
        self.tools.append(plan_executor_agent)
        # self.tools.append(store_messages) 
        self.tools.append(relevant_memory) 
        self.tools.append(recent_memory)
        self.tools.append(query_memory_id)


        self.llm = self.base_llm.bind_tools(self.tools)            
        self.tool_node = ToolNode(self.tools)
      

        self.plan_executer=PlanExecuter()
        await self.plan_executer.init()

        builder = StateGraph(ChatState)
        builder.add_node(SupervisorNode.START_CONV_VAL, self.init_conversation)
        builder.add_node(SupervisorNode.LLM_VAL, self.llm_node)
        builder.add_node(SupervisorNode.TOOLS_VAL, self.tools_node)
        builder.add_node(SupervisorNode.ROUTE_VAL, self.route_node)
        builder.add_node(SupervisorNode.PLAN_EXECUTER_VAL, create_handoff_back_node(self.plan_executer.graph,recursion_limit=100))
        builder.add_node(SupervisorNode.END_CONV_VAL, self.before_conversation_end)

        builder.set_entry_point(SupervisorNode.START_CONV_VAL)
        builder.add_edge(SupervisorNode.START_CONV_VAL, SupervisorNode.LLM_VAL)
        builder.add_edge(SupervisorNode.PLAN_EXECUTER_VAL, SupervisorNode.ROUTE_VAL)
        builder.add_edge(SupervisorNode.END_CONV_VAL, END)
        # builder.add_conditional_edges()
            
        
        # memory = InMemorySaver()
        # self._base_graph = builder.compile(checkpointer=memory, debug=False, name="fds_agent")
        os.makedirs("data", exist_ok=True)
        sql_file= "data/graph_data.sqlite"
        if os.environ.get("USING_LLM_STUDIO", "false").lower() == "true":
            sql_file= "data/graph_studio_data.sqlite"

        self.sql_lite_conn = sqlite3.connect(sql_file,check_same_thread=False)
        sqlite_saver = SqliteSaver(self.sql_lite_conn)
        self.checkpointer = AsyncSqliteSaverWrapper(sqlite_saver, max_workers=4)
        
        # Initialize SQLite store for long-term memory
        # store_sql_file = sql_file.replace("graph_data.sqlite", "store_data.sqlite").replace("graph_studio_data.sqlite", "store_studio_data.sqlite")
        # self.store_conn = await aiosqlite.connect(store_sql_file, check_same_thread=False)
        # self.store = AsyncSqliteStore(self.store_conn)
        # await self.store.setup()

        # index_config:IndexConfig = IndexConfig(embed=get_aws_embed_model(),dims=1536) # vector search not working
        # self.redis_ctx= AsyncRedisStore.from_conn_string("redis://localhost:6379",index=index_config)
        self.redis_ctx= AsyncRedisStore.from_conn_string("redis://localhost:6379")
        self.store =await self.redis_ctx.__aenter__()
        await self.store.setup()
        await self.store.aput(("test"),"test_key",{"value": "dummy"})

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

        if self.plan_executer:
            self.plan_executer.close()
        
        # Suppress warnings during cleanup
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            if self.sql_lite_conn:
                try:
                    print("Closing SqlLite Conn...")
                    self.sql_lite_conn.close()
                except Exception as e:
                    print(f"Error closing SQLite connection: {e}")
            # if self.redis_ctx:
            #     self.redis_ctx.__aexit__(None, None, None)

            # if self.store_conn:
            #     try:
            #         print("Closing Store SqlLite Conn...")
            #         self.store_conn.close()
            #     except Exception as e:
            #         print(f"Error closing store SQLite connection: {e}")
            
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

