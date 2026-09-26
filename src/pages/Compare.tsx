import { useState } from "react";
import { compareModels, type CompareResult, type Dataset } from "../api/client";
import { Badge, Button, Card, Field, Select, inputClass } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../api/errors";

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
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const modeTone = (m: string) =>
    m === "statistical" ? "success" : m === "grounded" ? "warning" : "neutral";

  const Column = ({ label, data }: { label: string; data: CompareResult["a"] }) => (
    <Card className="flex-1">
      <div className="flex items-center gap-2 mb-3">
        <Badge tone={modeTone(data.mode)}>{t(`mode.${data.mode}`)}</Badge>
        <span className="text-xs text-white/40">{label}</span>
      </div>
      <div className="whitespace-pre-wrap text-sm text-white/90 min-h-[60px]">{data.answer}</div>
      {data.fragments.length > 0 && (
        <details className="mt-2 text-xs text-white/50">
          <summary className="cursor-pointer hover:text-white/70 transition-colors">
            {data.fragments.length} {t("compare.fragments")}
          </summary>
          <ul className="mt-1 flex flex-col gap-1">
            {data.fragments.map((f, i) => (
              <li key={i} className="rounded bg-black/30 border border-white/10 px-2 py-1">
                <span className="text-emerald-400">{f.score.toFixed(3)}</span> {f.text}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-2xl font-semibold mb-1 tracking-tight">{t("compare.title")}</h1>
      <p className="text-sm text-white/40 mb-4">{t("compare.desc")}</p>

      <Card className="mb-4">
        <div className="flex flex-col gap-3">
          <Field label={t("compare.dataset")}>
            <Select
              value={dataset}
              options={datasets.map((d) => ({ value: d.name, label: d.name }))}
              onChange={setDataset}
              searchable={datasets.length > 6}
            />
          </Field>

          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={2}
            placeholder={t("compare.placeholder")}
            className={`${inputClass} resize-none`}
          />

          <div className="grid grid-cols-2 gap-3">
            <Field label={t("compare.modeA")}>
              <Select
                value={modeA}
                options={MODES.map((m) => ({ value: m, label: t(`mode.${m}`) }))}
                onChange={setModeA}
              />
            </Field>
            <Field label={t("compare.modeB")}>
              <Select
                value={modeB}
                options={MODES.map((m) => ({ value: m, label: t(`mode.${m}`) }))}
                onChange={setModeB}
              />
            </Field>
          </div>

          <Button
            onClick={run}
            disabled={!dataset || !query.trim()}
            loading={busy}
            variant="primary"
            className="self-start"
          >
            {busy ? t("compare.running") : t("compare.run")}
          </Button>
          {error && <p className="text-sm text-red-400">{error}</p>}
        </div>
      </Card>

      {result && (
        <div className="flex gap-4">
          <Column label="A" data={result.a} />
          <Column label="B" data={result.b} />
        </div>
      )}
    </div>
  );
}
