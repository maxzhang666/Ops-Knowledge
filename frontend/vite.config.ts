import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import semi from "@douyinfe/vite-plugin-semi"

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Semi Design custom theme — vendored locally under ./semi-theme and
    // pulled into node_modules via pnpm `file:` so the plugin can resolve
    // `node_modules/@ops-knowledge/semi-theme/scss/*` at SCSS-injection
    // time. Forked from @semi-bot/semi-theme-double v1.0.1 — see
    // semi-theme/README.md for update / customisation conventions.
    semi({ theme: "@ops-knowledge/semi-theme" }),
  ],
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
