import { useState } from "react";
import "./App.css";

// Components
import { ChatHistorySidebar } from "./components/ChatHistorySidebar";
import { ChatHeader } from "./components/ChatHeader";
import { ChatInput } from "./components/ChatInput";
import { ChatMessagesContainer } from "./components/ChatMessagesContainer";

// Hooks
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
  const {isRunning,totalTokenUsage,messages, groupedMessages,chatWithAgent,clearChat,respondToLastInterrupt } = useAgentService();

  // Helper function to start a new chat
  const startNewChat = async (message: string) => {
    try {
      const title = message.length > 50 ? message.substring(0, 50) + "..." : message;
      const newThread = await createNewThread(title, message);
      
      // Clear current chat messages when starting a new thread
      clearChat();

      
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
      respondToLastInterrupt(message);
      
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
          chatMessages={messages}
          respondToLastInterrupt={respondToLastInterrupt}
          groupedMessages={groupedMessages}
        />
      </div>
    </div>
  );
}

export default App;
