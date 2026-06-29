import { useState } from "react";
import {
  Dataset,
  pickJsonFile,
  startBuild,
  startBuildText,
  streamBuild,
  runOreganoTest,
  exportDatasetUrl,
  BuildEvent,
  OreganoResult,
} from "../api/client";
import { useI18n } from "../i18n";

const PROFILES = ["low-ram", "medium", "fast"] as const;
type BuildMode = "file" | "text";

export default function Knowledge({
  datasets,
  onChanged,
}: {
  datasets: Dataset[];
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [jsonPath, setJsonPath] = useState<string | null>(null);
  const [profile, setProfile] = useState<string>("low-ram");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<BuildEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [oreganoBusy, setOreganoBusy] = useState<string | null>(null);
  const [oreganoResults, setOreganoResults] = useState<Record<string, OreganoResult>>({});
  const [buildMode, setBuildMode] = useState<BuildMode>("file");
  const [rawText, setRawText] = useState("");
  const [pdfPath, setPdfPath] = useState<string | null>(null);

  async function pick() {
    const p = await pickJsonFile();
    if (p) {
      setJsonPath(p);
      if (!name) {
        const base = p.replace(/\\/g, "/").split("/").pop() ?? "dataset";
        setName(base.replace(/\.(json|jsonl|csv)$/i, ""));
      }
    }
  }

  async function pickPdf() {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      multiple: false,
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (typeof selected === "string") {
      setPdfPath(selected);
      if (!name) {
        const base = selected.replace(/\\/g, "/").split("/").pop() ?? "dataset";
        setName(base.replace(/\.pdf$/i, ""));
      }
    }
  }

  async function build() {
    if (!name) return;
    if (buildMode === "file" && !jsonPath) return;
    if (buildMode === "text" && !rawText.trim() && !pdfPath) return;
    setBusy(true);
    setError(null);
    setProgress({ stage: "start", pct: 0, msg: "Iniciando" });
    try {
      let jid: string;
      if (buildMode === "text") {
        const res = await startBuildText(name, rawText, profile, pdfPath ?? undefined);
        jid = res.job_id;
      } else {
        jid = await startBuild(name, jsonPath!, profile);
      }
      await streamBuild(jid, (e) => setProgress(e));
      onChanged();
      setProgress(null);
      setJsonPath(null);
      setRawText("");
      setPdfPath(null);
    } catch (e) {
      setError(String(e));
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  async function runOregano(datasetName: string) {
    setOreganoBusy(datasetName);
    setError(null);
    try {
      const result = await runOreganoTest(datasetName);
      setOreganoResults((prev) => ({ ...prev, [datasetName]: result }));
    } catch (e) {
      setError(String(e));
    } finally {
      setOreganoBusy(null);
    }
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">{t("knowledge.title")}</h1>
      <p className="text-sm text-white/40 mb-4">
        {t("knowledge.desc")}
      </p>

      <div className="rounded-xl border border-white/10 bg-white/5 p-5 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <button
            onClick={() => setBuildMode("file")}
            className={`rounded-lg px-3 py-1.5 text-xs ${buildMode === "file" ? "bg-indigo-600" : "bg-white/10 hover:bg-white/20"}`}
          >
            {t("knowledge.fileMode")}
          </button>
          <button
            onClick={() => setBuildMode("text")}
            className={`rounded-lg px-3 py-1.5 text-xs ${buildMode === "text" ? "bg-indigo-600" : "bg-white/10 hover:bg-white/20"}`}
          >
            {t("knowledge.textMode")}
          </button>
        </div>

        <div className="flex flex-col gap-3">
          {buildMode === "file" ? (
            <>
              <button
                onClick={pick}
                className="self-start rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-sm"
              >
                {jsonPath ? t("knowledge.changeFile") : t("knowledge.pickFile")}
              </button>
              {jsonPath && (
                <p className="text-xs text-white/50 break-all">{jsonPath}</p>
              )}
            </>
          ) : (
            <div className="flex flex-col gap-2">
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={6}
                placeholder={t("knowledge.textPlaceholder")}
                className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm resize-none placeholder:text-white/30"
              />
              <button
                onClick={pickPdf}
                className="self-start rounded-lg bg-white/10 hover:bg-white/20 px-3 py-1.5 text-xs"
              >
                {pdfPath ? t("knowledge.changePdf") : t("knowledge.importPdf")}
              </button>
              {pdfPath && (
                <p className="text-xs text-white/50 break-all">{pdfPath}</p>
              )}
            </div>
          )}

          <label className="text-sm">
            {t("knowledge.name")}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="mi-dataset"
              className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
            />
          </label>

          <label className="text-sm">
            {t("knowledge.profile")}
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
            disabled={busy || !name || (buildMode === "file" ? !jsonPath : !rawText.trim() && !pdfPath)}
            onClick={build}
            className="self-start rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 px-4 py-2 text-sm"
          >
            {busy ? t("knowledge.building") : t("knowledge.buildBtn")}
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

      <h2 className="font-medium mb-2">{t("knowledge.built")}</h2>
      {datasets.length === 0 ? (
        <p className="text-sm text-white/40">{t("knowledge.empty")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {datasets.map((d) => {
            const oregano = oreganoResults[d.name];
            return (
              <div
                key={d.name}
                className="rounded-xl border border-white/10 bg-white/5 p-4"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <span className="font-medium text-base">{d.name}</span>
                    <p className="text-xs text-white/40 mt-1">
                      {d.n_records} {t("knowledge.records")} · {t("knowledge.profileLabel")} {d.profile} · {d.dim ?? "?"} {t("knowledge.dim")}
                    </p>
                  </div>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => runOregano(d.name)}
                      disabled={oreganoBusy === d.name}
                      className="rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 px-3 py-1.5 text-xs"
                      title={t("knowledge.oreganoTip")}
                    >
                      {oreganoBusy === d.name ? t("knowledge.auditing") : t("knowledge.oregano")}
                    </button>
                    <a
                      href={`#`}
                      onClick={async (e) => {
                        e.preventDefault();
                        const url = await exportDatasetUrl(d.name);
                        window.open(url, "_blank");
                      }}
                      className="rounded-lg bg-white/10 hover:bg-white/20 px-3 py-1.5 text-xs"
                      title={t("knowledge.exportTip")}
                    >
                      {t("knowledge.export")}
                    </a>
                  </div>
                </div>

                {oregano && (
                  <div className="mt-3 rounded-lg bg-black/30 border border-white/10 p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-lg font-bold">
                        {oregano.score >= 80 ? "🟢" : oregano.score >= 50 ? "🟡" : "🔴"}
                      </span>
                      <span className="text-2xl font-bold">{oregano.score}</span>
                      <span className="text-xs text-white/40">{t("knowledge.confidence")}</span>
                    </div>
                    <p className="text-xs text-white/50 mb-1">
                      {oregano.passed} {t("knowledge.of")} {oregano.total} {t("knowledge.testsPassed")} · {oregano.hallucinations} {t("knowledge.hallucinations")}
                    </p>
                    {oregano.details.length > 0 && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-xs text-white/40">{t("knowledge.detail")}</summary>
                        <ul className="mt-1 flex flex-col gap-1">
                          {oregano.details.map((det, i) => (
                            <li key={i} className={`text-xs ${det.passed ? "text-emerald-400" : "text-red-400"}`}>
                              {det.passed ? "✓" : "✗"} {det.query}
                              {!det.passed && det.forbidden_found.length > 0 && (
                                <span className="text-white/30"> — {t("knowledge.termsHalled")}: {det.forbidden_found.join(", ")}</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
