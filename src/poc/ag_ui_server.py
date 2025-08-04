from fastapi import FastAPI
from .my_agents import MyAgent,ChatState  # Import your agent definition
from .patched_langgraph_agent import PatchedLangGraphAgent as LangGraphAgent
# from ag_ui_langgraph import LangGraphAgent
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from fastapi import Request
from fastapi import FastAPI, Request, Query
from typing import Optional
import json
import uuid
# from copilotkit.integrations.fastapi import add_fastapi_endpoint
# from copilotkit import CopilotKitRemoteEndpoint, Action as CopilotAction,LangGraphAgent

# Global agent instance

my_agent_instance:MyAgent=None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic here
    print("✅ Application startup logic")
    global my_agent_instance
    
    # Initialize agent once and keep it alive
    if not my_agent_instance:
        my_agent_instance = MyAgent()
        await my_agent_instance.init()

    app.state.my_agent = my_agent_instance
    
    agent = LangGraphAgent(
        name="fds_documentation_explorer",
        description="Agent to explore Fabric Design System documentations.",
        graph=my_agent_instance.graph,
        
    )
    add_langgraph_fastapi_endpoint(
        app=app,
        agent=agent,
        path="/ag-ui/"
    )

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


def add_missing_ids(config):
    state=my_agent_instance.get_state(config)
    for msg in state["messages"]:
        msg.id = msg.id or str(uuid.uuid4()) # !!! this is must ag-ui to work, every message must have an id
    my_agent_instance.set_state(config, state)

@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok"}

@app.get("/state")
def state(request: Request, thread_id: Optional[str] = Query(None, description="Thread ID for the conversation")) -> ChatState:
    """State check."""
    my_agent_instance:MyAgent=app.state.my_agent
    if thread_id is None:
        raise ValueError("thread_id query parameter is required")
    config = {"configurable": {"thread_id": thread_id}}
    add_missing_ids(config)
    return my_agent_instance.get_state(config)

@app.get("/state_history")
def state_history(request: Request, thread_id: Optional[str] = Query(None, description="Thread ID for the conversation")):
    """State check."""
    my_agent_instance:MyAgent=app.state.my_agent
    if thread_id is None:
        raise ValueError("thread_id query parameter is required")
    config = {"configurable": {"thread_id": thread_id}}
    return my_agent_instance.graph.get_state_history(config)
