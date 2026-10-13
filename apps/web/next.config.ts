import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const isStaticExport = process.env.HELIX_STATIC_EXPORT === "1";
// Self-contained server for the container image (apps/web/Dockerfile).
const isStandalone = process.env.HELIX_STANDALONE === "1";
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
// The browser calls the API on a relative /api path; Next forwards it here.
// Read when `next dev` starts / `next build` runs (rewrites are baked into the build).
const apiProxyTarget = (process.env.HELIX_API_PROXY_TARGET ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  typedRoutes: true,
  transpilePackages: ["@helixos/types", "@helixos/api-client"],
  outputFileTracingRoot: repoRoot,
  // Electron loads the Next dev server via 127.0.0.1; allow that origin for /_next/*.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  ...(isStaticExport
    ? {
        output: "export",
        trailingSlash: true,
        images: { unoptimized: true },
        // Electron loads the export via file:// — absolute "/_next/..." URLs
        // resolve against the filesystem root and never find the CSS/JS bundles.
        assetPrefix: "."
      }
    : {
        ...(isStandalone ? { output: "standalone" as const } : {}),
        // Rewrites are unavailable in a static export; the desktop shell talks
        // to its sidecar through window.helixDesktop instead.
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
        }
      })
};

export default nextConfig;
