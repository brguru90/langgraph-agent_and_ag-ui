// Utility functions for the chat application

export const getRandomString = (_len = 20) =>
  Array.from(window.crypto.getRandomValues(new Uint8Array(_len)))
    .map((c: number) => Number(c).toString(36))
    .join('');

export const randomUUID = () => {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback with timestamp to ensure uniqueness
  return `${Date.now()}-${getRandomString(16)}`;
};

// Add CSS for blinking cursor
export const injectBlinkingCursorStyles = () => {
  const styles = `
    @keyframes blink {
      0%, 50% { opacity: 1; }
      51%, 100% { opacity: 0; }
    }
  `;

  // Inject the styles
  if (typeof document !== 'undefined') {
    const styleSheet = document.createElement("style");
    styleSheet.type = "text/css";
    styleSheet.innerText = styles;
    document.head.appendChild(styleSheet);
  }
};
