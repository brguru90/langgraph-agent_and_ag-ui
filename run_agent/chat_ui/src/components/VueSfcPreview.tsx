import React, { useEffect, useRef } from "react";
import * as Vue from "vue";
import * as vueSfc from "vue3-sfc-loader";

interface VueSfcPreviewProps {
  code: string;
  onError?: (error: string) => void;
}

export const VueSfcPreview: React.FC<VueSfcPreviewProps> = ({
  code,
  onError,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const vueAppRef = useRef<App | null>(null);

  const renderVueComponent = async () => {
    // console.log({code})
    try {
      // Clean up previous Vue app if it exists
      if (vueAppRef.current) {
        vueAppRef.current.unmount();
      }

      // Dynamic import of vue3-sfc-loader
      const { loadModule, vueVersion } = window["vue3-sfc-loader"];
      console.log({ vueSfc, loadModule });

      const options = {
        moduleCache: {
          vue: Vue,
          myData: {
            vueVersion,
          },
        },
        async getFile(url: string) {
          console.log({ url });
          if (url.endsWith("/component.vue")) {
            console.log("return code", { code }, typeof code);
            // return Promise.resolve(code);

            return `
            <template>Test</template>
            <script>
            import { ref, reactive } from 'vue'
            import { EsButton } from '@esentire/fabric'

            </script>
            `;

            // return  Promise.resolve(`<template>Test</template><script setup></script><style scoped></style>`)
            // return {
            //     getContentData: (asBinary: boolean) => {
            //         console.log({asBinary})
            //         return asBinary ? new TextEncoder().encode(code) : code
            //     },
            //     type:"vue"
            // };
          } else if (url == "@esentire/fabric") {
            return fetch(`http://localhost:5173/node_modules/@esentire/fabric`).then(res => res.text());
            // const res = await fetch(
            //   `http://localhost:5173/node_modules/@esentire/fabric`
            // );
            // return {
            //   getContentData: (asBinary:boolean) =>
            //     asBinary ? res.arrayBuffer() : res.text(),
            // };
          }
          // For other dependencies, you might want to fetch from CDN
          const response = await fetch(url);
          if (!response.ok) {
            throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
          }
          return response.text();
        },
        addStyle(textContent: string) {
          const style = Object.assign(document.createElement("style"), {
            textContent,
          });
          const ref = document.head.getElementsByTagName("style")[0] || null;
          document.head.insertBefore(style, ref);
        },
        log(type, ...args) {
          console[type](...args);
        },
        onError(err, path) {
          console.error(`Error loading SFC "${path}":`, err);
        },
      };

      vueAppRef.current = Vue.createApp({
        components: {
          "my-component": Vue.defineAsyncComponent(() =>
            loadModule("./component.vue", options)
          ),
        },
        template: "<my-component></my-component>",
      });
      vueAppRef.current.mount("#vueApp");
    } catch (error) {
      console.error("Error rendering Vue SFC:", error);
      if (onError) {
        onError(
          error instanceof Error ? error.message : "Unknown error occurred"
        );
      }

      // Show error message in the container
      if (containerRef.current) {
        containerRef.current.innerHTML = `
            <div style="padding: 20px; background-color: #fee; border: 1px solid #fcc; border-radius: 4px; color: #d00;">
              <strong>Error rendering Vue component:</strong><br>
              ${error instanceof Error ? error.message : "Unknown error"}
            </div>
          `;
      }
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;

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
          border: "1px solid #ddd",
          borderRadius: "4px",
          padding: "16px",
          minHeight: "100px",
          backgroundColor: "#fafafa",
        }}
      >
        Loading Vue component...
      </div>
    </div>
  );
};

export default VueSfcPreview;
