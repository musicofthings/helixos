import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync, execFileSync } from "node:child_process";

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

// Release builds set HELIX_REQUIRE_RUNTIME=1: the Python runtime steps become fatal
// and the packaged runtime is import-checked, so a DMG can't ship without a way to
// start the API sidecar.
const requireRuntime = process.env.HELIX_REQUIRE_RUNTIME === "1";

function runStep(label, command, { required = false } = {}) {
  console.log(label);
  try {
    execSync(command, { cwd: repoRoot, stdio: "inherit" });
    return true;
  } catch (error) {
    if (required && requireRuntime) {
      throw new Error(`${label} failed: ${error instanceof Error ? error.message : error}`);
    }
    console.warn(`${label} skipped`);
    return false;
  }
}

function verifyPackagedRuntime() {
  const binary = path.join(resourcesRoot, "bin", process.platform === "win32" ? "helixos-api.exe" : "helixos-api");
  if (existsSync(binary)) {
    console.log(`Packaged API binary found: ${binary}`);
    return;
  }
  const venvPython = path.join(
    resourcesRoot,
    "pyvenv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python3"
  );
  if (!existsSync(venvPython)) {
    throw new Error("No usable runtime packaged: neither helixos-api binary nor embedded Python venv exists");
  }
  execFileSync(venvPython, ["-c", "import fastapi, uvicorn, helixos.main"], {
    env: { ...process.env, PYTHONPATH: path.join(resourcesRoot, "api") },
    stdio: "inherit"
  });
  console.log("Embedded Python runtime imports verified");
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
  "python3 services/api/scripts/fetch_embedded_python.py",
  { required: true }
);
if (fetchedPython) {
  runStep(
    "Bootstrapping embedded Python environment...",
    "python3 services/api/scripts/bootstrap_embedded_python_env.py",
    { required: true }
  );
}

console.log("Copying web, API, and MCP resources...");
copyTree(webOut, path.join(resourcesRoot, "web"));
copyTree(apiSource, path.join(resourcesRoot, "api"));
copyTree(mcpSource, path.join(resourcesRoot, "mcp"));

if (requireRuntime) {
  verifyPackagedRuntime();
}

console.log("Desktop resources prepared at apps/desktop/resources");
