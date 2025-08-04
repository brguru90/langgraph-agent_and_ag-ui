interface ChatInputProps {
  userInput: string;
  selectedThreadId: string | null;
  isRunning: boolean;
  onInputChange: (value: string) => void;
  onSendMessage: () => void;
}

export function ChatInput({
  userInput,
  selectedThreadId,
  isRunning,
  onInputChange,
  onSendMessage,
}: ChatInputProps) {
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      onSendMessage();
    }
  };

  return (
    <div
      style={{
        padding: "15px 20px",
        borderBottom: "1px solid #ccc",
        backgroundColor: "#fff",
      }}
    >
      <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
        <input
          type="text"
          value={userInput}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder={selectedThreadId ? "Continue conversation..." : "Start new conversation..."}
          disabled={isRunning}
          style={{
            flex: 1,
            padding: "10px",
            border: "1px solid #ccc",
            borderRadius: "4px",
            fontSize: "14px",
          }}
        />
        <button
          onClick={onSendMessage}
          disabled={!userInput.trim() || isRunning}
          style={{
            background: userInput.trim() && !isRunning ? "#007acc" : "#ccc",
            color: "white",
            border: "none",
            padding: "10px 20px",
            borderRadius: "4px",
            cursor: userInput.trim() && !isRunning ? "pointer" : "not-allowed",
            fontSize: "14px",
          }}
        >
          Send
        </button>
      </div>
      {selectedThreadId && (
        <div style={{ marginTop: "8px", fontSize: "12px", color: "#666" }}>
          Continuing conversation in thread: {selectedThreadId}
        </div>
      )}
    </div>
  );
}
