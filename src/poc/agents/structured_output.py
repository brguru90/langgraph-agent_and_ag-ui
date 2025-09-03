import uuid
from typing import Literal,Annotated, NotRequired,Dict,Optional,Any,cast,List

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langchain_core import messages
from langchain_core.runnables.config import RunnableConfig
from langgraph.store.base import BaseStore
from .utils import mcp_sampling_handler,get_aws_modal,create_handoff_tool
from fastmcp import Client
from langchain_mcp_adapters.tools import load_mcp_tools
from .state import ChatState,SupervisorNode,CodeSnippetsStructure
import traceback
from langgraph.prebuilt import InjectedState,InjectedStore, create_react_agent
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from langchain_core.messages.utils import count_tokens_approximately
from botocore.config import Config
from langchain_core.messages.utils import get_buffer_string
import json
from langgraph.config import get_stream_writer
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.tools.base import  BaseTool

code_parser = PydanticOutputParser(pydantic_object=CodeSnippetsStructure)

@tool
def combine_responses() -> str | list[str | dict]:
    """Combine the responses,
    - If the multiple user queries provided or the multiple steps involved with related response, then add one or more steps to combine the response or conclude the response meaningfully into single final response.
    - If the multiple unrelated queries provided or the multiple steps involved with unrelated response, then add one or more steps to combine all the information into different block/sections in the same single final response.
    - Don't summaries and don't loose any information from the final response while combining.
    - before combining the responses, first check whether the nature of query required the structured output if its required then first execute structured_output tools then execute the combine_responses tool.
    - While combining, if there is a structured output then don't modify the response and keep the structured output intact.
    """

    return ""


@tool(description=f"""Provide the structured output for the code implementations,

    Conditions for providing the structured response, if below conditions not met then don't structure the output and keep original response intact:
    - only structure the output if user explicitly asks for code implementation or executable code or runnable code or or complete code or similar
    - Don't structure the output if user only ask for documentation or code snippets or example or similar

    Guidelines:
    - Include all relevant code snippets, file names, and other contextual information.
    - Maintain the original formatting and structure of the code as much as possible.
    - The final code should be executable
      
    Output Schema:
    {code_parser.get_format_instructions()} 

    """)
def structured_output_for_code() -> CodeSnippetsStructure:
    """Provide the structured output for the code implementations,

    Conditions for providing the structured response, if below conditions not met then don't structure the output and keep original response intact:
    - only structure the output if user explicitly asks for code implementation or executable code or runnable code or or complete code or similar
    - Don't structure the output if user only ask for documentation or code snippets or example or similar

    Guidelines:
    - Include all relevant code snippets, file names, and other contextual information.
    - Maintain the original formatting and structure of the code as much as possible.
    - The final code should be executable

    """

    return ""

class StructuredOutputAgent:

    def __init__(self, return_to_supervisor=False):
        print("__StructuredOutputAgent__")
        self.return_to_supervisor = return_to_supervisor
        self.base_llm = None
        self.llm = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.name:str=SupervisorNode.STRUCTURED_OUTPUT_AGENT_VAL
        self.descriptions="Responsible for generating structured outputs and also combining the multiple information from different execution steps but it can do only one task for the agent execution means it can call only one tool for the current agent execution, if another tool call also needed then agent should be re-invoked."

    def get_steering_tool(self):
        return create_handoff_tool(agent_name=self.name, description=f"Assign task to a structured output agent ({self.descriptions}).")
    
    async def combine_responses(self, state: ChatState, config: RunnableConfig, *, store: BaseStore):
        """Combine responses node - only responsible for calling combine_responses tool"""    
        combine_response_payload=state["messages"][:]
        combine_response_payload.append(    
            messages.HumanMessage(
                content=f"""Combine the responses:
                - Don't summaries and don't loose any information from the final response while combining.
                - While combining, if there is a structured output then don't modify the response and keep the structured output intact.
                """,
                id=str(uuid.uuid4())
            )
        )
        response=await self.base_llm.ainvoke(get_buffer_string(combine_response_payload))
        
        return Command(
            update={
                'messages': state["messages"] + [response],
            },
            goto="route"
        )
    
    async def structured_output_for_code(self, state: ChatState, config: RunnableConfig, *, store: BaseStore):
        """Structured output for code node - only responsible for calling structured_output_for_code tool"""    
        structure_code_payload=state["messages"][:]
        structure_code_payload.append(    
            messages.HumanMessage(
                content=f"""
                * provide structured output for the code implementations for the plan
                * if the multiple unidentified code snippet present then try to relate each other before providing the structured output and if any data like file_name,language,framework,descriptions etc then try to identify or guess them
                * for the descriptions don't create README.md as a part of /file instead provide it as part of structured output which have fields for descriptions
                * Output Schema(Output response should be STRICTLY needed in the format): {code_parser.get_format_instructions()}
                """,
                id=str(uuid.uuid4())
            )
        )
        # response=await self.base_llm.with_structured_output(CodeSnippetsStructure).ainvoke(structure_code_payload)

        print(f"\n---- CodeSnippetsStructure, input token count={count_tokens_approximately(structure_code_payload)} ------\n")

        max_retry=3
        while max_retry > 0:
            try:
                response_struct:CodeSnippetsStructure=await self.base_llm.with_structured_output(CodeSnippetsStructure).ainvoke(get_buffer_string(structure_code_payload)) # include_raw will cause error since it will return tool message without tool call and this can't be used in other agent where this tools in not bind to llm
                response=messages.HumanMessage(
                    content=response_struct.model_dump_json(indent=2), 
                    id=str(uuid.uuid4()),
                    additional_kwargs={
                        "code_block":True
                    }
                )
                custom_response=messages.BaseMessage(
                    type="code",
                    content=[{
                        "type":"code",
                        "text":response_struct.model_dump_json(indent=2)
                    }], 
                    id=str(uuid.uuid4()),
                    additional_kwargs={
                        "code_block":True
                    }
                )
                await adispatch_custom_event("structured_output",{"chunk":custom_response},config=config)
                break
            except Exception as e:
                traceback.print_exc()
                traceback.print_stack()
                with open('plans.json', 'w') as f:
                    json.dump(structure_code_payload, f, default=str, indent=2)
                # import pdb; pdb.set_trace()
                structure_code_payload=await self.base_llm.ainvoke(get_buffer_string(structure_code_payload))
              
            max_retry -= 1

        # writer = get_stream_writer()
        # writer({"event":"structured_output","type":"code","data":response_struct.model_dump_json()})

        

        return Command(
            update={
                'messages': state["messages"] + [response],
            },
            goto="route"
        )

    async def llm_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """LLM node - only responsible for calling llm.invoke"""
        
        chat_messages = state["messages"]
        for msg in chat_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())
        try:
            response = await self.llm.ainvoke(chat_messages)
        except Exception as e:
            print(f"Error invoking LLM: {e}\n", chat_messages, traceback.print_exc())
            response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}", id=str(uuid.uuid4()))
        
        updated_messages = chat_messages + [response]

        return Command(
            update={
                'messages': updated_messages,
            },
            goto="route"
        )

    async def tools_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """Tools node - only responsible for calling tool_node.ainvoke"""    
        ai_msg: messages.AIMessage = state["messages"][-1]
        result = await self.tool_node.ainvoke(state)

        # Combine all messages for the updated state
        all_updated_messages = state['messages'] + result['messages']
        
        return Command(
            update={
                'messages': all_updated_messages,
            },
            goto="route"
        )

    def route_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["tools","combine_responses","structured_output_for_code"]]:
        """Route node - handles all routing logic using Command pattern"""
        
        last_message = state['messages'][-1]

        print(f"--route_node combine_out_agent: message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}, len={len(state['messages'])}", last_message)
        

        def check_call_to_agent():
            print("\n----- check_call_to_agent ------\n")
            delegate_to_node=["combine_responses","structured_output_for_code"]
            if not isinstance(last_message,messages.AIMessage):
                print("\n------check_call_to_agent return due to not AIMessage------\n")
                return False
            agent_node_name=last_message.tool_calls[0]['name'].replace(self.name+"_","")
            is_agent_call = agent_node_name in delegate_to_node
            if not is_agent_call:
                print(f"\n------check_call_to_agent return due to not is_agent_call({agent_node_name}) ------\n")
                return False
            
            tool_message = messages.ToolMessage(
                content=f"Successfully transferred to Agent `{agent_node_name}`",
                name=agent_node_name,
                tool_call_id=last_message.tool_calls[0]["id"]
            )

            print("\n------check_plan_executer------\n")
            return Command(
                update={
                    'messages':  state['messages'] + [tool_message]
                },
                goto=agent_node_name
            )  

        # Normal flow routing logic:
        # 1. If last message is AIMessage with tool_calls → go to tools
        # 2. If last message is ToolMessage → go to LLM (to process tool results)
        # 3. If last message is AIMessage without tool_calls → end (LLM finished)
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            forward_to_agent=check_call_to_agent()
            if forward_to_agent:
                return forward_to_agent
            # LLM wants to use tools
            return Command(
                update={},
                goto="tools"
            )
        else:
            # LLM finished without tool calls - end execution
            return Command(
                update={},
                goto=END
            )

    async def init(self):
        """Initialize the agent with MCP tools and LLM"""
        
        # Initialize LLMs
        config = Config(read_timeout=3600, connect_timeout=60)
        self.base_llm = get_aws_modal(config=config,additional_model_request_fields=None, temperature=0)

        self.tools:List[BaseTool] = []
        self.tools.append(combine_responses) 
        self.tools.append(structured_output_for_code)     

        for tool in self.tools:
            tool.name=self.name+"_"+tool.name  
        self.llm = self.base_llm.bind_tools(self.tools)
        self.tool_node = ToolNode(self.tools)

        # Build the graph using StateGraph
        builder = StateGraph(ChatState)
        builder.add_node('llm', self.llm_node)
        builder.add_node('tools', self.tools_node)
        builder.add_node('combine_responses', self.combine_responses)
        builder.add_node('structured_output_for_code', self.structured_output_for_code)
        builder.add_node('route', self.route_node)        

        builder.add_edge(START, 'llm')
        builder.add_edge("combine_responses", "route")
        builder.add_edge("structured_output_for_code", "route")
        builder.add_edge("route", END)

        self.graph = builder.compile(name=self.name)
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

        print("Agent cleanup completed")