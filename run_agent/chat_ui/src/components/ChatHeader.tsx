interface ChatHeaderProps {
  sidebarOpen: boolean;
  isRunning: boolean;
  totalTokenUsage: { totalInput: number; totalOutput: number; totalTokens: number } | null;
  onToggleSidebar: () => void;
  onClearChat: () => void;
  onRunDemo: () => void;
}

export function ChatHeader({
  sidebarOpen,
  isRunning,
  totalTokenUsage,
  onToggleSidebar,
  onClearChat,
  onRunDemo,
}: ChatHeaderProps) {
  return (
    <div
      style={{
        padding: "15px 20px",
        borderBottom: "1px solid #ccc",
        backgroundColor: "#fff",
        display: "flex",
        alignItems: "center",
        gap: "10px",
      }}
    >
      <button
        onClick={onToggleSidebar}
        style={{
          background: "transparent",
          border: "1px solid #ccc",
          padding: "6px 10px",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "12px",
        }}
      >
        {sidebarOpen ? "◀" : "▶"}
      </button>
      
      <h1 style={{ margin: 0, flex: 1 }}>AG-UI Agent Console</h1>
      
      {/* Token usage summary */}
      {totalTokenUsage && (
        <div style={{
          fontSize: "12px",
          color: "#666",
          backgroundColor: "#f8f9fa",
          padding: "4px 8px",
          borderRadius: "4px",
          fontFamily: "monospace",
          marginRight: "10px"
        }}>
          📊 Total: {totalTokenUsage.totalInput} + {totalTokenUsage.totalOutput} = {totalTokenUsage.totalTokens} tokens
        </div>
      )}
      
      {isRunning && (
        <div
          style={{
            background: "#007acc",
            color: "white",
            padding: "4px 8px",
            borderRadius: "4px",
            fontSize: "12px",
          }}
        >
          Running...
        </div>
      )}
      
      <button
        onClick={onClearChat}
        style={{
          background: "#dc3545",
          color: "white",
          border: "none",
          padding: "6px 12px",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "12px",
        }}
      >
        Clear Chat
      </button>
      
      <button
        onClick={onRunDemo}
        style={{
          background: "#3575dcff",
          color: "white",
          border: "none",
          padding: "6px 12px",
          borderRadius: "4px",
          cursor: "pointer",
          fontSize: "12px",
        }}
      >
        Run Demo
      </button>
    </div>
  );
}
