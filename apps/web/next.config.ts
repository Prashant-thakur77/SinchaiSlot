import type { NextConfig } from "next";

const api = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// STATIC_EXPORT=1 builds plain files into out/ for static hosting; worker/index.js then forwards /api and /health.
const isExport = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  ...(isExport
    ? { output: "export" as const, images: { unoptimized: true } }
    : { output: "standalone" as const, cacheComponents: true, partialPrefetching: true }),
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  ...(isExport
    ? {}
    : {
        async rewrites() {
          // The browser talks to the same origin; Next forwards to the FastAPI service.
          return [
            { source: "/api/:path*", destination: `${api}/api/:path*` },
            { source: "/health", destination: `${api}/health` },
          ];
        },
      }),
};

export default nextConfig;
