import { afterEach, describe, expect, it } from "vitest";

import { StdioConnectorHost } from "../mcp/host-manager";
import { isAlive, tempDir, waitUntil, writeConnectorScript } from "./fixtures";

const hosts: StdioConnectorHost[] = [];

function track(host: StdioConnectorHost): StdioConnectorHost {
  hosts.push(host);
  return host;
}

afterEach(async () => {
  await Promise.all(hosts.splice(0).map((host) => host.stop()));
});

const ECHO_TOOLS = `
rl.on("line", (line) => {
  const request = JSON.parse(line);
  const result = request.method === "tools/list" ? { tools: [{ name: "echo" }] } : { ok: true };
  process.stdout.write(JSON.stringify({ id: request.id, result }) + "\\n");
});
`;

describe("StdioConnectorHost spawn failures", () => {
  it("rejects start() instead of crashing when the binary is missing", async () => {
    const host = track(
      new StdioConnectorHost({
        id: "missing-binary",
        binaryPath: "/nonexistent/helix-connector",
        pythonExecutable: "python3"
      })
    );

    await expect(host.start()).rejects.toThrow(/failed to start/);
    expect(host.running).toBe(false);
    await expect(host.listTools()).rejects.toThrow(/not running/);
  });

  it("rejects start() when the python executable is missing", async () => {
    const dir = tempDir();
    const host = track(
      new StdioConnectorHost({
        id: "missing-python",
        scriptPath: writeConnectorScript(dir, ECHO_TOOLS),
        pythonExecutable: "/nonexistent/python3"
      })
    );

    await expect(host.start()).rejects.toThrow(/failed to start/);
    expect(host.running).toBe(false);
  });

  it("can start successfully after an earlier failed start", async () => {
    const dir = tempDir();
    const script = writeConnectorScript(dir, ECHO_TOOLS);
    const bad = track(
      new StdioConnectorHost({ id: "retry", scriptPath: script, pythonExecutable: "/nonexistent/node" })
    );
    await expect(bad.start()).rejects.toThrow();

    const good = track(
      new StdioConnectorHost({ id: "retry", scriptPath: script, pythonExecutable: process.execPath })
    );
    await good.start();
    expect(good.running).toBe(true);
    await expect(good.listTools()).resolves.toEqual(["echo"]);
  });

  it("rejects an in-flight request when the connector exits", async () => {
    const dir = tempDir();
    const host = track(
      new StdioConnectorHost({
        id: "crashy",
        scriptPath: writeConnectorScript(dir, `rl.on("line", () => process.exit(3));`),
        pythonExecutable: process.execPath
      })
    );
    await host.start();

    await expect(host.listTools()).rejects.toThrow(/exited with code 3/);
    await waitUntil(() => !host.running);
  });
});

describe("StdioConnectorHost stop()", () => {
  it("escalates to SIGKILL when the connector ignores SIGTERM", async () => {
    const dir = tempDir();
    const host = track(
      new StdioConnectorHost({
        id: "stubborn",
        scriptPath: writeConnectorScript(
          dir,
          `process.on("SIGTERM", () => {}); setInterval(() => {}, 1000); rl.on("line", () => {});`
        ),
        pythonExecutable: process.execPath
      })
    );
    await host.start();
    const pid = (host as unknown as { process: { pid: number } }).process.pid;
    expect(isAlive(pid)).toBe(true);

    const started = Date.now();
    await host.stop();

    await waitUntil(() => !isAlive(pid), 3_000);
    expect(Date.now() - started).toBeLessThan(4_000);
    expect(host.running).toBe(false);
  });

  it("is a no-op for a connector that already exited", async () => {
    const dir = tempDir();
    const host = track(
      new StdioConnectorHost({
        id: "already-dead",
        scriptPath: writeConnectorScript(dir, `process.exit(0);`),
        pythonExecutable: process.execPath
      })
    );
    await host.start();
    await waitUntil(() => !host.running);

    await expect(host.stop()).resolves.toBeUndefined();
  });
});
