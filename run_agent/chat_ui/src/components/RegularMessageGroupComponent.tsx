import type { ChatDisplayMessage } from "../types";
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {Prism as SyntaxHighlighter} from 'react-syntax-highlighter'
import {dark} from 'react-syntax-highlighter/dist/esm/styles/prism'
interface RegularMessageGroupComponentProps {
  messages: ChatDisplayMessage[];
}

export function RegularMessageGroupComponent({ messages }: RegularMessageGroupComponentProps) {
  // Combine all content from the group
  const combinedContent = messages
    .map(msg => msg.content)
    .filter(content => content && content.trim())
    .join("");
  
  const isUserMessage = messages[0]?.message_type === "user";
  const isCodeMessage = messages[0]?.message_type === "code";
  
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
        backgroundColor: isUserMessage ? "#007acc" : isCodeMessage ? "#f0f0f0" : "#fff",
        color: isUserMessage ? "white" : "#333",
        padding: "12px 16px",
        borderRadius: isUserMessage ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
        border: isUserMessage ? "none" : isCodeMessage ? "1px solid #ccc" : "1px solid #ddd",
        boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
        marginBottom: "20px",
      }}
    >
      {combinedContent && (
        <div style={{ 
          fontSize: "14px", 
          lineHeight: "1.4", 
          marginBottom: hasToolCalls ? "10px" : "0",
          maxWidth: "1000px",
        }}>
        <ReactMarkdown 
          children={combinedContent} 
          remarkPlugins={[remarkGfm]} 
          components={{
            code({className, children}) {
              const match = /language-(\w+)/.exec(className || '')
              return  match ? (
                <SyntaxHighlighter
                  children={String(children).replace(/\n$/, '')}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  style={dark as any}
                  language={match[1]}
                  PreTag="div"
                />
              ) : (
                <code className={className}>
                  {children}
                </code>
              )
            }
          }}
          />
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
