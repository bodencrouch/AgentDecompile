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
          if (url.pathname !== "/dashboard") return next();
          response.statusCode = 302;
          response.setHeader(
            "Location",
            `/dashboard/static/react/${url.search}${url.hash}`,
          );
          response.end();
        });
      },
    },
  ],
  base: "/dashboard/static/react/",
  server: {
    port: 5174,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "^/dashboard/(?!static/react)": {
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
