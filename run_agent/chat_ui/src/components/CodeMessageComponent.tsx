import type { ChatDisplayMessage, CodeSnippet } from "../types";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { dark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface CodeMessageComponentProps {
  messages: ChatDisplayMessage[];
}

const LanguageIcon = ({ language }: { language: string }) => {
  const icons: Record<string, string> = {
    typescript: "📘",
    javascript: "💛",
    tsx: "⚛️",
    jsx: "⚛️",
    python: "🐍",
    css: "🎨",
    html: "🌐",
    json: "📋",
    yaml: "📄",
    markdown: "📝",
    sql: "🗃️",
    bash: "💻",
    shell: "💻",
  };
  return <span>{icons[language.toLowerCase()] || "📄"}</span>;
};

const FrameworkBadge = ({ framework }: { framework: string }) => {
  const colors: Record<string, string> = {
    react: "#61DAFB",
    vue: "#4FC08D",
    angular: "#DD0031",
    svelte: "#FF3E00",
    nextjs: "#000000",
    "next.js": "#000000",
    nuxt: "#00DC82",
    gatsby: "#663399",
  };
  
  return (
    <span
      style={{
        backgroundColor: colors[framework.toLowerCase()] || "#6B7280",
        color: "white",
        padding: "2px 6px",
        borderRadius: "4px",
        fontSize: "10px",
        fontWeight: "600",
        textTransform: "uppercase",
      }}
    >
      {framework}
    </span>
  );
};

const CodeSnippetRenderer = ({ snippet }: { snippet: CodeSnippet }) => {
  const handleApplyClick = () => {
    // Store the snippet data in sessionStorage with a unique key
    const snippetId = `code_snippet_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    sessionStorage.setItem(snippetId, JSON.stringify(snippet));
    
    // Open in new tab with the snippet ID as a query parameter
    setTimeout(() => {
        const newUrl = `/code?snippetId=${snippetId}`;
        window.open(newUrl, '_blank');
    }, 800);
  };

  return (
    <div
      style={{
        border: "1px solid #E5E7EB",
        borderRadius: "8px",
        marginBottom: "16px",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          backgroundColor: "#F9FAFB",
          padding: "8px 12px",
          borderBottom: "1px solid #E5E7EB",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          fontSize: "12px",
        }}
      >
        <LanguageIcon language={snippet.language} />
        <span style={{ fontWeight: "600", color: "#374151" }}>
          {snippet.file_name}
        </span>
        <span style={{ color: "#6B7280" }}>
          ({snippet.language})
        </span>
        {snippet.framework && (
          <FrameworkBadge framework={snippet.framework} />
        )}
        {snippet.pluggable_live_preview_component && (
          <button
            onClick={handleApplyClick}
            style={{
              marginLeft: "auto",
              backgroundColor: "#3B82F6",
              color: "white",
              padding: "4px 8px",
              borderRadius: "4px",
              border: "none",
              fontSize: "11px",
              fontWeight: "600",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
            onMouseEnter={(e) => {
              (e.target as HTMLElement).style.backgroundColor = "#2563EB";
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLElement).style.backgroundColor = "#3B82F6";
            }}
          >
            �️ Preview
          </button>
        )}
      </div>

      {/* Code */}
      <div style={{ position: "relative" }}>
        <SyntaxHighlighter
          language={snippet.language}
          style={dark}
          customStyle={{
            margin: 0,
            fontSize: "13px",
            lineHeight: "1.4",
          }}
          showLineNumbers={true}
          wrapLines={true}
        >
          {snippet.code}
        </SyntaxHighlighter>
      </div>

      {/* Descriptions */}
      {snippet.descriptions && snippet.descriptions.length > 0 && (
        <div
          style={{
            backgroundColor: "#F3F4F6",
            padding: "8px 12px",
            borderTop: "1px solid #E5E7EB",
            fontSize: "11px",
            color: "#4B5563",
          }}
        >
          <strong>Description:</strong>
          <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
            {snippet.descriptions.map((desc, idx) => (
              <li key={idx} style={{ marginBottom: "2px" }}>
                {desc}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export function CodeMessageComponent({ messages }: CodeMessageComponentProps) {
  // Get all code data from messages
  const codeDataList = messages
    .map(msg => msg.codeData)
    .filter(data => data && data.codeContent);

  if (codeDataList.length === 0) {
    return (
      <div
        style={{
          alignSelf: "flex-start",
          maxWidth: "90%",
          backgroundColor: "#FEF3C7",
          color: "#92400E",
          padding: "12px 16px",
          borderRadius: "18px 18px 18px 4px",
          border: "1px solid #F59E0B",
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
          marginBottom: "20px",
        }}
      >
        <div style={{ fontSize: "14px", fontWeight: "600", marginBottom: "4px" }}>
          📄 Code Content
        </div>
        <div style={{ fontSize: "12px", color: "#78350F" }}>
          No code content available
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        alignSelf: "flex-start",
        maxWidth: "95%",
        backgroundColor: "#F8FAFC",
        padding: "16px",
        borderRadius: "12px",
        border: "1px solid #E2E8F0",
        boxShadow: "0 2px 4px rgba(0,0,0,0.05)",
        marginBottom: "20px",
      }}
    >
      {codeDataList.map((codeData, index) => {
        const content = codeData!.codeContent!;
        
        return (
          <div key={codeData!.message_id || index}>
            {/* Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                marginBottom: "12px",
                paddingBottom: "8px",
                borderBottom: "1px solid #E2E8F0",
              }}
            >
              <span style={{ fontSize: "16px" }}>💻</span>
              <span style={{ fontWeight: "600", color: "#1E293B", fontSize: "14px" }}>
                Code Snippets
              </span>
              <span style={{ fontSize: "12px", color: "#64748B" }}>
                ({content.code_snippets.length} snippet{content.code_snippets.length !== 1 ? 's' : ''})
              </span>
            </div>

            {/* Global descriptions */}
            {content.descriptions && content.descriptions.length > 0 && (
              <div
                style={{
                  backgroundColor: "#EFF6FF",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  marginBottom: "12px",
                  border: "1px solid #DBEAFE",
                }}
              >
                <div style={{ fontSize: "12px", fontWeight: "600", color: "#1E40AF", marginBottom: "4px" }}>
                  📋 Overview:
                </div>
                <ul style={{ margin: 0, padding: "0 0 0 16px", fontSize: "11px", color: "#1E3A8A" }}>
                  {content.descriptions.map((desc, idx) => (
                    <li key={idx} style={{ marginBottom: "2px" }}>
                      {desc}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Code snippets */}
            <div>
              {content.code_snippets.map((snippet, snippetIndex) => (
                <CodeSnippetRenderer key={snippetIndex} snippet={snippet} />
              ))}
            </div>
          </div>
        );
      })}

      {/* Timestamp */}
      <div
        style={{
          fontSize: "10px",
          color: "#94A3B8",
          marginTop: "8px",
          textAlign: "right",
        }}
      >
        {new Date().toLocaleTimeString()}
      </div>
    </div>
  );
}
