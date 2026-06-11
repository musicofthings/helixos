"use client";

import { BrainCircuit, History, LoaderCircle, Send, Wand2 } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { AgentRunContext } from "@helixos/types";

import { invalidateAuditEvents } from "../../hooks/use-helix-api";
import { createHelixClient } from "../../lib/api-config";

type AgentPanelProps = {
  organizationId?: string;
  sessionId?: string;
  context: AgentRunContext;
  onActivity: (message: string) => void;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export function AgentPanel({ organizationId, sessionId, context, onActivity }: AgentPanelProps) {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "intro",
      role: "assistant",
      content: "Ask for experiment summaries, QC suggestions, or next-step guidance. Suggestions are labeled as suggestions."
    }
  ]);
  const [draft, setDraft] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [toolEvents, setToolEvents] = useState<string[]>([]);

  const canRun = Boolean(organizationId && sessionId && draft.trim() && !isStreaming);

  const latestAssistant = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant")?.content ?? "",
    [messages]
  );

  async function runAgent(message: string) {
    if (!sessionId) {
      return;
    }

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: message
    };
    const assistantId = `assistant-${Date.now()}`;

    setMessages((items) => [...items, userMessage, { id: assistantId, role: "assistant", content: "" }]);
    setDraft("");
    setIsStreaming(true);
    setToolEvents([]);
    onActivity("Agent run started");

    try {
      let assistantText = "";
      for await (const event of createHelixClient().streamAgentRun({
        sessionId,
        message,
        context
      })) {
        if (event.event === "token" && typeof event.data.content === "string") {
          assistantText += event.data.content;
          setMessages((items) =>
            items.map((item) => (item.id === assistantId ? { ...item, content: assistantText } : item))
          );
        }

        if (event.event === "tool_call" && typeof event.data.tool === "string") {
          const label = `${event.data.tool}${typeof event.data.count === "number" ? ` (${event.data.count})` : ""}`;
          setToolEvents((items) => [...items, label]);
        }

        if (event.event === "error" && typeof event.data.message === "string") {
          throw new Error(event.data.message);
        }
      }

      onActivity("Agent run completed");
      await invalidateAuditEvents(queryClient, organizationId);
    } catch (error) {
      const messageText = error instanceof Error ? error.message : "Agent run failed";
      setMessages((items) =>
        items.map((item) => (item.id === assistantId ? { ...item, content: messageText } : item))
      );
      onActivity(`Agent run failed: ${messageText}`);
      await invalidateAuditEvents(queryClient, organizationId);
    } finally {
      setIsStreaming(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canRun) {
      return;
    }
    void runAgent(draft.trim());
  }

  function handleQuickPrompt() {
    const prompt = context.experiment_title
      ? `Summarize ${context.experiment_title} and suggest next QC steps.`
      : "Summarize open experiments and suggest next actions.";
    void runAgent(prompt);
  }

  return (
    <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-ink">
          <BrainCircuit size={17} />
          Lab agent
        </div>
        <button
          type="button"
          onClick={handleQuickPrompt}
          disabled={!sessionId || isStreaming}
          className="inline-flex items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed disabled:bg-black/5 disabled:text-black/40"
        >
          {isStreaming ? <LoaderCircle size={14} className="animate-spin" /> : <Wand2 size={14} />}
          Quick prompt
        </button>
      </div>

      {!organizationId ? (
        <p className="mt-4 rounded-md bg-[#fbfbf8] p-3 text-sm text-graphite">Connect to the API to start an agent session.</p>
      ) : (
        <>
          <div className="mt-4 grid max-h-72 gap-2 overflow-y-auto">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`rounded-md px-3 py-2 text-sm leading-6 ${
                  message.role === "user" ? "bg-[#edf5ef] text-ink" : "bg-[#fbfbf8] text-graphite"
                }`}
              >
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-black/45">
                  {message.role === "user" ? "You" : "Agent"}
                </div>
                {message.content || (isStreaming ? "Thinking..." : "")}
              </div>
            ))}
          </div>

          {toolEvents.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {toolEvents.map((tool) => (
                <span key={tool} className="rounded-md bg-[#eef1ed] px-2 py-1 text-xs text-graphite">
                  tool: {tool}
                </span>
              ))}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="mt-4 grid gap-2">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={3}
              placeholder="Ask the lab agent..."
              className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-fern"
            />
            <button
              type="submit"
              disabled={!canRun}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
            >
              <Send size={14} />
              Run agent
            </button>
          </form>
        </>
      )}

      <div className="mt-4 flex items-center gap-2 text-xs text-graphite">
        <History size={14} />
        Latest response: {latestAssistant.slice(0, 120) || "Waiting for first run."}
      </div>
    </section>
  );
}
