declare module 'vue3-sfc-loader' {
  interface LoadModuleOptions {
    moduleCache?: Record<string, unknown>;
    getFile?: (url: string) => Promise<string> | string;
    addStyle?: (textContent: string) => void;
  }
  
  export function loadModule(url: string, options: LoadModuleOptions): Promise<unknown>;
}
