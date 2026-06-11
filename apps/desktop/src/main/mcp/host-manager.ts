import { spawn, type ChildProcess } from "node:child_process";
import { createInterface } from "node:readline";
import path from "node:path";

type JsonObject = Record<string, unknown>;

type PendingRequest = {
  resolve: (value: JsonObject) => void;
  reject: (error: Error) => void;
};

export type StdioConnectorDefinition = {
  id: string;
  scriptPath?: string;
  binaryPath?: string;
  pythonExecutable: string;
};

export class StdioConnectorHost {
  private process: ChildProcess | null = null;
  private nextRequestId = 1;
  private pending = new Map<string, PendingRequest>();

  constructor(private readonly definition: StdioConnectorDefinition) {}

  get id(): string {
    return this.definition.id;
  }

  get running(): boolean {
    return this.process !== null && !this.process.killed;
  }

  async start(): Promise<void> {
    if (this.running) {
      return;
    }

    if (this.definition.binaryPath) {
      this.process = spawn(this.definition.binaryPath, [], {
        stdio: ["pipe", "pipe", "pipe"]
      });
    } else if (this.definition.scriptPath) {
      this.process = spawn(this.definition.pythonExecutable, [this.definition.scriptPath], {
        stdio: ["pipe", "pipe", "pipe"]
      });
    } else {
      throw new Error(`Connector ${this.definition.id} is missing a script or binary path`);
    }

    const child = this.process;
    if (!child.stdout || !child.stdin) {
      throw new Error(`Connector ${this.definition.id} failed to initialize stdio pipes`);
    }

    const reader = createInterface({ input: child.stdout });
    reader.on("line", (line) => {
      try {
        const payload = JSON.parse(line) as JsonObject;
        const requestId = String(payload.id ?? "");
        const pending = this.pending.get(requestId);
        if (!pending) {
          return;
        }
        this.pending.delete(requestId);
        if (payload.error) {
          pending.reject(new Error(String((payload.error as JsonObject).message ?? "Connector error")));
          return;
        }
        pending.resolve(payload);
      } catch (error) {
        console.error(`[mcp:${this.definition.id}] failed to parse connector response`, error);
      }
    });

    child.stderr?.on("data", (chunk: Buffer) => {
      const message = chunk.toString("utf8").trim();
      if (message) {
        console.error(`[mcp:${this.definition.id}] ${message}`);
      }
    });

    child.on("exit", (code) => {
      for (const [, pending] of this.pending) {
        pending.reject(new Error(`Connector exited with code ${code ?? "unknown"}`));
      }
      this.pending.clear();
      this.process = null;
    });
  }

  async stop(): Promise<void> {
    if (!this.process) {
      return;
    }
    const child = this.process;
    this.process = null;
    await new Promise<void>((resolve) => {
      child.once("exit", () => resolve());
      child.kill("SIGTERM");
      setTimeout(() => {
        if (!child.killed) {
          child.kill("SIGKILL");
        }
        resolve();
      }, 1_000);
    });
  }

  async listTools(): Promise<string[]> {
    const response = await this.request("tools/list", {});
    const result = response.result as JsonObject | undefined;
    const tools = result?.tools;
    if (!Array.isArray(tools)) {
      return [];
    }
    return tools
      .map((tool) => (typeof tool === "object" && tool && "name" in tool ? String((tool as JsonObject).name) : null))
      .filter((name): name is string => Boolean(name));
  }

  async callTool(toolName: string, args: JsonObject): Promise<JsonObject> {
    const response = await this.request("tools/call", { name: toolName, arguments: args });
    return (response.result as JsonObject | undefined) ?? {};
  }

  private request(method: string, params: JsonObject): Promise<JsonObject> {
    if (!this.process?.stdin) {
      throw new Error(`Connector ${this.definition.id} is not running`);
    }

    const requestId = String(this.nextRequestId++);
    const payload = JSON.stringify({ id: requestId, method, params });

    return new Promise<JsonObject>((resolve, reject) => {
      this.pending.set(requestId, { resolve, reject });
      this.process?.stdin?.write(`${payload}\n`, (error) => {
        if (error) {
          this.pending.delete(requestId);
          reject(error);
        }
      });
    });
  }
}

export class McpHostManager {
  private hosts = new Map<string, StdioConnectorHost>();

  register(definition: StdioConnectorDefinition): StdioConnectorHost {
    const existing = this.hosts.get(definition.id);
    if (existing) {
      void existing.stop();
    }
    const host = new StdioConnectorHost(definition);
    this.hosts.set(definition.id, host);
    return host;
  }

  getHost(connectorId: string): StdioConnectorHost | undefined {
    return this.hosts.get(connectorId);
  }

  listStatuses(): Array<{ id: string; running: boolean }> {
    return [...this.hosts.values()].map((host) => ({ id: host.id, running: host.running }));
  }

  async startAll(): Promise<void> {
    await Promise.all([...this.hosts.values()].map((host) => host.start()));
  }

  async stopAll(): Promise<void> {
    await Promise.all([...this.hosts.values()].map((host) => host.stop()));
  }
}

export function createDefaultHostManager(options: {
  repoRoot: string;
  pythonExecutable: string;
}): McpHostManager {
  const manager = new McpHostManager();
  manager.register({
    id: "biopython-local",
    scriptPath: path.join(options.repoRoot, "mcp/servers/biopython_local/server.py"),
    pythonExecutable: options.pythonExecutable
  });
  return manager;
}

export const mcpHostManager = new McpHostManager();
