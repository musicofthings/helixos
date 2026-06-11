import http from "node:http";

import { McpHostManager } from "./host-manager";

type BridgeServerOptions = {
  host: string;
  port: number;
  manager: McpHostManager;
};

export class McpBridgeServer {
  private server: http.Server | null = null;
  private activePort = 0;

  get baseUrl(): string {
    return this.activePort ? `http://${this.host}:${this.activePort}` : "";
  }

  constructor(
    private readonly host: string,
    private readonly manager: McpHostManager
  ) {}

  async start(preferredPort: number): Promise<number> {
    if (this.server) {
      return this.activePort;
    }

    this.activePort = await listen(this.host, preferredPort, (server) => {
      this.server = server;
    }, (request, response) => {
      void this.handle(request, response);
    });

    return this.activePort;
  }

  async stop(): Promise<void> {
    if (!this.server) {
      return;
    }

    const server = this.server;
    this.server = null;
    this.activePort = 0;
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }

  private async handle(request: http.IncomingMessage, response: http.ServerResponse): Promise<void> {
    try {
      const url = new URL(request.url ?? "/", `http://${this.host}`);
      if (request.method === "GET" && url.pathname === "/health") {
        writeJson(response, 200, { status: "ok" });
        return;
      }

      if (request.method === "GET" && url.pathname === "/connectors") {
        writeJson(response, 200, { connectors: this.manager.listStatuses() });
        return;
      }

      const match = url.pathname.match(/^\/connectors\/([^/]+)\/tools\/([^/]+)$/);
      if (request.method === "POST" && match) {
        const connectorId = decodeURIComponent(match[1]);
        const toolName = decodeURIComponent(match[2]);
        const host = this.manager.getHost(connectorId);
        if (!host) {
          writeJson(response, 404, { message: "Connector not registered" });
          return;
        }
        if (!host.running) {
          await host.start();
        }

        const body = await readJsonBody(request);
        const argumentsPayload = (body.arguments as Record<string, unknown> | undefined) ?? {};
        const result = await host.callTool(toolName, argumentsPayload);
        writeJson(response, 200, { status: "completed", result });
        return;
      }

      writeJson(response, 404, { message: "Not found" });
    } catch (error) {
      writeJson(response, 500, {
        message: error instanceof Error ? error.message : "Bridge failure"
      });
    }
  }
}

function listen(
  host: string,
  preferredPort: number,
  onListening: (server: http.Server) => void,
  handler: (request: http.IncomingMessage, response: http.ServerResponse) => void
): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = http.createServer(handler);
    server.once("error", reject);
    server.listen(preferredPort, host, () => {
      onListening(server);
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("Unable to resolve bridge port"));
        return;
      }
      resolve(address.port);
    });
  });
}

async function readJsonBody(request: http.IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  if (!chunks.length) {
    return {};
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
}

function writeJson(response: http.ServerResponse, statusCode: number, payload: Record<string, unknown>): void {
  response.writeHead(statusCode, { "Content-Type": "application/json" });
  response.end(JSON.stringify(payload));
}

export function createMcpBridgeServer(manager: McpHostManager, preferredPort = 8766): McpBridgeServer {
  return new McpBridgeServer("127.0.0.1", manager);
}
