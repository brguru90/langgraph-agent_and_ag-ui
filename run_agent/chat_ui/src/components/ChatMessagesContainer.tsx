import type { ChatDisplayMessage } from "../types";
import { InterruptMessageComponent } from "./InterruptMessageComponent";
import { ToolCallGroupComponent } from "./ToolCallGroupComponent";
import { RegularMessageGroupComponent } from "./RegularMessageGroupComponent";
import { groupMessages } from "../utils/messageGrouping";
import { useMemo } from "react";

interface ChatMessagesContainerProps {
  chatMessages: ChatDisplayMessage[];
  respondToLastInterrupt: (message: string) => void;
}

export function ChatMessagesContainer({
  chatMessages,
  respondToLastInterrupt
}: ChatMessagesContainerProps) {

  // Group messages by type and conversation flow
  const messageGroups = useMemo(() => groupMessages(chatMessages), [chatMessages]);
  
  if (chatMessages.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          border: "1px solid #ccc",
          margin: "0 20px 20px 20px",
          borderRadius: "4px",
          overflowY: "auto",
          backgroundColor: "#f8f9fa",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ padding: "20px", color: "#666", textAlign: "center" }}>
          No messages yet. Start a conversation to see messages here.
        </div>
      </div>
    );
  }


  return (
    <div
      style={{
        flex: 1,
        border: "1px solid #ccc",
        margin: "0 20px 20px 20px",
        borderRadius: "4px",
        overflowY: "auto",
        backgroundColor: "#f8f9fa",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div style={{ flex: 1, padding: "15px" }}>
        {/* Render grouped messages */}
        {messageGroups.map((group) => {
          if (group.type === 'interrupt') {
            return (
              <InterruptMessageComponent
                key={group.id}
                message={group.messages[0]}
                respondToLastInterrupt={respondToLastInterrupt}
              />
            );
          } else if (group.type === 'tool') {
            return (
              <ToolCallGroupComponent
                key={group.id}
                messages={group.messages}
              />
            );
          } else {
            return (
              <RegularMessageGroupComponent
                key={group.id}
                messages={group.messages}
              />
            );
          }
        })}
      </div>
    </div>
  );
}
