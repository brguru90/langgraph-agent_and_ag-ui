import { useState, useCallback, useMemo } from "react";
import type { ChatDisplayMessage, TokenUsage, InterruptPrompt } from "../types";
import { randomUUID } from "../utils";

export const useChatState = () => {
  // State for chat display instead of raw logs
  const [chatMessages, setChatMessages] = useState<ChatDisplayMessage[]>([]);
  const [currentMessage, setCurrentMessage] = useState<ChatDisplayMessage | null>(null);
  const [currentToolCalls, setCurrentToolCalls] = useState<Map<string, {
    id: string;
    name: string;
    args: string;
    result?: string;
    isComplete?: boolean;
  }>>(new Map());
  const [interruptPrompt, setInterruptPrompt] = useState<InterruptPrompt | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  
  // Token usage tracking
  const [currentTokenUsage, setCurrentTokenUsage] = useState<TokenUsage | null>(null);
  
  // Calculate total token usage for the conversation
  const totalTokenUsage = useMemo(() => {
    let totalInput = 0;
    let totalOutput = 0;
    let totalTokens = 0;
    
    chatMessages.forEach(msg => {
      if (msg.tokenUsage) {
        totalInput += msg.tokenUsage.input_tokens;
        totalOutput += msg.tokenUsage.output_tokens;
        totalTokens += msg.tokenUsage.total_tokens;
      }
    });
    
    // Add current message tokens if available
    if (currentTokenUsage) {
      totalInput += currentTokenUsage.input_tokens;
      totalOutput += currentTokenUsage.output_tokens;
      totalTokens += currentTokenUsage.total_tokens;
    }
    
    return totalTokens > 0 ? { totalInput, totalOutput, totalTokens } : null;
  }, [chatMessages, currentTokenUsage]);

  // Helper function to add a chat message
  const addChatMessage = useCallback(
    (role: "user" | "assistant" | "system", content: string, message_type: "assistance" | "tool" | "interrupt" | "user" = "assistance") => {
      const newMessage: ChatDisplayMessage = {
        id: randomUUID(),
        message_type,
        role,
        content,
        timestamp: new Date(),
        isComplete: true,
      };
      setChatMessages((prev) => [...prev, newMessage]);
      return newMessage;
    },
    []
  );

  // Helper function to clear chat
  const clearChat = useCallback(() => {
    setChatMessages([]);
    setCurrentMessage(null);
    setCurrentToolCalls(new Map());
    setInterruptPrompt(null);
    setCurrentTokenUsage(null);
  }, []);

  return {
    // State
    chatMessages,
    currentMessage,
    currentToolCalls,
    interruptPrompt,
    isRunning,
    currentTokenUsage,
    totalTokenUsage,
    
    // Actions
    addChatMessage,
    clearChat,
    
    // Setters for advanced use cases
    setChatMessages,
    setCurrentMessage,
    setCurrentToolCalls,
    setInterruptPrompt,
    setIsRunning,
    setCurrentTokenUsage,
  };
};
