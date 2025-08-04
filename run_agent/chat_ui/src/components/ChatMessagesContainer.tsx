import { useState } from "react";
import type { ChatDisplayMessage } from "../types";
import type { UseAgentService } from "../hooks/useAgentService";

interface ChatMessagesContainerProps {
  chatMessages: ChatDisplayMessage[];
  respondToLastInterrupt: () => void;
}

// Helper function to group messages by conversation blocks
function groupMessages(messages: ChatDisplayMessage[]): Array<{
  type: 'regular' | 'tool' | 'interrupt';
  messages: ChatDisplayMessage[];
  id: string;
}> {
  const groups: Array<{
    type: 'regular' | 'tool' | 'interrupt';
    messages: ChatDisplayMessage[];
    id: string;
  }> = [];
  
  let currentGroup: ChatDisplayMessage[] = [];
  let currentType: 'regular' | 'tool' | 'interrupt' = 'regular';
  
  for (const message of messages) {
    if (message.message_type === 'interrupt') {
      // Finish current group if exists
      if (currentGroup.length > 0) {
        groups.push({
          type: currentType,
          messages: [...currentGroup],
          id: `group-${groups.length}`
        });
        currentGroup = [];
      }
      
      // Add interrupt as standalone group
      groups.push({
        type: 'interrupt',
        messages: [message],
        id: `interrupt-${message.id}`
      });
      
      currentType = 'regular';
    } else if (message.message_type === 'tool' || (message.message_type === 'assistance' && message.toolCalls && message.toolCalls.length > 0 && (!message.content || message.content.trim() === ''))) {
      // Group as tool if:
      // 1. message_type is 'tool' (old logic), OR
      // 2. message_type is 'assistance' but has tool calls and no meaningful text content
      if (currentType !== 'tool' && currentGroup.length > 0) {
        groups.push({
          type: currentType,
          messages: [...currentGroup],
          id: `group-${groups.length}`
        });
        currentGroup = [];
      }
      
      currentGroup.push(message);
      currentType = 'tool';
    } else {
      // Regular message (user/assistance)
      if (currentType !== 'regular' && currentGroup.length > 0) {
        groups.push({
          type: currentType,
          messages: [...currentGroup],
          id: `group-${groups.length}`
        });
        currentGroup = [];
      }
      
      currentGroup.push(message);
      currentType = 'regular';
    }
  }
  
  // Add final group if exists
  if (currentGroup.length > 0) {
    groups.push({
      type: currentType,
      messages: [...currentGroup],
      id: `group-${groups.length}`
    });
  }
  
  return groups;
}

// Component for rendering interrupt prompt
function InterruptMessageComponent({ 
  message, 
  respondToLastInterrupt 
}: { 
  message: ChatDisplayMessage;
  respondToLastInterrupt: UseAgentService["respondToLastInterrupt"];
}) {
  const [input, setInput] = useState("");
  const [isResponded, setIsResponded] = useState(!!message.interruptData?.response);

  const handleSubmit = (response: string) => {
    respondToLastInterrupt(response);
    setIsResponded(true);
  };

  const handleQuickResponse = (type: "yes" | "no") => {
    handleSubmit(type);
  };

  return (
    <div
      style={{
        marginBottom: "20px",
        display: "flex",
        flexDirection: "column",
        alignSelf: "center",
        maxWidth: "90%",
      }}
    >
      <div
        style={{
          backgroundColor: "#fff3cd",
          color: "#856404",
          padding: "12px 16px",
          borderRadius: "8px",
          border: "1px solid #ffeaa7",
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
        }}
      >
        <div style={{ fontSize: "14px", lineHeight: "1.4", marginBottom: "15px" }}>
          <strong>⚠️ Agent needs input:</strong>
          <br />
          {message.interruptData?.question || message.content}
        </div>
        
        {/* Show response if already provided */}
        {isResponded && message.interruptData?.response && (
          <div style={{ 
            marginBottom: "10px", 
            padding: "8px",
            backgroundColor: "#d4edda",
            color: "#155724",
            borderRadius: "4px",
            fontSize: "12px"
          }}>
            <strong>✓ Response provided:</strong> {message.interruptData.response}
          </div>
        )}
        
        {/* Interactive prompt if not yet responded */}
        {!isResponded && (
          <>
            {/* Quick response buttons */}
            <div style={{ display: "flex", gap: "8px", marginBottom: "10px", justifyContent: "center" }}>
              <button
                onClick={() => handleQuickResponse("yes")}
                style={{
                  background: "#28a745",
                  color: "white",
                  border: "none",
                  padding: "8px 16px",
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontSize: "12px",
                  fontWeight: "bold",
                }}
              >
                Yes
              </button>
              <button
                onClick={() => handleQuickResponse("no")}
                style={{
                  background: "#dc3545",
                  color: "white",
                  border: "none",
                  padding: "8px 16px",
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontSize: "12px",
                  fontWeight: "bold",
                }}
              >
                No
              </button>
            </div>
            
            {/* Custom response input */}
            <div style={{ fontSize: "12px", marginBottom: "8px", textAlign: "center", color: "#6c757d" }}>
              Or provide custom response:
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === "Enter" && input.trim()) {
                    handleSubmit(input.trim());
                  }
                }}
                placeholder="Enter custom response..."
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  border: "1px solid #ccc",
                  borderRadius: "4px",
                  fontSize: "12px",
                }}
              />
              <button
                onClick={() => handleSubmit(input.trim())}
                disabled={!input.trim()}
                style={{
                  background: input.trim() ? "#007acc" : "#ccc",
                  color: "white",
                  border: "none",
                  padding: "8px 12px",
                  borderRadius: "4px",
                  cursor: input.trim() ? "pointer" : "not-allowed",
                  fontSize: "12px",
                }}
              >
                Submit
              </button>
            </div>
          </>
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
    </div>
  );
}

// Component for rendering grouped tool calls
function ToolCallGroupComponent({ messages }: { messages: ChatDisplayMessage[] }) {
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

// Component for rendering regular message group
function RegularMessageGroupComponent({ messages }: { messages: ChatDisplayMessage[] }) {
  // Combine all content from the group
  const combinedContent = messages
    .map(msg => msg.content)
    .filter(content => content && content.trim())
    .join("");
  
  const isUserMessage = messages[0]?.message_type === "user";
  
  // Check if any message in the group has tool calls
  const hasToolCalls = messages.some(msg => msg.toolCalls && msg.toolCalls.length > 0);
  
  // Collect all tool calls from all messages in the group
  const allToolCalls = messages.reduce((acc, msg) => {
    if (msg.toolCalls && msg.toolCalls.length > 0) {
      acc.push(...msg.toolCalls);
    }
    return acc;
  }, [] as NonNullable<ChatDisplayMessage['toolCalls']>);
  
  const totalTokenUsage = messages.reduce((acc, msg) => {
    if (msg.tokenUsage) {
      return {
        totalInput: acc.totalInput + msg.tokenUsage.totalInput,
        totalOutput: acc.totalOutput + msg.tokenUsage.totalOutput,
        totalTokens: acc.totalTokens + msg.tokenUsage.totalTokens,
      };
    }
    return acc;
  }, { totalInput: 0, totalOutput: 0, totalTokens: 0 });

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
        marginBottom: "20px",
      }}
    >
      {combinedContent && (
        <div style={{ 
          fontSize: "14px", 
          lineHeight: "1.4", 
          whiteSpace: "pre-wrap",
          marginBottom: hasToolCalls ? "10px" : "0"
        }}>
          {combinedContent}
        </div>
      )}
      
      {/* Tool calls section for assistant messages with tools */}
      {hasToolCalls && !isUserMessage && (
        <div style={{ marginTop: combinedContent ? "10px" : "0" }}>
          <div style={{ fontSize: "12px", fontWeight: "bold", marginBottom: "8px", color: "#f59e0b" }}>
            🔧 Tool Operations
          </div>
          {allToolCalls.map((toolCall) => (
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
                  <strong>Input:</strong>
                  <pre style={{ 
                    margin: "4px 0", 
                    padding: "4px", 
                    backgroundColor: "#fff", 
                    borderRadius: "4px",
                    fontSize: "10px",
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
                    fontSize: "10px",
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
      
      {/* Token usage display for combined messages */}
      {totalTokenUsage.totalTokens > 0 && (
        <div style={{ 
          fontSize: "10px", 
          color: isUserMessage ? "rgba(255,255,255,0.6)" : "#666",
          marginTop: "6px",
          padding: "4px 8px",
          backgroundColor: isUserMessage ? "rgba(255,255,255,0.1)" : "#f5f5f5",
          borderRadius: "4px",
          fontFamily: "monospace"
        }}>
          📊 {totalTokenUsage.totalInput} input + {totalTokenUsage.totalOutput} output = {totalTokenUsage.totalTokens} tokens
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

export function ChatMessagesContainer({
  chatMessages,
  respondToLastInterrupt
}: ChatMessagesContainerProps) {
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

  // Group messages by type and conversation flow
  const messageGroups = groupMessages(chatMessages);

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
