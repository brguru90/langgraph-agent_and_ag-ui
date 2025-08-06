import asyncio,json
from langchain_aws import ChatBedrockConverse
from .my_agents import MyAgent
from langgraph.types import  Command,Interrupt
from langchain_core import messages
import uuid

async def run_test_tool_calls(my_agent:MyAgent):
    thread_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25  # Increase recursion limit to prevent premature termination
    }
    interrupted=False
    # Interactive chat loop
    print('Type an instruction or "quit".\n')
    while True:
        try:
            user_message = input('> ')
            output=""

            if user_message.lower() == 'quit':
                break
            if interrupted:
                # Resume with Command pattern
                output=await my_agent.graph.ainvoke(Command(resume=user_message), config=config)
            else:
                state=my_agent.get_state(config)
                state['messages'].append(messages.HumanMessage(content=user_message))
                my_agent.set_state(config, state)
                # print("Current state: ", my_agent.get_state(config), '\n')
                output=await my_agent.graph.ainvoke(my_agent.get_state(config), config=config)

            interrupted=False                
            # Check for interrupts in the new format
            interrupt_info = output.get("__interrupt__", None)
            if interrupt_info:
                print(">> Paused awaiting feedback:", interrupt_info)
                interrupted=True
                continue

            # print(json.dumps(output, indent=2,default=str), '\n')
            my_agent.set_state(config, output)
            print(my_agent.get_state(config)['messages'][-1].content, '\n')
            await asyncio.sleep(2)
            # print(json.dumps(my_agent.state, indent=2,default=str), '\n')
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except EOFError:
            print("\nExiting...")
            break

def test_tool_calls():
    # New init/close pattern
    async def run():
        my_agent = MyAgent()
        await my_agent.init()
        
        try:
            await run_test_tool_calls(my_agent)        
        finally:
            print("Closing agent...")
            await my_agent.close()
        print('MyAgent exiting...\n')
    asyncio.run(run())

# async def test_tool_calls():
#     # Alternative: still supports async context manager for backward compatibility
#     async with MyAgent() as my_agent:        
#         await run_test_tool_calls(my_agent)  
#     print('MyAgent exiting...\n')

    
def debug_tool():
    """Start the LangGraph development server programmatically"""
    import os
    import sys
    import pathlib
    
    try:
        # Import the actual development server function and configuration
        from langgraph_cli.cli import dev
        cwd = os.getcwd()
        sys.path.append(cwd)
        config_path = pathlib.Path(f"langgraph.json")
        # print("config_path",config_path)
        # dev([ "--config", "langgraph.json","--allow-blocking"], standalone_mode=False)

        # import click
        
        # # Create a Click context manually
        # ctx = click.Context(dev)
        # ctx.params = {
        #     'host': '127.0.0.1',
        #     'port': 2024,
        #     'no_reload': False,
        #     'config': 'langgraph.json',
        #     'n_jobs_per_worker': None,
        #     'no_browser': False,
        #     'debug_port': None,
        #     'wait_for_client': False,
        #     'studio_url': None,
        #     'allow_blocking': True,
        #     'tunnel': False,
        #     'server_log_level': 'WARNING'
        # }
        
        # print("Calling dev function with Click context...")
        # with ctx:
        #     dev.invoke(ctx)


        from langgraph_api.cli import run_server
        import langgraph_cli.config
        import pathlib
        
        # Load and validate the configuration file
        config_path = pathlib.Path("langgraph.json")
        config_json = langgraph_cli.config.validate_config_file(config_path)
        
        # Check for unsupported features
        if config_json.get("node_version"):
            raise Exception(
                "In-mem server for JS graphs is not supported in this version. Use `npx @langchain/langgraph-cli` instead."
            )

        # Add current directory and dependencies to Python path
        cwd = os.getcwd()
        sys.path.append(cwd)
        dependencies = config_json.get("dependencies", [])
        for dep in dependencies:
            dep_path = pathlib.Path(cwd) / dep
            if dep_path.is_dir() and dep_path.exists():
                sys.path.append(str(dep_path))

        # Extract graphs configuration
        graphs = config_json.get("graphs", {})
        
        # Call the development server with the correct parameters
        run_server(
            "127.0.0.1",  # host
            2024,  # port
            True,  # reload (not no_reload where no_reload=False)
            graphs,  # graphs
            n_jobs_per_worker=None,
            open_browser=True,  # not no_browser where no_browser=False
            debug_port=None,
            env=config_json.get("env"),
            store=config_json.get("store"),
            wait_for_client=False,
            auth=config_json.get("auth"),
            http=config_json.get("http"),
            ui=config_json.get("ui"),
            ui_config=config_json.get("ui_config"),
            studio_url=None,
            allow_blocking=True,
            tunnel=False,
            server_level="WARNING",
        )
    # except ImportError as e:
    #     if "langgraph_api" in str(e):
    #         print("Required package 'langgraph-api' is not installed.")
    #         print("Please install it with:")
    #         print('    pip install -U "langgraph-cli[inmem]"')
    #     else:
    #         print(f"Import error: {e}")
    #     raise
    except Exception as e:
        print(f"Error starting development server: {e}")
        raise

def test_bedrock():
    """Test AWS Bedrock connection"""
    try:
        llm = ChatBedrockConverse(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", 
            region_name="us-west-2", 
            temperature=0.0,
            max_tokens=20000, 
        )
        messages = [
            ("system", "You are a helpful assistant."),
            ("human", "Translate 'Hello' into French."),
        ]
        response = llm.invoke(messages)
        print(response.content)
        return True
    except Exception as e:
        print(f"AWS Bedrock test failed: {e}")
        return False


if __name__ == '__main__':
    test_bedrock()
   

