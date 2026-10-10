// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

import { HelixOSApiError, HelixOSClient } from "@helixos/api-client";

const client = new HelixOSClient({ baseUrl: "http://api.test", token: "t" });

function json(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json", ...(init.headers as Record<string, string>) },
    ...init
  });
}

function sseResponse(frames: string[], headers: Record<string, string> = {}): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      }
    }),
    { headers: { "Content-Type": "text/event-stream", ...headers } }
  );
}

const frame = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

afterEach(() => vi.unstubAllGlobals());

describe("paginated lists", () => {
  it("follows X-Next-Offset until the last page and concatenates in order", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json([{ id: "p1" }, { id: "p2" }], { headers: { "X-Next-Offset": "2" } }))
      .mockResolvedValueOnce(json([{ id: "p3" }, { id: "p4" }], { headers: { "X-Next-Offset": "4" } }))
      .mockResolvedValueOnce(json([{ id: "p5" }]));
    vi.stubGlobal("fetch", fetchMock);

    const projects = await client.listProjects({ workspaceId: "ws_1" });

    expect(projects.map((p) => p.id)).toEqual(["p1", "p2", "p3", "p4", "p5"]);
    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls[0]).toBe("http://api.test/api/v1/projects?workspace_id=ws_1&limit=500&offset=0");
    expect(urls[1]).toContain("offset=2");
    expect(urls[2]).toContain("offset=4");
  });

  it("stops on an empty page even if the server still advertises a next offset", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json([], { headers: { "X-Next-Offset": "10" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(client.listWorkspaces()).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("propagates a failure on a later page instead of returning a partial list", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json([{ id: "p1" }], { headers: { "X-Next-Offset": "1" } }))
        .mockResolvedValueOnce(
          json({ error: { code: "boom", message: "db down", details: {}, request_id: "req_page2" } }, { status: 500 })
        )
    );

    const error = await client.listExperiments().catch((e) => e);
    expect(error).toBeInstanceOf(HelixOSApiError);
    expect(error.requestId).toBe("req_page2");
  });
});

describe("error request IDs", () => {
  it("uses the request_id in the error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({ error: { code: "not_found", message: "nope", details: {}, request_id: "req_body" } }, { status: 404 })
      )
    );
    const error = await client.getExperiment("x").catch((e) => e);
    expect(error).toMatchObject({ status: 404, code: "not_found", requestId: "req_body" });
  });

  it("falls back to the X-Request-ID header when the body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502, headers: { "X-Request-ID": "req_hdr" } }))
    );
    const error = await client.getExperiment("x").catch((e) => e);
    expect(error).toMatchObject({ status: 502, code: "http_error", requestId: "req_hdr" });
  });
});

describe("agent run streaming", () => {
  const input = { sessionId: "s1", message: "hi" };

  async function collect(stream: AsyncGenerator<{ event: string; data: Record<string, unknown> }>) {
    const events: string[] = [];
    for await (const event of stream) events.push(event.event);
    return events;
  }

  it("yields events across arbitrary chunk boundaries", async () => {
    const whole = frame("token", { content: "a" }) + frame("done", { status: "completed" });
    const cut = Math.floor(whole.length / 2);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([whole.slice(0, cut), whole.slice(cut)])));

    expect(await collect(client.streamAgentRun(input))).toEqual(["token", "done"]);
  });

  it("throws stream_truncated (with the request ID) when the stream ends without done", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(sseResponse([frame("token", { content: "a" })], { "X-Request-ID": "req_trunc" }))
    );

    const error = await collect(client.streamAgentRun(input)).catch((e) => e);
    expect(error).toBeInstanceOf(HelixOSApiError);
    expect(error).toMatchObject({ code: "stream_truncated", requestId: "req_trunc" });
  });

  it("surfaces non-2xx start failures as API errors with the request ID", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({ error: { code: "not_found", message: "Agent session not found", details: {}, request_id: "req_nf" } }, { status: 404 })
      )
    );
    const error = await collect(client.streamAgentRun(input)).catch((e) => e);
    expect(error).toMatchObject({ status: 404, requestId: "req_nf" });
  });

  it("cancels the response body when the consumer stops iterating early", async () => {
    const cancel = vi.fn();
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(frame("token", { content: "a" })));
      },
      cancel
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));

    const iterator = client.streamAgentRun(input);
    await iterator.next();
    await iterator.return(undefined);
    expect(cancel).toHaveBeenCalled();
  });

  it("passes the AbortSignal to fetch and rejects with AbortError when aborted", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn((_url: string, init: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError"))
        );
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const pending = collect(client.streamAgentRun({ ...input, signal: controller.signal })).catch((e) => e);
    controller.abort();

    const error = await pending;
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
    expect(error).toMatchObject({ name: "AbortError" });
  });
});
