import type { ChatDisplayMessage } from "../types";

interface ToolCallGroupComponentProps {
  messages: ChatDisplayMessage[];
}

export function ToolCallGroupComponent({ messages }: ToolCallGroupComponentProps) {
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
        marginBottom: "20px",
      }}
    >
      <div style={{ fontSize: "14px", fontWeight: "bold", marginBottom: "10px", color: "#f59e0b" }}>
        🔧 Tool Operations
      </div>
      
      {messages.map((message, index) => (
        <div key={message.id} style={{ marginBottom: index < messages.length - 1 ? "12px" : "0" }}>
          {/* Text content if any */}
          {message.content && message.content.trim() && (
            <div style={{ 
              fontSize: "14px", 
              lineHeight: "1.4", 
              marginBottom: "8px",
              padding: "8px",
              backgroundColor: "#f8f9fa",
              borderRadius: "4px"
            }}>
              {message.content}
            </div>
          )}
          
          {/* Tool calls */}
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
                    marginBottom: "6px",
                    fontSize: "12px",
                  }}
                >
                  <div style={{ fontWeight: "bold", color: "#92400e", marginBottom: "5px" }}>
                    Tool: {toolCall.name} {toolCall.isComplete ? "✅" : "⏳"}
                  </div>
                  {toolCall.args && (
                    <div style={{ color: "#451a03", marginBottom: "5px" }}>
                      <strong>Input:</strong>
                      <pre style={{ 
                        margin: "4px 0", 
                        padding: "4px", 
                        backgroundColor: "#fff", 
                        borderRadius: "4px",
                        fontSize: "11px",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word"
                      }}>
                        {toolCall.args}
                      </pre>
                    </div>
                  )}
                  {toolCall.result && (
                    <div style={{ color: "#451a03" }}>
                      <strong>Output:</strong>
                      <pre style={{ 
                        margin: "4px 0", 
                        padding: "4px", 
                        backgroundColor: "#fff", 
                        borderRadius: "4px",
                        fontSize: "11px",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word"
                      }}>
                        {toolCall.result}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          
          {/* Token usage for this tool message */}
          {message.tokenUsage && (
            <div style={{ 
              fontSize: "10px", 
              color: "#666",
              marginTop: "6px",
              padding: "4px 8px",
              backgroundColor: "#f5f5f5",
              borderRadius: "4px",
              fontFamily: "monospace"
            }}>
              📊 {message.tokenUsage.totalInput} input + {message.tokenUsage.totalOutput} output = {message.tokenUsage.totalTokens} tokens
            </div>
          )}
        </div>
      ))}
      
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
