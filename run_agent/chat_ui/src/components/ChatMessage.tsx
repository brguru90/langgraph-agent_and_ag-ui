import type { ChatDisplayMessage } from "../types";

interface ChatMessageProps {
  message: ChatDisplayMessage;
}

export function ChatMessage({ message }: ChatMessageProps) {
  if (message.message_type === "interrupt") {
    // Interrupt message display
    return (
      <div
        style={{
          alignSelf: "center",
          maxWidth: "90%",
          backgroundColor: "#fff3cd",
          color: "#856404",
          padding: "12px 16px",
          borderRadius: "8px",
          border: "1px solid #ffeaa7",
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
        }}
      >
        <div style={{ fontSize: "14px", lineHeight: "1.4", marginBottom: "10px" }}>
          <strong>⚠️ Agent needs input:</strong>
          <br />
          {message.content}
        </div>
        {message.interruptData?.response && (
          <div style={{ 
            marginTop: "10px", 
            padding: "8px",
            backgroundColor: "#f8f9fa",
            borderRadius: "4px",
            fontSize: "12px"
          }}>
            <strong>Response:</strong> {message.interruptData.response}
          </div>
        )}
        <div
          style={{
            fontSize: "10px",
            color: "#856404",
            marginTop: "8px",
            textAlign: "right",
          }}
        >
          {new Date().toLocaleTimeString()}
        </div>
      </div>
    );
  }

  if (message.message_type === "tool") {
    // Tool message display
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
        
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div>
            {message.toolCalls.map((toolCall) => (
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
                <div style={{ color: "#451a03", marginBottom: "5px" }}>
                  <strong>Arguments:</strong> {toolCall.args}
                </div>
                {toolCall.result && (
                  <div style={{ color: "#451a03" }}>
                    <strong>Result:</strong> {toolCall.result}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        
        <div
          style={{
            fontSize: "10px",
            color: "#999",
            marginTop: "8px",
            textAlign: "right",
          }}
        >
          {new Date().toLocaleTimeString()}
        </div>
      </div>
    );
  }

  // Regular user/assistant message (may include both text and tool calls)
  const hasTextContent = message.content && message.content.trim().length > 0;
  const hasToolCalls = message.toolCalls && message.toolCalls.length > 0;
  const isUserMessage = message.message_type === "user";

  return (
    <div
      style={{
        alignSelf: isUserMessage ? "flex-end" : "flex-start",
        maxWidth: "80%",
        backgroundColor: isUserMessage ? "#007acc" : "#fff",
        color: isUserMessage ? "white" : "#333",
        padding: "12px 16px",
        borderRadius: isUserMessage ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
        border: isUserMessage ? "none" : "1px solid #ddd",
        boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
      }}
    >
      {/* Text content */}
      {hasTextContent && (
        <div style={{ 
          fontSize: "14px", 
          lineHeight: "1.4", 
          whiteSpace: "pre-wrap",
          marginBottom: hasToolCalls ? "10px" : "0"
        }}>
          {message.content}
        </div>
      )}
      
      {/* Tool calls section for assistant messages */}
      {hasToolCalls && !isUserMessage && (
        <div>
          <div style={{ fontSize: "12px", fontWeight: "bold", marginBottom: "8px", color: "#f59e0b" }}>
            🔧 Tool Operations
          </div>
          {message.toolCalls?.map((toolCall) => (
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
      
      {/* Token usage display */}
      {message.tokenUsage && (
        <div style={{ 
          fontSize: "10px", 
          color: isUserMessage ? "rgba(255,255,255,0.6)" : "#666",
          marginTop: "6px",
          padding: "4px 8px",
          backgroundColor: isUserMessage ? "rgba(255,255,255,0.1)" : "#f5f5f5",
          borderRadius: "4px",
          fontFamily: "monospace"
        }}>
          📊 {message.tokenUsage.totalInput} input + {message.tokenUsage.totalOutput} output = {message.tokenUsage.totalTokens} tokens
        </div>
      )}
      <div
        style={{
          fontSize: "10px",
          color: isUserMessage ? "rgba(255,255,255,0.7)" : "#999",
          marginTop: "8px",
          textAlign: "right",
        }}
      >
        {new Date().toLocaleTimeString()}
      </div>
    </div>
  );
}
