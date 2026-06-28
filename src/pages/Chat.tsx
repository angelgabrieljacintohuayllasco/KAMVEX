import { useState } from "react";
import { Dataset } from "../api/client";
import type { Conversation } from "../App";
import ModeSelector, { type AgentBMode } from "../components/ModeSelector";
import MetricsPanel from "../components/MetricsPanel";
import SamplerControls, { type Samplers } from "../components/SamplerControls";
import { useI18n } from "../i18n";

export default function Chat({
  conversation,
  datasets,
  selectedDataset,
  setSelectedDataset,
  onSend,
  busy,
  error,
  goKnowledge,
  agentBMode,
  setAgentBMode,
  inferenceRunning,
}: {
  conversation: Conversation | null;
  datasets: Dataset[];
  selectedDataset: string | null;
  setSelectedDataset: (s: string) => void;
  onSend: (q: string, samplers?: Samplers) => void;
  busy: boolean;
  error: string | null;
  goKnowledge: () => void;
  agentBMode: AgentBMode;
  setAgentBMode: (m: AgentBMode) => void;
  inferenceRunning: boolean;
}) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [samplers, setSamplers] = useState<Samplers>({
    temperature: 0.1,
    top_p: 0.95,
    top_k: 40,
    repeat_penalty: 1.0,
  });
  const empty = !conversation || conversation.messages.length === 0;
  const showSamplers = agentBMode !== "statistical" && inferenceRunning;

  function submit() {
    const q = query.trim();
    if (!q || busy) return;
    setQuery("");
    onSend(q, showSamplers ? samplers : undefined);
  }

  const InputCard = (
    <div className="w-full max-w-2xl">
      <div className="rounded-2xl border border-white/10 bg-white/5 p-3 shadow-lg">
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
        <div className="flex items-center justify-between pt-2">
          {datasets.length === 0 ? (
            <button
              onClick={goKnowledge}
              className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs text-amber-300"
            >
              {t("chat.buildKnowledge")}
            </button>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-1 rounded-full bg-black/30 border border-white/10 px-2 py-1 text-xs">
                <span className="text-white/40">📚</span>
                <select
                  value={selectedDataset ?? ""}
                  onChange={(e) => setSelectedDataset(e.target.value)}
                  className="bg-transparent outline-none text-white/80"
                >
                  {datasets.map((d) => (
                    <option key={d.name} value={d.name} className="bg-[#0b0e14]">
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
              <ModeSelector
                mode={agentBMode}
                onChange={setAgentBMode}
                disabled={agentBMode !== "statistical" && !inferenceRunning}
              />
              <MetricsPanel />
            </div>
          )}
          <button
            onClick={submit}
            disabled={busy || !query.trim() || datasets.length === 0}
            className="rounded-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-30 w-9 h-9 flex items-center justify-center"
          >
            {busy ? "…" : "↑"}
          </button>
        </div>
        {showSamplers && (
          <div className="mt-2">
            <SamplerControls samplers={samplers} onChange={setSamplers} />
          </div>
        )}
      </div>
      {error && <p className="mt-2 text-center text-sm text-red-400">{error}</p>}
    </div>
  );

  if (empty) {
    return (
      <div className="h-full flex flex-col items-center justify-center px-6">
        <h1 className="text-4xl font-semibold mb-2">{t("chat.greeting")}</h1>
        <p className="text-white/50 mb-8">{t("chat.howHelp")}</p>
        {InputCard}
        <p className="mt-4 text-xs text-white/30">
          {t("chat.grounded")}
        </p>
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
                <div className="rounded-2xl bg-indigo-600 px-4 py-2 text-sm">
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={i} className="self-start max-w-[95%]">
                <div className="whitespace-pre-wrap text-white/90">{m.content}</div>
                {m.fragments && m.fragments.length > 0 && (
                  <details className="mt-2 text-xs text-white/50">
                    <summary className="cursor-pointer">
                      {m.fragments.length} {t("chat.fragments")}
                    </summary>
                    <ul className="mt-2 flex flex-col gap-1">
                      {m.fragments.map((f, j) => (
                        <li
                          key={j}
                          className="rounded bg-black/30 border border-white/10 px-3 py-2"
                        >
                          <span className="text-emerald-400">
                            {f.score.toFixed(3)}
                          </span>{" "}
                          <span className="text-white/40">[{f.source_id}]</span>{" "}
                          {f.text}
                        </li>
                      ))}
                    </ul>
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
