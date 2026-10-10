import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../config", () => ({
  buildApiBaseUrl: (port: number) => `http://127.0.0.1:${port}`
}));

import { ApiSidecar, type SidecarStartOptions } from "../sidecar";
import { isAlive, tempDir, waitUntil, writeSidecarBinary } from "./fixtures";

const sidecars: ApiSidecar[] = [];

function create(): ApiSidecar {
  const sidecar = new ApiSidecar();
  sidecars.push(sidecar);
  return sidecar;
}

afterEach(async () => {
  await Promise.all(sidecars.splice(0).map((sidecar) => sidecar.stop()));
});

function options(overrides: Partial<SidecarStartOptions>): SidecarStartOptions {
  return {
    apiDir: tempDir(),
    preferredPort: 0,
    pythonExecutable: "python3",
    ...overrides
  };
}

describe("ApiSidecar spawn failures", () => {
  it("fails fast with a clear error when the API binary is missing", async () => {
    const statuses: Array<[string, string | undefined]> = [];
    const sidecar = create();
    const started = Date.now();

    await expect(
      sidecar.start(
        options({
          apiBinary: "/nonexistent/helixos-api",
          onStatus: (status, message) => statuses.push([status, message])
        })
      )
    ).rejects.toThrow(/failed to start/i);

    // Not the full 10s health-check budget.
    expect(Date.now() - started).toBeLessThan(5_000);
    expect(statuses.map(([status]) => status)).toContain("error");
    expect(sidecar.apiBaseUrl).toBeNull();
  });

  it("fails fast when the python executable is missing", async () => {
    const sidecar = create();
    await expect(
      sidecar.start(options({ pythonExecutable: "/nonexistent/python3" }))
    ).rejects.toThrow(/failed to start/i);
    expect(sidecar.apiBaseUrl).toBeNull();
  });

  it("can start again after a failed start", async () => {
    const sidecar = create();
    await expect(sidecar.start(options({ apiBinary: "/nonexistent/helixos-api" }))).rejects.toThrow();

    const port = await sidecar.start(options({ apiBinary: writeSidecarBinary(tempDir()) }));
    expect(sidecar.apiBaseUrl).toBe(`http://127.0.0.1:${port}`);
  });
});

describe("ApiSidecar stop()", () => {
  it("escalates to SIGKILL when the sidecar ignores SIGTERM", async () => {
    const sidecar = create();
    await sidecar.start(
      options({ apiBinary: writeSidecarBinary(tempDir(), `process.on("SIGTERM", () => {});`) })
    );
    const pid = (sidecar as unknown as { process: { pid: number } }).process.pid;
    expect(isAlive(pid)).toBe(true);

    const started = Date.now();
    await sidecar.stop();

    await waitUntil(() => !isAlive(pid), 3_000);
    expect(Date.now() - started).toBeLessThan(5_000);
    expect(sidecar.apiBaseUrl).toBeNull();
  });

  it("stops a cooperative sidecar promptly without SIGKILL delay", async () => {
    const sidecar = create();
    await sidecar.start(options({ apiBinary: writeSidecarBinary(tempDir()) }));

    const started = Date.now();
    await sidecar.stop();
    expect(Date.now() - started).toBeLessThan(1_500);
  });
});
