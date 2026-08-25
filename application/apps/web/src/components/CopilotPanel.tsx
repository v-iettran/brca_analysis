"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { askCopilot, getChatHistory } from "@/lib/api";
import type { ActiveView, CopilotChatMessage, CopilotChatSource, GroundedRationale } from "@/lib/types";

interface DisplayMessage extends CopilotChatMessage {
  sources?: CopilotChatSource[];
  usedLocalModel?: boolean;
  provider?: string | null;
  model?: string | null;
  rationale?: GroundedRationale | null;
}

export function CopilotPanel({
  runId,
  selectedDrug,
  selectedCluster,
  activeView,
}: {
  runId: string;
  selectedDrug: string | null;
  selectedCluster: number | null;
  activeView: ActiveView;
}) {
  const [messages, setMessages] = useState<DisplayMessage[]>([
    {
      role: "assistant",
      content:
        "I can explain overlap nominations, residual signatures, Q2 annotations, ALMANAC pairs, and trial criteria already computed for this run. I will not invent approval, dosage, or eligibility.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    getChatHistory(runId)
      .then((payload) => {
        const restored = (payload.messages || [])
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
        if (restored.length > 0) {
          setMessages(restored);
        }
      })
      .catch(() => undefined)
      .finally(() => setHistoryLoaded(true));
  }, [runId]);

  const suggestions = useMemo(
    () =>
      activeView === "clinical_trials"
        ? [
            "Summarize trial eligibility for this patient",
            "Which criteria are unknown?",
            selectedDrug ? `Any trials linked to ${selectedDrug}?` : "How should I read potential matches?",
          ]
        : [
            "Summarize this patient profile",
            selectedDrug ? `Why was ${selectedDrug} nominated?` : "How should I read overlap nominations?",
            "Explain the residual signature",
            selectedCluster != null
              ? `Explain subgroup ${selectedCluster}`
              : "Explain this tumour's subgroup",
          ],
    [activeView, selectedCluster, selectedDrug]
  );

  async function sendMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed || loading) return;
    const userMessage: DisplayMessage = { role: "user", content: trimmed };
    const next = [...messages, userMessage];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const result = await askCopilot(
        runId,
        trimmed,
        next.slice(-8).map(({ role, content }) => ({ role, content })),
        selectedDrug,
        selectedCluster,
        activeView
      );
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: result.answer,
          sources: result.sources,
          usedLocalModel: result.used_local_model,
          provider: result.provider,
          model: result.model,
          rationale: result.rationale,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: `I could not load the run-aware explanation: ${String(error)}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  return (
    <aside className="flex min-h-[620px] flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-lg shadow-slate-200/40 xl:sticky xl:top-5 xl:h-[calc(100vh-5rem)]">
      <header className="border-b border-slate-100 bg-gradient-to-br from-indigo-600 to-violet-700 px-5 py-5 text-white">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/15 text-sm">✦</span>
              <h2 className="font-semibold">Research Copilot</h2>
            </div>
            <p className="mt-1 text-xs text-indigo-100">
              Persistent · view-aware · {historyLoaded ? "history loaded" : "loading history"}
            </p>
          </div>
          <span className="rounded-full border border-white/20 bg-white/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide">
            {activeView === "clinical_trials" ? "Trials view" : "Analysis view"}
          </span>
        </div>
        {(selectedDrug || selectedCluster != null) && (
          <div className="mt-4 flex flex-wrap gap-2">
            {selectedCluster != null && (
              <span className="rounded-full bg-white/10 px-2.5 py-1 text-[11px]">
                Context: Subgroup {selectedCluster}
              </span>
            )}
            {selectedDrug && (
              <span className="rounded-full bg-white/10 px-2.5 py-1 text-[11px] capitalize">
                Drug: {selectedDrug}
              </span>
            )}
          </div>
        )}
      </header>

      <div className="border-b border-slate-100 px-4 py-3">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
          Suggested questions
        </p>
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((suggestion) => (
            <button
              type="button"
              key={suggestion}
              onClick={() => void sendMessage(suggestion)}
              disabled={loading}
              className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-600 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4" aria-live="polite">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={message.role === "user" ? "ml-8" : "mr-4"}>
            <div
              className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
                message.role === "user"
                  ? "rounded-br-md bg-slate-900 text-white"
                  : "rounded-bl-md border border-slate-200 bg-slate-50 text-slate-700"
              }`}
            >
              {message.content}
            </div>
            {message.sources && message.sources.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {message.sources.map((source) => (
                  <a
                    key={`${source.section}-${source.label}`}
                    href={`#${source.section}`}
                    className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-medium text-indigo-600 hover:bg-indigo-100"
                  >
                    {source.label}
                  </a>
                ))}
                <span className="px-1 py-1 text-[10px] text-slate-400">
                  {message.usedLocalModel || message.provider
                    ? `${message.provider || "model"} explanation${message.model ? ` · ${message.model}` : ""}`
                    : "Deterministic fallback"}
                </span>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="mr-12 rounded-2xl rounded-bl-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
            Reviewing the run evidence…
          </div>
        )}
      </div>

      <form onSubmit={submit} className="border-t border-slate-100 bg-white p-4">
        <div className="flex items-end gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void sendMessage(input);
              }
            }}
            rows={2}
            placeholder="Ask about this evidence…"
            className="min-h-12 flex-1 resize-none bg-transparent px-2 py-1 text-sm text-slate-800 outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
        <p className="mt-2 text-center text-[10px] leading-4 text-slate-400">
          Summarizes existing evidence only · no clinical decisions
        </p>
      </form>
    </aside>
  );
}
