import type { Message } from "@ag-ui/client";
import type { LangGraphMessage } from "../types";
import { randomUUID } from "../utils";

export function mapStateMessagesToAGUI(stateMessages: LangGraphMessage[]): Message[] {
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
