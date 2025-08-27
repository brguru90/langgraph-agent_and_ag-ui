import asyncio,json
from typing import Annotated, NotRequired,Dict,Optional,Any,cast
from langgraph.prebuilt import InjectedState,InjectedStore, create_react_agent
from typing import TypedDict, Literal,List
from langchain_ollama import ChatOllama
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core import messages
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph,MessagesState, START, END
from fastmcp.client.transports import StdioTransport
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastmcp import Client
from fastmcp.client.sampling import (
    SamplingMessage,
    SamplingParams,
    RequestContext,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from langchain_core.runnables.config import RunnableConfig
from langchain_core.runnables.base import RunnableBindingBase
from langchain_core.tracers.schemas import Run
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.modifier import RemoveMessage
from langchain_core.messages.utils import count_tokens_approximately
from langmem.short_term import SummarizationNode,summarize_messages,RunningSummary
from langgraph.func import entrypoint, task
import uuid
from langgraph.checkpoint.base import Checkpoint, BaseCheckpointSaver
from langchain_core.prompts.chat import ChatPromptTemplate, ChatPromptValue
from langchain_core.messages.utils import get_buffer_string
from langgraph.store.base import BaseStore,SearchItem
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import AsyncSqliteStore
from langgraph.store.redis import AsyncRedisStore
from langgraph.store.base import IndexConfig
from langchain_aws import BedrockEmbeddings
import sqlite3
import aiosqlite
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import traceback
from .coding_agent import CodingAgent
from .research_agent import ResearchAgent
from .structured_output import StructuredOutputAgent
from langgraph_supervisor.handoff import create_forward_message_tool
from .state import ChatState,SupervisorNode,PlanOutputModal,CodeSnippetsStructure
from .utils import get_aws_modal,max_tokens,AsyncSqliteSaverWrapper,create_handoff_back_node
from langgraph_supervisor import create_supervisor
from langchain_core.language_models import BaseChatModel, LanguageModelLike
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph.state import CompiledStateGraph
from langchain_core.tools import BaseTool
# from langgraph.config import get_stream_writer
from langchain_core.callbacks.manager import adispatch_custom_event
import warnings

plan_structure_parser = PydanticOutputParser(pydantic_object=PlanOutputModal)
code_structure_parser = PydanticOutputParser(pydantic_object=CodeSnippetsStructure)
plan_prompt="""
        You are a supervisor agent responsible for breaking down the user's query into a step-by-step plan for execution. 

        Your task is to generate a plan as a list of steps, following this schema:

        StepModal:
        - step_uid: Unique identifier for this step (generate a UUID or unique string)
        - agent_name: Name of the agent executing this step
        - instruction: A clear instruction describing what needs to be done in this step, and specify exactly what information is needed to avoid the unnecessary information from the agent which will overflow the context limit
        - sub_steps: List of sub-steps to be executed within this step
        - available_tools: List of tools or functions that should be used in this step (choose from the available tools)
        - response_from_previous_step: List of step_uid(s) whose responses are required as input for this step (if any)
        - response: Leave this empty for now; it will be filled after execution
        - status: Set to "pending" for all steps in the initial plan

        PlanOutputModal:
        - plan: List of StepModal objects representing the execution steps(try to keep one step within the plan for each agent, and each agent can execute multiple tool calls in its lifecycle so avoid calling the agent repeatedly just to use single tool from agent instead try to batch the tool calls in same step, to avoid re-execution of same agent)


        Guidelines:
        - Analyze the user query and break it down into logical, sequential steps.
        - For each step, specify which agents and set of tools to use and multiple agents are allowed to get the different information's or to get the missing or additional information from different sources.
        - Important!, after getting the information add one or more additional steps to find and filter the most relevant information for the user query if the information from multiple source acquired.
        - create step in plan to only extract necessary information based on user query and don't fetch additional information which may not require or may not be much important and each agent can execute multiple tool calls in its lifecycle so avoid calling the agent repeatedly just to use single tool from agent instead try to batch the tool calls in same step, to avoid crossing the context limit because of response from multiple step.
        - If a step depends on the output of a previous step, reference the step_uid(s) in response_from_previous_step.
        - A query generating new response which depends on some response_from_previous_step, in result it might not combine the response_from_previous_step always and its new response. So for the future step try to avoid the chaining response_from_previous_step from one step to another, instead include all the dependent response_from_previous_step for each step
         Example where B dependent on A's response_from_previous_step and C dependent on both A's and B's response_from_previous_step
         so instead of A -> B, B -> C consider A-> B, (A,B) -> C
        - Do not execute the steps; only generate the plan.
        - Output only the structured plan as per the schema above.
        - If the multiple user queries provided or the multiple steps involved with related response, then add one or more steps to combine the response or conclude the response meaningfully into single final response.
        - If the multiple unrelated queries provided or the multiple steps involved with unrelated response, then add one or more steps to combine all the information into different block/sections in the same single final response.
        - Don't summaries and don't loose any information from the final response while combining.
        - before combining the responses, first check whether the nature of query required the structured output if its required then first execute structured_output tools then execute the combine_responses tool.
        - While combining response to single final response, if there is a structured output then don't modify the response and keep the structured output intact.
        - use the tool calls name,descriptions, arguments as additional context to create the steps for the plan.

        Conditions for providing the structured response, if below conditions not met then don't structure the output and keep original response intact:
        - only structure the output if user explicitly asks for code implementation or executable code or runnable code or or complete code or similar
        - if the structured output for code required try to make it as single file application or single component application
        - Don't structure the output if user only ask for documentation or code snippets or example or similar
        - If the structured response is required and there are multiple chunks of information, for example if its a code implementation and there are multiple code snippets associated with multiple files, then strictly breakdown these into multiple steps in the plan and structure them individually and after structuring all the chunks of information then add one more step to finally embed them as list into single response keep the the structures in list intact.

        Note:
        - keep in mind that maximum token limit set is around {max_tokens}, so ensure the input to process final conversation is less than the maximum token limit

        think harder.

        Available Tools and Agents:
        {tools}

        If structured response for code have to be provided, then collect the information to satisfy below schema,:
        {code_structure}

        Output Schema:
        {output_schema}        
        """


class PlanExecuter:   
    def __init__(self):
        print("__PlanExecuter__")
        self.base_llm = None
        self.llm = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.agents=[]
        self.system_message="""
            - You are an supervisor agent, responsible for overseeing and managing other agents.
            - Decide the required tool call to execute agent at the beginning and don't forget to execute planned agents and may be you can understanding each agent by executing first it with dummy query or any /help command like query and list all the available tool for planning then start real execution with real query may be you can retry the original user query usually it will be first message.
            - Avoid re-executing of same agent unless the some additional information is required
            - Your primary role is to delegate tasks to specialized agents based on the user's requests and the context of the conversation.
            - you can use multiple tools and agents to achieve the desired outcome.
            - you can use tools to decide which agent to delegate a task to.
            - You should also keep track of the overall progress and ensure that all agents are working effectively towards the common goal.
            - Important!, Don't summaries the SubAgents responses

    """

        
    
    async def init_conversation(self, state: ChatState, config: RunnableConfig) ->  Command[Literal[SupervisorNode.ROUTE]]: # get_state won't  work properly in initial conv
        """Initialize the conversation state"""     
        tools=[]
        for agent in self.agents:
            graph:CompiledStateGraph=agent.graph
            agent_tools:list[BaseTool]=agent.tools
            tools.append({
                "agent_name":graph.name,
                "agent_description":agent.descriptions,
                "tools":[{"name":tool.name,"description":tool.description,"args":tool.args} for tool in agent_tools]
            })

        plan=await self.base_llm.with_structured_output(PlanOutputModal).ainvoke([messages.SystemMessage(content=self.system_message,id=str(uuid.uuid4()))]+state["messages"]+[messages.HumanMessage(content=plan_prompt.format(tools=json.dumps(tools,default=str),output_schema=plan_structure_parser.get_format_instructions(),code_structure=code_structure_parser.get_format_instructions(),max_tokens=max_tokens), id=str(uuid.uuid4()))])

        # writer = get_stream_writer()
        # writer({"event":"plan","data":plan.model_dump_json()})
        await adispatch_custom_event("plan",{"chunk":{"type":"text","text":plan.model_dump()}},config=config)

        return Command(
            update={
                "plan": plan,
                "original_messages":state["messages"]
            },
            goto=SupervisorNode.ROUTE_VAL
        )
    
   
 
    def route_node(self, state:ChatState,config: RunnableConfig) -> Command[Literal[SupervisorNode.CODING_AGENT,SupervisorNode.RESEARCH_AGENT,SupervisorNode.STRUCTURED_OUTPUT_AGENT, SupervisorNode.END_CONV]]:
        """Route node - handles all routing logic using Command pattern"""
        last_message = state['messages'][0]

        print(f"--route_node(plan executer): message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}")

        print(f"\n--route_node(plan executer-last_message):",json.dumps(last_message,default=str,indent=2),end="\n\n")

        plans=state["plan"].plan
        for plan in plans:
            if plan.status == "pending":
                instructions=plan.model_dump()
                print("\n---instructions",instructions)
                dependent_response=[dependent_plan.response.content for dependent_plan in plans if dependent_plan.step_uid in plan.response_from_previous_step and dependent_plan.response is not None]
                try:
                    dependent_response=[get_buffer_string([dependent_plan.response]) for dependent_plan in plans if dependent_plan.step_uid in plan.response_from_previous_step and dependent_plan.response]
                except Exception as e:
                    print(f"Error processing dependent responses: {e}")
                # total_input_tokens = sum(dependent_plan.response_token_size for dependent_plan in plans if dependent_plan.step_uid in plan.response_from_previous_step and dependent_plan.response_token_size is not None)
                del instructions["step_uid"]
                del instructions["agent_name"]
                del instructions["response"]
                del instructions["response_from_previous_step"]
                del instructions["response_token_size"]
                del instructions["status"]
                return Command(
                    update={
                        "tool_call_count":0,
                        'messages':  [
                            state["original_messages"][0],
                            messages.HumanMessage(content=f"current query: {plan.instruction}",id=str(uuid.uuid4())),
                            messages.HumanMessage(content=f"complete instructions:\n {json.dumps(instructions,default=str)}\n\n Depend on the responses(knowledge base):\n{dependent_response}",id=str(uuid.uuid4()))
                        ]
                    },
                    goto=plan.agent_name
                )


        return Command(
            update={},
            goto=SupervisorNode.END_CONV_VAL
        )

    def post_agent_execution(self, state: ChatState, config: RunnableConfig) ->  Command[Literal[SupervisorNode.ROUTE]]:
        plans=state["plan"].plan
        for plan in plans:
            if plan.status == "pending":
                plan.status="completed"
                plan.response=state["messages"][-1]
                plan.response_token_size=count_tokens_approximately([plan.response]) 
                break
        state["plan"].plan=plans
        return Command(
            update={
                "plans":state["plan"]
            },
            goto=SupervisorNode.ROUTE_VAL
        )

    async def before_conversation_end(self, state:ChatState,config: RunnableConfig, *, store: BaseStore):
         return Command(
            update={
                "messages": state["original_messages"] + state["messages"][-1:]
            },
            goto=END
        )

    async def init(self):
        """Initialize the agent with MCP tools and LLM"""

        # Initialize LLMs
        self.base_llm = get_aws_modal()        

        self.tools = []        

        coding_agent=CodingAgent()
        research_agent=ResearchAgent()
        structured_output_agent=StructuredOutputAgent()
        await coding_agent.init()
        await research_agent.init()
        await structured_output_agent.init()
        self.agents.append(coding_agent)
        self.agents.append(research_agent)
        self.agents.append(structured_output_agent)

        self.llm = self.base_llm.bind_tools(self.tools)            
        self.tool_node = ToolNode(self.tools)
      

        builder = StateGraph(ChatState)
        builder.add_node(SupervisorNode.START_CONV_VAL, self.init_conversation)
        builder.add_node(SupervisorNode.CODING_AGENT_VAL, create_handoff_back_node(coding_agent.graph,recursion_limit=100))
        builder.add_node(SupervisorNode.RESEARCH_AGENT_VAL, create_handoff_back_node(research_agent.graph))
        builder.add_node(SupervisorNode.STRUCTURED_OUTPUT_AGENT_VAL, create_handoff_back_node(structured_output_agent.graph))
        builder.add_node(SupervisorNode.ROUTE_VAL, self.route_node)
        builder.add_node(SupervisorNode.POST_AGENT_EXECUTION_VAL, self.post_agent_execution)
        builder.add_node(SupervisorNode.END_CONV_VAL, self.before_conversation_end)

        builder.set_entry_point(SupervisorNode.START_CONV_VAL)
        builder.add_edge(SupervisorNode.START_CONV_VAL, SupervisorNode.ROUTE_VAL)
        builder.add_edge(SupervisorNode.CODING_AGENT_VAL, SupervisorNode.POST_AGENT_EXECUTION_VAL)
        builder.add_edge(SupervisorNode.RESEARCH_AGENT_VAL, SupervisorNode.POST_AGENT_EXECUTION_VAL)
        builder.add_edge(SupervisorNode.STRUCTURED_OUTPUT_AGENT_VAL, SupervisorNode.POST_AGENT_EXECUTION_VAL)
        builder.add_edge(SupervisorNode.END_CONV_VAL, END)

        self.graph = builder.compile(debug=False, name="plan_executer")
        self.graph.get_graph().print_ascii()
        

    async def close(self):
        """Clean up resources and close connections"""
        print("Closing agent resources...")
        await self.__aexit__(None, None, None)

    # Keep the async context manager methods for backward compatibility
    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources and close connections"""
        for agent in self.agents:
            try:
                await agent.close()
            except Exception as e:
                print(f"Error closing agent {agent}: {e}")
        
        print("Agent cleanup completed")
