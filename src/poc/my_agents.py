import asyncio,json
from typing import Annotated, NotRequired
from langgraph.prebuilt import InjectedState, create_react_agent
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
import os

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

class SummarizingSaver(BaseCheckpointSaver):
    def __init__(self, inner: BaseCheckpointSaver, summarizer, threshold: int, key="messages"):
        self.inner = inner
        self.summarizer = summarizer
        self.threshold = threshold
        self.channel = key

    # Delegate config_specs to inner saver
    @property
    def config_specs(self):
        return self.inner.config_specs

    # Sync methods - delegate to inner saver
    def get_tuple(self, config):
        return self.inner.get_tuple(config)

    def list(self, config, *, filter=None, before=None, limit=None):
        return self.inner.list(config, filter=filter, before=before, limit=limit)

    def put(self, config, checkpoint: Checkpoint, metadata, new_versions):
        values:ChatState = checkpoint["channel_values"]
        chat_messages:List[BaseMessage] = values.get(self.channel, [])
        llm = get_aws_modal()
        if len(chat_messages) > 0:
            # Ensure all messages have IDs before summarization
            for msg in chat_messages:
                if not hasattr(msg, 'id') or msg.id is None:
                    msg.id = str(uuid.uuid4())
            if len(chat_messages) == 1 and isinstance(chat_messages[0], messages.HumanMessage) and values.get("summary"):
                chat_messages.insert(0,messages.AIMessage(content=values.get("summary").summary, id=str(uuid.uuid4())))  # restore summary if message were lost in new checkpoint
            if not values.get("summary") or len(values.get("summary").summarized_message_ids.intersection(set([msg.id for msg in chat_messages]))) == 0:
                result = summarize_messages(
                    messages=chat_messages,
                    running_summary=values.get("summary"),
                    model=llm,
                    max_tokens=max_tokens/1.33,
                    max_tokens_before_summary=max_tokens/3.33,
                    max_summary_tokens=max_tokens/3.34,
                    token_counter=count_tokens_approximately,
                    initial_summary_prompt=INITIAL_SUMMARY_PROMPT,
                    existing_summary_prompt=EXISTING_SUMMARY_PROMPT
                )                
                for msg in result.messages:
                    if not hasattr(msg, 'id') or msg.id is None:
                        msg.id = str(uuid.uuid4())
                values[self.channel] = result.messages
                if result.messages and isinstance(result.messages[0], messages.SystemMessage):
                    running_summary_msg = get_buffer_string([result.messages[0]])
                    summarized_message_ids = set([msg.id for msg in result.messages])
                    result.messages[0]=messages.AIMessage(content=running_summary_msg,id=result.messages[0].id) # ag-ui don't want first message to be system message
                elif chat_messages:
                    running_summary_msg = get_buffer_string(chat_messages)
                    summarized_message_ids = {uuid.uuid4()}
                values["summary"] = RunningSummary(summary=running_summary_msg, summarized_message_ids=summarized_message_ids, last_summarized_message_id=None) 
        return self.inner.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config, writes, task_id, task_path=""):
        return self.inner.put_writes(config, writes, task_id, task_path)

    def delete_thread(self, thread_id):
        return self.inner.delete_thread(thread_id)

    # Async methods - delegate to inner saver
    async def aget_tuple(self, config):
        return await self.inner.aget_tuple(config)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        async for item in self.inner.alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(self, config, checkpoint: Checkpoint, metadata, new_versions):
        values:ChatState = checkpoint["channel_values"]
        chat_messages:List[BaseMessage] = values.get(self.channel, [])
        llm = get_aws_modal()
        if len(chat_messages) > 0:
            # Ensure all messages have IDs before summarization
            for msg in chat_messages:
                if not hasattr(msg, 'id') or msg.id is None:
                    msg.id = str(uuid.uuid4())
            if len(chat_messages) == 1 and isinstance(chat_messages[0], messages.HumanMessage) and values.get("summary"):
                chat_messages.insert(0,messages.AIMessage(content=values.get("summary").summary, id=str(uuid.uuid4()))) # restore summary if message were lost in new checkpoint
            
            if not values.get("summary") or len(values.get("summary").summarized_message_ids.intersection(set([msg.id for msg in chat_messages]))) == 0:
                result = summarize_messages(
                    messages=chat_messages,
                    running_summary=values.get("summary"),
                    model=llm,
                    max_tokens=max_tokens/1.33,
                    max_tokens_before_summary=max_tokens/3.33,
                    max_summary_tokens=max_tokens/3.34,
                    token_counter=count_tokens_approximately,
                    initial_summary_prompt=INITIAL_SUMMARY_PROMPT,
                    existing_summary_prompt=EXISTING_SUMMARY_PROMPT
                )                
                for msg in result.messages:
                    if not hasattr(msg, 'id') or msg.id is None:
                        msg.id = str(uuid.uuid4())
                values[self.channel] = result.messages
                if result.messages and isinstance(result.messages[0], messages.SystemMessage):
                    running_summary_msg = get_buffer_string([result.messages[0]])
                    summarized_message_ids = set([msg.id for msg in result.messages])                    
                    result.messages[0]=messages.AIMessage(content=running_summary_msg,id=result.messages[0].id) # ag-ui don't want first message to be system message
                elif chat_messages:
                    running_summary_msg = get_buffer_string(chat_messages)
                    summarized_message_ids = {uuid.uuid4()}
                values["summary"] = RunningSummary(summary=running_summary_msg, summarized_message_ids=summarized_message_ids, last_summarized_message_id=None) 
        return await self.inner.aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        return await self.inner.aput_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id):
        return await self.inner.adelete_thread(thread_id)

    def get_next_version(self, current, channel):
        return self.inner.get_next_version(current, channel)


class ChatState(TypedDict):
    messages: List[BaseMessage]
    tool_call_count: int
    thread_id: str 
    summary:RunningSummary | None


@tool(return_direct=True)
def dict_input(state: Annotated[ChatState, InjectedState],config: RunnableConfig):
    """ This function only exists to handle dictionary input from LangGraph Studio for Debug""" 
    # print(state)       
    last_too:messages.AIMessage=state["messages"][-1]
    state["messages"].append(
        messages.ToolMessage(
            id=str(uuid.uuid4()),
            content="",
            name="dict_input",
            tool_call_id=last_too.tool_calls[-1]["id"],
        )
    )
    return Command(
        update={
            "messages": state["messages"],
            "thread_id": config["configurable"]["thread_id"]
        },
        goto="llm"
    )
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
        self.max_tool_calls = 2
        

    def get_state(self, config:RunnableConfig) -> ChatState:
        """Get the current state of the agent"""
        if not self.graph.get_state(config).values:
            self.graph.update_state(config, values={'messages': [],"tool_call_count": 0,"thread_id": config["configurable"]["thread_id"],"summary":None},as_node="tools")
        return self.graph.get_state(config).values

    def set_state(self, config:RunnableConfig, new_state:ChatState,as_node:str='tools'):
        """Set the current state of the agent"""
        self.graph.update_state(config, values=new_state,as_node=as_node)

    def llm_node(self, state:ChatState) -> Command[Literal["route"]]:
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
            ).messages
        running_summary_msg=""
        summarized_message_ids={}
        if chat_messages and isinstance(chat_messages[0], messages.SystemMessage):
            running_summary_msg = get_buffer_string([chat_messages[0]])
            summarized_message_ids = set([msg.id for msg in chat_messages])
            chat_messages[0]=messages.AIMessage(content=running_summary_msg,id=chat_messages[0].id) # ag-ui don't want first message to be system message
        for msg in chat_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())
        try:
            response = self.llm.invoke(chat_messages)
        except Exception as e:
            print(f"Error invoking LLM: {e}")
            response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}",id=str(uuid.uuid4()))
        
        # Always go to router after LLM response
        return Command(
            update={'messages': state["messages"] + [response] ,"summary": RunningSummary(summary=running_summary_msg,summarized_message_ids=summarized_message_ids,last_summarized_message_id=None) if running_summary_msg else state["summary"]},
            goto="route"
        )

    async def tools_node(self, state:ChatState) -> Command[Literal["route"]]:
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

        # print("---tools_node: ",result,"\n\n")
        # Always go to router after tools execution
        return Command(
            update={
                'messages': state['messages'] + result['messages'],
                'tool_call_count': state['tool_call_count']+1
            },
            goto="route"
        )

    def route_node(self, state:ChatState) -> Command[Literal["tools", "llm"]]:
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
                    update={}  # No state update needed
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
                # Reset tool count and restart LLM processing
                return Command(
                    update={
                        'messages': state['messages'] + [messages.HumanMessage(content=user_answer)], 
                        'tool_call_count': 0
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
                update={}
            )     


    
    def llm_studio(self,state:ChatState)  -> Command[Literal["initializer_tools"]]:
        last = state["messages"][-1]
        if isinstance(last, dict):
            state["messages"][-1] = messages.HumanMessage(content=last["content"],id=str(uuid.uuid4()))
        if state.get("thread_id") is None:
            ai_msg = messages.AIMessage(
                content="",
                tool_calls=[{
                    "name": "dict_input",
                    "id": str(uuid.uuid4()),
                    "args":{},
                    "type": "tool_call"
                }]
            ) 
            state["messages"].append(ai_msg)   
        return Command(
            update={"messages": state["messages"], 'tool_call_count': 0,"summary":None,"thread_id": ""},
            goto="initializer_tools"
        )

    def on_start(self, run:Run, config:RunnableConfig):
         # just to initialise some state values
        # print("Agent started with config:", config)
        print("initial state:", json.dumps(self.get_state(config),default=str))
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
                    # "env": {
                    #     **os.environ,
                    #     "PYTHONUNBUFFERED": "1",
                    # }
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

        self.llm = self.llm.bind_tools(self.tools)
        
        # Initialize tool node and graph
        self.tool_node = ToolNode(self.tools)
        self.initializer_tools = ToolNode([dict_input],name="init_tools")
        
        builder = StateGraph(ChatState)


        # summarizer= SummarizationNode(
        #     token_counter=count_tokens_approximately,
        #     model=self.llm,
        #     max_tokens=2000,
        #     max_summary_tokens=1000,
        #     output_messages_key="messages",
        # )


        # Add nodes - now with separated routing logic
        # builder.add_node("summarize", summarizer)
        builder.add_node('llm', self.llm_node)
        builder.add_node('tools', self.tools_node)
        builder.add_node('route', self.route_node)

        # Set entry point - all flows start with LLM
        if os.environ.get("USING_LLM_STUDIO", "false").lower() == "true":
            builder.add_node("llm_studio", self.llm_studio)
            builder.add_node('initializer_tools', self.initializer_tools)

            builder.add_edge(START, 'llm_studio')
            builder.add_edge("llm_studio", 'initializer_tools')
            builder.add_edge("initializer_tools", 'llm')
        else:
            builder.add_edge(START, 'llm')
        # builder.set_entry_point("summarize")
        # builder.add_edge("llm", "summarize")
        
        # No conditional edges needed! The Command pattern handles all routing
        # The nodes themselves decide where to go next using Command.goto


        
        memory = InMemorySaver()
        wrapped = SummarizingSaver(memory, memory, threshold=5000)
        
        # Store the base compiled graph for LangGraph Studio API access
        self._base_graph = builder.compile(checkpointer=wrapped, debug=True, name="fds_agent")
        self._base_graph.get_graph().print_ascii()

        # Create the graph with listeners for actual execution
        self.graph = self._base_graph.with_listeners(
            on_start=self.on_start,
            on_end=lambda run, config: print("-------------------------- Agent run ended --------------------------")
        )     

        
        # Note: Removed print_ascii() as it was causing visualization errors
        print("✅ Graph compiled successfully with Command pattern")
        print("📊 Graph structure: START -> llm -> route -> [tools | END]")
        print("🔧 Using Command pattern for dynamic routing with separated concerns:")
        print("   - llm_node: Only handles LLM invocation")
        print("   - tools_node: Only handles tool invocation") 
        print("   - route_node: Handles all routing logic and human-in-the-loop")
        
        # async for event in self.graph.astream(self.state, stream_mode=["updates","messages"]):
        #     pass

    async def close(self):
        """Clean up resources and close connections"""
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

