import { useEffect, useState } from "react";
import { ArrowUp, FileText, Sparkles, Loader2 } from "lucide-react";
import { Dataset, parseCitation, type Expert } from "../api/client";
import type { Conversation } from "../App";
import ModeSelector, { type AgentBMode } from "../components/ModeSelector";
import MetricsPanel from "../components/MetricsPanel";
import SamplerControls, { type Samplers } from "../components/SamplerControls";
import { Badge, Button } from "../components/ui";
import { useI18n } from "../i18n";

export default function Chat({
  conversation,
  datasets,
  selectedDataset: _selectedDataset,
  setSelectedDataset: _setSelectedDataset,
  onSend,
  busy,
  error,
  agentBMode,
  setAgentBMode,
  inferenceRunning,
  autoStarting,
  hasLlmSelected,
  expert = null,
  pendingQuestion = null,
  onPendingConsumed,
}: {
  conversation: Conversation | null;
  datasets: Dataset[];
  selectedDataset: string | null;
  setSelectedDataset: (s: string) => void;
  onSend: (q: string, samplers?: Samplers) => void;
  busy: boolean;
  error: string | null;
  agentBMode: AgentBMode;
  setAgentBMode: (m: AgentBMode) => void;
  inferenceRunning: boolean;
  autoStarting: boolean;
  hasLlmSelected: boolean;
  /** Active expert: it owns corpus, mode, prompt and samplers. */
  expert?: Expert | null;
  /** Question pre-filled from an expert example. */
  pendingQuestion?: string | null;
  onPendingConsumed?: () => void;
}) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [samplers, setSamplers] = useState<Samplers>({
    temperature: 0.1,
    top_p: 0.95,
    top_k: 40,
    repeat_penalty: 1.0,
  });
  useEffect(() => {
    if (pendingQuestion) {
      setQuery(pendingQuestion);
      onPendingConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuestion]);

  const empty = !conversation || conversation.messages.length === 0;
  const effectiveMode = expert ? expert.default_mode : agentBMode;
  const showSamplers = effectiveMode !== "statistical" && inferenceRunning;
  const hasDatasets = datasets.length > 0;
  const needsLlm = effectiveMode !== "statistical";
  const canSend =
    query.trim() &&
    !busy &&
    (!!expert || agentBMode === "free" || hasDatasets) &&
    (effectiveMode === "statistical" || hasLlmSelected);

  function submit() {
    const q = query.trim();
    if (!q || busy) return;
    setQuery("");
    onSend(q, showSamplers ? samplers : undefined);
  }

  const statusHint = autoStarting
    ? t("flow.autoStarting")
    : agentBMode === "free" && !hasDatasets
      ? t("flow.freeModeHint")
      : needsLlm && inferenceRunning
        ? null
        : null;

  const InputCard = (
    <div className="w-full max-w-2xl">
      <div className="rounded-2xl border border-white/10 bg-white/5 p-3 shadow-card focus-within:border-white/20 transition-colors">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          placeholder={t("chat.placeholder")}
          className="w-full resize-none bg-transparent outline-none text-sm placeholder:text-white/30"
        />
        <div className="flex items-center justify-between pt-2 gap-2">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            {expert ? (
              <Badge tone="accent">
                <Sparkles className="h-2.5 w-2.5" /> {expert.name} · {t(`mode.${expert.default_mode}`)}
              </Badge>
            ) : (
              <ModeSelector mode={agentBMode} onChange={setAgentBMode} inferenceRunning={inferenceRunning || hasLlmSelected} />
            )}
            {inferenceRunning && <MetricsPanel />}
            {autoStarting && (
              <span className="flex items-center gap-1.5 text-xs text-amber-300 animate-pulse">
                <Loader2 className="h-3 w-3 animate-spin" />
                {t("flow.autoStarting")}
              </span>
            )}
          </div>
          <Button
            onClick={submit}
            disabled={!canSend}
            variant="primary"
            circle
            loading={busy}
            icon={<ArrowUp className="h-4 w-4" />}
          />
        </div>
        {showSamplers && (
          <div className="mt-2">
            <SamplerControls samplers={samplers} onChange={setSamplers} />
          </div>
        )}
      </div>
      {statusHint && !error && (
        <p className="mt-2 text-center text-xs text-white/40">{statusHint}</p>
      )}
      {error && <p className="mt-2 text-center text-sm text-red-400">{error}</p>}
    </div>
  );

  if (empty) {
    return (
      <div className="h-full flex flex-col items-center justify-center px-6">
        <h1 className="text-4xl font-semibold mb-2 tracking-tight">{t("chat.greeting")}</h1>
        <p className="text-white/50 mb-8">{t("chat.howHelp")}</p>
        {InputCard}
        <p className="mt-4 text-xs text-white/30 flex items-center gap-1.5 text-center max-w-lg">
          <Sparkles className="h-3 w-3 shrink-0" />
          {expert
            ? expert.description
            : agentBMode === "free" && !hasDatasets
              ? t("flow.freeModeHint")
              : t("chat.grounded")}
        </p>
        {expert && expert.examples.length > 0 && empty && (
          <div className="mt-3 flex flex-wrap gap-1.5 justify-center max-w-xl">
            {expert.examples.slice(0, 3).map((q) => (
              <button
                key={q}
                onClick={() => setQuery(q)}
                className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-white/60 hover:bg-white/10 hover:text-white/90 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 py-8 flex flex-col gap-6">
          {conversation!.messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="self-end max-w-[85%]">
                <div className="rounded-2xl bg-accent px-4 py-2 text-sm text-accent-fg">
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={i} className="self-start max-w-[95%]">
                <div className="whitespace-pre-wrap text-white/90 leading-relaxed">{m.content}</div>
                {m.fragments && m.fragments.length > 0 && (
                  <details className="mt-2 group">
                    <summary className="cursor-pointer text-xs text-white/40 hover:text-white/60 transition-colors list-none">
                      {m.fragments.length} {t("chat.fragments")}
                    </summary>
                    <div className="mt-2 flex flex-col gap-1.5">
                      {m.fragments.map((f, j) => {
                        const cite = parseCitation(f.source_id);
                        return (
                          <div
                            key={j}
                            className="rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-xs"
                          >
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <Badge tone="success">{f.score.toFixed(3)}</Badge>
                              {cite.page !== null ? (
                                <Badge tone="accent">
                                  <FileText className="h-2.5 w-2.5" /> {cite.label}
                                </Badge>
                              ) : (
                                cite.label && <span className="text-white/40">[{cite.label}]</span>
                              )}
                            </div>
                            <p className="text-white/70">{f.text}</p>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                )}
              </div>
            ),
          )}
        </div>
      </div>
      <div className="border-t border-white/10 p-4 flex justify-center">
        {InputCard}
      </div>
    </div>
  );
}
