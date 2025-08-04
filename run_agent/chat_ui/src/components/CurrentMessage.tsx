import type { ChatDisplayMessage, TokenUsage } from "../types";

interface CurrentMessageProps {
  currentMessage: ChatDisplayMessage;
  currentTokenUsage: TokenUsage | null;
  currentToolCalls: Map<string, {
    id: string;
    name: string;
    args: string;
    result?: string;
    isComplete?: boolean;
  }>;
}

export function CurrentMessage({ currentMessage, currentTokenUsage, currentToolCalls }: CurrentMessageProps) {
  // Check if we have both text content and tool calls
  const hasTextContent = currentMessage.content && currentMessage.content.trim().length > 0;
  const hasToolCalls = currentToolCalls.size > 0;

  if (currentMessage.message_type === "tool" || (hasToolCalls && !hasTextContent)) {
    // Current tool message (only tool calls, no text)
    return (
      <div
        style={{
          alignSelf: "flex-start",
          maxWidth: "80%",
          backgroundColor: "#fff",
          color: "#333",
          padding: "12px 16px",
          borderRadius: "18px 18px 18px 4px",
          border: "1px solid #ddd",
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
        }}
      >
        <div style={{ fontSize: "14px", fontWeight: "bold", marginBottom: "10px", color: "#f59e0b" }}>
          🔧 Tool Operations
        </div>
        
        {/* Display current tool calls */}
        {currentToolCalls.size > 0 && (
          <div>
            {Array.from(currentToolCalls.values()).map((toolCall) => (
              <div
                key={toolCall.id}
                style={{
                  backgroundColor: "#fef3c7",
                  border: "1px solid #f59e0b",
                  borderRadius: "8px",
                  padding: "10px",
                  marginBottom: "8px",
                  fontSize: "12px",
                }}
              >
                <div style={{ fontWeight: "bold", color: "#92400e", marginBottom: "5px" }}>
                  Tool: {toolCall.name} {toolCall.isComplete ? "✅" : "⏳"}
                </div>
                {toolCall.args && (
                  <div style={{ color: "#451a03", marginBottom: "5px" }}>
                    <strong>Arguments:</strong> {toolCall.args}
                  </div>
                )}
                {toolCall.result && (
                  <div style={{ color: "#451a03" }}>
                    <strong>Result:</strong> {toolCall.result}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Current assistance message (text content, possibly with tool calls)
  return (
    <div
      style={{
        alignSelf: "flex-start",
        maxWidth: "80%",
        backgroundColor: "#fff",
        color: "#333",
        padding: "12px 16px",
        borderRadius: "18px 18px 18px 4px",
        border: "1px solid #ddd",
        boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
      }}
    >
      {/* Text content */}
      {hasTextContent && (
        <div style={{ fontSize: "14px", lineHeight: "1.4", whiteSpace: "pre-wrap", marginBottom: hasToolCalls ? "10px" : "0" }}>
          {currentMessage.content}
        </div>
      )}
      
      {/* Tool calls section */}
      {hasToolCalls && (
        <div>
          <div style={{ fontSize: "12px", fontWeight: "bold", marginBottom: "8px", color: "#f59e0b" }}>
            🔧 Tool Operations
          </div>
          {Array.from(currentToolCalls.values()).map((toolCall) => (
            <div
              key={toolCall.id}
              style={{
                backgroundColor: "#fef3c7",
                border: "1px solid #f59e0b",
                borderRadius: "8px",
                padding: "8px",
                marginBottom: "6px",
                fontSize: "11px",
              }}
            >
              <div style={{ fontWeight: "bold", color: "#92400e", marginBottom: "4px" }}>
                Tool: {toolCall.name} {toolCall.isComplete ? "✅" : "⏳"}
              </div>
              {toolCall.args && (
                <div style={{ color: "#451a03", marginBottom: "4px" }}>
                  <strong>Arguments:</strong> {toolCall.args}
                </div>
              )}
              {toolCall.result && (
                <div style={{ color: "#451a03" }}>
                  <strong>Result:</strong> {toolCall.result}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      
      {/* Token usage display for current message */}
      {currentTokenUsage && (
        <div style={{ 
          fontSize: "10px", 
          color: "#666",
          marginTop: "6px",
          padding: "4px 8px",
          backgroundColor: "#f5f5f5",
          borderRadius: "4px",
          fontFamily: "monospace"
        }}>
          📊 {currentTokenUsage.totalInput} input + {currentTokenUsage.totalOutput} output = {currentTokenUsage.totalTokens} tokens
        </div>
      )}
    </div>
  );
}
