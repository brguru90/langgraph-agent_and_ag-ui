import React from 'react';

interface UnsupportedCodeViewerProps {
  language: string;
  code: string;
}

export const UnsupportedCodeViewer: React.FC<UnsupportedCodeViewerProps> = ({ language, code }) => {
  return (
    <div>
      <div style={{
        padding: '16px',
        backgroundColor: '#fff3cd',
        border: '1px solid #ffeaa7',
        borderRadius: '4px',
        marginBottom: '16px',
        color: '#856404'
      }}>
        <strong>Live Preview Not Supported</strong>
        <p style={{ margin: '8px 0 0 0' }}>
          Live preview is currently only supported for Vue 3 Single File Components (.vue). 
          The code below is displayed in read-only mode.
        </p>
      </div>
      
      <h4>Code ({language}):</h4>
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
        <code>{code}</code>
      </pre>
    </div>
  );
};

export default UnsupportedCodeViewer;
