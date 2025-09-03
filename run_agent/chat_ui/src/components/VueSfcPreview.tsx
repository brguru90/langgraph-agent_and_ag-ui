import React, { useEffect, useRef } from 'react';
import { createApp, type App } from 'vue';
import * as Vue from 'vue';

interface VueSfcPreviewProps {
  code: string;
  onError?: (error: string) => void;
}

export const VueSfcPreview: React.FC<VueSfcPreviewProps> = ({ code, onError }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const vueAppRef = useRef<App | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const renderVueComponent = async () => {
      try {
        // Clean up previous Vue app if it exists
        if (vueAppRef.current) {
          vueAppRef.current.unmount();
        }

        // Dynamic import of vue3-sfc-loader
        const { loadModule } = await import('vue3-sfc-loader');
        
        const options = {
          moduleCache: {
            vue: Vue,
          },
          async getFile(url: string) {
            if (url === '/component.vue') {
              return code;
            }
            // For other dependencies, you might want to fetch from CDN
            const response = await fetch(url);
            if (!response.ok) {
              throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
            }
            return response.text();
          },
          addStyle(textContent: string) {
            const style = Object.assign(document.createElement('style'), {
              textContent,
            });
            const ref = document.head.getElementsByTagName('style')[0] || null;
            document.head.insertBefore(style, ref);
          },
        };

        // Load the Vue component from the SFC code
        const component = await loadModule('/component.vue', options);

        // Create and mount the Vue app directly with the loaded component
        vueAppRef.current = createApp(component as unknown as object);
        vueAppRef.current.mount(containerRef.current);

      } catch (error) {
        console.error('Error rendering Vue SFC:', error);
        if (onError) {
          onError(error instanceof Error ? error.message : 'Unknown error occurred');
        }
        
        // Show error message in the container
        if (containerRef.current) {
          containerRef.current.innerHTML = `
            <div style="padding: 20px; background-color: #fee; border: 1px solid #fcc; border-radius: 4px; color: #d00;">
              <strong>Error rendering Vue component:</strong><br>
              ${error instanceof Error ? error.message : 'Unknown error'}
            </div>
          `;
        }
      }
    };

    renderVueComponent();

    // Cleanup function
    return () => {
      if (vueAppRef.current) {
        vueAppRef.current.unmount();
        vueAppRef.current = null;
      }
    };
  }, [code, onError]);

  return (
    <div>
      <h4>Live Preview:</h4>
      <div 
        ref={containerRef}
        style={{
          border: '1px solid #ddd',
          borderRadius: '4px',
          padding: '16px',
          minHeight: '100px',
          backgroundColor: '#fafafa'
        }}
      >
        Loading Vue component...
      </div>
    </div>
  );
};

export default VueSfcPreview;
