from langgraph.prebuilt import create_react_agent
from .utils import mcp_sampling_handler,get_aws_modal,create_handoff_tool
from fastmcp import Client
from langchain_mcp_adapters.tools import load_mcp_tools
from .state import ChatState


class ResearchAgent:

    def __init__(self, run_as_tool=False):
        print("__ResearchAgent__")
        self.agent_as_tool = run_as_tool
        self.llm = None
        self.graph = None

    def get_steering_tool(self):
        """Get the steering tool for the coding agent"""
        return create_handoff_tool(agent_name="research_agent", description="Assign task to a researcher agent.")

    async def init(self):
        self.llm=get_aws_modal()

        mcp_config={
                "fds": {
                    "url": "https://mcp.context7.com/mcp",
                    "transport": "http",
                }
        }
        self.client=Client(mcp_config,sampling_handler=mcp_sampling_handler)        
        self.client_session = (await self.client.__aenter__()).session
        tools = await load_mcp_tools(self.client_session)        
        if tools:
            print(f"Successfully loaded {len(tools)} MCP tools")
        else:
            raise ValueError("No tools loaded, returning...")
        
        self.graph = create_react_agent(
            model=self.llm,
            tools=tools,
            state_schema=ChatState,            
            prompt=(
                "You are a research agent.\n\n"
                "INSTRUCTIONS:\n"
                "- Assist ONLY with research-related tasks\n"
                "- After you're done with your tasks, respond to the supervisor directly\n"
                "- Respond ONLY with the results of your work, do NOT include ANY other text."
            ),
            name="research_agent",
        )
        self.graph.get_graph().print_ascii()


    async def close(self):
        """Clean up resources and close connections"""
        print("Closing agent resources...")
        await self.__aexit__(None, None, None)

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
                self.client = None
        
        print("Agent cleanup completed")