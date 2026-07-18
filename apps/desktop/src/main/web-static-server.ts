import { createReadStream, existsSync, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";

const MIME_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
  ".map": "application/json"
};

function contentTypeFor(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  return MIME_TYPES[ext] ?? "application/octet-stream";
}

function shouldProxy(pathname: string): boolean {
  return pathname === "/health" || pathname.startsWith("/api/");
}

/**
 * Serve the Next.js static export over loopback HTTP so absolute "/_next/..."
 * asset URLs resolve. Loading via file:// breaks those paths (unstyled UI).
 *
 * Optionally reverse-proxy /api and /health to the local FastAPI sidecar so the
 * renderer stays same-origin (avoids CORS against an ephemeral static port).
 */
export class WebStaticServer {
  private server: http.Server | null = null;
  private port: number | null = null;
  private apiProxyTarget: string | null = null;

  get baseUrl(): string | null {
    return this.port ? `http://127.0.0.1:${this.port}` : null;
  }

  setApiProxyTarget(target: string | null): void {
    this.apiProxyTarget = target ? target.replace(/\/$/, "") : null;
  }

  async start(webRoot: string, preferredPort = 0): Promise<number> {
    if (this.server && this.port) {
      return this.port;
    }

    const root = path.resolve(webRoot);
    if (!existsSync(root)) {
      throw new Error(`Packaged web root not found: ${root}`);
    }

    this.server = http.createServer((request, response) => {
      try {
        const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
        if (shouldProxy(requestUrl.pathname)) {
          void this.proxyApi(request, response, requestUrl);
          return;
        }

        let pathname = decodeURIComponent(requestUrl.pathname);
        if (pathname.endsWith("/")) {
          pathname = `${pathname}index.html`;
        }
        if (pathname === "") {
          pathname = "/index.html";
        }

        const resolved = path.normalize(path.join(root, pathname));
        if (!resolved.startsWith(root)) {
          response.writeHead(403).end("Forbidden");
          return;
        }

        let filePath = resolved;
        if (!existsSync(filePath) || statSync(filePath).isDirectory()) {
          const withIndex = path.join(filePath, "index.html");
          if (existsSync(withIndex)) {
            filePath = withIndex;
          } else if (existsSync(path.join(root, "404.html"))) {
            response.writeHead(404, { "Content-Type": "text/html; charset=utf-8" });
            createReadStream(path.join(root, "404.html")).pipe(response);
            return;
          } else {
            response.writeHead(404).end("Not found");
            return;
          }
        }

        response.writeHead(200, { "Content-Type": contentTypeFor(filePath) });
        createReadStream(filePath).pipe(response);
      } catch (error) {
        response.writeHead(500).end(error instanceof Error ? error.message : "Server error");
      }
    });

    await new Promise<void>((resolve, reject) => {
      this.server!.once("error", reject);
      this.server!.listen(preferredPort, "127.0.0.1", () => resolve());
    });

    const address = this.server.address();
    if (!address || typeof address === "string") {
      throw new Error("Failed to bind packaged web static server");
    }
    this.port = address.port;
    return this.port;
  }

  private proxyApi(
    request: http.IncomingMessage,
    response: http.ServerResponse,
    requestUrl: URL
  ): void {
    if (!this.apiProxyTarget) {
      response.writeHead(503, { "Content-Type": "application/json" }).end(
        JSON.stringify({ error: { code: "sidecar_unavailable", message: "API sidecar not ready" } })
      );
      return;
    }

    const target = new URL(requestUrl.pathname + requestUrl.search, `${this.apiProxyTarget}/`);
    const headers = { ...request.headers, host: target.host };
    delete headers["content-length"];

    const proxyRequest = http.request(
      target,
      {
        method: request.method,
        headers
      },
      (proxyResponse) => {
        response.writeHead(proxyResponse.statusCode ?? 502, proxyResponse.headers);
        proxyResponse.pipe(response);
      }
    );

    proxyRequest.on("error", (error) => {
      if (!response.headersSent) {
        response.writeHead(502, { "Content-Type": "application/json" }).end(
          JSON.stringify({
            error: {
              code: "sidecar_proxy_error",
              message: error instanceof Error ? error.message : "Proxy failed"
            }
          })
        );
      } else {
        response.end();
      }
    });

    request.pipe(proxyRequest);
  }

  async stop(): Promise<void> {
    const server = this.server;
    this.server = null;
    this.port = null;
    this.apiProxyTarget = null;
    if (!server) return;
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
  }
}

export const webStaticServer = new WebStaticServer();
