import { useCallback, useRef, useEffect } from "react";
import { HttpAgent } from "@ag-ui/client";
import type { RunData, ChatDisplayMessage, TokenUsage, InterruptPrompt } from "../types";
import { getAgentState } from "../services/api";
import { mapStateMessagesToAGUI } from "../services/messageMapper";
import { randomUUID } from "../utils";

interface UseAgentServiceProps {
  setIsRunning: (running: boolean) => void;
  currentMessage: ChatDisplayMessage | null;
  setCurrentMessage: (message: ChatDisplayMessage | null) => void;
  currentToolCalls: Map<string, {
    id: string;
    name: string;
    args: string;
    result?: string;
    isComplete?: boolean;
  }>;
  setCurrentToolCalls: React.Dispatch<React.SetStateAction<Map<string, {
    id: string;
    name: string;
    args: string;
    result?: string;
    isComplete?: boolean;
  }>>>;
  setCurrentTokenUsage: (usage: TokenUsage | null) => void;
  setChatMessages: React.Dispatch<React.SetStateAction<ChatDisplayMessage[]>>;
  setInterruptPrompt: React.Dispatch<React.SetStateAction<InterruptPrompt | null>>;
}

export const useAgentService = ({
  setIsRunning,
  currentMessage,
  setCurrentMessage,
  currentToolCalls,
  setCurrentToolCalls,
  setCurrentTokenUsage,
  setChatMessages,
  setInterruptPrompt,
}: UseAgentServiceProps) => {
  
  // Use refs to track mutable state that needs to be accessed in frequently called callbacks
  const currentMessageRef = useRef<ChatDisplayMessage | null>(null);
  const currentToolCallsRef = useRef<Map<string, {
    id: string;
    name: string;
    args: string;
    result?: string;
    isComplete?: boolean;
  }>>(new Map());
  
  // Sync refs with state
  useEffect(() => {
    currentMessageRef.current = currentMessage;
  }, [currentMessage]);
  
  useEffect(() => {
    currentToolCallsRef.current = currentToolCalls;
  }, [currentToolCalls]);
  
  const handleInterrupt = useCallback((message: string): Promise<string> => {
    return new Promise((resolve) => {
      const interruptId = randomUUID();
      
      // Add interrupt message to chat
      const interruptMessage: ChatDisplayMessage = {
        id: interruptId,
        message_type: "interrupt",
        role: "system",
        content: message,
        timestamp: new Date(),
        isComplete: false,
        interruptData: {
          question: message,
          isActive: true,
        }
      };
      
      setChatMessages((prev) => [...prev, interruptMessage]);
      
      const onSubmit = (response: string) => {
        // Determine response type
        const responseType: "yes" | "no" | "custom" = 
          response.toLowerCase().trim() === "yes" ? "yes" :
          response.toLowerCase().trim() === "no" ? "no" : "custom";
        
        // Update the interrupt message with response
        setChatMessages((prev) => 
          prev.map(msg => 
            msg.id === interruptId 
              ? {
                  ...msg,
                  isComplete: true,
                  interruptData: {
                    ...msg.interruptData!,
                    isActive: false,
                    response,
                    responseType
                  }
                }
              : msg
          )
        );
        
        setInterruptPrompt(null);
        resolve(response);
      };
      
      const onCancel = () => {
        // Update the interrupt message as cancelled
        setChatMessages((prev) => 
          prev.map(msg => 
            msg.id === interruptId 
              ? {
                  ...msg,
                  isComplete: true,
                  interruptData: {
                    ...msg.interruptData!,
                    isActive: false,
                    response: "",
                    responseType: "no"
                  }
                }
              : msg
          )
        );
        
        setInterruptPrompt(null);
        resolve("");
      };
      
      setInterruptPrompt({
        id: interruptId,
        message,
        isActive: true,
        onSubmit,
        onCancel,
      });
      
      // Log the interrupt to the console as well
      console.log(`\n⚠️ ${message}`);
    });
  }, [setChatMessages, setInterruptPrompt]);
  
  const chatWithAgent = useCallback(
    async function chatWithAgent(
      content: string,
      thread_id?: string
    ): Promise<{
      threadId: string;
      originalRunId: string;
    }> {
      setIsRunning(true);

      const agent = await (async () => {
        if (!thread_id) {
          return new HttpAgent({
            url: `http://localhost:8000/ag-ui/`,
          });
        }
        const state = await getAgentState(thread_id);
        return new HttpAgent({
          url: `http://localhost:8000/ag-ui/`,
          // debug: true,
          threadId: thread_id,
          initialState: state,
          initialMessages: mapStateMessagesToAGUI(state.messages),
        });
      })();

      console.log("🆔 Thread ID:", agent.threadId);
      console.log("------ Your query:", content);

      agent.messages.push({
        id: randomUUID(),
        role: "user",
        content: content,
      });

      const originalRunId = randomUUID(); // Create runId once and reuse it

      // Function to handle a single conversation run with interrupt handling
      async function runWithInterruptHandling(
        runData: RunData,
        isResume = false
      ): Promise<void> {
        return new Promise((resolve, reject) => {
          // For resume operations, restore state from server
          if (isResume) {
            // For resume calls, restore messages from server state
            getAgentState(agent.threadId).then(state => {
              console.log("Restoring messages from state:", state.messages?.length);
              agent.messages = mapStateMessagesToAGUI(state.messages);
              executeAgent();
            }).catch((error) => {
              console.error("Failed to restore state:", error);
              executeAgent(); // Continue anyway
            });
            return; // Exit early, executeAgent will be called in the then block
          }

          executeAgent();

          function executeAgent() {
            agent
              .runAgent(runData, {
              onRunStartedEvent({ event }) {
                console.log(
                  "🚀 Run started:",
                  event.runId,
                  Object.keys(event),
                  content
                );
              },
              
              onTextMessageStartEvent({ event }) {
                console.log(
                  "🤖 AG-UI assistant: ",
                  Object.keys(event),
                  content
                );
                
                // Create new current message for streaming
                const newMessage: ChatDisplayMessage = {
                  id: event.messageId,
                  message_type: "assistance",
                  role: "assistant",
                  content: "",
                  timestamp: new Date(),
                  isStreaming: true,
                  isComplete: false,
                };
                
                setCurrentMessage(newMessage);
                currentMessageRef.current = newMessage;
                
                // Clear any existing tool calls
                setCurrentToolCalls(new Map());
                currentToolCallsRef.current = new Map();
              },
              
              onTextMessageContentEvent({ event }) {
                console.log("📝 Streaming content delta:", event.delta);
                
                // Update current message with new content using ref for latest state
                const currentMsg = currentMessageRef.current;
                if (currentMsg && currentMsg.id === event.messageId) {
                  const updatedMessage = {
                    ...currentMsg,
                    content: currentMsg.content + event.delta,
                  };
                  setCurrentMessage(updatedMessage);
                  currentMessageRef.current = updatedMessage;
                }
              },
              
              onTextMessageEndEvent({ event }) {
                console.log("🏁 Text message ended for messageId:", event.messageId);
                
                // Mark current message as complete but keep it as current until run finalizes
                const currentMsg = currentMessageRef.current;
                if (currentMsg && currentMsg.id === event.messageId) {
                  const finalMessage = {
                    ...currentMsg,
                    isStreaming: false,
                    isComplete: true,
                  };
                  setCurrentMessage(finalMessage);
                  currentMessageRef.current = finalMessage;
                }
              },
              
              onToolCallStartEvent({ event }) {
                console.log(
                  "🔧 Tool call start:",
                  event.toolCallName,
                  event.toolCallId
                );
                
                // Add new tool call to map
                const newToolCall = {
                  id: event.toolCallId,
                  name: event.toolCallName,
                  args: "",
                  isComplete: false,
                };
                
                setCurrentToolCalls(prev => {
                  const newMap = new Map(prev);
                  newMap.set(event.toolCallId, newToolCall);
                  currentToolCallsRef.current = newMap;
                  return newMap;
                });
              },
              
              onToolCallArgsEvent({ event }) {
                console.log("🔧 Tool call args delta:", event.delta);
                
                // Update tool call arguments using ref for latest state
                setCurrentToolCalls(prev => {
                  const newMap = new Map(prev);
                  const existingCall = newMap.get(event.toolCallId);
                  if (existingCall) {
                    newMap.set(event.toolCallId, {
                      ...existingCall,
                      args: existingCall.args + event.delta,
                    });
                  }
                  currentToolCallsRef.current = newMap;
                  return newMap;
                });
              },
              
              onToolCallEndEvent({ event }) {
                console.log("🔧 Tool call end:", event.toolCallId);
                
                // Mark tool call as complete
                setCurrentToolCalls(prev => {
                  const newMap = new Map(prev);
                  const existingCall = newMap.get(event.toolCallId);
                  if (existingCall) {
                    newMap.set(event.toolCallId, {
                      ...existingCall,
                      isComplete: true,
                    });
                  }
                  currentToolCallsRef.current = newMap;
                  return newMap;
                });
              },
              
              onToolCallResultEvent({ event }) {
                console.log("🔍 Tool call result:", event.content);
                
                // Update tool call with result
                setCurrentToolCalls(prev => {
                  const newMap = new Map(prev);
                  const existingCall = newMap.get(event.toolCallId);
                  if (existingCall) {
                    newMap.set(event.toolCallId, {
                      ...existingCall,
                      result: event.content,
                      isComplete: true,
                    });
                  }
                  currentToolCallsRef.current = newMap;
                  return newMap;
                });
              },
              
              async onCustomEvent({ event }) {
                console.log("📋 Custom event received:", event.name);
                if (event.name === "on_interrupt") {
                  try {
                    const userChoice = await handleInterrupt(event.value);
                    console.log(`User responded: ${userChoice}`);
                    
                    // Resume with the user's choice using the same agent instance
                    const resumeRunData = {
                      runId: originalRunId, // Keep the same runId
                      forwardedProps: {
                        command: {
                          resume: userChoice,
                        },
                        node_name: "route"
                      },
                    };
                    
                    // Recursively handle the resumed run with same agent instance
                    await runWithInterruptHandling(resumeRunData, true);
                  } catch (error) {
                    console.error("Error handling interrupt:", error instanceof Error ? error.message : error);
                  }
                }
              },
              
              onRunFailed({ error }) {
                console.error("❌ Run failed:", error);
                reject(new Error(`Run failed: ${error.message || 'Unknown error'}`));
              },
              
              onStateSnapshotEvent(event) {
                console.log(
                  "==onStateSnapshotEvent",
                  Object.keys(event),
                  event.messages?.length,
                  content
                );
                // Update agent messages with snapshot (like in main.js)
                agent.messages = event.messages;
              },
              
              onStateDeltaEvent(event) {
                console.log(
                  "++onStateDeltaEvent",
                  Object.keys(event),
                  event.messages?.length
                );
                // Apply delta updates if needed
              },
              
              onRawEvent({ event: rawEventData }) {
                // Check for token usage in chat model end events
                if (rawEventData.rawEvent?.event === "on_chat_model_end" && 
                    rawEventData.rawEvent?.data?.output?.usage_metadata) {
                  const usage = rawEventData.rawEvent.data.output.usage_metadata;
                  const modelName = rawEventData.rawEvent.data.output.response_metadata?.model_name;
                  
                  setCurrentTokenUsage({
                    input_tokens: usage.input_tokens || 0,
                    output_tokens: usage.output_tokens || 0,
                    total_tokens: usage.total_tokens || 0,
                    model_name: modelName
                  });
                  
                  console.log(`📊 Token usage: ${usage.input_tokens} input + ${usage.output_tokens} output = ${usage.total_tokens} total tokens (${modelName})`);
                }
                
                // Also check for token usage in stream events
                if (rawEventData.rawEvent?.event === "on_chat_model_stream" && 
                    rawEventData.rawEvent?.data?.chunk?.usage_metadata) {
                  const usage = rawEventData.rawEvent.data.chunk.usage_metadata;
                  const modelName = rawEventData.rawEvent.data.chunk.response_metadata?.model_name;
                  
                  setCurrentTokenUsage({
                    input_tokens: usage.input_tokens || 0,
                    output_tokens: usage.output_tokens || 0,
                    total_tokens: usage.total_tokens || 0,
                    model_name: modelName
                  });
                  
                  console.log(`📊 Token usage (streaming): ${usage.input_tokens} input + ${usage.output_tokens} output = ${usage.total_tokens} total tokens (${modelName})`);
                }
              },
              
              onRunFinalized(event) {
                console.log(
                  `✅ Run finalized - ${
                    event.messages?.length || 0
                  } messages`,
                  Object.keys(event),
                  event.messages?.map((m: { role: string }) => m.role),
                  content
                );
                
                // When the run is finalized, we should finalize the current message
                console.log("🏁 Run finalized - finalizing current message");
                const currentMsg = currentMessageRef.current;
                if (currentMsg) {
                  const finalMessage = {
                    ...currentMsg,
                    isComplete: true,
                    isStreaming: false,
                    // Add tool calls if any
                    toolCalls: currentToolCallsRef.current.size > 0 ? 
                      Array.from(currentToolCallsRef.current.values()) : undefined
                  };
                  
                  // Add message to chat history
                  setChatMessages(prev => {
                    // Check if message already exists to avoid duplicates
                    const existingIndex = prev.findIndex(msg => msg.id === finalMessage.id);
                    if (existingIndex >= 0) {
                      // Update existing message
                      const newMessages = [...prev];
                      newMessages[existingIndex] = finalMessage;
                      return newMessages;
                    } else {
                      // Add new message
                      return [...prev, finalMessage];
                    }
                  });
                  
                  console.log("🏁 Message finalized and added to chat history:", finalMessage.id);
                  
                  // Clear current message state
                  setCurrentMessage(null);
                  setCurrentToolCalls(new Map());
                  currentMessageRef.current = null;
                  currentToolCallsRef.current = new Map();
                }
                
                // Mark run as completed
                setIsRunning(false);
                resolve();
              },
            })
            .then(() => {
              console.log("✅ Agent execution completed successfully");
              // Don't resolve here, wait for onRunFinalized
            })
            .catch((error) => {
              console.error("❌ Agent execution failed:", error);
              setIsRunning(false);
              reject(error);
            });
          }
        });
      }

      try {
        await runWithInterruptHandling({
          runId: originalRunId,
          // Don't explicitly pass threadId initially - let agent manage it
        });

        console.log("✅ Execution completed successfully.");
      } catch (error) {
        console.error("❌ Error running agent:", error);
        // On error, ensure we clean up the current message state
        const currentMsg = currentMessageRef.current;
        if (currentMsg) {
          const errorMessage = {
            ...currentMsg,
            isComplete: true,
            isStreaming: false
          };
          setChatMessages(prev => [...prev, errorMessage]);
          setCurrentMessage(null);
          setCurrentToolCalls(new Map());
          currentMessageRef.current = null;
          currentToolCallsRef.current = new Map();
        }
        
        // Mark run as completed even on error
        setIsRunning(false);
      }

      return {
        threadId: agent.threadId,
        originalRunId
      };
    },
    [setIsRunning, handleInterrupt, setCurrentMessage, setCurrentToolCalls, setCurrentTokenUsage, setChatMessages]
  );

  return {
    chatWithAgent,
    handleInterrupt,
  };
};
