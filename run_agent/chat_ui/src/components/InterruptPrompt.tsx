import { useState } from "react";
import type { InterruptPrompt } from "../types";

interface InterruptPromptComponentProps {
  prompt: InterruptPrompt;
}

export function InterruptPromptComponent({ prompt }: InterruptPromptComponentProps) {
  const [input, setInput] = useState("");
  const [responseType, setResponseType] = useState<"yes" | "no" | "custom">("custom");

  const handleSubmit = () => {
    const response = responseType === "custom" ? input : responseType;
    prompt.onSubmit(response);
    setInput("");
  };

  const handleCancel = () => {
    prompt.onCancel();
    setInput("");
  };

  const handleQuickResponse = (type: "yes" | "no") => {
    setResponseType(type);
    prompt.onSubmit(type);
  };

  return (
    <div
      style={{
        marginBottom: "20px",
        display: "flex",
        flexDirection: "column",
        alignSelf: "center",
        maxWidth: "90%",
      }}
    >
      <div
        style={{
          backgroundColor: "#fff3cd",
          color: "#856404",
          padding: "12px 16px",
          borderRadius: "8px",
          border: "1px solid #ffeaa7",
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
        }}
      >
        <div style={{ fontSize: "14px", lineHeight: "1.4", marginBottom: "15px" }}>
          <strong>⚠️ Agent needs input:</strong>
          <br />
          {prompt.message}
        </div>
        
        {/* Quick response buttons */}
        <div style={{ display: "flex", gap: "8px", marginBottom: "10px", justifyContent: "center" }}>
          <button
            onClick={() => handleQuickResponse("yes")}
            style={{
              background: "#28a745",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "12px",
              fontWeight: "bold",
            }}
          >
            Yes
          </button>
          <button
            onClick={() => handleQuickResponse("no")}
            style={{
              background: "#dc3545",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "12px",
              fontWeight: "bold",
            }}
          >
            No
          </button>
        </div>
        
        {/* Custom response input */}
        <div style={{ fontSize: "12px", marginBottom: "8px", textAlign: "center", color: "#6c757d" }}>
          Or provide custom response:
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input
            type="text"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setResponseType("custom");
            }}
            onKeyPress={(e) => {
              if (e.key === "Enter") {
                handleSubmit();
              } else if (e.key === "Escape") {
                handleCancel();
              }
            }}
            placeholder="Enter custom response..."
            style={{
              flex: 1,
              padding: "8px 12px",
              border: "1px solid #ccc",
              borderRadius: "4px",
              fontSize: "12px",
            }}
          />
          <button
            onClick={handleSubmit}
            disabled={responseType === "custom" && !input.trim()}
            style={{
              background: (responseType === "custom" && input.trim()) || responseType !== "custom" ? "#007acc" : "#ccc",
              color: "white",
              border: "none",
              padding: "8px 12px",
              borderRadius: "4px",
              cursor: (responseType === "custom" && input.trim()) || responseType !== "custom" ? "pointer" : "not-allowed",
              fontSize: "12px",
            }}
          >
            Submit
          </button>
          <button
            onClick={handleCancel}
            style={{
              background: "#6c757d",
              color: "white",
              border: "none",
              padding: "8px 12px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "12px",
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
