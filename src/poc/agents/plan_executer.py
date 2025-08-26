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
from langgraph_supervisor.handoff import create_forward_message_tool
from .state import ChatState,SupervisorNode,PlanOutputModal
from .utils import get_aws_modal,max_tokens,AsyncSqliteSaverWrapper,create_handoff_back_node
from langgraph_supervisor import create_supervisor
from langchain_core.language_models import BaseChatModel, LanguageModelLike
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph.state import CompiledStateGraph
from langchain_core.tools import BaseTool

import warnings

parser = PydanticOutputParser(pydantic_object=PlanOutputModal)
plan_prompt="""
        You are a supervisor agent responsible for breaking down the user's query into a step-by-step plan for execution. 

        Your task is to generate a plan as a list of steps, following this schema:

        StepModal:
        - step_uid: Unique identifier for this step (generate a UUID or unique string)
        - agent_name: Name of the agent executing this step
        - instruction: A clear instruction describing what needs to be done in this step
        - sub_steps: List of sub-steps to be executed within this step
        - available_tools: List of tools or functions that should be used in this step (choose from the available tools)
        - response_from_previous_step: List of step_uid(s) whose responses are required as input for this step (if any)
        - response: Leave this empty for now; it will be filled after execution
        - status: Set to "pending" for all steps in the initial plan

        PlanOutputModal:
        - plan: List of StepModal objects representing the execution steps(keep one plan for each agent, to avoid re-execution of same agent)


        Guidelines:
        - Analyze the user query and break it down into logical, sequential steps.
        - For each step, specify which agents and set of tools to use.
        - If a step depends on the output of a previous step, reference the step_uid(s) in response_from_previous_step.
        - Do not execute the steps; only generate the plan.
        - Output only the structured plan as per the schema above.
        - If the multiple user queries provided, then add one or more steps to combine the response or conclude the response meaningfully into single final response.
        - If the multiple unrelated queries provided, then add one or more steps to combine all the information into different block/sections in the same single final response.

        Available Tools and Agents:
        {tools}

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
            - Decide the required tool call to execute agent at the beginning and don't forget to execute planned agents and may be you can understanding each agent by executing first it with dummy query or any /help command like query and list all the available tool for planning then start real execution with real query may be you can retry the original user query usually it will be first message or you can get the user original queries back by calling "get_user_original_queries" tool.
            - Avoid re-executing of same agent unless the some additional information is required
            - Your primary role is to delegate tasks to specialized agents based on the user's requests and the context of the conversation.
            - you can use multiple tools and agents to achieve the desired outcome.
            - you can use tools to decide which agent to delegate a task to.
            - You should also keep track of the overall progress and ensure that all agents are working effectively towards the common goal.
            - Important!, Don't summaries the SubAgents responses

    """

        
    
    def init_conversation(self, state: ChatState, config: RunnableConfig) ->  Command[Literal[SupervisorNode.ROUTE]]: # get_state won't  work properly in initial conv
        """Initialize the conversation state"""     
        tools=[]
        for agent in self.agents:
            graph:CompiledStateGraph=agent.graph
            agent_tools:list[BaseTool]=agent.tools
            tools.append({
                "agent_name":graph.name,
                "tools":[{"name":tool.name,"description":tool.description,"args":tool.args} for tool in agent_tools]
            })

        plan=self.base_llm.with_structured_output(PlanOutputModal).invoke([messages.SystemMessage(content=self.system_message,id=str(uuid.uuid4()))]+state["messages"]+[messages.HumanMessage(content=plan_prompt.format(tools=json.dumps(tools,default=str),output_schema=parser.get_format_instructions()), id=str(uuid.uuid4()))])

        return Command(
            update={
                "plan": plan
            },
            goto=SupervisorNode.ROUTE_VAL
        )
    
   
 
    def route_node(self, state:ChatState,config: RunnableConfig) -> Command[Literal[SupervisorNode.CODING_AGENT,SupervisorNode.RESEARCH_AGENT,SupervisorNode.END_CONV]]:
        """Route node - handles all routing logic using Command pattern"""
        last_message = state['messages'][0]

        print(f"--route_node(plan executer): message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}")

        print(f"\n--route_node(plan executer-last_message):",json.dumps(last_message,default=str,indent=2),end="\n\n")

        plans=state["plan"].plan
        for plan in plans:
            if plan.status == "pending":
                instructions=plan.model_dump_json()
                return Command(
                    update={
                        'messages':  [
                            last_message,
                            messages.HumanMessage(content=instructions,id=str(uuid.uuid4()))
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
            update={},
            goto=END
        )

    async def init(self):
        """Initialize the agent with MCP tools and LLM"""

        # Initialize LLMs
        self.base_llm = get_aws_modal()        

        self.tools = []        

        coding_agent=CodingAgent()
        research_agent=ResearchAgent()
        await coding_agent.init()
        await research_agent.init()
        self.agents.append(coding_agent)
        self.agents.append(research_agent)

        # mostly tool to add another tool_call messages to decide next agent
        # self.tools.append(coding_agent.get_steering_tool())
        # self.tools.append(research_agent.get_steering_tool())

        self.llm = self.base_llm.bind_tools(self.tools)            
        self.tool_node = ToolNode(self.tools)
      

        builder = StateGraph(ChatState)
        builder.add_node(SupervisorNode.START_CONV_VAL, self.init_conversation)
        builder.add_node(SupervisorNode.CODING_AGENT_VAL, create_handoff_back_node(coding_agent.graph))
        builder.add_node(SupervisorNode.RESEARCH_AGENT_VAL, create_handoff_back_node(research_agent.graph))
        builder.add_node(SupervisorNode.ROUTE_VAL, self.route_node)
        builder.add_node(SupervisorNode.POST_AGENT_EXECUTION_VAL, self.post_agent_execution)
        builder.add_node(SupervisorNode.END_CONV_VAL, self.before_conversation_end)

        builder.set_entry_point(SupervisorNode.START_CONV_VAL)
        builder.add_edge(SupervisorNode.START_CONV_VAL, SupervisorNode.ROUTE_VAL)
        builder.add_edge(SupervisorNode.CODING_AGENT_VAL, SupervisorNode.POST_AGENT_EXECUTION_VAL)
        builder.add_edge(SupervisorNode.RESEARCH_AGENT_VAL, SupervisorNode.POST_AGENT_EXECUTION_VAL)
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
