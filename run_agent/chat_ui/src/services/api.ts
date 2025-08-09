import type { ChatThread, ChatMessage, ChatHistoryResponse, ThreadMessagesResponse, LangGraphMessage } from "../types";
import { randomUUID } from "../utils";

// Mock API functions for chat history
export class MockChatHistoryAPI {
  private static threads: ChatThread[] = [
    {
      id: "thread-1",
      title: "Button Component Documentation",
      createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000), // 2 days ago
      lastMessageAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
      messageCount: 4,
    },
    {
      id: "thread-2", 
      title: "Form Validation Questions",
      createdAt: new Date(Date.now() - 24 * 60 * 60 * 1000), // 1 day ago
      lastMessageAt: new Date(Date.now() - 24 * 60 * 60 * 1000),
      messageCount: 6,
    },
    {
      id: "thread-3",
      title: "State Management Help",
      createdAt: new Date(Date.now() - 4 * 60 * 60 * 1000), // 4 hours ago
      lastMessageAt: new Date(Date.now() - 4 * 60 * 60 * 1000),
      messageCount: 2,
    },
  ];

  private static messages: ChatMessage[] = [
    // Thread 1 messages
    {
      id: "msg-1-1",
      threadId: "thread-1",
      role: "user",
      content: "provide me documentation for button component",
      timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
    },
    {
      id: "msg-1-2",
      threadId: "thread-1", 
      role: "assistant",
      content: "Here's the documentation for the button component...",
      timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000 + 30000),
    },
    // Thread 2 messages
    {
      id: "msg-2-1",
      threadId: "thread-2",
      role: "user", 
      content: "How do I validate forms in React?",
      timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000),
    },
    {
      id: "msg-2-2",
      threadId: "thread-2",
      role: "assistant",
      content: "There are several ways to validate forms in React...",
      timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000 + 45000),
    },
    // Thread 3 messages
    {
      id: "msg-3-1", 
      threadId: "thread-3",
      role: "user",
      content: "What's the best state management library?", 
      timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000),
    },
    {
      id: "msg-3-2",
      threadId: "thread-3",
      role: "assistant",
      content: "The choice depends on your needs...",
      timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000 + 20000),
    },
  ];

  static async getChatHistory(): Promise<ChatHistoryResponse> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 300));
    return {
      threads: this.threads.sort((a, b) => b.lastMessageAt.getTime() - a.lastMessageAt.getTime()),
    };
  }

  static async getThreadMessages(threadId: string): Promise<ThreadMessagesResponse> {
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 200));
    const messages = this.messages
      .filter(msg => msg.threadId === threadId)
      .sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
    
    return { messages };
  }

  static async createThread(title: string, firstMessage: string): Promise<ChatThread> {
    await new Promise(resolve => setTimeout(resolve, 100));
    const newThreadId = randomUUID();
    
    // Check if thread already exists (shouldn't happen but safety check)
    const existingThread = this.threads.find(t => t.id === newThreadId);
    if (existingThread) {
      return existingThread;
    }
    
    const newThread: ChatThread = {
      id: newThreadId,
      title,
      createdAt: new Date(),
      lastMessageAt: new Date(),
      messageCount: 1,
    };
    
    const newMessage: ChatMessage = {
      id: `msg-${randomUUID()}`,
      threadId: newThread.id,
      role: "user",
      content: firstMessage,
      timestamp: new Date(),
    };
    
    this.threads.unshift(newThread);
    this.messages.push(newMessage);
    
    return newThread;
  }

  static async updateThread(threadId: string, updates: Partial<ChatThread>): Promise<void> {
    await new Promise(resolve => setTimeout(resolve, 100));
    const threadIndex = this.threads.findIndex(t => t.id === threadId);
    if (threadIndex !== -1) {
      this.threads[threadIndex] = { ...this.threads[threadIndex], ...updates };
    }
  }

  static async addMessage(message: Omit<ChatMessage, 'id' | 'timestamp'>): Promise<ChatMessage> {
    await new Promise(resolve => setTimeout(resolve, 100));
    const newMessage: ChatMessage = {
      ...message,
      id: `msg-${randomUUID()}`,
      timestamp: new Date(),
    };
    
    this.messages.push(newMessage);
    
    // Update thread's last message time and count
    const thread = this.threads.find(t => t.id === message.threadId);
    if (thread) {
      thread.lastMessageAt = new Date();
      thread.messageCount += 1;
    }
    
    return newMessage;
  }
}

// Function to get state from the server
export async function getAgentState(
  thread_id: string
): Promise<{ messages: LangGraphMessage[] }> {
  try {
    const url = `http://localhost:8000/state?thread_id=${encodeURIComponent(
      thread_id
    )}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const state = await response.json();
    return state;
  } catch (error) {
    console.error("Error fetching state:", error);
    throw error;
  }
}
