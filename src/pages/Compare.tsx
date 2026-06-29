import { useState } from "react";
import { compareModels, type CompareResult, type Dataset } from "../api/client";
import { useI18n } from "../i18n";

const MODES = ["statistical", "grounded", "free"] as const;

export default function Compare({ datasets }: { datasets: Dataset[] }) {
  const { t } = useI18n();
  const [dataset, setDataset] = useState<string>(datasets[0]?.name ?? "");
  const [query, setQuery] = useState("");
  const [modeA, setModeA] = useState<string>("statistical");
  const [modeB, setModeB] = useState<string>("grounded");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!dataset || !query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await compareModels(dataset, query, modeA, modeB);
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const Column = ({ label, data }: { label: string; data: CompareResult["a"] }) => (
    <div className="flex-1 rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className={`rounded-full px-2 py-0.5 text-xs ${
          data.mode === "statistical" ? "bg-emerald-500/20 text-emerald-300" :
          data.mode === "grounded" ? "bg-amber-500/20 text-amber-300" :
          "bg-white/15 text-white/80"
        }`}>
          {data.mode}
        </span>
        <span className="text-xs text-white/40">{label}</span>
      </div>
      <div className="whitespace-pre-wrap text-sm text-white/90 min-h-[60px]">
        {data.answer}
      </div>
      {data.fragments.length > 0 && (
        <details className="mt-2 text-xs text-white/50">
          <summary className="cursor-pointer">{data.fragments.length} {t("compare.fragments")}</summary>
          <ul className="mt-1 flex flex-col gap-1">
            {data.fragments.map((f, i) => (
              <li key={i} className="rounded bg-black/30 border border-white/10 px-2 py-1">
                <span className="text-emerald-400">{f.score.toFixed(3)}</span> {f.text}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1">{t("compare.title")}</h1>
      <p className="text-sm text-white/40 mb-4">
        {t("compare.desc")}
      </p>

      <div className="rounded-xl border border-white/10 bg-white/5 p-5 mb-4">
        <div className="flex flex-col gap-3">
          <label className="text-sm">
            {t("compare.dataset")}
            <select
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
            >
              {datasets.map((d) => (
                <option key={d.name} value={d.name}>{d.name}</option>
              ))}
            </select>
          </label>

          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={2}
            placeholder={t("compare.placeholder")}
            className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm resize-none"
          />

          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">
              {t("compare.modeA")}
              <select
                value={modeA}
                onChange={(e) => setModeA(e.target.value)}
                className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
              >
                {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label className="text-sm">
              {t("compare.modeB")}
              <select
                value={modeB}
                onChange={(e) => setModeB(e.target.value)}
                className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
              >
                {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          </div>

          <button
            onClick={run}
            disabled={busy || !dataset || !query.trim()}
            className="self-start rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-4 py-2 text-sm"
          >
            {busy ? t("compare.running") : t("compare.run")}
          </button>
          {error && <p className="text-sm text-red-400">{error}</p>}
        </div>
      </div>

      {result && (
        <div className="flex gap-4">
          <Column label="A" data={result.a} />
          <Column label="B" data={result.b} />
        </div>
      )}
    </div>
  );
}
