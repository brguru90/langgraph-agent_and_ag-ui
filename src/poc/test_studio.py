import asyncio
from typing import Callable,Dict
from poc.agents.supervisor import MyAgent
from langgraph.pregel import Pregel
from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables.config import RunnableConfig
import json,sys
import atexit
import signal


# Global agent instance to avoid re-initialization
_agent: MyAgent = None
_compiled_graph = None
user_id='008f00fb-b8d0-4acc-b3f1-649d86a76b8d'

def cleanup_function():
    if _agent:
        _agent.close()
atexit.register(cleanup_function)

class MyPregel(CompiledStateGraph):  

    override_callback: Callable[[Dict],Dict] | None=None
    base: CompiledStateGraph=None

    def __init__(self, base: CompiledStateGraph, override_callback: Callable[[Dict],Dict] | None=None):
        self._base = base
        self.override_callback=override_callback

    def copy(self, update = None):
        if self.override_callback:
            update = self.override_callback(update)
        return self._base.copy(update)


async def create_graph(config:RunnableConfig):
    """Create and return the compiled graph for LangGraph Studio"""
    global _agent, _compiled_graph
    


    def patch(update:Dict):
        # this langgraph studio overrides its owen memory checkpointer, to override it again with patched value
        update["checkpointer"] = _agent.checkpointer
        update["store"]=_agent.store
        # print("\n------------ override ------------ ", update)
        return update
    
    if _agent is None:
        _agent = MyAgent()
        # if config:
        #     config["configurable"]["user_id"] = user_id
        #     config["user_id"] = user_id
        #     config["configurable"]["group"] = "Engineering"
        #     config["configurable"]["context_scope"] = "thread" 
        try:
            print("Creating graph...",json.dumps(config, indent=2,default=str))
            print("Creating and initializing MyAgent...")
            # config["configurable"]["__pregel_checkpointer"]=_agent.checkpointer
            await _agent.init()           
            # Store the base compiled graph before it gets wrapped with listeners
            _compiled_graph = MyPregel(_agent.get_base_graph(),override_callback=patch)
            print("Agent initialized successfully!")
            print(f"Base graph object: {_compiled_graph}")
        except Exception as e:
            print(f"Error creating graph: {e}")
            import traceback
            traceback.print_exc()
            return None
    elif _agent.graph:
        # config["configurable"]["__pregel_checkpointer"]=_agent.checkpointer
        _compiled_graph =  MyPregel(_agent.get_base_graph(),override_callback=patch)
        print("Using existing agent instance")
    return _compiled_graph
    
    