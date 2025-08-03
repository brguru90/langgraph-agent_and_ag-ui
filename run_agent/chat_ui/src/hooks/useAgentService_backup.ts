import { useCallback, useRef, useEffect } from "react";
import { HttpAgent } from "@ag-ui/client";
import type { RunData, ChatDisplayMessage, TokenUsage, InterruptPrompt } from "../types";
import { getAgentState } from "../services/api";
import { mapStateMessagesToAGUI } from "../services/messageMapper";
import { randomUUID } from "../utils";

interface UseAgentServiceProps {
  setIsRunning: (running: boolean) => void;
  updateCurrentMessage: (content: string) => void;
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
  updateCurrentMessage,
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
            // debug: true,
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
          // For resume operations, use the same agent instance but clear messages
          // to avoid message mismatch on server side

          if (isResume) {
            // For resume calls, temporarily clear messages - let server handle state
            // & anyway without clearing the message the response to interrupt was not working for me
            // agent.messages = []; // Clear messages for resume
            getAgentState(agent.threadId)
              .then(s => {
                console.log("messagess", s)
                agent.messages = mapStateMessagesToAGUI(s.messages)
                
                // Continue with agent execution after state is loaded
                executeAgent();
              })
              .catch(reject);
            return; // Exit early, executeAgent will be called in the then block
          }

          executeAgent();

          function executeAgent() {
            agent
              .runAgent(runData, {
              onRunStartedEvent({ event }) {
                console.log(`🚀 Run started: ${event.runId}`, Object.keys(event), content);
              },
              onTextMessageStartEvent({ event }) {
                console.log(`🤖 AG-UI assistant:`, Object.keys(event), event.messageId, content);
                
                // Always create a new message for each text message start
                const newMessage: ChatDisplayMessage = {
                  id: event.messageId,
                  message_type: "assistance",
                  role: "assistant",
                  content: "",
                  timestamp: new Date(),
                  isStreaming: true,
                  isComplete: false,
                };
                console.log("📝 Created new text message:", newMessage.id);
                setCurrentMessage(newMessage);
              },
              onTextMessageContentEvent({ event }) {
                console.log("📝 Streaming content delta:", event.delta, "for messageId:", event.messageId);
                // Always update the current message with the delta
                updateCurrentMessage(event.delta);
              },
              onTextMessageEndEvent({ event }) {
                console.log("📝 Text message ended for messageId:", event.messageId);
                // Mark the text content as complete but don't finalize yet
                // Let other events like tool calls complete first
                if (currentMessage && currentMessage.id === event.messageId) {
                  const updatedMessage = { 
                    ...currentMessage, 
                    isStreaming: false 
                  };
                  setCurrentMessage(updatedMessage);
                  console.log("📝 Text message streaming completed");
                  
                  // If this is a text-only message (no tool calls expected), 
                  // we can tentatively finalize it, but onRunFinalized will still be the authoritative source
                  if (currentToolCalls.size === 0) {
                    console.log("📝 Text-only message, preparing for finalization");
                  }
                }
              },
              onToolCallStartEvent({ event }) {
                console.log(`🔧 Tool call start: ${event.toolCallName} (${event.toolCallId})`);
                console.log("🔧 Current message state before tool call:", {
                  hasCurrentMessage: !!currentMessage,
                  currentMessageId: currentMessage?.id,
                  parentMessageId: event.parentMessageId
                });
                
                // Ensure we have a message to attach tool calls to
                // If there's no current message or the parent message ID doesn't match, create/update appropriately
                if (!currentMessage || (event.parentMessageId && currentMessage.id !== event.parentMessageId)) {
                  // If there's a parent message ID that doesn't match current message, we need to update our message reference
                  // This can happen when the assistant message contains both text and tool calls
                  if (event.parentMessageId) {
                    // Update the current message to use the parent message ID
                    const newMessage: ChatDisplayMessage = {
                      id: event.parentMessageId,
                      message_type: "assistance", // This message will contain both text and tool calls
                      role: "assistant",
                      content: currentMessage?.content || "", // Preserve any existing content
                      timestamp: new Date(),
                      isStreaming: false,
                      isComplete: false,
                    };
                    console.log("🔧 Updated message for tool calls with parent ID:", event.parentMessageId);
                    setCurrentMessage(newMessage);
                  } else {
                    // No parent message ID, create a new message for tool calls only
                    const newMessage: ChatDisplayMessage = {
                      id: randomUUID(),
                      message_type: "tool",
                      role: "assistant", 
                      content: "",
                      timestamp: new Date(),
                      isStreaming: false,
                      isComplete: false,
                    };
                    console.log("🔧 Created new tool-only message:", newMessage.id);
                    setCurrentMessage(newMessage);
                  }
                } else {
                  // Update existing message type to indicate it has tool calls
                  const updatedMessage = { 
                    ...currentMessage, 
                    message_type: "assistance" as const // Message contains both text and tool calls
                  };
                  console.log("🔧 Updated existing message to include tool calls");
                  setCurrentMessage(updatedMessage);
                }
                
                // Add tool call to tracking
                setCurrentToolCalls(prev => {
                  const newMap = new Map(prev);
                  newMap.set(event.toolCallId, {
                    id: event.toolCallId,
                    name: event.toolCallName,
                    args: "",
                    isComplete: false,
                  });
                  console.log("🔧 Added tool call to map:", event.toolCallId, "Total tool calls:", newMap.size);
                  return newMap;
                });
              },
              onToolCallArgsEvent({ event }) {
                console.log("🔧 Tool args delta:", event.delta);
                setCurrentToolCalls(prev => {
                  const newMap = new Map(prev);
                  const existing = newMap.get(event.toolCallId);
                  if (existing) {
                    newMap.set(event.toolCallId, {
                      ...existing,
                      args: existing.args + event.delta,
                    });
                  }
                  return newMap;
                });
              },
              onToolCallEndEvent({ event }) {
                console.log(`🔧 Tool call end: ${event.toolCallId}`);
                setCurrentToolCalls(prev => {
                  const newMap = new Map(prev);
                  const existing = newMap.get(event.toolCallId);
                  if (existing) {
                    newMap.set(event.toolCallId, {
                      ...existing,
                      isComplete: true,
                    });
                  }
                  return newMap;
                });
              },
              onToolCallResultEvent({ event }) {
                console.log(`🔍 Tool call result for ${event.toolCallId}:`, event.content);
                if (event.content) {
                  setCurrentToolCalls(prev => {
                    const newMap = new Map(prev);
                    const existing = newMap.get(event.toolCallId);
                    if (existing) {
                      newMap.set(event.toolCallId, {
                        ...existing,
                        result: event.content,
                      });
                    }
                    return newMap;
                  });
                }
              },
              onRunFailed({ error }) {
                console.error(`❌ Run failed: ${error}`);
                setIsRunning(false);
              },
              async onCustomEvent({ event }) {
                console.log(`📋 Custom event received: ${event.name}`);

                if (event.name === "on_interrupt") {
                  try {
                    const userChoice = await handleInterrupt(event.value);
                    console.log(`User responded: ${userChoice}`);

                    // Resume with the user's choice using the same agent instance
                    const resumeRunData: RunData = {
                      runId: originalRunId, // Keep the same runId
                      forwardedProps: {
                        command: {
                          resume: userChoice,
                        },
                      },
                    };
                    // Recursively handle the resumed run with same agent instance (maintains threadId)
                    await runWithInterruptHandling(resumeRunData, true);
                  } catch (error) {
                    console.error(`Error handling interrupt: ${
                      error instanceof Error ? error.message : error
                    }`);
                  }
                }
              },
              onStateSnapshotEvent(event) {
                // entire snapshot
                console.log(
                  `==onStateSnapshotEvent - ${event.messages.length} messages`,
                  Object.keys(event),
                  event.messages.map((m: { role: string }) => m.role),
                  content
                );
                // Update agent messages like in main.js
                agent.messages = event.messages;
              },
              onStateDeltaEvent(event) {
                // incremental update
                console.log(
                  `++onStateDeltaEvent - ${event.messages.length} messages`,
                  Object.keys(event),
                  event.messages.map((m: { role: string }) => m.role)
                );
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
                if (currentMessage) {
                  const finalMessage = {
                    ...currentMessage,
                    isComplete: true,
                    isStreaming: false
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
                }
                
                // Mark run as completed
                setIsRunning(false);
              },
            })
            .then(() => {
              resolve();
            })
            .catch((error) => {
              console.log(error);
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
        if (currentMessage) {
          console.log("🏁 Finalizing current message after error");
          const errorMessage = {
            ...currentMessage,
            isComplete: true,
            isStreaming: false
          };
          setCurrentMessage(errorMessage);
          
          // Add message to chat history even on error
          setChatMessages(prev => {
            const existingIndex = prev.findIndex(msg => msg.id === errorMessage.id);
            if (existingIndex >= 0) {
              const newMessages = [...prev];
              newMessages[existingIndex] = errorMessage;
              return newMessages;
            } else {
              return [...prev, errorMessage];
            }
          });
          
          // Clear current message state on error
          setCurrentMessage(null);
          setCurrentToolCalls(new Map());
        }
        
        // Mark run as completed even on error
        setIsRunning(false);
      }

      return {
        threadId: agent.threadId,
        originalRunId
      };
    },
    [setIsRunning, handleInterrupt, updateCurrentMessage, currentMessage, setCurrentMessage, currentToolCalls, setCurrentToolCalls, setCurrentTokenUsage, setChatMessages]
  );

  return {
    chatWithAgent,
    handleInterrupt,
  };
};
