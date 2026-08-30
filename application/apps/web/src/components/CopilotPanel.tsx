"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Warning } from "@phosphor-icons/react";
import { askCopilot, getChatHistory } from "@/lib/api";
import { AnswerText } from "@/components/AnswerText";
import type {
  ActiveView,
  CopilotChatMessage,
  CopilotChatSource,
  GroundedRationale,
  WithheldAnswer,
} from "@/lib/types";

interface DisplayMessage extends CopilotChatMessage {
  sources?: CopilotChatSource[];
  usedLocalModel?: boolean;
  provider?: string | null;
  model?: string | null;
  rationale?: GroundedRationale | null;
  answerSource?: "model" | "deterministic";
  withheld?: WithheldAnswer | null;
}

const OPENING =
  "Ask about this run and I will answer from the evidence on screen: the subgroup this tumour falls in, what defines it, what was retrieved, and what each gate reports. I cannot recommend treatment, and any figure I cannot trace back to this run is withheld rather than shown.";

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
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getChatHistory(runId)
      .then((payload) => {
        const restored = (payload.messages || [])
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
        if (restored.length > 0) setMessages(restored);
      })
      .catch(() => undefined);
  }, [runId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  const suggestions = useMemo(
    () =>
      activeView === "clinical_trials"
        ? ["Summarise trial eligibility for this patient", "Which criteria are unknown?"]
        : [
            "Summarise this case",
            selectedCluster != null
              ? `What defines subgroup ${selectedCluster + 1}?`
              : "What defines this tumour's subgroup?",
            "Which gates did not pass, and what does that mean?",
            selectedDrug ? `Why was ${selectedDrug} retrieved?` : "How should I read the retrieved compounds?",
          ],
    [activeView, selectedCluster, selectedDrug]
  );

  async function sendMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed || loading) return;
    const next: DisplayMessage[] = [...messages, { role: "user", content: trimmed }];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const result = await askCopilot(
        runId,
        trimmed,
        next.slice(-8).map(({ role, content }) => ({ role, content: content.slice(0, 1900) })),
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
          answerSource: result.answer_source,
          withheld: result.withheld,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", content: `The run-aware explanation could not be loaded: ${String(error)}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  const empty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-0.5" aria-live="polite">
        {empty && (
          <>
            <p className="text-[12.5px] leading-relaxed text-[var(--text-secondary)]">{OPENING}</p>
            <div className="pt-1">
              <p className="eyebrow mb-1.5">Try asking</p>
              <div className="flex flex-col gap-1">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => void sendMessage(suggestion)}
                    className="pressable border border-[var(--line)] px-2.5 py-1.5 text-left text-[12px] text-[var(--text-secondary)]"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="flex justify-end">
              <p className="max-w-[85%] rounded-[12px] rounded-br-[4px] bg-[var(--cluster-1)] px-3 py-2 text-[12.5px] leading-relaxed text-white">
                {message.content}
              </p>
            </div>
          ) : (
            <div key={index} className="space-y-1.5">
              <AnswerText text={message.content} />

              {/* The gate is shown, not hidden: a reader must be able to tell a
                  model answer from the deterministic summary that replaced it. */}
              {message.withheld && message.withheld.reasons.length > 0 && (
                <div className="rounded-[var(--radius-inner)] border border-[var(--warning-line)] bg-[var(--warning-wash)] p-2">
                  <p className="flex items-start gap-1.5 text-[11.5px] text-[var(--warning)]">
                    <Warning size={13} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
                    <span>
                      The model&apos;s answer was withheld because it {message.withheld.reasons.join(", and ")}.
                      The summary above is generated deterministically from the run instead.
                    </span>
                  </p>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-1.5">
                {(message.sources ?? []).map((source) => (
                  <a
                    key={`${source.section}-${source.label}`}
                    href={`#${source.section}`}
                    className="pressable border border-[var(--line)] px-1.5 py-0.5 text-[10.5px] text-[var(--text-secondary)]"
                  >
                    {source.label}
                  </a>
                ))}
                {(message.sources || message.answerSource) && (
                  <span className="text-[10px] text-[var(--text-muted)]">
                    {message.answerSource === "model"
                      ? `${message.provider ?? "model"}${message.model ? ` · ${message.model}` : ""}`
                      : "deterministic summary"}
                  </span>
                )}
              </div>
            </div>
          )
        )}

        {loading && (
          <div className="flex items-center gap-1.5 py-1" aria-label="Working">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-muted)]"
                style={{ animationDelay: `${i * 160}ms` }}
              />
            ))}
            <span className="ml-1 text-[11.5px] text-[var(--text-muted)]">reading the run evidence</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="mt-3 shrink-0">
        <div className="flex items-end gap-1.5 rounded-[var(--radius-inner)] border border-[var(--line)] bg-[var(--surface)] p-1.5 focus-within:border-[var(--line-strong)]">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void sendMessage(input);
              }
            }}
            rows={1}
            placeholder="Ask about this run…"
            aria-label="Ask the research copilot"
            className="max-h-28 min-h-8 flex-1 resize-none bg-transparent px-1.5 py-1 text-[12.5px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            aria-label="Send"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--cluster-1)] text-white transition-opacity disabled:opacity-30"
          >
            <ArrowUp size={14} weight="bold" aria-hidden />
          </button>
        </div>
        <p className="mt-1.5 text-[10px] leading-4 text-[var(--text-muted)]">
          Answers describe the analysis, never the patient&apos;s care. Figures that cannot be traced to this
          run are withheld.
        </p>
      </form>
    </div>
  );
}
