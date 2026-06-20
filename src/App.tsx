import { useEffect, useState } from "react";
import { waitForSidecar, listDatasets, Dataset } from "./api/client";
import Datasets from "./pages/Datasets";
import Chat from "./pages/Chat";
import Settings from "./pages/Settings";

type Tab = "datasets" | "chat" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "datasets", label: "Datasets" },
  { id: "chat", label: "Chat" },
  { id: "settings", label: "Settings" },
];

export default function App() {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<Tab>("datasets");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  async function refresh() {
    try {
      const ds = await listDatasets();
      setDatasets(ds);
      setSelected((cur) => cur ?? (ds[0]?.name ?? null));
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

  if (!ready) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-lg font-medium">
            {failed ? "No se pudo iniciar el backend" : "Iniciando DASA…"}
          </p>
          <p className="text-sm text-white/40 mt-1">
            {failed
              ? "Revisa que Python y las dependencias del sidecar estén instalados."
              : "Cargando el motor de recuperación."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex">
      <nav className="w-44 shrink-0 border-r border-white/10 bg-black/20 p-3 flex flex-col gap-1">
        <div className="px-2 py-3 text-lg font-bold tracking-tight">
          DASA<span className="text-indigo-400">·UI</span>
        </div>
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`text-left rounded-lg px-3 py-2 text-sm ${
              tab === t.id ? "bg-indigo-600" : "hover:bg-white/5 text-white/70"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="flex-1 min-w-0 h-full overflow-hidden">
        {tab === "datasets" && (
          <Datasets datasets={datasets} onChanged={refresh} />
        )}
        {tab === "chat" && (
          <Chat datasets={datasets} selected={selected} setSelected={setSelected} />
        )}
        {tab === "settings" && <Settings />}
      </main>
    </div>
  );
}
