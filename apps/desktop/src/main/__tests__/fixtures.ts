import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

export function tempDir(): string {
  return mkdtempSync(path.join(tmpdir(), "helix-desktop-test-"));
}

export function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export async function waitUntil(predicate: () => boolean, timeoutMs = 5_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) {
      throw new Error("waitUntil timed out");
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

/** Connector stub speaking the newline-delimited JSON protocol. */
export function writeConnectorScript(dir: string, body: string): string {
  const file = path.join(dir, "connector.cjs");
  writeFileSync(
    file,
    `
const readline = require("node:readline");
const rl = readline.createInterface({ input: process.stdin });
${body}
`
  );
  return file;
}

/** Executable sidecar stub: serves /health on the port given as argv[2]. */
export function writeSidecarBinary(dir: string, extra = ""): string {
  const file = path.join(dir, "fake-api");
  writeFileSync(
    file,
    `#!${process.execPath}
const http = require("node:http");
${extra}
http.createServer((req, res) => { res.statusCode = 200; res.end("ok"); })
  .listen(Number(process.argv[2]), "127.0.0.1");
`
  );
  chmodSync(file, 0o755);
  return file;
}
