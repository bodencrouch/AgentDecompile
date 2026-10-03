import { createHash } from "node:crypto";
import { createLogger, defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Inventory the actual bundle, including Vite's emitted worker sub-bundles.
// Every emitted file is required, not only files reachable from the entry's
// static imports. This also covers CSS, fonts, Wasm and lazy-only assets.
function publicationMetadata() {
  const references = new Set<string>();
  const collect: Plugin["generateBundle"] = {
    order: "post",
    handler(_options, bundle) {
      for (const output of Object.values(bundle)) {
        if (output.type !== "chunk") continue;
        for (const file of [...output.imports, ...output.dynamicImports, ...output.referencedFiles,
          ...(output.viteMetadata?.importedCss ?? []), ...(output.viteMetadata?.importedAssets ?? [])]) {
          references.add(file);
        }
      }
    },
  };
  return {
    recordUrl(file: string) { references.add(file); },
    worker: (): Plugin => ({ name: "react-worker-dependencies", generateBundle: collect }),
    plugin: {
      name: "react-publication-metadata",
      apply: "build",
      enforce: "post",
      buildStart() { references.clear(); },
      generateBundle: collect,
      // writeBundle sees the final outputs after all generateBundle hooks.
      writeBundle: {
        order: "post",
        async handler(options, bundle) {
          const { writeFile } = await import("node:fs/promises");
          const { resolve } = await import("node:path");
          if (!options.dir || !bundle["index.html"] ||
              !Object.values(bundle).some(file => file.type === "chunk" && file.isEntry)) {
            this.error("REACT_STAGE_INCOMPLETE: expected an HTML entry and module entry");
          }
          const files = Object.values(bundle).map(file => {
            const bytes = file.type === "chunk" ? Buffer.from(file.code) :
              typeof file.source === "string" ? Buffer.from(file.source) : Buffer.from(file.source);
            return { path: file.fileName, size: bytes.length,
              sha256: createHash("sha256").update(bytes).digest("hex") };
          }).sort((a, b) => a.path.localeCompare(b.path));
          const emitted = new Set(files.map(file => file.path));
          for (const file of references) {
            if (!emitted.has(file)) this.error(`REACT_STAGE_MISSING_REFERENCE: ${file}`);
          }
          await writeFile(resolve(options.dir!, "react-publication.json"), JSON.stringify({
            schema: "agentdecompile.react-publication/v1", base: "/react/", entry: "index.html",
            files, references: [...references].sort(),
          }) + "\n", { flag: "wx" });
        },
      },
    } satisfies Plugin,
  };
}

const backend =
  process.env.VITE_AGENTDECOMPILE_BACKEND ||
  process.env.AGENTDECOMPILE_BACKEND ||
  "http://127.0.0.1:8080";

export default defineConfig(({ command }) => {
  const publication = publicationMetadata();
  const logger = createLogger();
  // Vite can otherwise leave unresolved CSS/URL references in output after a
  // warning. A packaged generation must not silently accept such output.
  if (command === "build") {
    const warn = logger.warn.bind(logger);
    logger.warn = (message, options) => {
      // This advisory describes complete output; Monaco can legitimately be
      // larger than Vite's default chunk-size threshold.
      if (message.includes("Some chunks are larger than")) return warn(message, options);
      throw new Error(`REACT_BUILD_WARNING: ${message}`);
    };
    logger.warnOnce = logger.warn;
  }
  return {
  customLogger: logger,
  plugins: [
    react(),
    publication.plugin,
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
  publicDir: false,
  experimental: {
    renderBuiltUrl(filename) { publication.recordUrl(filename); return undefined; },
  },
  worker: { plugins: () => [publication.worker()] },
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
  build: { outDir: "dist/react-stage", emptyOutDir: true, sourcemap: false },
  };
});
