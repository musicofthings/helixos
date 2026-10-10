import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HelixOSApiError } from "@helixos/api-client";
import type { AgentStreamEvent } from "@helixos/types";

import { api, makeQueryClient, resetApi, wrapperFor } from "./helpers";

vi.mock("../lib/api-config", () => ({
  createHelixClient: () => api,
  getApiBaseUrl: () => "http://api.test"
}));

import { AgentPanel } from "../components/agent/agent-panel";

type StreamInput = { sessionId: string; message: string; signal?: AbortSignal };

function stream(events: Array<AgentStreamEvent | Error>) {
  return async function* () {
    for (const event of events) {
      if (event instanceof Error) throw event;
      yield event;
    }
  };
}

function renderPanel() {
  const onActivity = vi.fn();
  const view = render(
    <AgentPanel organizationId="org_demo" sessionId="sess_1" context={{}} onActivity={onActivity} />,
    { wrapper: wrapperFor(makeQueryClient()) }
  );
  return { onActivity, ...view };
}

function ask(text: string) {
  fireEvent.change(screen.getByPlaceholderText("Ask the lab agent..."), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /Run agent/ }));
}

const token = (content: string): AgentStreamEvent => ({ event: "token", data: { content } });
const done: AgentStreamEvent = { event: "done", data: { status: "completed" } };

beforeEach(() => resetApi());
afterEach(() => cleanup());

describe("AgentPanel streaming", () => {
  it("renders streamed tokens and reports completion", async () => {
    api.streamAgentRun.mockImplementation(stream([token("Hel"), token("lo"), done]));
    const { onActivity } = renderPanel();

    ask("hi");

    expect(await screen.findAllByText("Hello")).not.toHaveLength(0);
    await waitFor(() => expect(onActivity).toHaveBeenCalledWith("Agent run completed"));
  });

  it("shows a truncated stream as a failure instead of a silent success", async () => {
    api.streamAgentRun.mockImplementation(
      stream([
        token("partial"),
        new HelixOSApiError(500, "stream_truncated", "Agent run ended before completion", {}, "req_cut")
      ])
    );
    const { onActivity } = renderPanel();

    ask("hi");

    await waitFor(() =>
      expect(onActivity).toHaveBeenCalledWith(
        "Agent run failed: Agent run ended before completion (ref req_cut)"
      )
    );
    expect(onActivity).not.toHaveBeenCalledWith("Agent run completed");
  });

  it("shows a server-reported run error with its request ref", async () => {
    api.streamAgentRun.mockImplementation(
      stream([{ event: "error", data: { message: "provider down", request_id: "req_agent" } }, done])
    );
    const { onActivity } = renderPanel();

    ask("hi");

    await waitFor(() =>
      expect(onActivity).toHaveBeenCalledWith("Agent run failed: provider down (ref req_agent)")
    );
  });

  it("aborts the in-flight stream when the panel unmounts, without reporting a failure", async () => {
    let seenSignal: AbortSignal | undefined;
    api.streamAgentRun.mockImplementation(async function* (input: StreamInput) {
      seenSignal = input.signal;
      yield token("working");
      await new Promise<void>((_resolve, reject) => {
        input.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    });
    const { onActivity, unmount } = renderPanel();

    ask("long task");
    await screen.findAllByText("working");
    expect(seenSignal?.aborted).toBe(false);

    unmount();

    expect(seenSignal?.aborted).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(onActivity).not.toHaveBeenCalledWith(expect.stringContaining("Agent run failed"));
  });
});

describe("AgentPanel session errors", () => {
  it("includes the request ref when the session cannot start", () => {
    render(
      <AgentPanel
        organizationId="org_demo"
        sessionError={new HelixOSApiError(503, "unavailable", "Session service down", {}, "req_sess")}
        context={{}}
        onActivity={vi.fn()}
      />,
      { wrapper: wrapperFor(makeQueryClient()) }
    );

    expect(screen.getByText(/Session service down \(ref req_sess\)/)).toBeTruthy();
  });
});
