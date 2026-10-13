import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const dist = path.join(root, "dist");

try {
  rmSync(dist, { recursive: true, force: true });
} catch {
  // dist may not exist on first build
}
mkdirSync(dist, { recursive: true });

for (const name of ["index.html", "styles.css", "main.js", "_headers", "_redirects", "robots.txt"]) {
  const source = path.join(root, name);
  try {
    cpSync(source, path.join(dist, name));
  } catch {
    // Optional deploy files may not exist.
  }
}

const assetsSrc = path.join(root, "assets");
const assetsDest = path.join(dist, "assets");
try {
  cpSync(assetsSrc, assetsDest, { recursive: true });
} catch {
  mkdirSync(assetsDest, { recursive: true });
}

// Keep this for the legacy GitHub Pages fallback workflow.
writeFileSync(path.join(dist, ".nojekyll"), "");

console.log(`Built landing site → ${dist}`);
