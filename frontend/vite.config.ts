import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // hls.js is ~520 kB, React-free, and needed only on /watch, so it
        // gets its own long-lived cache entry instead of riding along in a
        // route chunk.
        //
        // Nothing else is split here on purpose. Putting React in one chunk
        // and its dependents (recharts, Radix) in others lets a dependent
        // evaluate before React has initialised -- recharts then dies on
        // `Cannot read properties of undefined (reading 'forwardRef')` and
        // the page renders blank. Tests and tsc stay green while it happens,
        // so only a browser catches it.
        manualChunks(id) {
          if (id.includes("node_modules") && id.includes("hls.js")) {
            return "vendor-hls";
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@api": path.resolve(__dirname, "./src/lib/api"),
    },
  },
});
