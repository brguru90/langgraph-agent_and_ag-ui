"use client";

import { useState } from "react";
import { CustomChatUI } from "../components/CustomChatUI";
import { CopilotKit } from "@copilotkit/react-core";

type AgentState = {
  queries: string[];
  messages: string[];
};

export default function CopilotKitPage() {
  const [debugMode, setDebugMode] = useState(false);
  const [state, setState] = useState<AgentState>({
    queries: [],
    messages: []
  });

  const handleMessageSent = (message: string) => {
    // Update state with new query
    setState(prev => ({
      ...prev,
      queries: [...prev.queries, message]
    }));
    
    console.log("Message sent to agent:", message);
  };

  return (
    <CopilotKit 
      runtimeUrl="/api/copilotkit"
      agent="fds_documentation_explorer"
    >
      <main className="app-container">
        <CustomChatUI
          onMessageSent={handleMessageSent}
          title="🎨 FDS Documentation Explorer"
          subtitle="Your intelligent assistant for the Fabric Design System"
          placeholder="Ask about FDS components, usage examples, best practices, or implementation details..."
        />

        {/* Debug Panel */}
        <div className="debug-panel">
          <button 
            onClick={() => setDebugMode(!debugMode)} 
          className="debug-toggle"
        >
          {debugMode ? '🔼' : '🔽'} Debug Panel
        </button>
        
        {debugMode && (
          <div className="debug-content">
            <div className="debug-section">
              <h4>🔍 Recent Queries</h4>
              {state?.queries?.length ? (
                <ul>
                  {state.queries.slice(-5).map((query, index) => (
                    <li key={index}>{query}</li>
                  ))}
                </ul>
              ) : (
                <p>No queries yet</p>
              )}
            </div>
            
            <div className="debug-section">
              <h4>📊 Agent Messages</h4>
              {state?.messages?.length ? (
                <ul>
                  {state.messages.slice(-5).map((msg, index) => (
                    <li key={index}>{msg}</li>
                  ))}
                </ul>
              ) : (
                <p>No agent messages yet</p>
              )}
            </div>
          </div>
        )}
      </div>

      <style jsx>{`
        .app-container {
          height: 100vh;
          position: relative;
          display:flex;
          flex-direction: column;
          overflow: auto;
        }

        .debug-panel {
          display:none;
          color: white;
          z-index: 1000;
          background: rgba(0, 0, 0, 0.9);
          transition: all 0.3s ease;
          position: sticky;
          bottom: 0;
          left: 0;
          right: 0;
        }

        .debug-toggle {
          color: white;
          cursor: pointer;
          text-align: center;
          background: rgba(0, 0, 0, 0.8);
          border: none;
          width: 100%;
          padding: 8px 16px;
          font-size: 12px;
          transition: background 0.2s ease;
        }

        .debug-toggle:hover {
          background: rgba(0, 0, 0, 0.6);
        }

        .debug-content {
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          max-height: 200px;
          padding: 16px;
          display: grid;
          overflow-y: auto;
        }

        .debug-section h4 {
          color: white;
          margin: 0 0 8px 0;
          font-size: 14px;
        }

        .debug-section ul {
          margin: 0;
          padding: 0;
          font-size: 12px;
          list-style: none;
        }

        .debug-section li {
          opacity: 0.8;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          padding: 4px 0;
        }

        .debug-section p {
          opacity: 0.6;
          margin: 0;
          font-size: 12px;
          font-style: italic;
        }

        @media (max-width: 768px) {
          .debug-content {
            grid-template-columns: 1fr;
            gap: 16px;
          }
        }
      `}</style>
    </main>
    </CopilotKit>
  );
}
