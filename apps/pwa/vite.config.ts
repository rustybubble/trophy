import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served at https://trophy.photo/cam/ through Caddy (infra/caddy/Caddyfile.dev -> 127.0.0.1:5173).
const domain = process.env.TROPHY_DOMAIN ?? "trophy.photo";

export default defineConfig({
  base: "/cam/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    allowedHosts: [domain, "localhost", "127.0.0.1"],
    // HMR through Caddy's TLS origin
    hmr: { protocol: "wss", host: domain, clientPort: 443 },
    // the same routes Caddy serves, for testing on http://127.0.0.1:5173/cam/
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", ws: true },
      "/stdb": { target: "http://127.0.0.1:3000", ws: true, rewrite: (p) => p.replace(/^\/stdb/, "") },
    },
  },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true, allowedHosts: [domain] },
  build: { target: "es2022", sourcemap: true },
});
