import net from "node:net";
import { spawn, type ChildProcess } from "node:child_process";

import type { SidecarStatus } from "../shared/desktop-bridge";
import { buildApiBaseUrl } from "./config";

export type SidecarStartOptions = {
  apiDir: string;
  apiBinary?: string;
  preferredPort: number;
  pythonExecutable: string;
  mcpBridgeUrl?: string;
  sidecarEnv?: NodeJS.ProcessEnv;
  onStatus?: (status: SidecarStatus, message?: string) => void;
  onLog?: (line: string) => void;
};

export class ApiSidecar {
  private process: ChildProcess | null = null;
  private port: number | null = null;

  get apiBaseUrl(): string | null {
    return this.port ? buildApiBaseUrl(this.port) : null;
  }

  async start(options: SidecarStartOptions): Promise<number> {
    if (this.process) {
      return this.port ?? options.preferredPort;
    }

    options.onStatus?.(
      "starting",
      options.apiBinary ? "Launching bundled API sidecar" : "Launching FastAPI sidecar"
    );
    const port = await findAvailablePort(options.preferredPort);
    const sidecarEnv = {
      ...(options.sidecarEnv ?? process.env),
      HELIX_API_PORT: String(port),
      HELIX_MCP_BRIDGE_URL: options.mcpBridgeUrl ?? ""
    };

    if (options.apiBinary) {
      this.process = spawn(options.apiBinary, [String(port)], {
        env: sidecarEnv,
        stdio: ["ignore", "pipe", "pipe"]
      });
    } else {
      this.process = spawn(
        options.pythonExecutable,
        ["-m", "uvicorn", "helixos.main:app", "--host", "127.0.0.1", "--port", String(port)],
        {
          cwd: options.apiDir,
          env: {
            ...sidecarEnv,
            PYTHONPATH: options.apiDir
          },
          stdio: ["ignore", "pipe", "pipe"]
        }
      );
    }

    const child = this.process;
    this.port = port;

    child.stdout?.on("data", (chunk: Buffer) => {
      options.onLog?.(chunk.toString("utf8").trim());
    });

    child.stderr?.on("data", (chunk: Buffer) => {
      options.onLog?.(chunk.toString("utf8").trim());
    });

    child.on("exit", (code) => {
      options.onStatus?.("stopped", `Sidecar exited with code ${code ?? "unknown"}`);
      this.process = null;
      this.port = null;
    });

    try {
      await waitForHealth(buildApiBaseUrl(port));
      options.onStatus?.("ready", buildApiBaseUrl(port));
      return port;
    } catch (error) {
      options.onStatus?.("error", error instanceof Error ? error.message : "Sidecar failed to start");
      await this.stop();
      throw error;
    }
  }

  async restart(options: SidecarStartOptions): Promise<number> {
    await this.stop();
    return this.start(options);
  }

  async stop(): Promise<void> {
    if (!this.process) {
      return;
    }

    const child = this.process;
    this.process = null;
    this.port = null;

    await new Promise<void>((resolve) => {
      child.once("exit", () => resolve());
      child.kill("SIGTERM");
      setTimeout(() => {
        if (!child.killed) {
          child.kill("SIGKILL");
        }
        resolve();
      }, 2_000);
    });
  }
}

async function findAvailablePort(preferred: number): Promise<number> {
  const candidates = [preferred, 0];

  for (const port of candidates) {
    const available = await isPortAvailable(port);
    if (available !== null) {
      return available;
    }
  }

  throw new Error("Unable to find an available port for the API sidecar");
}

function isPortAvailable(port: number): Promise<number | null> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();

    server.once("error", () => resolve(null));
    server.listen(port, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => resolve(null));
        return;
      }

      const boundPort = address.port;
      server.close(() => resolve(boundPort));
    });
  });
}

async function waitForHealth(baseUrl: string, attempts = 40, delayMs = 250): Promise<void> {
  const healthUrl = `${baseUrl}/health`;
  let lastError = "Sidecar health check timed out";

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(healthUrl);
      if (response.ok) {
        return;
      }
      lastError = `Health check returned ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : "Health check failed";
    }

    await sleep(delayMs);
  }

  throw new Error(lastError);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export const apiSidecar = new ApiSidecar();
