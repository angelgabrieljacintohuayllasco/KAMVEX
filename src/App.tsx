import { useEffect, useState } from "react";
import { waitForSidecar, listDatasets, chat, Dataset, Fragment } from "./api/client";
import Chat from "./pages/Chat";
import Knowledge from "./pages/Datasets";
import Hub from "./pages/Hub";
import Settings from "./pages/Settings";

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

type View = "chat" | "knowledge" | "hub" | "settings";

export default function App() {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<View>("chat");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const ds = await listDatasets();
      setDatasets(ds);
      setSelectedDataset((cur) => cur ?? (ds[0]?.name ?? null));
    } catch {
      /* sidecar not ready yet */
    }
  }

  useEffect(() => {
    waitForSidecar().then((ok) => {
      setReady(ok);
      setFailed(!ok);
      if (ok) refresh();
    });
  }, []);

  const active = conversations.find((c) => c.id === activeId) ?? null;

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

  async function send(query: string) {
    if (!selectedDataset) {
      setError("Selecciona o construye conocimiento primero (pestaña Knowledge).");
      return;
    }
    setError(null);
    setBusy(true);

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
      const res = await chat(selectedDataset, query);
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
            {failed ? "No se pudo iniciar KAMVEX" : "Iniciando KAMVEX…"}
          </p>
          <p className="text-sm text-white/40 mt-2">
            {failed
              ? "Revisa que Python y las dependencias del backend estén instalados."
              : "Levantando el motor local."}
          </p>
        </div>
      </div>
    );
  }

  const NavBtn = ({ v, label, icon }: { v: View; label: string; icon: string }) => (
    <button
      onClick={() => setView(v)}
      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm w-full text-left ${
        view === v ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5"
      }`}
    >
      <span className="w-4 text-center">{icon}</span>
      {label}
    </button>
  );

  return (
    <div className="h-full flex">
      <nav className="w-60 shrink-0 border-r border-white/10 bg-black/30 flex flex-col">
        <div className="px-4 py-4 text-lg font-bold tracking-widest">
          KAM<span className="text-indigo-400">VEX</span>
        </div>

        <div className="px-3">
          <button
            onClick={newChat}
            className="w-full rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 px-3 py-2 text-sm text-left"
          >
            ＋ New Chat
          </button>
        </div>

        <div className="px-4 pt-4 pb-1 text-xs uppercase tracking-wider text-white/30">
          Recents
        </div>
        <div className="flex-1 overflow-y-auto px-2">
          {conversations.length === 0 && (
            <p className="px-2 py-1 text-xs text-white/30">Sin conversaciones.</p>
          )}
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => openChat(c.id)}
              className={`block w-full truncate rounded-md px-2 py-1.5 text-left text-sm ${
                c.id === activeId && view === "chat"
                  ? "bg-white/10 text-white"
                  : "text-white/60 hover:bg-white/5"
              }`}
              title={c.title}
            >
              {c.title || "Nueva conversación"}
            </button>
          ))}
        </div>

        <div className="border-t border-white/10 p-2 flex flex-col gap-0.5">
          <NavBtn v="knowledge" label="Knowledge" icon="📚" />
          <NavBtn v="hub" label="Hub" icon="◳" />
          <NavBtn v="settings" label="Settings" icon="⚙" />
        </div>
      </nav>

      <main className="flex-1 min-w-0 h-full overflow-hidden">
        {view === "chat" && (
          <Chat
            conversation={active}
            datasets={datasets}
            selectedDataset={selectedDataset}
            setSelectedDataset={setSelectedDataset}
            onSend={send}
            busy={busy}
            error={error}
            goKnowledge={() => setView("knowledge")}
          />
        )}
        {view === "knowledge" && (
          <Knowledge datasets={datasets} onChanged={refresh} />
        )}
        {view === "hub" && <Hub datasets={datasets} />}
        {view === "settings" && <Settings />}
      </main>
    </div>
  );
}
