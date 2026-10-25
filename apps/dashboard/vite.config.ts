import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served at https://trophy.photo/ through Caddy (infra/caddy/Caddyfile.dev -> 127.0.0.1:5174; static on the GPU box).
const domain = process.env.TROPHY_DOMAIN ?? "trophy.photo";

export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    allowedHosts: [domain, "localhost", "127.0.0.1"],
    hmr: { protocol: "wss", host: domain, clientPort: 443 },
    // the same routes Caddy serves, for testing on http://127.0.0.1:5174/
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", ws: true },
      "/stdb": { target: "http://127.0.0.1:3000", ws: true, rewrite: (p) => p.replace(/^\/stdb/, "") },
    },
  },
  preview: { host: "127.0.0.1", port: 5174, strictPort: true, allowedHosts: [domain] },
  build: { target: "es2022", sourcemap: true },
});
