import { useCallback, useRef, useState } from "react";
import {
  HttpAgent,
  type CustomEvent as MessageCustomEvent,
  EventType,
  type TextMessageContentEvent,
  type ToolCallStartEvent,
  type ToolCallArgsEvent,
  type ToolCallEndEvent,
  type ToolCallResultEvent,
  type RunErrorEvent,
} from "@ag-ui/client";
import type {
  RunData,
  ChatDisplayMessage,
  TokenUsage,
  MessageEvent,
  GroupedChatDisplayMessage,
} from "../types";
import { INTERRUPT_EVENT } from "../types";
import { getAgentState } from "../services/api";
import { mapStateMessagesToAGUI } from "../services/messageMapper";
import { randomUUID } from "../utils";

export interface UseAgentService {
  isRunning: boolean;
  messages: ChatDisplayMessage[];
  groupedMessages: GroupedChatDisplayMessage[];
  totalTokenUsage: TokenUsage;
  chatWithAgent: (message: string, threadId: string) => Promise<void>;
  clearChat: () => void;
  respondToLastInterrupt: (message: string) => void;
}

/**
 * Utility function to get the latest complete messages from grouped messages.
 * Filters out partial groups to get only fully formed message blocks.
 */
export const getCompleteGroupedMessages = (
  groupedMessages: GroupedChatDisplayMessage[]
): GroupedChatDisplayMessage[] => {
  return groupedMessages.filter((group) => !group.partial);
};

/**
 * Utility function to get only partial (streaming) messages from grouped messages.
 * Useful for showing loading states or streaming content.
 */
export const getPartialGroupedMessages = (
  groupedMessages: GroupedChatDisplayMessage[]
): GroupedChatDisplayMessage[] => {
  return groupedMessages.filter((group) => group.partial);
};

/**
 * Utility function to get messages by type from grouped messages.
 */
export const getMessagesByType = (
  groupedMessages: GroupedChatDisplayMessage[],
  messageType: ChatDisplayMessage["message_type"]
): GroupedChatDisplayMessage[] => {
  return groupedMessages.filter((group) => group.group_type === messageType);
};

/**
 * Custom hook for managing agent service interactions with efficient message grouping.
 *
 * Features:
 * - Efficiently groups messages by type and message lifecycle (start/content/end)
 * - Uses incremental ID tracking to process only new messages during frequent streaming
 * - Maintains partial state for incomplete message blocks
 * - Automatically handles message state transitions from start -> content -> end
 *
 * The grouping algorithm:
 * 1. Only processes messages with IDs greater than lastProcessedId for efficiency
 * 2. Groups messages by message_type ("assistance", "tool", "interrupt", "user")
 * 3. Tracks partial state - true for incomplete messages, false for complete ones
 * 4. Handles three block types:
 *    - "start": Creates new group, marks as partial
 *    - "content": Updates existing group or creates new one for standalone content
 *    - "end": Marks group as complete (partial = false)
 *
 * @returns {UseAgentService} Object containing messages, groupedMessages, and control functions
 */
export const useAgentService = (): UseAgentService => {
  const messages_ids = useRef<number>(0);
  const messages_ref = useRef<ChatDisplayMessage[]>([]);
  const groupedMessages_ref = useRef<GroupedChatDisplayMessage[]>([]);
  const lastProcessedId = useRef<number>(-1);

  const [messages, setMessages] = useState<ChatDisplayMessage[]>([]);
  const [groupedMessages, setGroupedMessages] = useState<
    GroupedChatDisplayMessage[]
  >([]);
  const [isRunning, setIsRunning] = useState(false);
  const [totalTokenUsage, setTotalTokenUsage] = useState<TokenUsage>({
    totalInput: 0,
    totalOutput: 0,
    totalTokens: 0,
  });

  // Efficient message grouping function
  // Only processes new messages since last update for performance during streaming
  const groupMessagesByType = useCallback(() => {
    const currentMessages = messages_ref.current;
    const currentGroups = groupedMessages_ref.current;

    // Find new messages since last processing - efficient filtering by ID comparison
    const newMessages = currentMessages.filter(
      (msg) => typeof msg.id === "number" && msg.id > lastProcessedId.current
    );

    if (newMessages.length === 0) {
      return; // No new messages to process
    }

    // Process each new message and update grouping
    newMessages.forEach((message) => {
      const messageType = message.message_type;
      const messageId =
        typeof message.id === "number"
          ? message.id
          : parseInt(String(message.id));

      // Find existing partial group for this message type
      const existingGroup = currentGroups.find(
        (group) => group.group_type === messageType && group.partial
      );

      if (message.block === "start") {
        // Start of a new message block - create new group or mark existing as partial
        const currentExistingGroup = currentGroups.find(
          (group) => group.group_type === messageType && group.partial
        );

        if (currentExistingGroup && currentExistingGroup.partial) {
          // Complete the previous partial group
          currentExistingGroup.partial = false;
        }

        // Create new group for this message
        const newGroup: GroupedChatDisplayMessage = {
          id: messageId,
          messages: [message],
          group_type: messageType,
          partial: true,
        };
        currentGroups.push(newGroup);
      } else if (message.block === "content") {
        // Content of ongoing message - add to existing group or create new one
        if (!existingGroup) {
          // No existing partial group, create new one (for standalone content messages)
          const newGroup: GroupedChatDisplayMessage = {
            id: messageId,
            messages: [message],
            group_type: messageType,
            partial: message.message_type !== "user", // User messages are typically complete
          };
          currentGroups.push(newGroup);
        } else {
          // Add to existing partial group
          const existingMessageIndex = existingGroup.messages.findIndex(
            (msg) => msg.id === message.id
          );
          if (existingMessageIndex >= 0) {
            // Update existing message in group
            existingGroup.messages[existingMessageIndex] = message;
          } else {
            // Add new message to group
            existingGroup.messages.push(message);
          }
        }
      } else if (message.block === "end") {
        // End of message block - mark group as complete
        if (existingGroup) {
          const existingMessageIndex = existingGroup.messages.findIndex(
            (msg) => msg.id === message.id
          );
          if (existingMessageIndex >= 0) {
            // Update existing message in group
            existingGroup.messages[existingMessageIndex] = message;
          } else {
            // Add final message to group
            existingGroup.messages.push(message);
          }
          existingGroup.partial = false;
        } else {
          // No existing group, create completed group
          const newGroup: GroupedChatDisplayMessage = {
            id: messageId,
            messages: [message],
            group_type: messageType,
            partial: false,
          };
          currentGroups.push(newGroup);
        }
      }

      // Update last processed ID for efficient future filtering
      if (messageId > lastProcessedId.current) {
        lastProcessedId.current = messageId;
      }
    });

    // Update state with new grouped messages
    setGroupedMessages([...currentGroups]);
  }, []);

  const updateMessages = useCallback(() => {
    setMessages([...messages_ref.current]);
    groupMessagesByType();
  }, [groupMessagesByType]);

  const pushMessages = useCallback(
    (event: MessageEvent):  number => {
      const return_id = (() => {
        switch (event.type) {
          case EventType.CUSTOM: {
            const customEvent = event as MessageCustomEvent;
            switch (customEvent.name) {
              case "on_interrupt":
                messages_ref.current.push({
                  id: messages_ids.current++,
                  message_type: "interrupt",
                  block: "start",
                  interruptData: {
                    question: customEvent.value,
                    isActive: true,
                  },
                });
                return messages_ids.current-1;
              case "user_start_chat":
                messages_ref.current.push({
                  id: messages_ids.current++,
                  message_type: "user",
                  block: "content",
                  content: customEvent.value,
                });
                return messages_ids.current-1;
            }
            break;
          }
          case EventType.TEXT_MESSAGE_START: {
            messages_ref.current.push({
              id: messages_ids.current++,
              message_type: "assistance",
              block: "start",
              content: "",
            });
            return messages_ids.current-1;
          }
          case EventType.TEXT_MESSAGE_CONTENT: {
            const contentEvent = event as TextMessageContentEvent;
            const lastMessage =
              messages_ref.current[messages_ref.current.length - 1];
            if (
              lastMessage &&
              (lastMessage.message_type === "assistance" ||
                lastMessage.message_type === "tool")
            ) {
              lastMessage.content =
                (lastMessage.content || "") + contentEvent.delta;
              lastMessage.block = "content";
            }
            return lastMessage?.id || -1;
          }
          case EventType.TEXT_MESSAGE_END: {
            // Message is complete, mark it as ended
            const lastMessage =
              messages_ref.current[messages_ref.current.length - 1];
            if (
              lastMessage &&
              (lastMessage.message_type === "assistance" ||
                lastMessage.message_type === "tool")
            ) {
              lastMessage.block = "end";
            }
            return lastMessage?.id || -1;
          }
          case EventType.TOOL_CALL_START: {
            const toolEvent = event as ToolCallStartEvent;
            const lastMessage =
              messages_ref.current[messages_ref.current.length - 1];
            
            // Check if we have an existing message that can be used for tool calls
            if (lastMessage && lastMessage.message_type === "tool") {
              // Change message type to "tool" to properly categorize tool call messages
              lastMessage.message_type = "tool";
              
              if (!lastMessage.toolCalls) {
                lastMessage.toolCalls = [];
              }
              lastMessage.toolCalls.push({
                id: toolEvent.toolCallId,
                name: toolEvent.toolCallName,
                args: "",
                isComplete: false,
              });
              // Update block to content when tool calls are happening
              lastMessage.block = "content";
            } else {
              // Create a new tool message if no existing message can be used
              messages_ref.current.push({
                id: messages_ids.current++,
                message_type: "tool",
                block: "content",
                content: "",
                toolCalls: [{
                  id: toolEvent.toolCallId,
                  name: toolEvent.toolCallName,
                  args: "",
                  isComplete: false,
                }],
              });
              return messages_ids.current - 1;
            }
            return lastMessage?.id || -1;
          }
          case EventType.TOOL_CALL_ARGS: {
            const argsEvent = event as ToolCallArgsEvent;
            const lastMessage =
              messages_ref.current[messages_ref.current.length - 1];
            if (lastMessage && lastMessage.message_type === "tool" && lastMessage.toolCalls) {
              const toolCall = lastMessage.toolCalls.find(
                (tc) => tc.id === argsEvent.toolCallId
              );
              if (toolCall) {
                toolCall.args += argsEvent.delta || "";
              }
              // Keep block as content while receiving args
              lastMessage.block = "content";
            }
            return lastMessage?.id || -1;
          }
          case EventType.TOOL_CALL_END: {
            const endEvent = event as ToolCallEndEvent;
            const lastMessage =
              messages_ref.current[messages_ref.current.length - 1];
            if (lastMessage && lastMessage.message_type === "tool" && lastMessage.toolCalls) {
              lastMessage.toolCalls[0].args=JSON.stringify(event.rawEvent?.event?.data?.input) ?? lastMessage.toolCalls[0].args
              const toolCall = lastMessage.toolCalls.find(
                (tc) => tc.id === endEvent.toolCallId
              );
              if (toolCall) {
                toolCall.isComplete = true;
              }
              // Check if all tool calls are complete to determine block status
              const allComplete = lastMessage.toolCalls.every(
                (tc) => tc.isComplete
              );
              if (allComplete) {
                lastMessage.block = "content"; // Keep as content, will be set to end by TEXT_MESSAGE_END
              }
            }
            return lastMessage?.id || -1;
          }
          case EventType.TOOL_CALL_RESULT: {
            const resultEvent = event as ToolCallResultEvent;
            const lastMessage =
              messages_ref.current[messages_ref.current.length - 1];
            if (lastMessage && lastMessage.message_type === "tool" && lastMessage.toolCalls) {
              const toolCall = lastMessage.toolCalls.find(
                (tc) => tc.id === resultEvent.toolCallId
              );
              if (toolCall) {
                toolCall.result = resultEvent.content || "";
              }
              // Keep block as content while receiving results
              lastMessage.block = "content";
            }
            return lastMessage?.id || -1;
          }
          case EventType.RUN_STARTED: {
            // Run started - could be used for loading states
            return -1;
          }
          case EventType.RUN_ERROR: {
            const errorEvent = event as RunErrorEvent;
            // Handle run errors by adding an error message with assistance type
            messages_ref.current.push({
              id: messages_ids.current++,
              message_type: "assistance",
              block: "end",
              content: `❌ Error: ${
                errorEvent.message || "An error occurred during execution"
              }`,
            });
            return messages_ids.current-1;
          }
          case EventType.STATE_DELTA:
          case EventType.STATE_SNAPSHOT: {
            // State events - these might be used for debugging or state management
            // For now, we'll just ignore them in the UI
            return -1;
          }
        }
        return -1;
      })();
      updateMessages();
      return return_id as number;
    },
    [updateMessages]
  );

  const clearChat = useCallback(() => {
    messages_ids.current = 0;
    messages_ref.current = [];
    groupedMessages_ref.current = [];
    lastProcessedId.current = -1;
    setMessages([]);
    setGroupedMessages([]);
    setTotalTokenUsage({
      totalInput: 0,
      totalOutput: 0,
      totalTokens: 0,
    });
  }, []);

  const respondToLastInterrupt = useCallback((message: string) => {
    const event = new CustomEvent(INTERRUPT_EVENT, { detail: message });
    document.dispatchEvent(event);
  }, []);

  const handleInterrupt = useCallback(
    (interruptData: unknown): Promise<string> => {
      const customEvent: MessageCustomEvent = {
        type: EventType.CUSTOM,
        name: "on_interrupt",
        value: interruptData,
      };
      const id = pushMessages(customEvent);
      if (id === -1) return Promise.reject("Failed to push messages");
      return new Promise((resolve) => {
        document.addEventListener(
          INTERRUPT_EVENT,
          (event) => {
            const detail = (event as CustomEvent).detail;
            if (messages_ref.current[id]?.interruptData) {
              messages_ref.current[id].interruptData.isActive = false;
              messages_ref.current[id].interruptData.response = detail;
              updateMessages();
            }
            resolve(detail);
          },
          { once: true }
        );
      });
    },
    [pushMessages, updateMessages]
  );

  const chatWithAgent = useCallback(
    async (message: string, threadId: string,userId:string="guru"): Promise<void> => {
      // Prevent concurrent runs
      if (isRunning) {
        console.warn("⚠️ Agent is already running. Ignoring new request.");
        return;
      }

      setIsRunning(true);
      const agent = await (async () => {
        if (!threadId) {
          return new HttpAgent({
            url: `http://localhost:8000/ag-ui/`,
            // debug: true,
          });
        }
        // const state = await getAgentState(threadId);
        return new HttpAgent({
          url: `http://localhost:8000/ag-ui/`,
          // debug: true,
          threadId: threadId,
          // initialState: state,
          // initialMessages: mapStateMessagesToAGUI(state.messages),
        });
      })();
      agent.messages.push({
        id: randomUUID(),
        role: "user",
        content: message,
      });
      pushMessages({
        type: EventType.CUSTOM,
        name: "user_start_chat",
        value: message,
      });
      const runId = randomUUID();
      console.log("🆔 Thread ID:", agent.threadId);
      console.log("------ Your query:", message);

      let isResume = true;
      let runConfig: RunData = {
        runId: runId,
        forwardedProps:{
          user_id:userId,
        }
      };

      while (isResume) {
        async function runWithInterruptHandling(runData: RunData) {
          if (runConfig.forwardedProps?.command?.resume) {
            agent.messages=[]
            // const s = await getAgentState(agent.threadId);
            // console.log("messagess", s);
            // agent.messages = mapStateMessagesToAGUI(s.messages);
          }

          isResume = false;

          return new Promise<void>((resolve, reject) => {
            agent
              .runAgent(runData, {
                onRunStartedEvent(event) {
                  console.log(
                    "🚀 Run started:",
                    event.event.runId,
                    Object.keys(event),
                    event.messages?.length,
                    event.messages?.map((m) => m.role),
                    message
                  );
                  pushMessages(event.event);
                },
                onTextMessageStartEvent(event) {
                  console.log(
                    "🤖 AG-UI assistant: ",
                    Object.keys(event),
                    event.messages?.length,
                    event.messages?.map((m) => m.role),
                    message
                  );
                  pushMessages(event.event);
                },
                onTextMessageContentEvent({ event }) {
                  // console.log(JSON.stringify(event, null, 2));
                  console.log(event.delta);
                  pushMessages(event);
                },
                onTextMessageEndEvent(event) {
                  console.log("");
                  pushMessages(event.event);
                },
                onRawEvent({event}){
                  console.log("📡 Raw event:", event,typeof(event.event));
                  
                  // Handle tool call events via raw events
                  if (event.event && typeof event.event === 'object') {
                    const rawEventData = event.event;

                    if(event.event?.additional_kwargs?.hidden_from_chat) {
                      console.log("🔒 Hidden from chat:", event.event.additional_kwargs.hidden_from_chat);
                      return;  // Skip processing this event
                    }

                    // Handle tool start event
                    if (rawEventData.event === 'on_tool_start') {
                      console.log(
                        "🔧 Tool call start (raw):",
                        rawEventData.name,
                        rawEventData.run_id
                      );
                      console.log("tool==>", rawEventData.name);
                      
                      // Create a synthetic tool call start event for compatibility
                      const syntheticEvent: ToolCallStartEvent = {
                        type: EventType.TOOL_CALL_START,
                        toolCallId: rawEventData.run_id,
                        toolCallName: rawEventData.name,
                        timestamp: Date.now(),
                        rawEvent: event
                      };
                      pushMessages(syntheticEvent);
                    }
                    
                    // Handle tool end event
                    else if (rawEventData.event === 'on_tool_end') {
                      console.log("🔧 Tool call end (raw):", rawEventData.run_id);
                      console.log("tool==>", rawEventData.name);
                      
                      // Extract tool result content
                      let toolResult = '';
                      if (rawEventData.data && rawEventData.data.output) {
                        if (typeof rawEventData.data.output === 'string') {
                          toolResult = rawEventData.data.output;
                        } else if (rawEventData.data.output.content) {
                          toolResult = rawEventData.data.output.content;
                        }
                      }
                      
                      console.log("🔍 Tool call result (raw):", toolResult);
                      console.log("tool==>", toolResult);
                      
                      // Create synthetic tool call end and result events for compatibility
                      const syntheticEndEvent: ToolCallEndEvent = {
                        type: EventType.TOOL_CALL_END,
                        toolCallId: rawEventData.run_id,
                        timestamp: Date.now(),
                        rawEvent: event
                      };
                      
                      const syntheticResultEvent: ToolCallResultEvent = {
                        type: EventType.TOOL_CALL_RESULT,
                        messageId: `msg-${rawEventData.run_id}`,
                        toolCallId: rawEventData.run_id,
                        content: toolResult,
                        role: 'tool',
                        timestamp: Date.now(),
                        rawEvent: event
                      };
                      
                      pushMessages(syntheticEndEvent);
                      pushMessages(syntheticResultEvent);
                    }
                  }
                },
                onRunFailed(error) {
                  console.error("❌ Run failed:", error);
                },
                async onCustomEvent({ event }) {
                  console.log("📋 Custom event received:", event.name);
                  if (event.name === "on_interrupt") {
                    try {
                      const userChoice = await handleInterrupt(event.value?.text ?? event.value);
                      console.log(`User responded: ${userChoice}`);
                      // Instead of recursively calling runWithInterruptHandling,
                      // let the current run continue by resolving the promise
                      // The agent will handle the resume internally
                      runConfig = {
                        runId: runId,
                        forwardedProps: {
                          user_id:userId,
                          command: {
                            resume: userChoice,
                          },
                          // node_name: "route",
                        },
                      };
                      console.log(
                        "Interrupt handled, continuing current run..."
                      );
                      isResume=true
                    } catch (error: unknown) {
                      if (error instanceof Error) {
                        console.error(
                          "Error handling interrupt:",
                          error.message
                        );
                      } else {
                        console.error(
                          "Error handling interrupt:",
                          String(error)
                        );
                      }
                      reject(new Error(`Interrupt handling failed: ${error}`));
                    }
                  }
                },
                onRunErrorEvent(error) {
                  console.error("AG-UI Agent error:", error);
                  reject(error);
                },
                
              })
              .then(() => {
                resolve();
              })
              .catch((error) => {
                console.error("❌ Agent run failed:", error);
                // Add specific handling for step-related errors
                if (
                  error?.message?.includes("Step") &&
                  error?.message?.includes("already active")
                ) {
                  console.error(
                    "💡 This appears to be a step management issue. The agent may be trying to start a step that's already running."
                  );
                  console.error(
                    "💡 Consider checking the agent's state management or avoiding concurrent runs."
                  );
                }
                pushMessages({
                  type: EventType.RUN_ERROR,
                  message:
                    error?.message ||
                    "An error occurred during agent execution",
                });
                reject(error);
              });
          });
        }

        try {
          await runWithInterruptHandling(runConfig);
          console.log("✅ Execution completed successfully.");
        } catch (error) {
          console.error("❌ Error running agent:", error);
          // Add specific error message to the chat
          pushMessages({
            type: EventType.RUN_ERROR,
            message:
              error instanceof Error
                ? error.message
                : "An unexpected error occurred",
          });
        } finally {
          setIsRunning(false);
        }
      }

    },
    [isRunning, setIsRunning, pushMessages, handleInterrupt]
  );

  return {
    messages,
    groupedMessages,
    isRunning,
    totalTokenUsage,
    chatWithAgent,
    clearChat,
    respondToLastInterrupt,
  };
};
