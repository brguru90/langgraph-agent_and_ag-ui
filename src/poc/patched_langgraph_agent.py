"""
Patched LangGraphAgent to fix the NoneType mapping error in ag-ui-langgraph
"""
from ag_ui_langgraph import LangGraphAgent as OriginalLangGraphAgent
from ag_ui_langgraph.types import MessageInProgress
from typing import Optional


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
