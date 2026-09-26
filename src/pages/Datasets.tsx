import { useCallback, useEffect, useState } from "react";
import { FileText, Settings2, Trash2 } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  Dataset,
  pickJsonFile,
  pickFile,
  startBuild,
  startBuildText,
  streamBuild,
  runOreganoTest,
  exportDatasetUrl,
  datasetSummary,
  deleteDataset,
  embeddingsStatus,
  embeddingsSetup,
  llamaEnsureBinary,
  subscribeHubDownload,
  BuildEvent,
  OreganoResult,
  type EmbeddingsStatus,
} from "../api/client";
import { Badge, Button, Card, Field, Modal, Select, inputClass } from "../components/ui";
import DatasetCatalog from "../components/DatasetCatalog";
import { rebuildDataset } from "../api/client";
import { useI18n } from "../i18n";
import { errorMessage } from "../api/errors";

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
  const [summaryOpen, setSummaryOpen] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<Record<string, string>>({});
  const [summaryBusy, setSummaryBusy] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [manageOpen, setManageOpen] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [embed, setEmbed] = useState<EmbeddingsStatus | null>(null);
  const [embedBusy, setEmbedBusy] = useState(false);
  const [embedPct, setEmbedPct] = useState<number | null>(null);
  const [rebuilding, setRebuilding] = useState<string | null>(null);
  const [rebuildProgress, setRebuildProgress] = useState<BuildEvent | null>(null);

  async function rebuild(datasetName: string) {
    setRebuilding(datasetName);
    setError(null);
    try {
      const { job_id } = await rebuildDataset(datasetName, profile);
      await streamBuild(job_id, (e) => setRebuildProgress(e));
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRebuilding(null);
      setRebuildProgress(null);
    }
  }

  const refreshEmbed = useCallback(() => {
    embeddingsStatus().then(setEmbed).catch(() => setEmbed(null));
  }, []);

  useEffect(() => {
    refreshEmbed();
  }, [refreshEmbed]);

  /** Download the llama.cpp CPU engine (Rust) + the MiniLM GGUF (sidecar) if missing. */
  async function setupEmbeddings() {
    setEmbedBusy(true);
    setError(null);
    setEmbedPct(null);
    try {
      await llamaEnsureBinary("cpu");
      const res = await embeddingsSetup();
      if (res.status === "started" && res.download_id) {
        await new Promise<void>((resolve, reject) => {
          subscribeHubDownload(res.download_id!, (p) => {
            setEmbedPct(p.pct);
            if (p.status === "done") resolve();
            else if (p.status === "error") reject(new Error(p.error));
            else if (p.status === "cancelled") reject(new Error("cancelled"));
          });
        });
      }
      refreshEmbed();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setEmbedBusy(false);
      setEmbedPct(null);
    }
  }

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
    const selected = await pickFile("PDF", ["pdf"]);
    if (selected) {
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
    setProgress({ stage: "start", pct: 0, msg: t("knowledge.starting") });
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
      refreshEmbed();
    } catch (e) {
      setError(errorMessage(e));
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
      setError(errorMessage(e));
    } finally {
      setOreganoBusy(null);
    }
  }

  async function openSummary(datasetName: string) {
    setSummaryOpen(datasetName);
    if (summaries[datasetName]) return;
    setSummaryBusy(datasetName);
    setSummaryError(null);
    try {
      const s = await datasetSummary(datasetName);
      setSummaries((prev) => ({ ...prev, [datasetName]: s }));
    } catch (e) {
      setSummaryError(errorMessage(e));
    } finally {
      setSummaryBusy(null);
    }
  }

  async function exportDataset(datasetName: string) {
    const url = await exportDatasetUrl(datasetName);
    try {
      await openUrl(url);
    } catch {
      window.open(url, "_blank");
    }
  }

  async function removeDataset(datasetName: string) {
    setDeleting(true);
    setError(null);
    try {
      await deleteDataset(datasetName);
      setOreganoResults((prev) => {
        const next = { ...prev };
        delete next[datasetName];
        return next;
      });
      setManageOpen(null);
      setConfirmDelete(false);
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setDeleting(false);
    }
  }

  const embedReady = embed?.ready ?? true;

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1 tracking-tight">{t("knowledge.title")}</h1>
      <p className="text-sm text-white/40 mb-4">{t("knowledge.desc")}</p>

      {embed && !embedReady && (
        <Card className="mb-4 border-amber-500/30">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 className="font-medium text-amber-300">{t("knowledge.embedNotReady")}</h2>
              <p className="text-xs text-white/50 mt-1">{t("knowledge.embedHint")}</p>
            </div>
            <Button onClick={setupEmbeddings} loading={embedBusy} variant="primary">
              {embedBusy
                ? `${t("knowledge.embedPreparing")}${embedPct != null ? ` ${embedPct}%` : ""}`
                : t("knowledge.embedSetup")}
            </Button>
          </div>
        </Card>
      )}

      <DatasetCatalog onChanged={onChanged} embedReady={embedReady} />

      <Card className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Button
            onClick={() => setBuildMode("file")}
            variant={buildMode === "file" ? "primary" : "secondary"}
            size="sm"
          >
            {t("knowledge.fileMode")}
          </Button>
          <Button
            onClick={() => setBuildMode("text")}
            variant={buildMode === "text" ? "primary" : "secondary"}
            size="sm"
          >
            {t("knowledge.textMode")}
          </Button>
          {embed && embedReady && (
            <span className="ml-auto text-[10px] text-white/30">
              {t("knowledge.embedBackend")}: {embed.backend}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-3">
          {buildMode === "file" ? (
            <>
              <Button onClick={pick} variant="primary" className="self-start">
                {jsonPath ? t("knowledge.changeFile") : t("knowledge.pickFile")}
              </Button>
              {jsonPath && <p className="text-xs text-white/50 break-all">{jsonPath}</p>}
            </>
          ) : (
            <div className="flex flex-col gap-2">
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={6}
                placeholder={t("knowledge.textPlaceholder")}
                className={`${inputClass} resize-none`}
              />
              <Button onClick={pickPdf} variant="secondary" size="sm" className="self-start">
                {pdfPath ? t("knowledge.changePdf") : t("knowledge.importPdf")}
              </Button>
              {pdfPath && <p className="text-xs text-white/50 break-all">{pdfPath}</p>}
            </div>
          )}

          <Field label={t("knowledge.name")}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="mi-dataset"
              className={inputClass}
            />
          </Field>

          <Field label={t("knowledge.profile")}>
            <Select
              value={profile}
              options={PROFILES.map((p) => ({ value: p, label: p }))}
              onChange={setProfile}
            />
          </Field>

          <Button
            disabled={!name || !embedReady || (buildMode === "file" ? !jsonPath : !rawText.trim() && !pdfPath)}
            loading={busy}
            onClick={build}
            variant="success"
            className="self-start"
          >
            {busy ? t("knowledge.building") : t("knowledge.buildBtn")}
          </Button>

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
          {error && <p className="text-sm text-red-400 whitespace-pre-wrap">{error}</p>}
        </div>
      </Card>

      <h2 className="font-medium mb-2">{t("knowledge.built")}</h2>
      {datasets.length === 0 ? (
        <p className="text-sm text-white/40">{t("knowledge.empty")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {datasets.map((d) => {
            const oregano = oreganoResults[d.name];
            return (
              <Card key={d.name}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <span className="font-medium text-base">{d.name}</span>
                    <p className="text-xs text-white/40 mt-1">
                      {d.source_doc && (
                        <>
                          📄 {d.source_doc}
                          {d.n_pages ? ` · ${d.n_pages} ${t("knowledge.pages")}` : ""} ·{" "}
                        </>
                      )}
                      {d.n_records} {t("knowledge.records")} · {t("knowledge.profileLabel")} {d.profile} · {d.dim ?? "?"} {t("knowledge.dim")}
                      {d.embedding_backend && <> · {d.embedding_backend}</>}
                    </p>
                  </div>
                  <div className="flex gap-1.5 flex-wrap">
                    {d.source_doc && (
                      <Button
                        onClick={() => openSummary(d.name)}
                        variant="secondary"
                        size="sm"
                        icon={<FileText className="h-3.5 w-3.5" />}
                        title={t("knowledge.summaryTip")}
                      >
                        {t("knowledge.summary")}
                      </Button>
                    )}
                    <Button
                      onClick={() => { setManageOpen(d.name); setConfirmDelete(false); }}
                      variant="secondary"
                      size="sm"
                      icon={<Settings2 className="h-3.5 w-3.5" />}
                      title={t("knowledge.manageTip")}
                    >
                      {t("knowledge.manage")}
                    </Button>
                    <Button
                      onClick={() => runOregano(d.name)}
                      loading={oreganoBusy === d.name}
                      variant="secondary"
                      size="sm"
                      title={t("knowledge.oreganoTip")}
                    >
                      {oreganoBusy === d.name ? t("knowledge.auditing") : t("knowledge.oregano")}
                    </Button>
                    <Button
                      onClick={() => exportDataset(d.name)}
                      variant="secondary"
                      size="sm"
                      title={t("knowledge.exportTip")}
                    >
                      {t("knowledge.export")}
                    </Button>
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
              </Card>
            );
          })}
        </div>
      )}

      <Modal open={summaryOpen !== null} onClose={() => setSummaryOpen(null)} title={t("knowledge.summary")}>
        {summaryBusy === summaryOpen ? (
          <p className="text-sm text-white/40">{t("knowledge.summarizing")}</p>
        ) : summaryError ? (
          <p className="text-sm text-red-400">{summaryError}</p>
        ) : (
          <p className="text-sm text-white/80 whitespace-pre-wrap leading-relaxed">
            {summaryOpen ? summaries[summaryOpen] : ""}
          </p>
        )}
      </Modal>

      <Modal open={manageOpen !== null} onClose={() => setManageOpen(null)} title={manageOpen ?? ""}>
        {(() => {
          const d = datasets.find((x) => x.name === manageOpen);
          if (!d) return null;
          return (
            <div className="flex flex-col gap-1.5 text-sm">
              {d.source_doc && <Row k={t("knowledge.sourceDoc")} v={d.source_doc} />}
              {d.n_pages !== undefined && <Row k={t("knowledge.pages")} v={String(d.n_pages)} />}
              <Row k={t("knowledge.records")} v={String(d.n_records)} />
              <Row k={t("knowledge.profileLabel")} v={d.profile} />
              <Row k={t("knowledge.dim")} v={String(d.dim ?? "?")} />
              {d.embedding_backend && (
                <Row k={t("knowledge.builtWith")} v={`${d.embedding_backend}${d.embedding_model ? ` · ${d.embedding_model}` : ""}`} />
              )}
              <Row k={t("knowledge.path")} v={d.path} />
              {d.has_records && (
                <div className="pt-3">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={rebuilding === d.name}
                    onClick={() => rebuild(d.name)}
                    title={t("knowledge.rebuildTip")}
                  >
                    {rebuilding === d.name ? t("knowledge.rebuilding") : t("knowledge.rebuild")}
                  </Button>
                  {rebuilding === d.name && rebuildProgress && (
                    <p className="text-xs text-white/50 mt-1">{rebuildProgress.stage} — {rebuildProgress.msg} ({rebuildProgress.pct}%)</p>
                  )}
                </div>
              )}
              <div className="flex items-center gap-2 pt-3">
                {confirmDelete ? (
                  <>
                    <Button variant="danger" size="sm" loading={deleting} onClick={() => removeDataset(d.name)}>
                      {deleting ? t("knowledge.deleting") : t("common.confirm")}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                      {t("common.cancel")}
                    </Button>
                  </>
                ) : (
                  <Button variant="ghost" size="sm" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setConfirmDelete(true)} className="text-red-300">
                    {t("knowledge.deleteDataset")}
                  </Button>
                )}
                {embed && <Badge tone="neutral">{embed.backend}</Badge>}
              </div>
            </div>
          );
        })()}
      </Modal>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b border-white/5 py-2">
      <span className="text-white/50">{k}</span>
      <span className="font-medium text-right break-all ml-4">{v}</span>
    </div>
  );
}
