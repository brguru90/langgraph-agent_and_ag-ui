import asyncio
from poc.my_agents import MyAgent

# Global agent instance to avoid re-initialization
# _agent: MyAgent = None
# _compiled_graph = None

async def create_graph():
    """Create and return the compiled graph for LangGraph Studio"""
    _agent = MyAgent()
    await _agent.init()
    return  _agent.get_base_graph()
    # global _agent, _compiled_graph
    
    # if _agent is None:
    #     _agent = MyAgent()
    #     try:
    #         print("Creating and initializing MyAgent...")
    #         await _agent.init()
    #         # Store the base compiled graph before it gets wrapped with listeners
    #         _compiled_graph = _agent.get_base_graph()
    #         print("Agent initialized successfully!")
    #         print(f"Base graph object: {_compiled_graph}")
    #         return _compiled_graph
    #     except Exception as e:
    #         print(f"Error creating graph: {e}")
    #         import traceback
    #         traceback.print_exc()
    #         return None
    # elif _agent.graph:
    #     _compiled_graph = _agent.get_base_graph()
    #     print("Using existing agent instance")
    
    