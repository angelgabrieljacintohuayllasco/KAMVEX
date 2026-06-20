import { useState } from "react";
import {
  Dataset,
  pickJsonFile,
  startBuild,
  streamBuild,
  BuildEvent,
} from "../api/client";

const PROFILES = ["low-ram", "medium", "fast"] as const;

export default function Datasets({
  datasets,
  onChanged,
}: {
  datasets: Dataset[];
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [jsonPath, setJsonPath] = useState<string | null>(null);
  const [profile, setProfile] = useState<string>("low-ram");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<BuildEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick() {
    const p = await pickJsonFile();
    if (p) {
      setJsonPath(p);
      if (!name) {
        const base = p.replace(/\\/g, "/").split("/").pop() ?? "dataset";
        setName(base.replace(/\.json$/i, ""));
      }
    }
  }

  async function build() {
    if (!name || !jsonPath) return;
    setBusy(true);
    setError(null);
    setProgress({ stage: "start", pct: 0, msg: "Iniciando" });
    try {
      const jid = await startBuild(name, jsonPath, profile);
      await streamBuild(jid, (e) => setProgress(e));
      onChanged();
      setProgress(null);
      setJsonPath(null);
    } catch (e) {
      setError(String(e));
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-4">Datasets</h1>

      <div className="rounded-xl border border-white/10 bg-white/5 p-5 mb-6">
        <h2 className="font-medium mb-3">Construir inteligencia desde un JSON</h2>

        <div className="flex flex-col gap-3">
          <button
            onClick={pick}
            className="self-start rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-sm"
          >
            {jsonPath ? "Cambiar archivo JSON" : "Elegir archivo JSON"}
          </button>
          {jsonPath && (
            <p className="text-xs text-white/50 break-all">{jsonPath}</p>
          )}

          <label className="text-sm">
            Nombre
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="mi-dataset"
              className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
            />
          </label>

          <label className="text-sm">
            Perfil del índice
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
            >
              {PROFILES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>

          <button
            disabled={busy || !name || !jsonPath}
            onClick={build}
            className="self-start rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 px-4 py-2 text-sm"
          >
            {busy ? "Construyendo…" : "Construir índice"}
          </button>

          {progress && (
            <div className="mt-2">
              <div className="h-2 w-full rounded bg-black/40 overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all"
                  style={{ width: `${progress.pct}%` }}
                />
              </div>
              <p className="text-xs text-white/60 mt-1">
                {progress.stage} — {progress.msg}
              </p>
            </div>
          )}
          {error && <p className="text-sm text-red-400">{error}</p>}
        </div>
      </div>

      <h2 className="font-medium mb-2">Construidos</h2>
      {datasets.length === 0 ? (
        <p className="text-sm text-white/40">Aún no hay datasets.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {datasets.map((d) => (
            <li
              key={d.name}
              className="rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-sm flex justify-between"
            >
              <span className="font-medium">{d.name}</span>
              <span className="text-white/50">
                {d.n_records} registros · {d.profile}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
