import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://100.107.115.1:8200",
        changeOrigin: true,
        // Upgrade WebSocket handshakes onto the backend. Without this, the
        // browser's `ws://localhost:3000/api/.../events` request falls through
        // to Vite's HTTP handler and hangs in "Pending" forever.
        ws: true,
      },
    },
  },
})
