import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const isStaticExport = process.env.HELIX_STATIC_EXPORT === "1";
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

const nextConfig: NextConfig = {
  typedRoutes: true,
  transpilePackages: ["@helixos/types", "@helixos/api-client"],
  outputFileTracingRoot: repoRoot,
  ...(isStaticExport
    ? {
        output: "export",
        trailingSlash: true,
        images: { unoptimized: true }
      }
    : {})
};

export default nextConfig;
