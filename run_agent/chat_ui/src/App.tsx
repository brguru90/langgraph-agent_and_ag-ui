import { useState } from "react";
import "./App.css";

// Components
import { ChatHistorySidebar } from "./components/ChatHistorySidebar";
import { ChatHeader } from "./components/ChatHeader";
import { ChatInput } from "./components/ChatInput";
import { ChatMessagesContainer } from "./components/ChatMessagesContainer";

// Hooks
import { useChatState } from "./hooks/useChatState";
import { useChatHistory } from "./hooks/useChatHistory";
import { useAgentService } from "./hooks/useAgentService";

// Utils
import { injectBlinkingCursorStyles } from "./utils";

// Inject styles on module load
injectBlinkingCursorStyles();

function App() {
  // UI State
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [userInput, setUserInput] = useState("");

  // Chat state management
  const {
    chatMessages,
    currentMessage,
    currentToolCalls,
    interruptPrompt,
    isRunning,
    currentTokenUsage,
    totalTokenUsage,
    addChatMessage,
    clearChat,
    setChatMessages,
    setCurrentMessage,
    setCurrentToolCalls,
    setInterruptPrompt,
    setIsRunning,
    setCurrentTokenUsage,
  } = useChatState();

  // Chat history management
  const {
    chatThreads,
    selectedThreadId,
    isLoadingHistory,
    setSelectedThreadId,
    createNewThread,
    addMessageToThread,
  } = useChatHistory();

  // Agent service (includes interrupt handling)
  const { chatWithAgent } = useAgentService({
    setIsRunning,
    currentMessage,
    setCurrentMessage,
    currentToolCalls,
    setCurrentToolCalls,
    setCurrentTokenUsage,
    setChatMessages,
    setInterruptPrompt,
  });

  // Helper function to start a new chat
  const startNewChat = async (message: string) => {
    try {
      const title = message.length > 50 ? message.substring(0, 50) + "..." : message;
      const newThread = await createNewThread(title, message);
      
      // Clear current chat messages when starting a new thread
      clearChat();
      
      // Add user message to chat
      addChatMessage("user", message, "user");
      
      return await chatWithAgent(message, newThread.id);
    } catch (error) {
      console.error("Failed to create new chat:", error);
      throw error;
    }
  };

  // Helper function to continue existing chat
  const continueChat = async (message: string, threadId: string) => {
    try {
      // Add user message to chat first
      addChatMessage("user", message, "user");
      
      await addMessageToThread(threadId, "user", message);
      
      return await chatWithAgent(message, threadId);
    } catch (error) {
      console.error("Failed to continue chat:", error);
      throw error;
    }
  };

  // Helper function to handle user input
  const handleSendMessage = async () => {
    if (!userInput.trim() || isRunning) return;
    
    const message = userInput.trim();
    setUserInput("");
    
    try {
      if (selectedThreadId) {
        await continueChat(message, selectedThreadId);
      } else {
        await startNewChat(message);
      }
    } catch (error) {
      console.error("Failed to send message:", error);
    }
  };

  // Handle new chat button
  const handleNewChat = () => {
    setSelectedThreadId(null);
    setUserInput("");
    clearChat();
  };

  // Handle thread selection
  const handleSelectThread = (threadId: string) => {
    setSelectedThreadId(threadId);
  };

  // Enhanced main function with history support
  const runDemo = async () => {
    console.log("🚀 Starting main execution...");

    const lastAgent = await startNewChat("provide me documentation for button component");
    
    if (lastAgent?.threadId) {
      console.log(`First agent completed. Thread ID: ${lastAgent.threadId}`);
      
      await new Promise((resolve) => setTimeout(resolve, 1000));
      
      console.log("🔄 Running second query...");
      await continueChat("What was my last query", lastAgent.threadId);
    }
    
    console.log("-- Done --");
    console.log("🎉 All executions completed!");
  };

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "monospace" }}>
      {/* History Sidebar */}
      <ChatHistorySidebar
        sidebarOpen={sidebarOpen}
        chatThreads={chatThreads}
        selectedThreadId={selectedThreadId}
        isLoadingHistory={isLoadingHistory}
        isRunning={isRunning}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        onSelectThread={handleSelectThread}
        onNewChat={handleNewChat}
      />

      {/* Main Content Area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <ChatHeader
          sidebarOpen={sidebarOpen}
          isRunning={isRunning}
          totalTokenUsage={totalTokenUsage}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          onClearChat={clearChat}
          onRunDemo={runDemo}
        />

        {/* Chat Input Area */}
        <ChatInput
          userInput={userInput}
          selectedThreadId={selectedThreadId}
          isRunning={isRunning}
          onInputChange={setUserInput}
          onSendMessage={handleSendMessage}
        />

        {/* Chat Messages Area */}
        <ChatMessagesContainer
          chatMessages={chatMessages}
          currentMessage={currentMessage}
          currentTokenUsage={currentTokenUsage}
          currentToolCalls={currentToolCalls}
          interruptPrompt={interruptPrompt}
        />
      </div>
    </div>
  );
}

export default App;
