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

for (const name of ["index.html", "styles.css", "main.js"]) {
  cpSync(path.join(root, name), path.join(dist, name));
}

const assetsSrc = path.join(root, "assets");
const assetsDest = path.join(dist, "assets");
try {
  cpSync(assetsSrc, assetsDest, { recursive: true });
} catch {
  mkdirSync(assetsDest, { recursive: true });
}

// Helpful for GitHub Pages project sites that still hit /helixos
writeFileSync(path.join(dist, ".nojekyll"), "");

console.log(`Built landing site → ${dist}`);
