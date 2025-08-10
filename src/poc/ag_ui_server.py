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
from  .lg_ag_ui import LangGraphToAgUi
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

import pickle

async def handle_agent_events(request: Request, my_agent: MyAgent, payload: ChatState | Command, config: RunnableConfig, encoder: EventEncoder):
    """
    Handle streaming events from the LangGraph agent and yield encoded events.
    """
    print("----- Starting handle_agent_events -----", payload, json.dumps(config, indent=2, default=str))
    try:
        events_object = []
        event_transformer = LangGraphToAgUi()
        async for event in my_agent.graph.astream_events(payload, config, version="v2"):
            # print(f"---event type: {type(event)}")
            # print(f"---events: {json.dumps(event, default=str)}")
            events_object.append(event)

            if event.get("data",{}).get("input",{}) and isinstance(event.get("data",{}).get("input"),Command):
                cmd:Command=event["data"]["input"]
                event["data"]["input"]={"resume":cmd.resume}
            if event.get("data") and event["data"].get("input") and event["data"]["input"].get("store") is not None:  # encoder throws error because store will have checkpointer object
                event["data"]["input"]["store"] = "Accessing to store information"
            yield RawEvent(
                type=EventType.RAW,
                event=event,
            )

            async for transformed_event in event_transformer.transform_events(event):
                if transformed_event:
                    yield transformed_event           
        yield event_transformer.end_events()             
    except Exception as e:
        print(f"Error in handle_agent_events: {e}", e)
        traceback.print_exc()
        traceback.print_stack()
        import pdb; pdb.set_trace()

    with open("all_events.pkl", "wb") as file:
        pickle.dump(events_object, file)
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

            command: Command = None
            state: ChatState = ChatState(
                messages=human_msgs,
            )

            if input_data.forwarded_props.get("command"):
                command = Command(
                    resume=input_data.forwarded_props["command"].get("resume",""),
                )


            print("-----gen------")

            # Track if a RUN_ERROR event was sent
            run_error_detected = False
            
            # Handle agent events using the separate function
            async for event_data in handle_agent_events(request, my_agent, command if command else state, config, encoder):
                # Check if this is a RUN_ERROR event before yielding it
                # try:
                #     event_str = event_data.decode() if hasattr(event_data, 'decode') else str(event_data)
                #     if '"type":"RUN_ERROR"' in event_str:
                #         run_error_detected = True
                #         print("RUN_ERROR detected, will not send RUN_FINISHED")
                # except Exception as e:
                #     print(f"Error checking event data: {e}")

                yield encoder.encode(event_data)

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

