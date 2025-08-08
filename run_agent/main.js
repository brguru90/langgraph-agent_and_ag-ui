import { HttpAgent } from "@ag-ui/client";
// import { LangGraphHttpAgent as HttpAgent } from "@ag-ui/langgraph";
import { randomUUID } from "node:crypto";
import readline from "node:readline";
import fs from "node:fs";

function mapStateMessagesToAGUI(stateMessages) {
    const result = [];

    for (const langGraphMsg of stateMessages) {
      // Extract content as string
      let content;
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
      let role;
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
          type: "function" ,
          function: {
            name: toolCall.name,
            arguments: JSON.stringify(toolCall.args || {}),
          },
        }));

        // eslint-disable-next-line 
        // @ts-ignore
        result.push({
          ...baseMessage,
          role: "assistant" ,
          content: JSON.stringify(langGraphMsg.content),
          toolCalls,
        } );
      } else if (role === "tool") {
        // Tool messages need toolCallId
        result.push({
          id: langGraphMsg.id ?? randomUUID(),
          role: "tool" ,
          content: langGraphMsg.content,
          toolCallId: langGraphMsg.tool_call_id || "",
        } );
      } else if (role === "user") {
        result.push({
          ...baseMessage,
          role: "user" ,
          content,
        });
      } else if (role === "system") {
        result.push({
          ...baseMessage,
          role: "system" ,
          content,
        } );
      }
    }

    return result;
  }

// Function to get state from the server
async function get_state(thread_id) {
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

const validate_req = async ({ threadId, runId, messages }) => {
  let bodyContent = JSON.stringify({
    threadId,
    runId,
    tools: [],
    context: [],
    forwardedProps: {},
    messages,
    state: {},
  });

  let response = await fetch("http://localhost:8000/ag-ui/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: bodyContent,
  });
  try {
    let data = await response.text();
    console.log(data);
  } catch (error) {
    console.error("Error:", error);
    console.log(JSON.stringify(response, null, 2));
  }
};

// Function to handle user input for interrupts
function handleInterrupt(message) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });

    console.log(`\n⚠️ ${message}`);
    rl.question("Your choice: ", (answer) => {
      rl.close();
      resolve(answer.trim().toLowerCase());
    });
  });
}

async function runAgent(content, thread_id) {
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

  agent.messages.push({
    id: randomUUID(),
    role: "user",
    content: content,
  });

  agent.messages.forEach((msg) => {
    console.log("message==> ",msg.role,msg.content)
  })


  const originalRunId = randomUUID(); // Create runId once and reuse it

  // Function to handle a single conversation run with interrupt handling
  async function runWithInterruptHandling(runData, isResume = false) {
    return new Promise(async (resolve, reject) => {
      // For resume operations, use the same agent instance but clear messages
      // to avoid message mismatch on server side

      if (isResume) {
        // For resume calls, temporarily clear messages - let server handle state
        // & anyway without clearing the message the response to interrupt was not working for me
        agent.messages = []; // Clear messages for resume
        // const s=await get_state(agent.threadId)
        // console.log("messagess",s.messages)
        // agent.messages=mapStateMessagesToAGUI(s.messages)
      }

      agent
        .runAgent(runData, {
          onRunStartedEvent({ event }) {
            console.log(
              "🚀 Run started:",
              // event.runId,
              // Object.keys(event),
              // event.messages?.length,
              // event.messages?.map((m) => m.role),
              // content
            );
          },
          onTextMessageStartEvent(event) {
            // console.log(
            //   "🤖 AG-UI assistant: ",
            //   Object.keys(event),
            //   event.messages?.length,
            //   event.messages?.map((m) => m.role),
            //   content
            // );
          },
          onTextMessageContentEvent({ event }) {
            // console.log(JSON.stringify(event, null, 2));
            process.stdout.write(event.delta);
          },
          onTextMessageEndEvent(event) {
            console.log("");
          },
          onToolCallStartEvent({ event }) {
            console.log(
              "🔧 Tool call start:",
              event.toolCallName,
              event.toolCallId
            );
          },
          onToolCallArgsEvent({ event }) {
            process.stdout.write(event.delta);
          },
          onToolCallEndEvent({ event }) {
            console.log("🔧 Tool call end:", event.toolCallId);
          },
          onToolCallResultEvent({ event }) {
            if (event.content) {
              console.log("🔍 Tool call result:", event.content);
            }
          },
          onRunFailedEvent({ event }) {
            console.error("❌ Run failed:", event);
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
                    // node_name:"route"
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
                console.error(
                  "Error handling interrupt:",
                  error.message || error
                );
                // reject(error);
              }
            }
          },
          onError(error) {
            console.error("AG-UI Agent error:", error.message || error);
            reject(error);
          },
          
          // onStateSnapshotEvent(event) {
          //   // entire snapshot
          //   console.log(
          //     "==onStateSnapshotEvent",
          //     Object.keys(event),
          //     event.messages.length,
          //     event.messages.map((m) => m.role),
          //     content
          //   );
          //   agent.messages = event.messages;
          // },
          // onStateDeltaEvent(event) {
          //   // incremental update
          //   console.log(
          //     "++onStateDeltaEvent",
          //     Object.keys(event),
          //     event.messages.length,
          //     event.messages.map((m) => m.role)
          //   );
          //   // its not triggering some reason, i will sync from API
          //   // https://docs.ag-ui.com/concepts/state
          // },
          onRunFinalized(event) {
            console.log(
              "✅ Run finalized:",
              event.runId,
              Object.keys(event),
              event.messages?.length,
              event.messages?.map((m) => m.role),
              content
            );
          },
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
      runId: originalRunId,
      // Don't explicitly pass threadId initially - let agent manage it
    });

    console.log("✅ Execution completed successfully.");
  } catch (error) {
    console.error("❌ Error running agent:", error);
  }
  return { ...agent, originalRunId };
}

async function main() {
  const lastAgent = await runAgent(
    "provide me documentation for button component"
  );
  console.log(lastAgent.threadId);
  // fs.writeFileSync("state.json", JSON.stringify(lastAgent));
  // // fs.writeFileSync("messages.json", JSON.stringify(lastAgent.messages));
  await runAgent(
    "What was my last query",
    lastAgent.threadId,
  );
  console.log("-- Done --");

}

await main();
