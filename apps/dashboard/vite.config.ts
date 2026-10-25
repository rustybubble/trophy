import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served at https://trophy.photo/ through Caddy (infra/caddy/Caddyfile.dev -> 127.0.0.1:5174; static on the GPU box).
const domain = process.env.TROPHY_DOMAIN ?? "trophy.photo";
// a second stack on other ports (e.g. a throwaway test stack) sets these
const port = Number(process.env.DASHBOARD_PORT ?? 5174);
const gateway = process.env.GATEWAY_URL ?? "http://127.0.0.1:8000";
const stdb = process.env.SPACETIME_URI ?? "http://127.0.0.1:3000";

export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    allowedHosts: [domain, "localhost", "127.0.0.1"],
    // no `hmr` option: HMR uses the page's own origin (Caddy at trophy.photo, a public tunnel, or 127.0.0.1).
    // Pinning trophy.photo made every page loaded through `make tunnel` open a socket that can't connect.
    // the same routes Caddy serves, for testing on http://127.0.0.1:5174/
    proxy: {
      "/api": { target: gateway, ws: true },
      "/stdb": { target: stdb, ws: true, rewrite: (p) => p.replace(/^\/stdb/, "") },
    },
  },
  preview: { host: "127.0.0.1", port: 5174, strictPort: true, allowedHosts: [domain] },
  build: { target: "es2022", sourcemap: true },
});
