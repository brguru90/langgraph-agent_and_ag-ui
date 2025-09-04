import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import vue from '@vitejs/plugin-vue';


// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), vue()],
  resolve: {
    alias: {
      'vue': 'vue/dist/vue.esm-bundler.js'
    }
  },
  optimizeDeps: {
    exclude: ['vue3-sfc-loader'],
  },
  define: {
    // Vue compatibility flags for production builds
    __VUE_OPTIONS_API__: true,
    __VUE_PROD_DEVTOOLS__: false,
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false'
  },
  server: {
    proxy: {
      '/@esentire/fabric': {
        target: 'http://localhost:5173',
        changeOrigin: true,
        rewrite: () => '/node_modules/@esentire/fabric/dist/index.umd.cjs'
      }
    }
  }
})
