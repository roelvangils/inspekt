import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [svelte(), tailwindcss()],

  // Path alias for cleaner imports
  resolve: {
    alias: {
      $lib: resolve(__dirname, "./src/lib"),
    },
  },

  // Vite options tailored for Tauri development
  clearScreen: false,

  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
      },
    },
  },

  server: {
    port: 1420,
    strictPort: true,
    watch: {
      // Watch the src-tauri directory for changes
      ignored: ["**/src-tauri/**"],
    },
  },
});
