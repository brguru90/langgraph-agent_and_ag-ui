import { useCallback, useState } from "react";
import "./App.css";

import { HttpAgent, type Message } from "@ag-ui/client";
// import { LangGraphHttpAgent as HttpAgent } from "@ag-ui/langgraph";
// import { randomUUID } from "crypto";

const getRandomString = (_len = 20) =>
  Array.from(window.crypto.getRandomValues(new Uint8Array(_len)))
    .map((c: number) => Number(c).toString(36))
    .join('');

const randomUUID = () => crypto.randomUUID ? crypto.randomUUID() : getRandomString(20);

// Type definitions
interface LangGraphMessage {
  id: string;
  type: "human" | "ai" | "tool" | "system";
  content: string | ContentItem[];
  tool_call_id?: string;
  name?: string | null;
  example?: boolean;
  additional_kwargs?: Record<string, unknown>;
  response_metadata?: ResponseMetadata;
  tool_calls?: ToolCall[];
  invalid_tool_calls?: unknown[];
  usage_metadata?: UsageMetadata;
  artifact?: unknown;
  status?: string;
}

interface ContentItem {
  type: "text" | "tool_use";
  text?: string;
  id?: string;
  name?: string;
  index?: number;
  input?: string | Record<string, unknown>;
}

interface ResponseMetadata {
  stopReason?: string;
  metrics?: {
    latencyMs: number;
  };
  model_name?: string;
  ResponseMetadata?: {
    RequestId: string;
    HTTPStatusCode: number;
    HTTPHeaders: Record<string, string>;
    RetryAttempts: number;
  };
}

interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  id: string;
  type: string;
}

interface UsageMetadata {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_token_details?: {
    cache_creation: number;
    cache_read: number;
  };
}


interface RunData {
  runId: string;
  forwardedProps?: {
    command?: {
      resume: string;
    };
  };
}

interface LogEntry {
  id: string;
  timestamp: Date;
  type:
    | "run-start"
    | "text-message-start"
    | "text-content"
    | "text-end"
    | "tool-call-start"
    | "tool-call-args"
    | "tool-call-end"
    | "tool-call-result"
    | "run-failed"
    | "custom-event"
    | "state-snapshot"
    | "state-delta"
    | "run-finalized"
    | "general";
  message: string;
  data?: unknown;
}

function App() {
  // State for storing console logs
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  // Helper function to add a log entry
  const addLog = useCallback(
    (type: LogEntry["type"], message: string, data?: unknown) => {
      const logEntry: LogEntry = {
        id: randomUUID(),
        timestamp: new Date(),
        type,
        message,
        data,
      };
      setLogs((prev) => [...prev, logEntry]);
    },
    []
  );

  // Helper function to clear logs
  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);


  
  function mapStateMessagesToAGUI(stateMessages: LangGraphMessage[]): Message[] {
    const result: Message[] = [];

    for (const langGraphMsg of stateMessages) {
      // Extract content as string
      let content: string;
      if (Array.isArray(langGraphMsg.content)) {
        // For array content, extract text from text items and concatenate
        content = langGraphMsg.content
          .filter((item) => item.type === "text" && item.text)
          .map((item) => item.text)
          .join(" ");
      } else {
        content = langGraphMsg.content || "";
      }

      // Map LangGraph message types to AG-UI roles
      let role: string;
      switch (langGraphMsg.type) {
        case "human":
          role = "user";
          break;
        case "ai":
          role = "assistant";
          break;
        case "tool":
          role = "tool";
          break;
        case "system":
          role = "system";
          break;
        default:
          // Skip unknown message types
          continue;
      }

      // Create base message
      const baseMessage = {
        id: langGraphMsg.id,
        role,
        content,
        name: langGraphMsg.name || undefined,
      };

      // Handle different message types
      if (role === "assistant") {
        // Transform tool_calls to toolCalls for assistant messages
        const toolCalls = langGraphMsg.tool_calls?.map((toolCall) => ({
          id: toolCall.id,
          type: "function" as const,
          function: {
            name: toolCall.name,
            arguments: JSON.stringify(toolCall.args || {}),
          },
        }));

        // eslint-disable-next-line 
        // @ts-ignore
        result.push({
          ...baseMessage,
          role: "assistant" as const,
          content: JSON.stringify(langGraphMsg.content),
          toolCalls,
        } as Message);
      } else if (role === "tool") {
        // Tool messages need toolCallId
        result.push({
          id: langGraphMsg.id ?? randomUUID(),
          role: "tool" as const,
          content: langGraphMsg.content,
          toolCallId: langGraphMsg.tool_call_id || "",
        } as Message);
      } else if (role === "user") {
        result.push({
          ...baseMessage,
          role: "user" as const,
          content,
        } as Message);
      } else if (role === "system") {
        result.push({
          ...baseMessage,
          role: "system" as const,
          content,
        } as Message);
      }
    }

    return result;
  }
  

  // Function to get state from the server
  async function get_state(
    thread_id: string
  ): Promise<{ messages: LangGraphMessage[] }> {
    try {
      const url = `http://localhost:8000/state?thread_id=${encodeURIComponent(
        thread_id
      )}`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const state = await response.json();
      return state;
    } catch (error) {
      console.error("Error fetching state:", error);
      throw error;
    }
  }

  // Function to handle user input for interrupts
  function handleInterrupt(message: string): Promise<string> {
    return new Promise((resolve) => {
      const userInput = prompt("provide input");

      console.log(`\n⚠️ ${message}`);

      if (userInput !== null) {
        resolve(userInput.trim().toLowerCase());
      } else {
        resolve("");
      }
    });
  }

  const runAgent = useCallback(
    async function runAgent(
      content: string,
      thread_id?: string
    ): Promise<{
      threadId: string;
      originalRunId: string;
    }> {
      setIsRunning(true);
      addLog(
        "general",
        `🎯 Starting agent run: "${content}"${
          thread_id ? ` (thread: ${thread_id})` : ""
        }`
      );

      const agent = await (async () => {
        if (!thread_id) {
          return new HttpAgent({
            url: `http://localhost:8000/ag-ui/`,
            // debug: true,
          });
        }
        const state = await get_state(thread_id);
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
      addLog("general", `🆔 Thread ID: ${agent.threadId}`);
      addLog("general", `------ Your query: ${content}`);

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
            get_state(agent.threadId)
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
                const message = `🚀 Run started: ${event.runId}`;
                console.log(message, Object.keys(event), content);
                addLog("run-start", message, {
                  runId: event.runId,
                  eventKeys: Object.keys(event),
                  content,
                });
              },
              onTextMessageStartEvent(event) {
                const message = `🤖 AG-UI assistant:`;
                console.log(message, Object.keys(event), content);
                addLog("text-message-start", message, {
                  eventKeys: Object.keys(event),
                  content,
                });
              },
              onTextMessageContentEvent({ event }) {
                console.log(event.delta);
                addLog("text-content", event.delta);
              },
              onTextMessageEndEvent() {
                const message = "Text message ended";
                console.log("");
                addLog("text-end", message);
              },
              onToolCallStartEvent({ event }) {
                const message = `🔧 Tool call start: ${event.toolCallName} (${event.toolCallId})`;
                console.log(message);
                addLog("tool-call-start", message, {
                  toolCallName: event.toolCallName,
                  toolCallId: event.toolCallId,
                });
              },
              onToolCallArgsEvent({ event }) {
                console.log(event.delta);
                addLog("tool-call-args", event.delta);
              },
              onToolCallEndEvent({ event }) {
                const message = `🔧 Tool call end: ${event.toolCallId}`;
                console.log(message);
                addLog("tool-call-end", message, {
                  toolCallId: event.toolCallId,
                });
              },
              onToolCallResultEvent({ event }) {
                if (event.content) {
                  const message = `🔍 Tool call result: ${event.content}`;
                  console.log(message);
                  addLog("tool-call-result", message, {
                    content: event.content,
                  });
                }
              },
              onRunFailed({ error }) {
                const message = `❌ Run failed: ${error}`;
                console.error(message);
                addLog("run-failed", message, { error });
              },
              async onCustomEvent({ event }) {
                const message = `📋 Custom event received: ${event.name}`;
                console.log(message);
                addLog("custom-event", message, {
                  eventName: event.name,
                  eventValue: event.value,
                });

                if (event.name === "on_interrupt") {
                  try {
                    const userChoice = await handleInterrupt(event.value);
                    const responseMessage = `User responded: ${userChoice}`;
                    console.log(responseMessage);
                    addLog("custom-event", responseMessage, { userChoice });

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
                    // const result = await runWithInterruptHandling(
                    //   resumeRunData,
                    //   true
                    // );
                    // resolve(result);
                  } catch (error) {
                    const errorMessage = `Error handling interrupt: ${
                      error instanceof Error ? error.message : error
                    }`;
                    console.error(errorMessage);
                    addLog("run-failed", errorMessage, { error });
                    // reject(error);
                  }
                }
              },
              onStateSnapshotEvent(event) {
                // entire snapshot
                const message = `==onStateSnapshotEvent - ${event.messages.length} messages`;
                console.log(
                  message,
                  Object.keys(event),
                  event.messages.map((m: { role: string }) => m.role),
                  content
                );
                addLog("state-snapshot", message, {
                  eventKeys: Object.keys(event),
                  messageCount: event.messages.length,
                  roles: event.messages.map((m: { role: string }) => m.role),
                  content,
                });
                // agent.messages = event.messages;
              },
              onStateDeltaEvent(event) {
                // incremental update
                const message = `++onStateDeltaEvent - ${event.messages.length} messages`;
                console.log(
                  message,
                  Object.keys(event),
                  event.messages.map((m: { role: string }) => m.role)
                );
                addLog("state-delta", message, {
                  eventKeys: Object.keys(event),
                  messageCount: event.messages.length,
                  roles: event.messages.map((m: { role: string }) => m.role),
                });
              },
              onRunFinalized(event) {
                const message = `✅ Run finalized - ${
                  event.messages?.length || 0
                } messages`;
                console.log(
                  message,
                  Object.keys(event),
                  event.messages?.map((m: { role: string }) => m.role),
                  content
                );
                addLog("run-finalized", message, {
                  eventKeys: Object.keys(event),
                  messageCount: event.messages?.length || 0,
                  roles:
                    event.messages?.map((m: { role: string }) => m.role) || [],
                  content,
                });
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
        addLog("general", "✅ Execution completed successfully.");
      } catch (error) {
        console.error("❌ Error running agent:", error);
        addLog("run-failed", `❌ Error running agent: ${error}`, { error });
      }

      setIsRunning(false);
      return {
        threadId: agent.threadId,
        originalRunId
      };
    },
    [addLog, setIsRunning]
  );

  async function main() {
    addLog("general", "🚀 Starting main execution...");

    const lastAgent = await runAgent(
      "provide me documentation for button component"
    );
    console.log(lastAgent.threadId);
    addLog(
      "general",
      `First agent completed. Thread ID: ${lastAgent.threadId}`
    );

    await new Promise((resolve) => setTimeout(resolve, 1000));

    addLog("general", "🔄 Running second query...");
    await runAgent("What was my last query", lastAgent.threadId);
    console.log("-- Done --");
    addLog("general", "🎉 All executions completed!");

    // await new Promise((resolve) => setTimeout(resolve, 5000))
  }

  // useEffect(() => {
  //   main().catch((error) => {
  //     console.error(error);
  //     addLog("run-failed", `Main execution failed: ${error}`, { error });
  //   });
  // }, [runAgent, addLog]);

  return (
    <div style={{ padding: "20px", fontFamily: "monospace" }}>
      <div
        style={{
          marginBottom: "20px",
          display: "flex",
          alignItems: "center",
          gap: "10px",
        }}
      >
        <h1>AG-UI Agent Console</h1>
        {isRunning && (
          <div
            style={{
              background: "#007acc",
              color: "white",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "12px",
            }}
          >
            Running...
          </div>
        )}
        <button
          onClick={clearLogs}
          style={{
            background: "#dc3545",
            color: "white",
            border: "none",
            padding: "6px 12px",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "12px",
          }}
        >
          Clear Logs
        </button>
         <button
          onClick={main}
          style={{
            background: "#3575dcff",
            color: "white",
            border: "none",
            padding: "6px 12px",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "12px",
          }}
        >
          Run
        </button>
      </div>

      <div
        style={{
          border: "1px solid #ccc",
          borderRadius: "4px",
          maxHeight: "80vh",
          overflowY: "auto",
          backgroundColor: "#f8f9fa",
        }}
      >
        {logs.length === 0 ? (
          <div style={{ padding: "20px", color: "#666", textAlign: "center" }}>
            No logs yet. Logs will appear here as the agent runs.
          </div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              style={{
                padding: "8px 12px",
                borderBottom: "1px solid #eee",
                backgroundColor: getLogBackgroundColor(log.type),
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                }}
              >
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "4px",
                    }}
                  >
                    {log.timestamp.toLocaleTimeString()} -{" "}
                    {getLogTypeLabel(log.type)}
                  </div>
                  <div
                    style={{
                      color: getLogTextColor(log.type),
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {log.message}
                  </div>
                  {log.data != null && (
                    <details style={{ marginTop: "4px" }}>
                      <summary
                        style={{
                          cursor: "pointer",
                          fontSize: "11px",
                          color: "#666",
                        }}
                      >
                        Show Details
                      </summary>
                      <pre
                        style={{
                          fontSize: "10px",
                          background: "#fff",
                          padding: "8px",
                          borderRadius: "2px",
                          marginTop: "4px",
                          overflow: "auto",
                        }}
                      >
                        {JSON.stringify(
                          log.data as Record<string, unknown>,
                          null,
                          2
                        )}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  // Helper functions for styling
  function getLogBackgroundColor(type: LogEntry["type"]): string {
    switch (type) {
      case "run-failed":
        return "#fff5f5";
      case "run-start":
        return "#f0f9ff";
      case "run-finalized":
        return "#f0fdf4";
      case "tool-call-start":
      case "tool-call-end":
      case "tool-call-result":
        return "#fefce8";
      case "custom-event":
        return "#fdf4ff";
      default:
        return "#ffffff";
    }
  }

  function getLogTextColor(type: LogEntry["type"]): string {
    switch (type) {
      case "run-failed":
        return "#dc2626";
      case "run-start":
        return "#0369a1";
      case "run-finalized":
        return "#15803d";
      case "tool-call-start":
      case "tool-call-end":
      case "tool-call-result":
        return "#ca8a04";
      case "custom-event":
        return "#9333ea";
      default:
        return "#374151";
    }
  }

  function getLogTypeLabel(type: LogEntry["type"]): string {
    switch (type) {
      case "run-start":
        return "RUN START";
      case "text-message-start":
        return "TEXT START";
      case "text-content":
        return "TEXT CONTENT";
      case "text-end":
        return "TEXT END";
      case "tool-call-start":
        return "TOOL START";
      case "tool-call-args":
        return "TOOL ARGS";
      case "tool-call-end":
        return "TOOL END";
      case "tool-call-result":
        return "TOOL RESULT";
      case "run-failed":
        return "ERROR";
      case "custom-event":
        return "CUSTOM EVENT";
      case "state-snapshot":
        return "STATE SNAPSHOT";
      case "state-delta":
        return "STATE DELTA";
      case "run-finalized":
        return "RUN COMPLETE";
      case "general":
        return "INFO";
      default:
        return String(type).toUpperCase();
    }
  }
}

export default App;
