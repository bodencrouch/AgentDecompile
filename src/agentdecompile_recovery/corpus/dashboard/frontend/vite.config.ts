import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend =
  process.env.VITE_AGENTDECOMPILE_BACKEND ||
  process.env.AGENTDECOMPILE_BACKEND ||
  "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "dashboard-entry",
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const url = new URL(request.url || "/", "http://localhost");
          let pathname: string;
          try {
            pathname = decodeURIComponent(url.pathname);
          } catch {
            response.statusCode = 400;
            response.setHeader("Content-Type", "text/plain");
            response.end("Malformed URL path");
            return;
          }
          // Keep CSS/content negotiation while excluding Vite's HTML fallback.
          if (pathname.startsWith("/react/") && (pathname.startsWith("/react/assets/") || /\.[^/]+$/.test(pathname) && !pathname.endsWith(".html"))) {
            request.headers.accept = request.headers.accept?.split(",").filter(value => {
              const type = value.split(";", 1)[0].trim().toLowerCase();
              return type !== "text/html" && type !== "*/*";
            }).join(",") || "application/octet-stream";
          }
          if (url.pathname === "/dashboard" && url.searchParams.get("mode") === "static") return next();
          if (!["/react", "/dashboard", "/dashboard/static/react", "/dashboard/static/react/", "/dashboard/static/react/index.html"].includes(url.pathname)) return next();
          response.statusCode = 302;
          response.setHeader(
            "Location",
            `/react/${url.search}${url.hash}`,
          );
          response.end();
        });
      },
    },
  ],
  base: "/react/",
  server: {
    port: 5174,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "^/dashboard(?:/|\\?|$)": {
        target: backend,
        changeOrigin: true,
      },
      "/api": {
        target: backend,
        changeOrigin: true,
      },
      "/atlas": {
        target: backend,
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "../static/react", emptyOutDir: true, sourcemap: false },
});
