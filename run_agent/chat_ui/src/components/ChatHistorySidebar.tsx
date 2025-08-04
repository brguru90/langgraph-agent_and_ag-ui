import type { ChatThread } from "../types";

interface ChatHistorySidebarProps {
  sidebarOpen: boolean;
  chatThreads: ChatThread[];
  selectedThreadId: string | null;
  isLoadingHistory: boolean;
  isRunning: boolean;
  onToggleSidebar: () => void;
  onSelectThread: (threadId: string) => void;
  onNewChat: () => void;
}

export function ChatHistorySidebar({
  sidebarOpen,
  chatThreads,
  selectedThreadId,
  isLoadingHistory,
  isRunning,
  onSelectThread,
  onNewChat,
}: ChatHistorySidebarProps) {
  return (
    <div
      style={{
        width: sidebarOpen ? "300px" : "0",
        backgroundColor: "#f8f9fa",
        borderRight: "1px solid #ccc",
        transition: "width 0.3s ease",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          padding: "15px",
          borderBottom: "1px solid #ddd",
          backgroundColor: "#fff",
        }}
      >
        <h3 style={{ margin: "0 0 10px 0", fontSize: "16px" }}>Chat History</h3>
        <button
          onClick={onNewChat}
          style={{
            width: "100%",
            background: "#007acc",
            color: "white",
            border: "none",
            padding: "8px 12px",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "12px",
          }}
          disabled={isRunning}
        >
          + New Chat
        </button>
      </div>
      
      <div style={{ flex: 1, overflow: "auto", padding: "10px" }}>
        {isLoadingHistory ? (
          <div style={{ textAlign: "center", color: "#666", padding: "20px" }}>
            Loading...
          </div>
        ) : chatThreads.length === 0 ? (
          <div style={{ textAlign: "center", color: "#666", padding: "20px" }}>
            No chat history yet
          </div>
        ) : (
          chatThreads.map((thread) => (
            <div
              key={thread.id}
              onClick={() => onSelectThread(thread.id)}
              style={{
                padding: "12px",
                marginBottom: "8px",
                backgroundColor: selectedThreadId === thread.id ? "#e3f2fd" : "#fff",
                border: selectedThreadId === thread.id ? "2px solid #007acc" : "1px solid #ddd",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "12px",
                transition: "all 0.2s ease",
              }}
            >
              <div style={{ fontWeight: "bold", marginBottom: "4px" }}>
                {thread.title}
              </div>
              <div style={{ color: "#666", fontSize: "10px" }}>
                {thread.messageCount} messages • {thread.lastMessageAt.toLocaleDateString()}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
