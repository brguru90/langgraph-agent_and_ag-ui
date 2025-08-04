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
} from "../types";
import { INTERRUPT_EVENT } from "../types";
import { getAgentState } from "../services/api";
import { mapStateMessagesToAGUI } from "../services/messageMapper";
import { randomUUID } from "../utils";

export interface UseAgentService {
  isRunning: boolean;
  messages: ChatDisplayMessage[];
  totalTokenUsage: TokenUsage;
  chatWithAgent: (message: string, threadId: string) => Promise<void>;
  clearChat: () => void;
  respondToLastInterrupt: (message: string) => void;
}

export const useAgentService = (): UseAgentService => {
  const messages_ids = useRef<number>(0);
  const messages_ref = useRef<ChatDisplayMessage[]>([]);
  const [messages, setMessages] = useState<ChatDisplayMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [totalTokenUsage, setTotalTokenUsage] = useState<TokenUsage>({
    totalInput: 0,
    totalOutput: 0,
    totalTokens: 0,
  });

  const updateMessages = (messages: ChatDisplayMessage[]) => {
    setMessages(messages);
  };

  const pushMessages = useCallback((event: MessageEvent): string | number => {
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
              return messages_ids.current;
            case "user_start_chat":
              messages_ref.current.push({
                id: messages_ids.current++,
                message_type: "user",
                block: "content",
                content: customEvent.value,
              });
              return messages_ids.current;
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
          return messages_ids.current;
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
          if (lastMessage && lastMessage.message_type === "assistance") {
            // Keep message type as "assistance" but add tool calls
            // Don't change message type to "tool" to allow continued text content
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
          }
          return lastMessage?.id || -1;
        }
        case EventType.TOOL_CALL_ARGS: {
          const argsEvent = event as ToolCallArgsEvent;
          const lastMessage =
            messages_ref.current[messages_ref.current.length - 1];
          if (lastMessage && lastMessage.toolCalls) {
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
          if (lastMessage && lastMessage.toolCalls) {
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
          if (lastMessage && lastMessage.toolCalls) {
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
          return messages_ids.current;
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
    updateMessages(messages_ref.current);
    return return_id;
  }, []);



  const clearChat = useCallback(() => {
    messages_ids.current = 0;
    messages_ref.current = [];
    setMessages([]);
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
        document.addEventListener(INTERRUPT_EVENT, (event) => {
          const detail = (event as CustomEvent).detail;
          if (messages_ref.current[0].interruptData) {
            messages_ref.current[0].interruptData.isActive = false;
            messages_ref.current[0].interruptData.response = detail;
            updateMessages(messages_ref.current);
          }
          resolve(detail);
        });
      });
    },
    [pushMessages]
  );

  const chatWithAgent = useCallback(
    async (message: string, threadId: string): Promise<void> => {
      setIsRunning(true);
      const agent = await (async () => {
        if (!threadId) {
          return new HttpAgent({
            url: `http://localhost:8000/ag-ui/`,
            // debug: true,
          });
        }
        const state = await getAgentState(threadId);
        return new HttpAgent({
          url: `http://localhost:8000/ag-ui/`,
          // debug: true,
          threadId: threadId,
          initialState: state,
          initialMessages: mapStateMessagesToAGUI(state.messages),
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

      async function runWithInterruptHandling(
        runData: RunData,
        isResume = false
      ) {
        if (isResume) {
          const s = await getAgentState(agent.threadId);
          console.log("messagess", s);
          agent.messages = mapStateMessagesToAGUI(s.messages);
        }

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
              onToolCallStartEvent({ event }) {
                console.log(
                  "🔧 Tool call start:",
                  event.toolCallName,
                  event.toolCallId
                );
                pushMessages(event);
              },
              onToolCallArgsEvent({ event }) {
                pushMessages(event);
              },
              onToolCallEndEvent({ event }) {
                console.log("🔧 Tool call end:", event.toolCallId);
                pushMessages(event);
              },
              onToolCallResultEvent({ event }) {
                if (event.content) {
                  console.log("🔍 Tool call result:", event.content);
                }
                pushMessages(event);
              },
              onRunFailed(error) {
                console.error("❌ Run failed:", error);
              },
              async onCustomEvent({ event }) {
                console.log("📋 Custom event received:", event.name);
                if (event.name === "on_interrupt") {
                  try {
                    const userChoice = await handleInterrupt(event.value);
                    console.log(`User responded: ${userChoice}`);
                    const resumeRunData = {
                      runId: runId,
                      forwardedProps: {
                        command: {
                          resume: userChoice,
                        },
                        node_name: "route",
                      },
                    };
                    await runWithInterruptHandling(resumeRunData, true);
                  } catch (error: unknown) {
                    if (error instanceof Error) {
                      console.error("Error handling interrupt:", error.message);
                    } else {
                      console.error("Error handling interrupt:", String(error));
                    }
                  }
                }
              },
              onRunErrorEvent(error) {
                console.error("AG-UI Agent error:", error);
                reject(error);
              },
              // onStateSnapshotEvent(event) {
              //   // console.log(
              //   //   "==onStateSnapshotEvent",
              //   //   Object.keys(event),
              //   //   event.messages.length,
              //   //   event.messages.map((m) => m.role),
              //   //   message
              //   // );
              //   agent.messages = event.messages;
              // },
              // onStateDeltaEvent(event) {
              //   // console.log(
              //   //   "++onStateDeltaEvent",
              //   //   Object.keys(event),
              //   //   event.messages.length,
              //   //   event.messages.map((m) => m.role)
              //   // );
              // },
              // onRunFinalized(event) {
              //   console.log(
              //     "✅ Run finalized:",
              //     Object.keys(event),
              //     event.messages?.length,
              //     event.messages?.map((m) => m.role),
              //     message
              //   );
              // },
            })
            .then(() => {
              resolve();
            })
            .catch((error) => {
              console.log(error);
              reject(error);
            });
        });
      }

      try {
        await runWithInterruptHandling({
          runId,
        });

        console.log("✅ Execution completed successfully.");
      } catch (error) {
        console.error("❌ Error running agent:", error);
      } finally {
        setIsRunning(false);
      }
    },
    [setIsRunning, pushMessages, handleInterrupt]
  );

  return {
    messages,
    isRunning,
    totalTokenUsage,
    chatWithAgent,
    clearChat,
    respondToLastInterrupt,
  };
};
