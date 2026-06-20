import { useState } from "react";
import { Dataset, Fragment, chat } from "../api/client";

type Turn = { q: string; answer: string; fragments: Fragment[] };

export default function Chat({
  datasets,
  selected,
  setSelected,
}: {
  datasets: Dataset[];
  selected: string | null;
  setSelected: (s: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!selected || !query.trim()) return;
    const q = query.trim();
    setQuery("");
    setBusy(true);
    setError(null);
    try {
      const res = await chat(selected, q);
      setTurns((t) => [...t, { q, answer: res.answer, fragments: res.fragments }]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (datasets.length === 0) {
    return (
      <div className="p-6 text-white/50">
        Construye un dataset primero en la pestaña <b>Datasets</b>.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-white/10 flex items-center gap-3">
        <span className="text-sm text-white/50">Dataset</span>
        <select
          value={selected ?? ""}
          onChange={(e) => setSelected(e.target.value)}
          className="rounded-lg bg-black/30 border border-white/10 px-3 py-1.5 text-sm"
        >
          {datasets.map((d) => (
            <option key={d.name} value={d.name}>
              {d.name} ({d.n_records})
            </option>
          ))}
        </select>
      </div>

      <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
        {turns.length === 0 && (
          <p className="text-white/40 text-sm">
            Pregunta algo. Las respuestas se construyen solo con fragmentos del
            corpus (anti-alucinación).
          </p>
        )}
        {turns.map((t, i) => (
          <div key={i} className="flex flex-col gap-2">
            <p className="text-indigo-300 text-sm font-medium">{t.q}</p>
            <p className="text-white/90 whitespace-pre-wrap">{t.answer}</p>
            {t.fragments.length > 0 && (
              <details className="text-xs text-white/50 mt-1">
                <summary className="cursor-pointer">
                  {t.fragments.length} fragmento(s) fuente
                </summary>
                <ul className="mt-2 flex flex-col gap-1">
                  {t.fragments.map((f, j) => (
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
        ))}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>

      <div className="p-4 border-t border-white/10 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Escribe tu consulta…"
          className="flex-1 rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
        />
        <button
          disabled={busy || !selected}
          onClick={send}
          className="rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-5 py-2 text-sm"
        >
          {busy ? "…" : "Enviar"}
        </button>
      </div>
    </div>
  );
}
