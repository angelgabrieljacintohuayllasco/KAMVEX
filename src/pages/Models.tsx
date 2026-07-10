import { useEffect, useMemo, useRef, useState } from "react";
import { Search, ExternalLink, Download, Pause, Play, X, ChevronDown } from "lucide-react";
import {
  llamaReady,
  llamaStart,
  llamaStop,
  llamaEnsureBinary,
  autotuneFlags,
  inferenceConnect,
  inferenceDisconnect,
  inferenceStatus,
  downloadHubModel,
  subscribeHubDownload,
  cancelHubDownload,
  pauseHubDownload,
  resumeHubDownload,
  type Prescription,
  type DownloadProgress,
} from "../api/client";
import { Badge, Button, Card, Field, Select, inputClass } from "../components/ui";
import { useI18n } from "../i18n";
import {
  ALL_MODELS,
  PROVIDERS,
  getProvider,
  searchModels,
  applyFilters,
  sortModels,
  catalogStats,
  type CatalogModel,
  type CatalogFilters,
  type SortKey,
  type ModelCapability,
  type ModelType,
  type SizeCategory,
} from "../catalog";

const PRESETS = ["eco", "balanced", "max"] as const;

const SIZE_OPTIONS: { value: SizeCategory | ""; label: string }[] = [
  { value: "", label: "" },
  { value: "ultralight", label: "< 1 GB" },
  { value: "light", label: "1-3 GB" },
  { value: "medium", label: "3-6 GB" },
  { value: "large", label: "6-10 GB" },
  { value: "xl", label: "> 10 GB" },
];

function formatSize(sizeMb: number): string {
  if (sizeMb >= 1000) return `${(sizeMb / 1000).toFixed(sizeMb % 1000 === 0 ? 0 : 1)} GB`;
  return `${sizeMb} MB`;
}

function capBadgeTone(cap: ModelCapability): "accent" | "success" | "warning" | "neutral" | "danger" {
  switch (cap) {
    case "chat": return "neutral";
    case "tools": return "accent";
    case "vision": return "success";
    case "reasoning": return "warning";
    case "code": return "accent";
    case "embedding": return "danger";
  }
}

function sizeTone(cat?: SizeCategory): "success" | "accent" | "warning" | "danger" | "neutral" {
  switch (cat) {
    case "ultralight": return "success";
    case "light": return "accent";
    case "medium": return "warning";
    case "large": return "danger";
    case "xl": return "danger";
    default: return "neutral";
  }
}

export default function Models({ onModelsChanged }: { onModelsChanged?: () => void }) {
  const { t } = useI18n();

  // ── Local engine state ──
  const [modelPath, setModelPath] = useState<string | null>(null);
  const [modelSizeMb, setModelSizeMb] = useState<number>(4000);
  const [preset, setPreset] = useState<string>("balanced");
  const [draftModelPath, setDraftModelPath] = useState<string | null>(null);
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [binaryReady, setBinaryReady] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // ── Catalog state ──
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<CatalogFilters>({});
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [downloads, setDownloads] = useState<Record<string, { downloadId: string; progress: DownloadProgress }>>({});
  const unsubsRef = useRef<Record<string, () => void>>({});
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    inferenceStatus().then((s) => setRunning(s.connected)).catch(() => {});
  }, []);

  // ── Filtered + sorted catalog ──
  const catalog = useMemo(() => {
    let result = searchModels(ALL_MODELS, query);
    result = applyFilters(result, filters);
    return sortModels(result, sortKey);
  }, [query, filters, sortKey]);

  const localModels = useMemo(() => catalog.filter((m) => getProvider(m.provider)?.kind === "local"), [catalog]);
  const remoteModels = useMemo(() => catalog.filter((m) => getProvider(m.provider)?.kind === "remote"), [catalog]);

  const stats = catalogStats();
  const hasFilters = !!(filters.provider || filters.type || filters.capability || filters.size);

  const typeOptions = useMemo(() => [
    { value: "", label: t("catalog.allTypes") },
    { value: "chat", label: t("catalog.type.chat") },
    { value: "code", label: t("catalog.type.code") },
    { value: "reasoning", label: t("catalog.type.reasoning") },
    { value: "vision", label: t("catalog.type.vision") },
    { value: "multimodal", label: t("catalog.type.multimodal") },
    { value: "embedding", label: t("catalog.type.embedding") },
  ], [t]);

  const capOptions = useMemo(() => [
    { value: "", label: t("catalog.allCaps") },
    { value: "chat", label: t("catalog.cap.chat") },
    { value: "tools", label: t("catalog.cap.tools") },
    { value: "vision", label: t("catalog.cap.vision") },
    { value: "reasoning", label: t("catalog.cap.reasoning") },
    { value: "code", label: t("catalog.cap.code") },
    { value: "embedding", label: t("catalog.cap.embedding") },
  ], [t]);

  const sizeOptions = useMemo(() => [
    { value: "", label: t("catalog.allSizes") },
    ...SIZE_OPTIONS.filter((o) => o.value),
  ], [t]);

  const sortOptions = useMemo(() => [
    { value: "name", label: t("catalog.sort.name") },
    { value: "size", label: t("catalog.sort.size") },
    { value: "provider", label: t("catalog.sort.provider") },
  ], [t]);

  // ── Local engine actions ──
  async function pickModel() {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ multiple: false, filters: [{ name: "GGUF", extensions: ["gguf"] }] });
    if (typeof selected === "string") {
      setModelPath(selected);
      setBinaryReady(false);
      setPrescription(null);
    }
  }

  async function pickDraftModel() {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ multiple: false, filters: [{ name: "GGUF", extensions: ["gguf"] }] });
    if (typeof selected === "string") setDraftModelPath(selected);
  }

  async function computeTune() {
    if (!modelPath) return;
    setBusy(true); setError(null);
    try {
      const p = await autotuneFlags(modelSizeMb, preset);
      setPrescription(p);
      setBinaryReady(false);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function ensureBinary() {
    setDownloading(true); setError(null);
    try {
      await llamaEnsureBinary(prescription?.backend ?? "cpu");
      setBinaryReady(true);
    } catch (e) { setError(String(e)); }
    finally { setDownloading(false); }
  }

  async function start() {
    if (!modelPath || !prescription) return;
    setBusy(true); setError(null);
    try {
      const flags = [
        "-ngl", String(prescription.ngl), "-t", String(prescription.threads),
        "-c", String(prescription.ctx), "-b", String(prescription.batch),
        "-ub", String(prescription.batch), "-ctk", prescription.ctk, "-ctv", prescription.ctv,
        "--flash-attn", prescription.flash_attn ? "on" : "off",
        ...(prescription.mlock ? ["--mlock"] : []),
        ...(draftModelPath ? ["-md", draftModelPath] : []),
      ];
      const portStr = await llamaStart(modelPath, flags);
      const port = Number(portStr);
      let ready = false;
      for (let i = 0; i < 60; i++) {
        if (await llamaReady()) { ready = true; break; }
        await new Promise((r) => setTimeout(r, 500));
      }
      if (!ready) throw new Error("llama-server no respondió");
      await inferenceConnect(port);
      setRunning(true);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function stop() {
    setBusy(true);
    try { await inferenceDisconnect(); await llamaStop(); setRunning(false); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function downloadLocal(m: CatalogModel) {
    if (!m.repo || !m.file) return;
    try {
      const res = await downloadHubModel(m.repo, m.file);
      if (res.status === "already") { setModelPath(res.path ?? ""); return; }
      const dlId = res.download_id;
      if (!dlId) return;

      setDownloads((prev) => ({
        ...prev,
        [m.id]: { downloadId: dlId, progress: { status: "downloading", downloaded: 0, total: 0, pct: 0, speed_mbps: 0, error: "" } },
      }));

      const unsub = subscribeHubDownload(dlId, (p) => {
        setDownloads((prev) => {
          const cur = prev[m.id];
          if (!cur) return prev;
          return { ...prev, [m.id]: { ...cur, progress: p } };
        });
        if (p.status === "done") {
          delete unsubsRef.current[m.id];
          onModelsChanged?.();
        }
        if (p.status === "error") setError(p.error);
      });
      unsubsRef.current[m.id] = unsub;
    } catch (e) { setError(String(e)); }
  }

  async function pauseDownload(modelId: string) {
    const dl = downloads[modelId];
    if (!dl) return;
    await pauseHubDownload(dl.downloadId);
  }

  async function resumeDownload(modelId: string) {
    const dl = downloads[modelId];
    if (!dl) return;
    await resumeHubDownload(dl.downloadId);
  }

  async function cancelDownload(modelId: string) {
    const dl = downloads[modelId];
    if (!dl) return;
    await cancelHubDownload(dl.downloadId);
    unsubsRef.current[modelId]?.();
    delete unsubsRef.current[modelId];
    setDownloads((prev) => {
      const next = { ...prev };
      delete next[modelId];
      return next;
    });
  }

  function clearFilters() {
    setFilters({});
    setQuery("");
  }

  // ── Provider filter options ──
  const providerOptions = useMemo(() => [
    { value: "", label: t("catalog.allProviders") },
    ...PROVIDERS.map((p) => ({ value: p.id, label: p.name })),
  ], [t]);

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold mb-1 tracking-tight">{t("models.title")}</h1>
        <p className="text-sm text-white/40">
          {t("models.desc")} · {stats.total} {t("catalog.models")} · {stats.providers} {t("catalog.providers")}
        </p>
      </div>

      {/* Search + filter toggle */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("catalog.searchPlaceholder")}
            className={`${inputClass} rounded-xl pl-10 py-2.5`}
          />
        </div>
        <Button
          variant={showFilters || hasFilters ? "primary" : "secondary"}
          onClick={() => setShowFilters(!showFilters)}
          className="shrink-0"
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${showFilters ? "rotate-180" : ""}`} />
          {t("catalog.filters")}
          {hasFilters && <span className="ml-1 text-[10px] bg-white/20 rounded-full px-1.5">!</span>}
        </Button>
      </div>

      {/* Filter bar */}
      {showFilters && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 p-3 rounded-xl bg-white/5 border border-white/10">
          <Field label={t("catalog.provider")}>
            <Select value={filters.provider ?? ""} options={providerOptions} onChange={(v) => setFilters({ ...filters, provider: v || undefined })} />
          </Field>
          <Field label={t("catalog.type")}>
            <Select value={filters.type ?? ""} options={typeOptions} onChange={(v) => setFilters({ ...filters, type: (v as ModelType) || undefined })} />
          </Field>
          <Field label={t("catalog.capability")}>
            <Select value={filters.capability ?? ""} options={capOptions} onChange={(v) => setFilters({ ...filters, capability: (v as ModelCapability) || undefined })} />
          </Field>
          <Field label={t("catalog.size")}>
            <Select value={filters.size ?? ""} options={sizeOptions} onChange={(v) => setFilters({ ...filters, size: (v as SizeCategory) || undefined })} />
          </Field>
          <div className="col-span-2 sm:col-span-4 flex items-center justify-between">
            <Field label={t("catalog.sortBy")}>
              <Select value={sortKey} options={sortOptions} onChange={(v) => setSortKey(v as SortKey)} />
            </Field>
            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                {t("catalog.clearFilters")}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Local engine card */}
      <Card className="mb-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="font-medium mb-1">{t("models.localModel")}</h2>
            <p className="text-xs text-white/40">
              {modelPath ? modelPath : t("models.importHint")}
            </p>
          </div>
          <Button onClick={pickModel} variant="secondary">
            {modelPath ? t("models.changeModel") : t("models.importGguf")}
          </Button>
        </div>

        {modelPath && (
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label={t("models.sizeMb")}>
              <input type="number" value={modelSizeMb} onChange={(e) => setModelSizeMb(Number(e.target.value))} className={inputClass} />
            </Field>
            <Field label={t("models.preset")}>
              <Select value={preset} options={PRESETS.map((p) => ({ value: p, label: p }))} onChange={setPreset} />
            </Field>
          </div>
        )}

        {modelPath && (
          <Button onClick={computeTune} loading={busy} variant="primary" className="mt-4">
            {t("models.computeFlags")}
          </Button>
        )}

        {prescription && (
          <div className="mt-4 rounded-lg bg-black/20 border border-white/10 p-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-white/60">
              <span>backend <b className="text-white/90">{prescription.backend}</b></span>
              <span>ngl <b className="text-white/90">{prescription.ngl}</b></span>
              <span>threads <b className="text-white/90">{prescription.threads}</b></span>
              <span>ctx <b className="text-white/90">{prescription.ctx}</b></span>
              <span>KV <b className="text-white/90">{prescription.ctk}/{prescription.ctv}</b></span>
              <span>{t("models.flashAttn")} <b className="text-white/90">{prescription.flash_attn ? t("models.on") : t("models.off")}</b></span>
              <span>{t("models.mlock")} <b className="text-white/90">{prescription.mlock ? t("models.on") : t("models.off")}</b></span>
              <span>
                {t("models.specDecode")}{" "}
                <b className="text-white/90">{draftModelPath ? t("models.on") : t("models.off")}</b>
              </span>
            </div>
            {/* Speculative decoding — draft model */}
            <div className="mt-2 flex items-center gap-2">
              <Button onClick={pickDraftModel} variant="ghost" size="sm">
                {draftModelPath ? t("models.changeDraft") : t("models.addDraft")}
              </Button>
              {draftModelPath && (
                <>
                  <span className="text-[10px] text-white/40 truncate max-w-[200px]">{draftModelPath.split(/[\\/]/).pop()}</span>
                  <Button onClick={() => setDraftModelPath(null)} variant="ghost" size="sm" className="text-white/30 hover:text-red-400">
                    ✕
                  </Button>
                </>
              )}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button onClick={ensureBinary} disabled={binaryReady} loading={downloading} variant="secondary" size="sm">
                {binaryReady ? t("models.ready") : downloading ? t("models.downloading") : t("models.downloadBinary")}
              </Button>
              {!running ? (
                <Button onClick={start} disabled={!binaryReady} loading={busy} variant="success" size="sm">
                  {busy ? t("models.starting") : t("models.start")}
                </Button>
              ) : (
                <Button onClick={stop} loading={busy} variant="danger" size="sm">
                  {busy ? t("models.stopping") : t("models.stop")}
                </Button>
              )}
              {running && <Badge tone="success">{t("models.active")}</Badge>}
            </div>
          </div>
        )}
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </Card>

      {/* Catalog — Local models */}
      {localModels.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-medium">{t("catalog.localTitle")}</h2>
            <span className="text-xs text-white/40">{localModels.length} {t("catalog.models")}</span>
          </div>
          <div className="flex flex-col gap-3">
            {localModels.map((m) => (
              <ModelCard
                key={m.id}
                model={m}
                onDownload={() => downloadLocal(m)}
                dlState={downloads[m.id]?.progress}
                onPause={() => pauseDownload(m.id)}
                onResume={() => resumeDownload(m.id)}
                onCancel={() => cancelDownload(m.id)}
                t={t}
              />
            ))}
          </div>
        </section>
      )}

      {/* Catalog — Remote models */}
      {remoteModels.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-medium">{t("catalog.remoteTitle")}</h2>
            <span className="text-xs text-white/40">{remoteModels.length} {t("catalog.models")}</span>
          </div>
          <div className="flex flex-col gap-3">
            {remoteModels.map((m) => (
              <ModelCard key={m.id} model={m} t={t} />
            ))}
          </div>
        </section>
      )}

      {/* Empty state */}
      {catalog.length === 0 && (
        <div className="text-center py-12 text-white/40">
          <p className="text-sm">{t("models.noResults")}</p>
          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="mt-2">
              {t("catalog.clearFilters")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Model card component ──

function formatSpeed(mbps: number): string {
  if (mbps >= 1) return `${mbps.toFixed(1)} MB/s`;
  return `${(mbps * 1000).toFixed(0)} KB/s`;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${(bytes / 1e3).toFixed(0)} KB`;
}

function ModelCard({
  model: m,
  onDownload,
  dlState,
  onPause,
  onResume,
  onCancel,
  t,
}: {
  model: CatalogModel;
  onDownload?: () => void;
  dlState?: DownloadProgress;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  t: (key: string) => string;
}) {
  const provider = getProvider(m.provider);
  const isLocal = provider?.kind === "local";
  const isActive = dlState && (dlState.status === "downloading" || dlState.status === "paused");

  return (
    <Card hover>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-white/90">{m.name}</h3>
            {m.developer && <span className="text-xs text-white/40">{m.developer}</span>}
            {m.params && <Badge>{m.params}</Badge>}
            {m.sizeMb && <Badge tone={sizeTone(m.sizeCategory)}>{formatSize(m.sizeMb)}</Badge>}
            {m.quant && <Badge>GGUF · {m.quant}</Badge>}
            {m.contextK && <Badge>{m.contextK}K ctx</Badge>}
          </div>
          {m.description && <p className="text-sm text-white/50 mt-1">{m.description}</p>}
          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
            <Badge tone="neutral">{provider?.name ?? m.provider}</Badge>
            {m.capabilities.map((cap) => (
              <Badge key={cap} tone={capBadgeTone(cap)}>{cap}</Badge>
            ))}
            {m.needsMmproj && <Badge tone="warning">mmproj</Badge>}
            {!isLocal && <Badge tone="neutral">{t("catalog.pluggable")}</Badge>}
          </div>

          {/* Progress bar */}
          {isActive && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-[10px] text-white/50 mb-1">
                <span>
                  {dlState.status === "paused" ? t("models.paused") : t("models.downloading")}
                  {" "}{dlState.pct}%
                </span>
                <span>
                  {formatBytes(dlState.downloaded)}{dlState.total > 0 && ` / ${formatBytes(dlState.total)}`}
                  {dlState.status === "downloading" && dlState.speed_mbps > 0 && ` · ${formatSpeed(dlState.speed_mbps)}`}
                </span>
              </div>
              <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${dlState.status === "paused" ? "bg-yellow-500" : "bg-accent"}`}
                  style={{ width: `${dlState.pct}%` }}
                />
              </div>
            </div>
          )}
        </div>
        <div className="shrink-0 flex flex-col gap-2 items-end">
          {isLocal && isActive ? (
            <div className="flex items-center gap-1.5">
              {dlState.status === "downloading" ? (
                <Button onClick={onPause} variant="secondary" size="sm" className="rounded-full" title={t("models.pause")}>
                  <Pause className="h-3.5 w-3.5" />
                </Button>
              ) : (
                <Button onClick={onResume} variant="success" size="sm" className="rounded-full" title={t("models.resume")}>
                  <Play className="h-3.5 w-3.5" />
                </Button>
              )}
              <Button onClick={onCancel} variant="danger" size="sm" className="rounded-full" title={t("models.cancel")}>
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          ) : isLocal && onDownload && (!dlState || dlState.status === "cancelled" || dlState.status === "error") ? (
            <Button
              onClick={onDownload}
              variant="secondary"
              size="sm"
              className="rounded-full"
            >
              <Download className="h-3.5 w-3.5" />
              {t("models.download")}
            </Button>
          ) : dlState?.status === "done" ? (
            <Badge tone="success">{t("models.downloaded")}</Badge>
          ) : null}
          {provider?.exploreUrl && (
            <a
              href={provider.exploreUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-white/30 hover:text-accent flex items-center gap-1 transition-colors"
            >
              <ExternalLink className="h-3 w-3" />
              {t("catalog.explore")}
            </a>
          )}
        </div>
      </div>
    </Card>
  );
}
