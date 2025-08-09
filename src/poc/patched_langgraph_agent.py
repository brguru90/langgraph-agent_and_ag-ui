"""
Patched LangGraphAgent to fix the NoneType mapping error in ag-ui-langgraph
"""
from ag_ui_langgraph import LangGraphAgent as OriginalLangGraphAgent
from ag_ui_langgraph.types import MessageInProgress
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from ag_ui.core.types import RunAgentInput
from ag_ui.core import RawEvent
from ag_ui.encoder import EventEncoder

from ag_ui_langgraph import LangGraphAgent
import json

class PatchedLangGraphAgent(OriginalLangGraphAgent):
    """Patched version of LangGraphAgent to fix NoneType mapping error"""
    
    def get_message_in_progress(self, run_id: str) -> Optional[MessageInProgress]:
        """Override to ensure we always return a proper dict or None"""
        result = self.messages_in_process.get(run_id)
        if result is None:
            return {}  # Return empty dict instead of None
        return result

    def set_message_in_progress(self, run_id: str, data: MessageInProgress):
        """Override to safely handle None values"""
        current_message_in_progress = self.get_message_in_progress(run_id)
        
        # Ensure current_message_in_progress is a dict
        if current_message_in_progress is None:
            current_message_in_progress = {}
        
        # Safely merge the dictionaries
        self.messages_in_process[run_id] = {
            **current_message_in_progress,
            **data,
        }




def add_langgraph_fastapi_endpoint(app: FastAPI, agent: LangGraphAgent, path: str = "/"):
    """Adds an endpoint to the FastAPI app."""

    @app.post(path)
    async def langgraph_agent_endpoint(input_data: RunAgentInput, request: Request):
        # Get the accept header from the request
        accept_header = request.headers.get("accept")

        # Create an event encoder to properly format SSE events
        encoder = EventEncoder(accept=accept_header)

        async def event_generator():
            async for event in agent.run(input_data):
                event: RawEvent
                if hasattr(event, "event") and event.event.get("data", {}).get("store") is not None:
                    event.event["data"]["store"] = {}
                try:
                    yield encoder.encode(event)
                except:
                    print("Error encoding event: ",event)

        return StreamingResponse(
            event_generator(),
            media_type=encoder.get_content_type()
        )
