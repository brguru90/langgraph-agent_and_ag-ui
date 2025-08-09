from fastapi import FastAPI
from typing import List,TypedDict,Any,Optional
from typing_extensions import NotRequired
from .my_agents import MyAgent,ChatState  # Import your agent definition
from .patched_langgraph_agent import PatchedLangGraphAgent as LangGraphAgent,add_langgraph_fastapi_endpoint
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ag_ui.core import RunAgentInput, EventType
from ag_ui.core.types import UserMessage
from ag_ui.core.events import (
    RunStartedEvent, 
    RunFinishedEvent, 
    RunErrorEvent,
    TextMessageStartEvent,
    TextMessageEndEvent,
    TextMessageContentEvent,
    ToolCallStartEvent,
    ToolCallEndEvent,
    ToolCallArgsEvent,
    RawEvent,
    CustomEvent
)
from ag_ui.encoder import EventEncoder
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command,Send
from collections.abc import Hashable, Sequence
from fastapi import Request
from fastapi import FastAPI, Request, Query
from pydantic import  Field
import json
import uuid
import traceback
# Global agent instance

# my_agent_instance:MyAgent=None


class CommandType(TypedDict):
    # update: Any | None = None
    resume: dict[str, Any] | Any | None = None
    node_name: NotRequired[Optional[str]] # goto


class ForwardProps(TypedDict):
    command: NotRequired[Optional[CommandType]]=None
    user_id: str
class RunAgentInputExtended(RunAgentInput):
    forwarded_props: ForwardProps=Field(..., alias="forwardedProps")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic here
    print("✅ Application startup logic")
    # global my_agent_instance
    
    # Initialize agent once and keep it alive
    my_agent_instance:MyAgent=None
    if not my_agent_instance:
        my_agent_instance = MyAgent()
        await my_agent_instance.init()

    app.state.my_agent = my_agent_instance
    
    # agent = LangGraphAgent(
    #     name="fds_documentation_explorer",
    #     description="Agent to explore Fabric Design System documentations.",
    #     graph=my_agent_instance.graph,
        
    # )
    # add_langgraph_fastapi_endpoint(
    #     app=app,
    #     agent=agent,
    #     path="/ag-ui/"
    # )

    # sdk = CopilotKitRemoteEndpoint(
    #     agents=[agent],
    # )
    # add_fastapi_endpoint(app, sdk, "/copilotkit/",max_workers=2)
    yield
    
    # Shutdown logic here
    print("🔒 Application shutdown cleanup")
    if my_agent_instance:
        await my_agent_instance.close()



app = FastAPI(lifespan=lifespan,debug=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Allow all origins
    allow_credentials=True,    # Allow cookies & auth headers
    allow_methods=["*"],       # Allow all HTTP methods, including OPTIONS
    allow_headers=["*"],       # Allow all headers
)


def add_missing_ids(config:RunnableConfig,agent:MyAgent):
    state=agent.get_state(config)
    for msg in state["messages"]:
        msg.id = msg.id or str(uuid.uuid4()) # !!! this is must ag-ui to work, every message must have an id
    agent.set_state(config, state)

@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok"}

@app.get("/state")
def state(request: Request, thread_id: Optional[str] = Query(None, description="Thread ID for the conversation")) -> ChatState:
    """State check."""
    agent:MyAgent=app.state.my_agent
    if thread_id is None:
        raise ValueError("thread_id query parameter is required")
    config = {"configurable": {"thread_id": thread_id}}
    add_missing_ids(config,agent)
    return agent.get_state(config)

@app.get("/state_history")
def state_history(request: Request, thread_id: Optional[str] = Query(None, description="Thread ID for the conversation")):
    """State check."""
    agent:MyAgent=app.state.my_agent
    if thread_id is None:
        raise ValueError("thread_id query parameter is required")
    config = {"configurable": {"thread_id": thread_id}}
    return agent.graph.get_state_history(config)


async def handle_agent_events(my_agent: MyAgent, state: ChatState, config: RunnableConfig, encoder: EventEncoder):
    """
    Handle streaming events from the LangGraph agent and yield encoded events.
    
    Key improvements:
    1. Sends raw events in parallel for full transparency 
    2. Handles interrupt events by detecting on_custom_event with name="interrupt"
    3. Detects interrupts both during streaming and after completion
    4. Exits early on interrupt or error events
    5. Uses both 'messages' and 'events' stream modes for comprehensive coverage
    6. Properly implements TEXT_MESSAGE_START, TEXT_MESSAGE_CONTENT, TEXT_MESSAGE_END pattern
    7. Correctly tracks and separates tool calls from text messages
    """
    # Track message streaming state - separate tracking for tool calls and text messages
    current_message_id = None
    current_tool_call_id = None
    message_type = None  # "text" or "tool_call"
    interrupted = False

    print("----- Starting handle_agent_events -----", state, json.dumps(config, indent=2, default=str))
    
    try:
        # Stream events from LangGraph using astream_events v2
        async for event in my_agent.graph.astream_events(state, config, version="v2"):
            print(f"---event type: {type(event)}")
            print(f"---events: {json.dumps(event, default=str)}")
            
            # Send raw event in parallel - this provides full transparency
            yield encoder.encode(RawEvent(
                type=EventType.RAW,
                event=event,
                source="langgraph"
            ))
            
            # Extract event type and data from LangGraph event structure
            event_type = event.get("event")
            event_data = event.get("data", {})
            event_name = event.get("name")
            
            # Handle chat model streaming events
            if event_type == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if not chunk:
                    continue
                
                # Check if this is a tool call chunk
                tool_call_chunks = getattr(chunk, 'tool_call_chunks', [])
                tool_call_data = tool_call_chunks[0] if tool_call_chunks else None
                
                # Handle tool call events
                if tool_call_data:
                    tool_call_id = tool_call_data.get("id")
                    tool_call_name = tool_call_data.get("name")
                    tool_call_args = tool_call_data.get("args")
                    
                    # If we were streaming a text message, end it first
                    if message_type == "text" and current_message_id:
                        yield encoder.encode(TextMessageEndEvent(
                            type=EventType.TEXT_MESSAGE_END,
                            message_id=current_message_id
                        ))
                        current_message_id = None
                        message_type = None
                    
                    # Start new tool call if we have a name and no current tool call
                    if tool_call_name and not current_tool_call_id:
                        current_tool_call_id = tool_call_id or str(uuid.uuid4())
                        message_type = "tool_call"
                        
                        yield encoder.encode(ToolCallStartEvent(
                            type=EventType.TOOL_CALL_START,
                            tool_call_id=current_tool_call_id,
                            tool_call_name=tool_call_name,
                            parent_message_id=getattr(chunk, 'id', None)
                        ))
                    
                    # Stream tool call arguments if we have an active tool call
                    elif tool_call_args and current_tool_call_id and message_type == "tool_call":
                        yield encoder.encode(ToolCallArgsEvent(
                            type=EventType.TOOL_CALL_ARGS,
                            tool_call_id=current_tool_call_id,
                            delta=tool_call_args
                        ))
                
                # Handle text content streaming
                elif hasattr(chunk, 'content') and chunk.content:
                    # If we were in a tool call, end it first
                    if message_type == "tool_call" and current_tool_call_id:
                        yield encoder.encode(ToolCallEndEvent(
                            type=EventType.TOOL_CALL_END,
                            tool_call_id=current_tool_call_id
                        ))
                        current_tool_call_id = None
                        message_type = None
                    
                    # Start text message if not already started
                    if not current_message_id or message_type != "text":
                        current_message_id = getattr(chunk, 'id', None) or str(uuid.uuid4())
                        message_type = "text"
                        
                        # Send TEXT_MESSAGE_START event
                        yield encoder.encode(TextMessageStartEvent(
                            type=EventType.TEXT_MESSAGE_START,
                            message_id=current_message_id,
                            role="assistant"
                        ))
                    
                    # Stream content if available
                    if current_message_id and message_type == "text":
                        # Extract text content from the message
                        content_text = ""
                        if isinstance(chunk.content, str):
                            content_text = chunk.content
                        elif isinstance(chunk.content, list):
                            for content_block in chunk.content:
                                if isinstance(content_block, dict) and content_block.get("type") == "text":
                                    content_text += content_block.get("text", "")
                                elif isinstance(content_block, str):
                                    content_text += content_block
                        
                        if content_text:
                            yield encoder.encode(TextMessageContentEvent(
                                type=EventType.TEXT_MESSAGE_CONTENT,
                                message_id=current_message_id,
                                delta=content_text
                            ))
            
            # Handle chat model end events
            elif event_type == "on_chat_model_end":
                # End any ongoing message or tool call
                if message_type == "tool_call" and current_tool_call_id:
                    yield encoder.encode(ToolCallEndEvent(
                        type=EventType.TOOL_CALL_END,
                        tool_call_id=current_tool_call_id
                    ))
                    current_tool_call_id = None
                    message_type = None
                elif message_type == "text" and current_message_id:
                    yield encoder.encode(TextMessageEndEvent(
                        type=EventType.TEXT_MESSAGE_END,
                        message_id=current_message_id
                    ))
                    current_message_id = None
                    message_type = None
            
            # Handle tool start and end events (separate from chat model events)
            elif event_type == "on_tool_start":
                tool_name = event_name
                if tool_name:
                    # End any ongoing message first
                    if message_type == "text" and current_message_id:
                        yield encoder.encode(TextMessageEndEvent(
                            type=EventType.TEXT_MESSAGE_END,
                            message_id=current_message_id
                        ))
                        current_message_id = None
                        message_type = None
                    
                    # Start new tool call if not already in one
                    if not current_tool_call_id:
                        current_tool_call_id = str(uuid.uuid4())
                        message_type = "tool_call"
                        yield encoder.encode(ToolCallStartEvent(
                            type=EventType.TOOL_CALL_START,
                            tool_call_id=current_tool_call_id,
                            tool_call_name=tool_name,
                            parent_message_id=None
                        ))
            
            elif event_type == "on_tool_end":
                # End tool call if we have one active
                if message_type == "tool_call" and current_tool_call_id:
                    yield encoder.encode(ToolCallEndEvent(
                        type=EventType.TOOL_CALL_END,
                        tool_call_id=current_tool_call_id
                    ))
                    current_tool_call_id = None
                    message_type = None
            
            # Handle custom events for interrupts
            elif event_type == "on_custom_event":
                # Check for interrupt events
                if event_name == "interrupt":
                    interrupted = True
                    
                    # End any ongoing message or tool call before sending interrupt
                    if message_type == "tool_call" and current_tool_call_id:
                        yield encoder.encode(ToolCallEndEvent(
                            type=EventType.TOOL_CALL_END,
                            tool_call_id=current_tool_call_id
                        ))
                        current_tool_call_id = None
                        message_type = None
                    elif message_type == "text" and current_message_id:
                        yield encoder.encode(TextMessageEndEvent(
                            type=EventType.TEXT_MESSAGE_END,
                            message_id=current_message_id
                        ))
                        current_message_id = None
                        message_type = None
                    
                    # Send interrupt event
                    yield encoder.encode(CustomEvent(
                        type=EventType.CUSTOM,
                        name="on_interrupt",
                        value=json.dumps(event_data) if event_data else "{}"
                    ))
                    
                    # Exit the stream early on interrupt
                    break
            
            # Handle error events
            elif event_type == "error":
                # End any ongoing message or tool call before sending error
                if message_type == "tool_call" and current_tool_call_id:
                    yield encoder.encode(ToolCallEndEvent(
                        type=EventType.TOOL_CALL_END,
                        tool_call_id=current_tool_call_id
                    ))
                    current_tool_call_id = None
                    message_type = None
                elif message_type == "text" and current_message_id:
                    yield encoder.encode(TextMessageEndEvent(
                        type=EventType.TEXT_MESSAGE_END,
                        message_id=current_message_id
                    ))
                    current_message_id = None
                    message_type = None
                
                # Send RUN_ERROR and set interrupted flag to prevent RUN_FINISHED
                yield encoder.encode(RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message=event_data.get("message", "Unknown error")
                ))
                interrupted = True
                break
        
        # End any ongoing message or tool call if stream completed normally
        if not interrupted:
            if message_type == "tool_call" and current_tool_call_id:
                yield encoder.encode(ToolCallEndEvent(
                    type=EventType.TOOL_CALL_END,
                    tool_call_id=current_tool_call_id
                ))
            elif message_type == "text" and current_message_id:
                yield encoder.encode(TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=current_message_id
                ))
        
        # Check for interrupts after stream ends (if not already interrupted)
        if not interrupted:
            try:
                final_state = await my_agent.graph.aget_state(config)
                tasks = final_state.tasks if len(final_state.tasks) > 0 else None
                interrupts = tasks[0].interrupts if tasks else []
                
                if interrupts:
                    interrupted = True
                    for interrupt in interrupts:
                        yield encoder.encode(CustomEvent(
                            type=EventType.CUSTOM,
                            name="on_interrupt", 
                            value=json.dumps(interrupt.value) if not isinstance(interrupt.value, str) else interrupt.value
                        ))
            except Exception as e:
                print(f"Error checking for interrupts: {e}")
                
    except Exception as e:
        print(f"Error in handle_agent_events: {e}", e)
        traceback.print_exc()
        traceback.print_stack()
        
        # End any ongoing message or tool call before sending error
        if message_type == "tool_call" and current_tool_call_id:
            yield encoder.encode(ToolCallEndEvent(
                type=EventType.TOOL_CALL_END,
                tool_call_id=current_tool_call_id
            ))
        elif message_type == "text" and current_message_id:
            yield encoder.encode(TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=current_message_id
            ))
        
        # Send RUN_ERROR and set interrupted flag to prevent RUN_FINISHED from being sent later
        try:
            error_event = RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=str(e)
            )
            yield encoder.encode(error_event)
        except Exception as encode_error:
            print(f"Failed to encode RUN_ERROR event: {encode_error}")
        
        # Return immediately after sending RUN_ERROR
        return


    print("----- Ending handle_agent_events -----")

@app.post("/ag-ui/")
async def endpoint(input_data: RunAgentInputExtended, request: Request): 
    print(f"Received input_data: {type(input_data)}={json.dumps(input_data.model_dump(),indent=2, default=str)}")
    accept_header = request.headers.get("accept")
    encoder = EventEncoder(accept=accept_header)
    my_agent:MyAgent = request.app.state.my_agent
    config: RunnableConfig = {
        "configurable": {
            "thread_id": input_data.thread_id,
            "user_id": input_data.forwarded_props["user_id"],
        },
        "run_id": input_data.run_id,
        "recursion_limit": 25
    }

    async def gen():
        try:
            # Send run started event
            yield encoder.encode(RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id
            ))
            
            # print(f"input_data: {[m for m in input_data.messages]}")
            user_msgs: List[UserMessage] = input_data.messages
            human_msgs = [HumanMessage(content=m.content,id=str(uuid.uuid4())) for m in user_msgs]
            
            # Process through agent
            # my_agent.state['messages'].append(human_msgs[-1])

            state: ChatState = ChatState(
                messages=human_msgs,
            )

            print("-----gen------")

            # Track if a RUN_ERROR event was sent
            run_error_detected = False
            
            # Handle agent events using the separate function
            async for event_data in handle_agent_events(my_agent, state, config, encoder):
                # Check if this is a RUN_ERROR event before yielding it
                try:
                    event_str = event_data.decode() if hasattr(event_data, 'decode') else str(event_data)
                    if '"type":"RUN_ERROR"' in event_str:
                        run_error_detected = True
                        print("RUN_ERROR detected, will not send RUN_FINISHED")
                except Exception as e:
                    print(f"Error checking event data: {e}")
                
                yield event_data
            
            # Only send RUN_FINISHED if no RUN_ERROR was detected
            if not run_error_detected:
                try:
                    yield encoder.encode(RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=input_data.thread_id,
                        run_id=input_data.run_id
                    ))
                except Exception as e:
                    print(f"Error sending RUN_FINISHED: {e}")
                    # Don't try to send another RUN_ERROR here as that could cause more problems
            
        except Exception as error:
            print(f"Error in agent processing: {error}")
            traceback.print_exc()
            
            # Only send RUN_ERROR if no RUN_ERROR was already detected
            if not run_error_detected:
                try:
                    # Send RUN_ERROR event but don't send RUN_FINISHED afterward
                    yield encoder.encode(RunErrorEvent(
                        type=EventType.RUN_ERROR,
                        message=str(error)
                    ))
                except Exception as e:
                    print(f"Error sending RUN_ERROR: {e}")
            
            # Exit generator early to avoid sending RUN_FINISHED after an error
            return
        print("-----")

    return StreamingResponse(gen(), media_type=encoder.get_content_type())

