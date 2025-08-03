"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useCopilotChat } from "@copilotkit/react-core";
import { TextMessage, Role } from "@copilotkit/runtime-client-gql";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  tokens?: number;
  isStreaming?: boolean;
}

interface StreamingChunk {
  type: string;
  text: string;
}

interface CustomChatUIProps {
  onMessageSent?: (message: string) => void;
  title?: string;
  subtitle?: string;
  placeholder?: string;
}

export const CustomChatUI: React.FC<CustomChatUIProps> = ({
  onMessageSent,
  title = "FDS Documentation Explorer",
  subtitle = "Your intelligent assistant for the Fabric Design System",
  placeholder = "Ask about FDS components, usage examples, best practices...",
}) => {
  const [inputValue, setInputValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [tokenCount, setTokenCount] = useState(0);
  const [currentTokens, setCurrentTokens] = useState(0);
  const [isStreamingActive, setIsStreamingActive] = useState(false);
  const [currentStreamingMessage, setCurrentStreamingMessage] = useState<ChatMessage | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [isScrolling, setIsScrolling] = useState(false);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastScrollTopRef = useRef<number>(0);
  const programmaticScrollRef = useRef<boolean>(false);

  // Use CopilotKit's useCopilotChat hook
  const { appendMessage, isLoading, visibleMessages } = useCopilotChat({
    id: "fds_documentation_explorer",
    initialMessages: [],
  });

  // Process streaming chunks similar to CLI implementation
  const processStreamingChunks = useCallback((content: string) => {
    const lines = content.split('\n').filter(line => line.trim());
    let assembledContent = '';
    let lastType = '';
    const msgBuffer: string[] = [];

    for (const line of lines) {
      try {
        // Handle concatenated JSON objects
        const jsonObjects = line.match(/\{[^}]*\}/g) || [];
        
        for (const jsonStr of jsonObjects) {
          try {
            const chunk: StreamingChunk = JSON.parse(jsonStr);
            
            if (chunk.type === "text") {
              msgBuffer.push(chunk.text);
              
              // If type changed or it's text, flush the buffer
              if (chunk.type === "text" || chunk.type !== lastType) {
                if (chunk.type !== lastType && chunk.type !== "text") {
                  assembledContent += `\n\n[[ ${chunk.type} ]]:\n`;
                } else if (chunk.type !== lastType && chunk.type === "text") {
                  assembledContent += `\n\n🤖 LLM:\n`;
                }
                assembledContent += msgBuffer.join("");
                msgBuffer.splice(0, msgBuffer.length); // Clear buffer
              }
              lastType = chunk.type;
            } else if (chunk.type === "tool_use") {
              if (chunk.type !== lastType) {
                assembledContent += `\n\n🔧 Tool call: ${chunk.text}\n`;
              } else {
                assembledContent += chunk.text;
              }
              lastType = chunk.type;
            } else if (chunk.type === "tool_out") {
              if (chunk.type !== lastType) {
                assembledContent += `\n\n🔍 Tool result:\n`;
              }
              assembledContent += chunk.text;
              lastType = chunk.type;
            } else if (chunk.type === "input") {
              assembledContent += `\n\n📝 Input: ${chunk.text}\n`;
              lastType = chunk.type;
            }
          } catch (parseError) {
            console.warn('Failed to parse JSON chunk:', jsonStr, parseError);
            // If it's not valid JSON, treat as plain text
            assembledContent += jsonStr;
          }
        }
      } catch (error) {
        console.warn('Failed to process line:', line, error);
        // Fallback: treat as plain text
        assembledContent += line + '\n';
      }
    }

    // Flush any remaining buffer content
    if (msgBuffer.length > 0) {
      assembledContent += msgBuffer.join("");
    }

    return assembledContent;
  }, []);

  // Convert CopilotKit messages to our format and track tokens
  useEffect(() => {
    const convertedMessages = visibleMessages.map((msg, index: number) => {
      console.log({ msg });
      
      // Type guard for message properties
      const hasContent = 'content' in msg && typeof msg.content === 'string';
      const hasRole = 'role' in msg;
      const hasId = 'id' in msg && typeof msg.id === 'string';
      const hasCreatedAt = 'createdAt' in msg;
      
      // Get the raw content and process it if it contains JSON chunks
      let content: string = hasContent ? msg.content as string : "";
      
      // Check if content contains JSON chunks and process them
      if (content.includes('{"type":')) {
        content = processStreamingChunks(content);
      }
      
      // Count tokens roughly (split by spaces and punctuation)
      const tokenEstimate = content
        .split(/[\s\n\r\t\.,;:!?\-\(\)\[\]{}'"]+/)
        .filter((t: string) => t.length > 0).length || 0;

      return {
        id: hasId ? msg.id : `msg-${index}`,
        role: hasRole && msg.role === Role.User ? ("user" as const) : ("assistant" as const),
        content: content,
        timestamp: new Date(hasCreatedAt && typeof msg.createdAt === 'string' ? msg.createdAt : Date.now()),
        tokens: tokenEstimate,
        isStreaming: false,
      };
    });

    // During streaming, exclude the last assistant message to avoid duplication with currentStreamingMessage
    let finalMessages = convertedMessages;
    if (isLoading && convertedMessages.length > 0) {
      const lastMessage = convertedMessages[convertedMessages.length - 1];
      if (lastMessage.role === 'assistant') {
        // Remove the last assistant message during streaming as it will be shown via currentStreamingMessage
        finalMessages = convertedMessages.slice(0, -1);
      }
    }

    setMessages(finalMessages);

    // Update total token count (use all messages including the one being streamed)
    const totalTokens = convertedMessages.reduce(
      (sum, msg) => sum + (msg.tokens || 0),
      0
    );
    setTokenCount(totalTokens);

    // Check if streaming is active
    setIsStreamingActive(isLoading);
  }, [visibleMessages, isLoading, processStreamingChunks]);

  // Track real-time token updates during streaming
  useEffect(() => {
    if (isLoading && visibleMessages.length > 0) {
      const lastMessage = visibleMessages[visibleMessages.length - 1];
      console.log({ lastVisibleMessage: lastMessage });
      
      const hasRole = 'role' in lastMessage;
      const hasContent = 'content' in lastMessage && typeof lastMessage.content === 'string';
      
      if (hasRole && lastMessage.role === Role.Assistant && hasContent) {
        let content: string = lastMessage.content as string;
        
        // Process streaming chunks for real-time display
        if (content.includes('{"type":')) {
          content = processStreamingChunks(content);
        }
        
        const tokenEstimate = content
          .split(/[\s\n\r\t\.,;:!?\-\(\)\[\]{}'"]+/)
          .filter((t: string) => t.length > 0).length || 0;
        setCurrentTokens(tokenEstimate);
        
        // Update current streaming message
        setCurrentStreamingMessage({
          id: `streaming-${Date.now()}`,
          role: 'assistant',
          content: content,
          timestamp: new Date(),
          tokens: tokenEstimate,
          isStreaming: true,
        });
      }
    } else {
      setCurrentTokens(0);
      setCurrentStreamingMessage(null);
    }
  }, [visibleMessages, isLoading, processStreamingChunks]);

  // Check if user is at the bottom of the scroll area
  const isAtBottom = useCallback(() => {
    if (!messagesContainerRef.current) return true;
    
    const container = messagesContainerRef.current;
    const threshold = 50; // Allow 50px tolerance
    const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - threshold;
    
    return isNearBottom;
  }, []);

  const scrollToBottom = useCallback((force = false) => {
    if (!messagesEndRef.current || !messagesContainerRef.current) return;
    
    // Don't auto-scroll if user has manually scrolled up, unless forced
    if (!force && userScrolledUp) {
      console.log('Auto-scroll prevented: user has scrolled up');
      return;
    }
    
    console.log('Scrolling to bottom, force:', force, 'userScrolledUp:', userScrolledUp);
    setIsScrolling(true);
    programmaticScrollRef.current = true;
    
    // Clear any existing timeout
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }
    
    messagesEndRef.current.scrollIntoView({ 
      behavior: "smooth",
      block: "end"
    });
    
    // Reset scrolling state after animation completes
    scrollTimeoutRef.current = setTimeout(() => {
      setIsScrolling(false);
      programmaticScrollRef.current = false;
    }, 1000); // Smooth scroll animation typically takes ~500-800ms
  }, [userScrolledUp]);

  // Handle scroll events to track user scroll position
  const handleScroll = useCallback(() => {
    if (!messagesContainerRef.current) return;
    
    const container = messagesContainerRef.current;
    const currentScrollTop = container.scrollTop;
    
    // If this is a programmatic scroll, update the reference but don't change user state
    if (programmaticScrollRef.current) {
      lastScrollTopRef.current = currentScrollTop;
      return;
    }
    
    // Don't process scroll events that are too close to the last known position
    // This helps filter out minor scroll adjustments
    const scrollDiff = Math.abs(currentScrollTop - lastScrollTopRef.current);
    if (scrollDiff < 3) return;
    
    // Check if user scrolled up manually (significant movement upward)
    if (currentScrollTop < lastScrollTopRef.current - 5) {
      // User scrolled up - pause auto-scrolling immediately
      if (!userScrolledUp) {
        setUserScrolledUp(true);
        console.log('User scrolled up, pausing auto-scroll');
      }
    }
    
    // Check if user scrolled back to bottom
    if (isAtBottom()) {
      // User is at bottom - resume auto-scrolling
      if (userScrolledUp) {
        setUserScrolledUp(false);
        console.log('User at bottom, resuming auto-scroll');
      }
    }
    
    lastScrollTopRef.current = currentScrollTop;
  }, [isAtBottom, userScrolledUp]);

  useEffect(() => {
    // Always scroll for new messages unless user has scrolled up
    scrollToBottom(false);
  }, [messages, isStreamingActive, currentStreamingMessage, scrollToBottom]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  // Initialize scroll position reference
  useEffect(() => {
    if (messagesContainerRef.current) {
      lastScrollTopRef.current = messagesContainerRef.current.scrollTop;
    }
  }, []);

  // Add wheel event listener to detect user scroll intent
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      // If user scrolls up with wheel, immediately pause auto-scroll
      if (e.deltaY < 0) {
        console.log('User wheel scroll up detected, pausing auto-scroll');
        setUserScrolledUp(true);
      }
    };

    const handleTouchStart = () => {
      // If user starts touch scroll, pause auto-scroll
      console.log('User touch scroll detected, pausing auto-scroll');
      setUserScrolledUp(true);
    };

    container.addEventListener('wheel', handleWheel, { passive: true });
    container.addEventListener('touchstart', handleTouchStart, { passive: true });

    return () => {
      container.removeEventListener('wheel', handleWheel);
      container.removeEventListener('touchstart', handleTouchStart);
    };
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!inputValue.trim() || isLoading) return;

      const messageContent = inputValue.trim();

      // Clear input immediately
      setInputValue("");

      // Reset token count for new conversation
      setCurrentTokens(0);
      
      // Reset scroll state - user is sending a message, so they want to see the response
      setUserScrolledUp(false);

      // Call onMessageSent callback if provided
      onMessageSent?.(messageContent);

      try {
        // Use CopilotKit's appendMessage to send the message
        await appendMessage(
          new TextMessage({
            content: messageContent,
            role: Role.User,
          })
        );
        
        // Force scroll to bottom after sending a message
        setTimeout(() => {
          scrollToBottom(true);
        }, 100);
      } catch (error) {
        console.error("Failed to send message:", error);

        // Add error message to local state if needed
        const errorMessage: ChatMessage = {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: "❌ Sorry, I encountered an error. Please try again.",
          timestamp: new Date(),
          tokens: 0,
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    },
    [inputValue, isLoading, onMessageSent, appendMessage, scrollToBottom]
  );

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as React.FormEvent);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);

    // Auto-resize textarea
    const textarea = e.target;
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
  };

  return (
    <div className="chat-container">
      {/* Header */}
      <div className="chat-header">
        <div className="header-content">
          <h1 className="chat-title">{title}</h1>
          <p className="chat-subtitle">{subtitle}</p>
        </div>

        {/* Real-time Token Counter */}
        <div className="token-counter">
          <div className="token-info">
            <span className="token-label">Tokens:</span>
            <span className="token-count">{tokenCount + (isStreamingActive ? currentTokens : 0)}</span>
            {isStreamingActive && currentTokens > 0 && (
              <span className="streaming-tokens">
                (+{currentTokens} streaming)
              </span>
            )}
            {isStreamingActive && (
              <div className="streaming-indicator">
                <div className="pulse-dot"></div>
                <span>Streaming...</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="messages-container" ref={messagesContainerRef} onScroll={handleScroll}>
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">🎨</div>
            <h3>Welcome to FDS Documentation Explorer</h3>
            <p>Ask me anything about the Fabric Design System!</p>
            <div className="example-queries">
              <button onClick={() => setInputValue("List all FDS components")}>
                List all FDS components
              </button>
              <button
                onClick={() =>
                  setInputValue("Show me Button component documentation")
                }
              >
                Show me Button component documentation
              </button>
              <button
                onClick={() => setInputValue("How do I implement theming?")}
              >
                How do I implement theming?
              </button>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${
              message.role === "user" ? "user-message" : "assistant-message"
            }`}
          >
            <div className="message-avatar">
              {message.role === "user" ? "👤" : "🤖"}
            </div>
            <div className="message-content">
              <div className="message-header">
                <span className="message-role">
                  {message.role === "user" ? "You" : "FDS Assistant"}
                </span>
                <span className="message-timestamp">
                  {message.timestamp.toLocaleTimeString()}
                </span>
                {message.tokens !== undefined && message.tokens > 0 && (
                  <span className="message-tokens">
                    {message.tokens} tokens
                  </span>
                )}
              </div>
              <div 
                className="message-text"
                style={{ whiteSpace: 'pre-wrap' }}
              >
                {message.content}
              </div>
            </div>
          </div>
        ))}

        {/* Show current streaming message */}
        {currentStreamingMessage && (
          <div className="message assistant-message streaming">
            <div className="message-avatar">🤖</div>
            <div className="message-content">
              <div className="message-header">
                <span className="message-role">FDS Assistant</span>
                <span className="streaming-indicator">
                  <div className="pulse-dot"></div>
                  Streaming...
                </span>
                {currentStreamingMessage.tokens !== undefined && currentStreamingMessage.tokens > 0 && (
                  <span className="message-tokens">
                    {currentStreamingMessage.tokens} tokens
                  </span>
                )}
              </div>
              <div 
                className="message-text"
                style={{ whiteSpace: 'pre-wrap' }}
              >
                {currentStreamingMessage.content}
              </div>
            </div>
          </div>
        )}

        {/* Fallback streaming indicator when no content yet */}
        {isStreamingActive && !currentStreamingMessage && (
          <div className="message assistant-message streaming">
            <div className="message-avatar">🤖</div>
            <div className="message-content">
              <div className="message-header">
                <span className="message-role">FDS Assistant</span>
                <span className="streaming-indicator">
                  <div className="pulse-dot"></div>
                  Thinking...
                </span>
              </div>
              <div className="typing-indicator">
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="input-container">
        <form onSubmit={handleSubmit} className="input-form">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyPress}
              placeholder={placeholder}
              className="message-input"
              disabled={isLoading}
              rows={1}
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || isLoading}
              className="send-button"
            >
              {isLoading ? (
                <div className="loading-spinner" />
              ) : (
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="currentColor"
                >
                  <path d="M8 0L16 8L8 16L7 15L13 9H0V7H13L7 1L8 0Z" />
                </svg>
              )}
            </button>
          </div>
        </form>
      </div>

      <style jsx>{`
        .chat-container {
          display: flex;
          flex-direction: column;
          height: 100vh;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
            sans-serif;
        }

        .chat-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px 24px;
          background: rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(20px);
          border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }

        .header-content {
          flex: 1;
        }

        .chat-title {
          margin: 0;
          font-size: 24px;
          font-weight: 700;
          color: white;
          text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }

        .chat-subtitle {
          margin: 4px 0 0 0;
          font-size: 14px;
          color: rgba(255, 255, 255, 0.8);
        }

        .token-counter {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 8px;
        }

        .token-info {
          display: flex;
          align-items: center;
          gap: 8px;
          background: rgba(255, 255, 255, 0.1);
          padding: 8px 12px;
          border-radius: 16px;
          border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .token-label {
          font-size: 12px;
          color: rgba(255, 255, 255, 0.7);
          font-weight: 500;
        }

        .token-count {
          font-size: 14px;
          color: white;
          font-weight: 600;
          min-width: 30px;
          text-align: right;
        }

        .streaming-tokens {
          font-size: 12px;
          color: #4ade80;
          font-weight: 500;
        }

        .streaming-indicator {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #4ade80;
        }

        .pulse-dot {
          width: 6px;
          height: 6px;
          background: #4ade80;
          border-radius: 50%;
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0%,
          100% {
            opacity: 0.4;
            transform: scale(1);
          }
          50% {
            opacity: 1;
            transform: scale(1.2);
          }
        }

        .messages-container {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .empty-state {
          text-align: center;
          padding: 60px 20px;
          color: white;
        }

        .empty-icon {
          font-size: 48px;
          margin-bottom: 16px;
        }

        .empty-state h3 {
          margin: 0 0 8px 0;
          font-size: 24px;
          font-weight: 600;
        }

        .empty-state p {
          margin: 0 0 24px 0;
          opacity: 0.8;
        }

        .example-queries {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-width: 300px;
          margin: 0 auto;
        }

        .example-queries button {
          background: rgba(255, 255, 255, 0.1);
          border: 1px solid rgba(255, 255, 255, 0.2);
          color: white;
          padding: 12px 16px;
          border-radius: 8px;
          font-size: 14px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .example-queries button:hover {
          background: rgba(255, 255, 255, 0.2);
          transform: translateY(-1px);
        }

        .message {
          display: flex;
          gap: 12px;
          align-items: flex-start;
        }

        .user-message {
          flex-direction: row-reverse;
        }

        .message-avatar {
          width: 36px;
          height: 36px;
          border-radius: 18px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
          background: rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255, 255, 255, 0.2);
          flex-shrink: 0;
        }

        .message-content {
          max-width: 70%;
          background: rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: 16px;
          padding: 16px;
          color: white;
        }

        .user-message .message-content {
          background: rgba(255, 255, 255, 0.2);
        }

        .message-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          font-size: 12px;
        }

        .message-role {
          font-weight: 600;
          color: white;
        }

        .message-timestamp {
          opacity: 0.6;
        }

        .message-tokens {
          background: rgba(255, 255, 255, 0.1);
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 10px;
          margin-left: auto;
        }

        .message-text {
          line-height: 1.5;
          word-wrap: break-word;
        }

        .message-text :global(strong) {
          font-weight: 600;
        }

        .message-text :global(em) {
          font-style: italic;
        }

        .message-text :global(code) {
          background: rgba(0, 0, 0, 0.2);
          padding: 2px 4px;
          border-radius: 4px;
          font-family: "Monaco", "Consolas", monospace;
          font-size: 0.9em;
        }

        .streaming {
          opacity: 0.8;
        }

        .typing-indicator {
          display: flex;
          gap: 4px;
          padding: 8px 0;
        }

        .typing-dot {
          width: 6px;
          height: 6px;
          background: rgba(255, 255, 255, 0.6);
          border-radius: 50%;
          animation: typing 1.4s ease-in-out infinite;
        }

        .typing-dot:nth-child(2) {
          animation-delay: 0.2s;
        }

        .typing-dot:nth-child(3) {
          animation-delay: 0.4s;
        }

        @keyframes typing {
          0%,
          60%,
          100% {
            transform: translateY(0);
            opacity: 0.4;
          }
          30% {
            transform: translateY(-10px);
            opacity: 1;
          }
        }

        .input-container {
          padding: 20px 24px;
          background: rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(20px);
          border-top: 1px solid rgba(255, 255, 255, 0.2);
        }

        .input-form {
          width: 100%;
        }

        .input-wrapper {
          display: flex;
          gap: 12px;
          align-items: flex-end;
          background: rgba(255, 255, 255, 0.1);
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: 16px;
          padding: 12px;
          transition: all 0.2s ease;
        }

        .input-wrapper:focus-within {
          border-color: rgba(255, 255, 255, 0.4);
          background: rgba(255, 255, 255, 0.15);
        }

        .message-input {
          flex: 1;
          background: transparent;
          border: none;
          outline: none;
          color: white;
          font-size: 16px;
          resize: none;
          min-height: 20px;
          max-height: 120px;
          line-height: 1.4;
        }

        .message-input::placeholder {
          color: rgba(255, 255, 255, 0.6);
        }

        .message-input:disabled {
          opacity: 0.5;
        }

        .send-button {
          background: linear-gradient(135deg, #4ade80, #22c55e);
          border: none;
          border-radius: 8px;
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          cursor: pointer;
          transition: all 0.2s ease;
          flex-shrink: 0;
        }

        .send-button:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(74, 222, 128, 0.3);
        }

        .send-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
        }

        .loading-spinner {
          width: 16px;
          height: 16px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top: 2px solid white;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          0% {
            transform: rotate(0deg);
          }
          100% {
            transform: rotate(360deg);
          }
        }

        @media (max-width: 768px) {
          .chat-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 12px;
          }

          .token-counter {
            align-self: stretch;
            align-items: flex-start;
          }

          .message-content {
            max-width: 85%;
          }

          .chat-title {
            font-size: 20px;
          }

          .example-queries {
            max-width: 100%;
          }
        }
      `}</style>
    </div>
  );
};
