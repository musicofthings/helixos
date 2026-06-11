import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "../..");
const resourcesRoot = path.join(desktopRoot, "resources");

function copyTree(source, destination) {
  cpSync(source, destination, {
    recursive: true,
    filter: (src) => !src.includes("__pycache__") && !src.includes(".pytest_cache") && !src.includes(".DS_Store")
  });
}

function runStep(label, command) {
  console.log(label);
  try {
    execSync(command, { cwd: repoRoot, stdio: "inherit" });
    return true;
  } catch {
    console.warn(`${label} skipped`);
    return false;
  }
}

console.log("Building static web export...");
execSync("npm run build", {
  cwd: path.join(repoRoot, "apps/web"),
  stdio: "inherit",
  env: {
    ...process.env,
    HELIX_STATIC_EXPORT: "1"
  }
});

const webOut = path.join(repoRoot, "apps/web/out");
const apiSource = path.join(repoRoot, "services/api");
const mcpSource = path.join(repoRoot, "mcp");

rmSync(resourcesRoot, { recursive: true, force: true });
mkdirSync(resourcesRoot, { recursive: true });
mkdirSync(path.join(resourcesRoot, "bin"), { recursive: true });

runStep("Building desktop Python binaries (optional)...", "python3 services/api/scripts/build_desktop_binaries.py");

const fetchedPython = runStep(
  "Fetching embedded Python runtime...",
  "python3 services/api/scripts/fetch_embedded_python.py"
);
if (fetchedPython) {
  runStep(
    "Bootstrapping embedded Python environment...",
    "python3 services/api/scripts/bootstrap_embedded_python_env.py"
  );
}

console.log("Copying web, API, and MCP resources...");
copyTree(webOut, path.join(resourcesRoot, "web"));
copyTree(apiSource, path.join(resourcesRoot, "api"));
copyTree(mcpSource, path.join(resourcesRoot, "mcp"));

console.log("Desktop resources prepared at apps/desktop/resources");
