from fastapi import FastAPI
from typing import List,TypedDict,Any,Optional,Dict
from typing_extensions import NotRequired
from .agents.supervisor import MyAgent,ChatState  # Import your agent definition
# from .patched_langgraph_agent import PatchedLangGraphAgent as LangGraphAgent,add_langgraph_fastapi_endpoint
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ag_ui.core import RunAgentInput, EventType
from ag_ui.core.types import UserMessage
from ag_ui.core.events import (
    RunStartedEvent, 
    RunFinishedEvent, 
    RunErrorEvent,
    RawEvent,
)
from ag_ui.encoder import EventEncoder
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from fastapi import Request
from fastapi import FastAPI, Request, Query
from pydantic import  Field
import json
import uuid
import traceback
from  .lg_ag_ui import LangGraphToAgUi
import pickle 
import tempfile
from langchain_core import messages

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
    print("✅ Application started")

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

async def handle_agent_events(request: Request, my_agent: MyAgent, payload: ChatState | Command, config: RunnableConfig, encoder: EventEncoder):
    print("----- Starting handle_agent_events -----", payload, json.dumps(config, indent=2, default=str))
    try:
        events_object = []
        event_transformer = LangGraphToAgUi()
        async for event in my_agent.graph.astream_events(payload, config, version="v2"):
            # print(f"---event type: {type(event)}")
            # print(f"---events: {json.dumps(event, default=str)}")
            events_object.append(event)  
            __event=event         

            if event.get("data",{}).get("input",{}) and isinstance(event.get("data",{}).get("input"),Command):
                cmd:Command=event["data"]["input"]
                # event["data"]["input"]={"resume":cmd.resume}
                __event={
                    **event,
                    "data":{
                        **event["data"],
                        "input":{"resume":cmd.resume}
                    }
                }
            if __event.get("data") and __event["data"].get("input") and isinstance(__event["data"]["input"],dict) and __event["data"]["input"].get("store") is not None:  # encoder throws error because store will have checkpointer object
                # event["data"]["input"]["store"] = "Accessing to store information"
                __event={
                    **__event,
                    "data":{
                        **__event["data"],
                        "input":{"store":"Accessing to store information"}
                    }
                }
            yield RawEvent(
                type=EventType.RAW,
                event=__event,
            )
            async for transformed_event in event_transformer.transform_events(__event):
                if transformed_event:
                    yield transformed_event           
        yield event_transformer.end_events()      
               
    except Exception as e:
        print(f"Error in handle_agent_events: {e}", e)
        traceback.print_exc()
        traceback.print_stack()
        import pdb; pdb.set_trace()

    with open("all_events.pkl", "wb") as file:
        temp_file = tempfile.TemporaryFile()
        final_event_objects=[]
        for _obj in events_object:
            try:
                pickle.dump(_obj, temp_file)
                final_event_objects.append(_obj)
            except:
                pass
        pickle.dump(final_event_objects, file)
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
            yield encoder.encode(RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id
            ))
            
            user_msgs: List[UserMessage] = input_data.messages
            human_msgs = [HumanMessage(content=m.content,id=str(uuid.uuid4())) for m in user_msgs]

            command: Command = None
            state: ChatState = ChatState(
                messages=human_msgs,
            )

            if input_data.forwarded_props.get("command"):
                command = Command(
                    resume=input_data.forwarded_props["command"].get("resume",""),
                )

            async for event_data in handle_agent_events(request, my_agent, command if command else state, config, encoder):
                try:
                    yield encoder.encode(event_data)
                except Exception as e:
                    print(f"Error encoding event: {e}", e)
                    traceback.print_exc()
                    yield f"data: {event_data.model_dump_json(by_alias=True, exclude_none=True,fallback=lambda x: str(x))}\n\n"

            yield encoder.encode(RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id
            ))
            
        except Exception as error:
            print(f"Error in agent processing: {error}")
            traceback.print_exc()

            yield encoder.encode(RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=str(error)
            ))

    return StreamingResponse(gen(), media_type=encoder.get_content_type())

