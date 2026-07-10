import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  waitForSidecar, listDatasets, chat, federatedChat, freeChat, inferenceStatus,
  listLocalModels, llamaStart, llamaReady, llamaEnsureBinary, autotuneFlags, inferenceConnect,
  Dataset, Fragment, LocalModel,
} from "./api/client";
import { BookOpen, Cpu, MessageSquarePlus, Search, Settings as SettingsIcon, Zap } from "lucide-react";
import Chat from "./pages/Chat";
import Knowledge from "./pages/Datasets";
import Models from "./pages/Models";
import Compare from "./pages/Compare";
import Settings from "./pages/Settings";
import TopBar, { KnowledgeSelector, LlmSelector } from "./components/TopBar";
import type { AgentBMode } from "./components/ModeSelector";
import { useI18n } from "./i18n";

export type Message = {
  role: "user" | "assistant";
  content: string;
  fragments?: Fragment[];
};
export type Conversation = {
  id: string;
  title: string;
  dataset: string | null;
  messages: Message[];
};

type View = "chat" | "knowledge" | "models" | "compare" | "settings";

export default function App() {
  const { t } = useI18n();
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<View>("chat");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentBMode, setAgentBMode] = useState<AgentBMode>("statistical");
  const [inferenceRunning, setInferenceRunning] = useState(false);
  const [federated, setFederated] = useState(false);
  const [search, setSearch] = useState("");
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [selectedLlm, setSelectedLlm] = useState<string | null>(() =>
    localStorage.getItem("kamvex-llm-model"),
  );
  const [autoStarting, setAutoStarting] = useState(false);
  const autoStartAttempted = useRef(false);

  async function refresh() {
    try {
      const ds = await listDatasets();
      setDatasets(ds);
      setSelectedDataset((cur) => cur ?? (ds[0]?.name ?? null));
    } catch {
      /* sidecar not ready yet */
    }
  }

  async function refreshModels() {
    try {
      const models = await listLocalModels();
      setLocalModels(models);
    } catch { /* sidecar not ready */ }
  }

  const handleSelectLlm = useCallback((path: string | null) => {
    setSelectedLlm(path);
    if (path) localStorage.setItem("kamvex-llm-model", path);
    else localStorage.removeItem("kamvex-llm-model");
  }, []);

  async function autoStartEngine(modelPath: string): Promise<boolean> {
    if (autoStarting || inferenceRunning) return inferenceRunning;
    setAutoStarting(true);
    try {
      const model = localModels.find((m) => m.path === modelPath);
      const sizeMb = model?.size_mb ?? 4000;
      const prescription = await autotuneFlags(sizeMb, "balanced");
      await llamaEnsureBinary(prescription.backend);
      const flags = [
        "-ngl", String(prescription.ngl), "-t", String(prescription.threads),
        "-c", String(prescription.ctx), "-b", String(prescription.batch),
        "-ub", String(prescription.batch), "-ctk", prescription.ctk, "-ctv", prescription.ctv,
        ...(prescription.flash_attn ? ["-fa"] : []),
        ...(prescription.mlock ? ["--mlock"] : []),
      ];
      const portStr = await llamaStart(modelPath, flags);
      const port = Number(portStr);
      for (let i = 0; i < 60; i++) {
        if (await llamaReady()) break;
        await new Promise((r) => setTimeout(r, 500));
      }
      await inferenceConnect(port);
      setInferenceRunning(true);
      return true;
    } catch {
      return false;
    } finally {
      setAutoStarting(false);
    }
  }

  useEffect(() => {
    waitForSidecar().then((ok) => {
      setReady(ok);
      setFailed(!ok);
      if (ok) { refresh(); refreshModels(); }
    });
    const interval = setInterval(() => {
      inferenceStatus().then((s) => setInferenceRunning(s.connected)).catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  const filteredConversations = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => (c.title || t("app.newConvo")).toLowerCase().includes(q));
  }, [conversations, search, t]);

  function newChat() {
    setActiveId(null);
    setView("chat");
    setError(null);
  }

  function openChat(id: string) {
    setActiveId(id);
    setView("chat");
    setError(null);
  }

  async function send(query: string, samplers?: { temperature?: number; top_p?: number; top_k?: number; repeat_penalty?: number }) {
    const needsLlm = agentBMode !== "statistical";
    const useDataset = selectedDataset && datasets.length > 0;

    if (agentBMode === "statistical" && !useDataset) {
      setError(t("flow.needsKnowledge"));
      return;
    }
    if (agentBMode === "grounded" && !useDataset) {
      setError(t("flow.needsBoth"));
      return;
    }
    if (needsLlm && !selectedLlm) {
      setError(t("flow.needsLlm"));
      return;
    }

    setError(null);
    setBusy(true);

    if (needsLlm && !inferenceRunning && selectedLlm) {
      if (!autoStartAttempted.current) {
        autoStartAttempted.current = true;
        const ok = await autoStartEngine(selectedLlm);
        if (!ok) {
          setError(t("flow.autoStartFailed"));
          setBusy(false);
          autoStartAttempted.current = false;
          return;
        }
      }
    }

    let convId = activeId;
    if (!convId) {
      convId = crypto.randomUUID();
      const conv: Conversation = {
        id: convId,
        title: query.slice(0, 48),
        dataset: selectedDataset,
        messages: [],
      };
      setConversations((prev) => [conv, ...prev]);
      setActiveId(convId);
    }
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? { ...c, messages: [...c.messages, { role: "user", content: query }] }
          : c,
      ),
    );

    try {
      let res;
      if (agentBMode === "free" && !useDataset) {
        res = await freeChat(query, samplers);
      } else if (federated) {
        res = await federatedChat(query, agentBMode, samplers);
      } else {
        res = await chat(selectedDataset!, query, agentBMode, samplers);
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: [
                  ...c.messages,
                  { role: "assistant", content: res.answer, fragments: res.fragments },
                ],
              }
            : c,
        ),
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!ready) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-xl font-semibold tracking-tight">
            {failed ? t("app.failed") : t("app.starting")}
          </p>
          <p className="text-sm text-white/40 mt-2">
            {failed ? t("app.checkPython") : t("app.startingEngine")}
          </p>
        </div>
      </div>
    );
  }

  const NavBtn = ({ v, label, icon }: { v: View; label: string; icon: React.ReactNode }) => (
    <button
      onClick={() => setView(v)}
      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm w-full text-left transition-colors ${
        view === v ? "bg-white/10 text-white" : "text-white/55 hover:bg-white/5 hover:text-white/85"
      }`}
    >
      <span className="w-4 shrink-0 flex items-center justify-center text-white/60">{icon}</span>
      {label}
    </button>
  );

  return (
    <div className="h-full flex">
      <nav className="w-60 shrink-0 border-r border-white/10 bg-black/30 flex flex-col">
        <div className="px-4 py-4 text-lg font-bold tracking-widest">
          KAM<span className="text-accent">VEX</span>
        </div>

        <div className="px-3 flex flex-col gap-2">
          <button
            onClick={newChat}
            className="flex items-center gap-2 w-full rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 px-3 py-2 text-sm text-left transition-colors"
          >
            <MessageSquarePlus className="h-4 w-4 text-white/50" />
            {t("app.newChat")}
          </button>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("app.searchChats")}
              className="w-full rounded-lg bg-black/20 border border-white/10 pl-8 pr-2 py-1.5 text-xs outline-none placeholder:text-white/30 focus:border-white/20 transition-colors"
            />
          </div>
        </div>

        <div className="px-4 pt-4 pb-1 text-xs uppercase tracking-wider text-white/30">
          {t("app.recents")}
        </div>
        <div className="flex-1 overflow-y-auto px-2">
          {filteredConversations.length === 0 && (
            <p className="px-2 py-1 text-xs text-white/30">{t("app.noConvos")}</p>
          )}
          {filteredConversations.map((c) => (
            <button
              key={c.id}
              onClick={() => openChat(c.id)}
              className={`block w-full truncate rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                c.id === activeId && view === "chat"
                  ? "bg-white/10 text-white"
                  : "text-white/60 hover:bg-white/5"
              }`}
              title={c.title}
            >
              {c.title || t("app.newConvo")}
            </button>
          ))}
        </div>

        <div className="border-t border-white/10 p-2 flex flex-col gap-0.5">
          <NavBtn v="knowledge" label={t("nav.knowledge")} icon={<BookOpen className="h-4 w-4" />} />
          <NavBtn v="models" label={t("nav.models")} icon={<Cpu className="h-4 w-4" />} />
          <NavBtn v="compare" label={t("nav.compare")} icon={<Zap className="h-4 w-4" />} />
          <NavBtn v="settings" label={t("nav.settings")} icon={<SettingsIcon className="h-4 w-4" />} />
        </div>
      </nav>

      <main className="flex-1 min-w-0 h-full flex flex-col overflow-hidden">
        {view === "chat" && (
          <TopBar
            left={
              <KnowledgeSelector
                datasets={datasets}
                selectedDataset={selectedDataset}
                setSelectedDataset={setSelectedDataset}
                federated={federated}
                setFederated={setFederated}
              />
            }
            right={
              <LlmSelector
                models={localModels}
                selected={selectedLlm}
                onSelect={handleSelectLlm}
                running={inferenceRunning}
                starting={autoStarting}
                goModels={() => setView("models")}
              />
            }
          />
        )}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {view === "chat" && (
            <Chat
              conversation={active}
              datasets={datasets}
              selectedDataset={selectedDataset}
              setSelectedDataset={setSelectedDataset}
              onSend={send}
              busy={busy || autoStarting}
              error={error}
              agentBMode={agentBMode}
              setAgentBMode={setAgentBMode}
              inferenceRunning={inferenceRunning}
              autoStarting={autoStarting}
              hasLlmSelected={!!selectedLlm}
            />
          )}
          {view === "knowledge" && (
            <Knowledge datasets={datasets} onChanged={refresh} />
          )}
          {view === "models" && <Models onModelsChanged={refreshModels} />}
          {view === "compare" && <Compare datasets={datasets} />}
          {view === "settings" && <Settings />}
        </div>
      </main>
    </div>
  );
}
