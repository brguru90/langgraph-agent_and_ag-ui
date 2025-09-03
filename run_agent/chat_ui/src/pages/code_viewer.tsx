import {  useSearchParams } from 'react-router';
import { useEffect, useRef, useState } from 'react';
import type { CodeSnippet } from '../types';
import VueSfcPreview from '../components/VueSfcPreview';
import UnsupportedCodeViewer from '../components/UnsupportedCodeViewer';

export default function CodeViewer() {
  const [searchParams] = useSearchParams();
  const [codeSnippet, setCodeSnippet] = useState<CodeSnippet | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const loaded=useRef(false)

  useEffect(() => {
    // First, try to get from URL parameter (new tab approach)
    const snippetId = searchParams.get('snippetId');

    if (!loaded.current) {
      loaded.current=true
      return;
    }

    if (snippetId && !codeSnippet) {
      try {
        const storedSnippet = sessionStorage.getItem(snippetId);
        if (storedSnippet) {
          const parsedSnippet = JSON.parse(storedSnippet);
          setCodeSnippet(parsedSnippet);
          // Clean up the stored data after use
          // sessionStorage.removeItem(snippetId);
        } else {
          setError('Code snippet not found. The link may have expired.');
        }
      } catch (err) {
        setError('Failed to load code snippet data.');
        console.error('Error parsing snippet from sessionStorage:', err);
      }
    }
    
    setLoading(false);
  }, [searchParams]);

  if (loading) {
    return (
      <div style={{ padding: "20px", textAlign: "center" }}>
        <h2>Loading Code Snippet...</h2>
      </div>
    );
  }

  if (error || !codeSnippet) {
    return (
      <div style={{ padding: "20px", textAlign: "center" }}>
        <h2>No Code Snippet Available</h2>
        <p>{error || "Please select a code snippet from the chat to view it here."}</p>
      </div>
    );
  }

  // Check if this is a Vue SFC (Single File Component)
  const isVueSfc = codeSnippet.language.toLowerCase() === 'vue' || 
                   codeSnippet.file_name.toLowerCase().endsWith('.vue') ||
                   codeSnippet.framework?.toLowerCase() === 'vue' ||
                   codeSnippet.code.includes('<template>') && codeSnippet.code.includes('<script>');

  return (
    <div style={{ padding: "20px" }}>
      <h1>Code Viewer</h1>
      <div style={{ marginBottom: "20px" }}>
        <h2>{codeSnippet.file_name}</h2>
        <p><strong>Language:</strong> {codeSnippet.language}</p>
        {codeSnippet.framework && <p><strong>Framework:</strong> {codeSnippet.framework}</p>}
        {codeSnippet.pluggable_live_preview_component && (
          <p><strong>Live Preview Component:</strong> {codeSnippet.pluggable_live_preview_component}</p>
        )}
      </div>
      
      {codeSnippet.descriptions && codeSnippet.descriptions.length > 0 && (
        <div style={{ marginBottom: "20px" }}>
          <h3>Descriptions:</h3>
          <ul>
            {codeSnippet.descriptions.map((desc, idx) => (
              <li key={idx}>{desc}</li>
            ))}
          </ul>
        </div>
      )}

      <div style={{ marginBottom: "20px" }}>
        {isVueSfc ? (
          <VueSfcPreview 
            code={codeSnippet.code}
            onError={(error) => console.error('Vue SFC Preview Error:', error)}
          />
        ) : (
          <UnsupportedCodeViewer 
            language={codeSnippet.language}
            code={codeSnippet.code}
          />
        )}
      </div>

      {isVueSfc && (
        <div style={{ marginTop: "20px" }}>
          <h4>Source Code:</h4>
          <pre style={{
            backgroundColor: "#f8f9fa",
            padding: "16px",
            borderRadius: "6px",
            overflow: "auto",
            whiteSpace: "pre-wrap",
            border: "1px solid #e9ecef",
            fontSize: "14px",
            lineHeight: "1.5"
          }}>
            <code>{codeSnippet.code}</code>
          </pre>
        </div>
      )}
    </div>
  );
}
