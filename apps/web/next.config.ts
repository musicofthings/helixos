import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const isStaticExport = process.env.HELIX_STATIC_EXPORT === "1";
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

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
    : {})
};

export default nextConfig;
