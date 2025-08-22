
import json
from typing import Dict,TypedDict
from enum import Enum
from langgraph.types import Command,Interrupt
from langchain_core import messages as langchain_messages
from ag_ui.core import EventType
import copy

from ag_ui.core import (
    EventType,
    CustomEvent,
    MessagesSnapshotEvent,
    RawEvent,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ThinkingTextMessageStartEvent,
    ThinkingTextMessageContentEvent,
    ThinkingTextMessageEndEvent,
    ThinkingStartEvent,
    ThinkingEndEvent,
)


class EventTrackType(str, Enum):
    REGISTERED = "registered"
    START = "start"
    END = "end"


class TrackEvent(TypedDict):
    state: EventTrackType
    type: EventType


class LangGraphToAgUi:

    def __init__(self):
        self.ref={"wrap_status":None,"last_type":None,"last_id":None}
        self.tool_use_id=None

        self.event_types={}
        self.chunk_types={}
        self.parsed_events={}
        self.unparsed_events={}
        self.filtered_event=None
        self.track_event:Dict[str,TrackEvent]={} # mostly all events are sequential except tool calls

    def __get_filtered_data(self,event):
        if "event" in event:
            self.track_event[event["run_id"]]=self.track_event.get(event["run_id"],{})
            _type=event["event"]
            self.event_types[_type]=self.event_types.get(_type,0)+1
            _contents=None
            if isinstance(event.get("data",{}).get("chunk",{}),langchain_messages.BaseMessage):
                ai_msg:langchain_messages.AIMessage=event.get("data",{}).get("chunk",{})
                _contents=ai_msg.content
                self.unparsed_events[_type]=self.unparsed_events.get(_type,0)+1            
            elif event.get("data") and event["data"].get("output") and type(event["data"]["output"])==Command:  
                self.unparsed_events[_type]=self.unparsed_events.get(_type,0)+1           
                return None
            elif (event.get("data") and event["data"].get("chunk") and type(event["data"]["chunk"])==Command):
                self.unparsed_events[_type]=self.unparsed_events.get(_type,0)+1   
                return None
            elif event.get("data",{}).get("chunk",{}).get("__interrupt__",False):
                _interrupt:Interrupt= event["data"]["chunk"]["__interrupt__"]
                _contents={
                    "type": "interrupt",
                    "value":_interrupt[0].value,
                    "id": _interrupt[0].id,
                }            
            elif _type in ["on_tool_start","on_tool_end"]:
                pass
            elif not isinstance(event.get("data",{}).get("chunk",{}),langchain_messages.BaseMessage):
                if event.get("data",{}).get("chunk",{}).get("start_conv",True):
                    self.unparsed_events[_type]=self.unparsed_events.get(_type,0)+1   
                    return None
                if event.get("data",{}).get("chunk",{}).get("llm",True):
                    self.unparsed_events[_type]=self.unparsed_events.get(_type,0)+1   
                    return None
                if event.get("data",{}).get("chunk",{}).get("route",True):
                    self.unparsed_events[_type]=self.unparsed_events.get(_type,0)+1   
                    return None      
                print("Unhandled", event)    
            elif event.get("data") and event["data"].get("input") and event["data"]["input"].get("store"):
                event["data"]["input"]["store"] = "Accessing to store information"   
            else:
                _contents=event.get("data",{}).get("chunk",{}).get("content")
            self.parsed_events[_type]=self.parsed_events.get(_type,0)+1
            if _type=="on_chat_model_stream" and _contents is not None and type(_contents) is list:
                for _content in _contents:
                    if "type" in _content:
                        self.chunk_types[_type]=self.chunk_types.get(_type,set()) | {_content["type"]}
            else:
                self.chunk_types[_type]=self.chunk_types.get(_type,0)+1

        return event

    
    def __process_chunk(self,event,_type,_content):
        last_type=self.ref.get("last_type",_type)
        ac_events=[]
        if _type!= last_type and last_type is not None and self.ref["wrap_status"]=="started":
            if last_type=="text":
                ac_events.append(TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=self.ref["last_id"] or ""
                ))
            elif last_type=="reasoning_content":
                ac_events.append(CustomEvent(
                    type=EventType.CUSTOM,
                    name=last_type,
                    value={"text":"","type":EventType.THINKING_TEXT_MESSAGE_END,"message_id":self.ref["last_id"] or ""}
                ))
            elif last_type=="tool_use":
                ac_events.append(CustomEvent(
                    type=EventType.CUSTOM,
                    name=last_type,
                    value={"text":"","type":EventType.TEXT_MESSAGE_END,"message_id":self.ref["last_id"] or ""}
                ))
            self.ref["wrap_status"]="ended"
            self.ref["last_id"]=None
        if _type!= last_type and self.ref["wrap_status"] != "started":
            if _type=="text":
                self.ref["last_id"]="text_"+event["run_id"]
                ac_events.append(TextMessageStartEvent(
                    type=EventType.TEXT_MESSAGE_START,
                    role='assistant',
                    message_id=self.ref["last_id"] or ""
                ))
            elif _type=="reasoning_content":
                self.ref["last_id"]="reasoning_content_"+event["run_id"]
                ac_events.append(CustomEvent(
                    type=EventType.CUSTOM,
                    name=_type,
                    value={"text":"","type":EventType.THINKING_TEXT_MESSAGE_START,"message_id":self.ref["last_id"] or ""},
                ))
            elif _type=="tool_use":
                self.ref["last_id"]="tool_use_"+event["run_id"]
                ac_events.append(CustomEvent(
                    type=EventType.CUSTOM,
                    name=_type,
                    value={"text":"","type":EventType.TEXT_MESSAGE_START,"message_id":self.ref["last_id"] or ""},
                ))
            self.ref["wrap_status"]="started"    
        if _content:
            if _type=="text":
                if _content.get("text"):
                    ac_events.append(TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id="text_"+event["run_id"],
                        # raw_event=event,
                        delta= _content.get("text"),
                    ))
            elif _type=="tool_use":
                if _content.get("id") and _content.get("name"):
                    ac_events.append(CustomEvent(
                        type=EventType.CUSTOM,
                        # raw_event=event,
                        name=_type,
                        value= {"text":f"Proposed Tool Call: Name: {_content["name"]}, Id: {_content["id"]}","type":EventType.TEXT_MESSAGE_CONTENT,"message_id":"tool_use_"+event["run_id"]}
                    ))
                elif _content.get("input"):
                    ac_events.append(CustomEvent(
                        type=EventType.CUSTOM,
                        # raw_event=event,
                        name=_type,
                        value= {"text":f"Arguments: {_content["input"]}","type":EventType.TEXT_MESSAGE_CONTENT,"message_id":"tool_use_"+event["run_id"]}
                    ))   
            elif _type=="reasoning_content":
                reasoning_text=_content.get("reasoning_content",{}).get("text")
                if reasoning_text:
                    ac_events.append(CustomEvent(
                        type=EventType.CUSTOM,
                        name=_type,
                        value= {"text":reasoning_text,"type":EventType.THINKING_TEXT_MESSAGE_CONTENT,"message_id":"reasoning_content_"+event["run_id"]}
                    ))   
            else:
                print("Unhandled chunk type:", _type, _content)
        return ac_events
    
    def __process_chunks(self,event):
        chunks=[]
        if event["event"]=="on_chat_model_stream": # if its still chunk, close other type if any before creating new chunk
            base_message:langchain_messages.BaseMessage=event.get("data",{}).get("chunk",{})  
            _contents=base_message.content
            for i in range(len(_contents)):
                _content=_contents[i]
                if "type" in _content:
                    chunks.extend(self.__process_chunk(event, _content["type"], _content))
                    self.ref["last_type"] = _content["type"]
        elif self.ref["wrap_status"]=="started": # since this function called first, handle end of text or tool_use use for any other event
            allow_close=self.ref["last_type"] in ["text","tool_use"]
            if allow_close:
                chunks.extend(self.__process_chunk(event, event["event"], None))
                self.ref["last_type"]=None
                self.ref["wrap_status"]="ended"
                self.ref["last_id"]=None
        return chunks
        
    def __process_non_chunks(self,event):
        ac_events=[]
        if not isinstance(event.get("data",{}).get("chunk",{}),langchain_messages.BaseMessage):
            if event["event"]=="on_tool_start":
                self.ref["wrap_status"]="started"
                self.ref["last_type"]="tool_call"
                ac_events.append(ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_name=event["name"],
                    tool_call_id=event["run_id"] or"",
                    raw_event=event
                ))
                ac_events.append(ToolCallArgsEvent(
                    type=EventType.TOOL_CALL_ARGS,
                    delta=json.dumps(event["data"]["input"], default=str),
                    tool_call_id=event["run_id"] or "",
                    raw_event=event
                ))
            elif event["event"]=="on_tool_end":
                self.ref["wrap_status"]="ended"
                self.ref["last_id"]=None
                self.ref["last_type"]="tool_call"
                tool_message:langchain_messages.ToolMessage=event["data"]["output"]
                ac_events.append(ToolCallEndEvent(
                    type=EventType.TOOL_CALL_END,
                    tool_call_id=event["run_id"] or "",
                    raw_event=event
                ))
            elif event.get("data",{}).get("chunk",{}).get("__interrupt__",False):
                _interrupt:Interrupt= event["data"]["chunk"]["__interrupt__"]
                ac_events.append(CustomEvent(
                    type=EventType.CUSTOM,
                    name="on_interrupt",
                    value={
                        "text": _interrupt[0].value,
                        "id": _interrupt[0].id,
                        "type": "on_interrupt"
                    },
                    raw_event=event
                ))
            else:
                print("Unhandled event:", event)
        return ac_events

    async def __handle_event(self,event):
        chunks=[]
        chunks.extend(self.__process_chunks(event))
        chunks.extend(self.__process_non_chunks(event))           
        if chunks:
            for chunk in chunks:
                yield chunk

    async def transform_events(self,event):  # !event: don't modify event it will have reference
        # event=copy.deepcopy(event) # !Caution, avoid modifying langgraph data, since it will have reference to all its internal variables
        _event=self.__get_filtered_data(event)
        self.filtered_event=_event
        if _event is None:
            yield None
        else:
            async for transformed_event in self.__handle_event(_event):
                yield transformed_event

    def __end_events(self):
        if self.ref["wrap_status"]=="started":
            if self.ref["last_type"]=="text":
                return TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=self.ref["last_id"] or ""
                )
            elif self.ref["last_type"]=="tool_use":
                return CustomEvent(
                    type=EventType.CUSTOM,
                    name=self.ref["last_type"],
                    value={"text":"","type":EventType.TEXT_MESSAGE_END,"message_id":self.ref["last_id"] or ""}
                )
            else:
                print("Unhandled end event type:", self.ref["last_type"])
                return RawEvent(
                    type=EventType.RAW,
                    event=f"Unhandled end event type: {self.ref['last_type']}"
                )
        else:
            print("No active wrap status to end:", self.ref["wrap_status"])
            return RawEvent(
                type=EventType.RAW,
                event="No active wrap status to end"
            )

    def end_events(self):
        data=self.__end_events()
        print("event_types", self.event_types)
        print("chunk_types", self.chunk_types)
        print("parsed_events", self.parsed_events)
        print("unparsed_events", self.unparsed_events)
        self.ref= {"wrap_status": None, "last_type": None}
        return data