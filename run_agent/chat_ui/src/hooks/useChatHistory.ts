import { useState, useEffect, useMemo } from "react";
import type { ChatThread } from "../types";
import { MockChatHistoryAPI } from "../services/api";

export const useChatHistory = () => {
  const [chatThreads, setChatThreads] = useState<ChatThread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  // Memoize chat threads to prevent unnecessary re-renders
  const memoizedChatThreads = useMemo(() => {
    // Remove any potential duplicates by thread ID
    const uniqueThreads = chatThreads.filter((thread, index, self) => 
      index === self.findIndex(t => t.id === thread.id)
    );
    return uniqueThreads;
  }, [chatThreads]);

  // Load chat history on component mount
  useEffect(() => {
    const loadHistory = async () => {
      setIsLoadingHistory(true);
      try {
        const response = await MockChatHistoryAPI.getChatHistory();
        setChatThreads(response.threads);
      } catch (error) {
        console.error("Failed to load chat history:", error);
      } finally {
        setIsLoadingHistory(false);
      }
    };
    loadHistory();
  }, []);

  const loadChatHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const response = await MockChatHistoryAPI.getChatHistory();
      setChatThreads(response.threads);
    } catch (error) {
      console.error("Failed to load chat history:", error);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const createNewThread = async (title: string, firstMessage: string) => {
    try {
      const newThread = await MockChatHistoryAPI.createThread(title, firstMessage);
      
      // Update chat threads list without duplicates
      setChatThreads(prev => {
        const existing = prev.find(t => t.id === newThread.id);
        if (existing) {
          return prev; // Don't add duplicate
        }
        return [newThread, ...prev];
      });
      
      setSelectedThreadId(newThread.id);
      return newThread;
    } catch (error) {
      console.error("Failed to create new chat:", error);
      throw error;
    }
  };

  const addMessageToThread = async (threadId: string, role: "user" | "assistant", content: string) => {
    try {
      await MockChatHistoryAPI.addMessage({
        threadId,
        role,
        content,
      });
      await loadChatHistory(); // Refresh the list
    } catch (error) {
      console.error("Failed to add message to thread:", error);
      throw error;
    }
  };

  return {
    chatThreads: memoizedChatThreads,
    selectedThreadId,
    isLoadingHistory,
    setSelectedThreadId,
    loadChatHistory,
    createNewThread,
    addMessageToThread,
  };
};
