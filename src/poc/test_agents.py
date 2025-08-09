import asyncio,json
from langchain_aws import ChatBedrockConverse
from .my_agents import MyAgent
from langgraph.types import  Command,Interrupt
from langchain_core import messages
import uuid

async def run_test_tool_calls(my_agent:MyAgent):
    # thread_id = str(uuid.uuid4())
    thread_id="1517e275-850e-426a-970b-da3bb41a30d7"
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": "guru",
        },
        "run_id":str(uuid.uuid4()),
        "recursion_limit": 25  # Increase recursion limit to prevent premature termination
    }
    interrupted=False
    # Interactive chat loop
    print('Type an instruction or "quit".\n')
    while True:
        try:
            user_message = input('(type quit to exit)> ' if interrupted else '> ')
            output=""

            if user_message.lower() == 'quit':
                break
            if interrupted:
                # Resume with Command pattern
                output=await my_agent.graph.ainvoke(Command(resume=user_message), config=config)
            else:
                state=my_agent.get_state(config)
                state['messages']=[messages.HumanMessage(content=user_message)]
                output=await my_agent.graph.ainvoke(state, config=config)

            interrupted=False                
            # Check for interrupts in the new format
            interrupt_info = output.get("__interrupt__", None)
            if interrupt_info:
                print(">> Paused awaiting feedback:", interrupt_info)
                interrupted=True
                continue

            # print(json.dumps(output, indent=2,default=str), '\n')
            print(output['messages_history'][-1].content, '\n')
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
        print("config_path",config_path)
        dev([ "--config", "langgraph.json","--allow-blocking"])

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
   

