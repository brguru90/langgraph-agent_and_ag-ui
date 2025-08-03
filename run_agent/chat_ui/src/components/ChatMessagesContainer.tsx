import { ChatMessage } from "./ChatMessage";
import { CurrentMessage } from "./CurrentMessage";
import { InterruptPromptComponent } from "./InterruptPrompt";
import type { ChatDisplayMessage, InterruptPrompt, TokenUsage } from "../types";

interface ChatMessagesContainerProps {
  chatMessages: ChatDisplayMessage[];
  currentMessage: ChatDisplayMessage | null;
  currentTokenUsage: TokenUsage | null;
  currentToolCalls: Map<string, {
    id: string;
    name: string;
    args: string;
    result?: string;
    isComplete?: boolean;
  }>;
  interruptPrompt: InterruptPrompt | null;
}

export function ChatMessagesContainer({
  chatMessages,
  currentMessage,
  currentTokenUsage,
  currentToolCalls,
  interruptPrompt,
}: ChatMessagesContainerProps) {
  if (chatMessages.length === 0 && !currentMessage && !interruptPrompt) {
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
        {/* Display chat messages */}
        {chatMessages.map((message) => (
          <div
            key={message.id}
            style={{
              marginBottom: "20px",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <ChatMessage message={message} />
          </div>
        ))}

        {/* Display current streaming message */}
        {currentMessage && (
          <div
            style={{
              marginBottom: "20px",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <CurrentMessage
              currentMessage={currentMessage}
              currentTokenUsage={currentTokenUsage}
              currentToolCalls={currentToolCalls}
            />
          </div>
        )}

        {/* Display interrupt prompt only if not already in messages */}
        {interruptPrompt && interruptPrompt.isActive && !chatMessages.some(msg => 
          msg.message_type === "interrupt" && 
          msg.interruptData?.isActive
        ) && (
          <InterruptPromptComponent
            prompt={interruptPrompt}
          />
        )}
      </div>
    </div>
  );
}
