import { useCallback, useEffect, useState } from "react";
import { Cpu, FolderOpen, Trash2 } from "lucide-react";
import {
  autotuneFlags,
  deleteLocalModel,
  inferenceDisconnect,
  listLocalModels,
  llamaBinaryPresent,
  llamaStatus,
  llamaStop,
  modelInfo,
  pickFile,
  startEngine,
  type GgufInfo,
  type LlamaStatus,
  type LocalModel,
  type Prescription,
} from "../api/client";
import { Badge, Button, Card, Field, Select, inputClass } from "./ui";
import { useI18n } from "../i18n";

const PRESETS = ["eco", "balanced", "max"] as const;

function fmtMb(mb: number): string {
  return mb >= 1000 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/**
 * Local inference engine: pick / list downloaded GGUFs, read their metadata,
 * auto-tune a prescription for this hardware and start/stop llama-server.
 * The selected model is shared with the chat top bar (App owns it).
 */
export default function EngineCard({
  selectedModel,
  onSelectModel,
  refreshToken,
  onModelsChanged,
}: {
  selectedModel: string | null;
  onSelectModel: (path: string | null) => void;
  /** Bump to force a reload of the downloaded-models list (after a download finishes). */
  refreshToken: number;
  onModelsChanged?: () => void;
}) {
  const { t } = useI18n();
  const [models, setModels] = useState<LocalModel[]>([]);
  const [info, setInfo] = useState<GgufInfo | null>(null);
  const [infoLoading, setInfoLoading] = useState(false);
  const [preset, setPreset] = useState<string>("balanced");
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  // Manual overrides on top of the automatic prescription (README promise: every flag editable).
  const [overrides, setOverrides] = useState<Partial<Prescription>>({});
  const effective: Prescription | null = prescription ? { ...prescription, ...overrides } : null;
  const modified = Object.keys(overrides).length > 0;
  const [draftModelPath, setDraftModelPath] = useState<string | null>(null);
  const [binaryReady, setBinaryReady] = useState<boolean | null>(null);
  const [status, setStatus] = useState<LlamaStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const reloadModels = useCallback(() => {
    listLocalModels().then(setModels).catch(() => {});
  }, []);

  useEffect(() => {
    reloadModels();
  }, [reloadModels, refreshToken]);

  useEffect(() => {
    const tick = () => llamaStatus().then(setStatus).catch(() => {});
    tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, []);

  // Model changed → read GGUF metadata, then auto-tune for the current preset.
  useEffect(() => {
    setInfo(null);
    setPrescription(null);
    setError(null);
    if (!selectedModel) return;
    let cancelled = false;
    setInfoLoading(true);
    modelInfo(selectedModel)
      .then((i) => { if (!cancelled) setInfo(i); })
      .catch(() => { if (!cancelled) setInfo(null); })
      .finally(() => { if (!cancelled) setInfoLoading(false); });
    return () => { cancelled = true; };
  }, [selectedModel]);

  useEffect(() => {
    if (!selectedModel) return;
    let cancelled = false;
    autotuneFlags({ modelPath: selectedModel, preset })
      .then((p) => { if (!cancelled) setPrescription(p); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [selectedModel, preset]);

  const effectiveBackend = effective?.backend ?? null;
  useEffect(() => {
    if (!effectiveBackend) { setBinaryReady(null); return; }
    llamaBinaryPresent(effectiveBackend).then(setBinaryReady).catch(() => setBinaryReady(false));
  }, [effectiveBackend]);

  useEffect(() => {
    setOverrides({});
  }, [selectedModel, preset]);

  function setField<K extends keyof Prescription>(key: K, value: Prescription[K]) {
    setOverrides((o) => ({ ...o, [key]: value }));
  }

  async function importGguf() {
    const path = await pickFile("GGUF", ["gguf"]);
    if (path) onSelectModel(path);
  }

  async function pickDraft() {
    const path = await pickFile("GGUF", ["gguf"]);
    if (path) setDraftModelPath(path);
  }

  async function removeModel(m: LocalModel) {
    setError(null);
    try {
      await deleteLocalModel(m.file);
      if (selectedModel === m.path) onSelectModel(null);
      setConfirmDelete(null);
      reloadModels();
      onModelsChanged?.();
    } catch (e) {
      setError(String(e));
    }
  }

  async function start() {
    if (!selectedModel || !effective) return;
    setBusy(true);
    setError(null);
    try {
      const res = await startEngine(selectedModel, preset, {
        prescription: { ...effective },
        draftModel: draftModelPath,
        onStage: (s) => setStage(s),
      });
      setPrescription({ ...res.prescription, ...overrides });
      setBinaryReady(true);
      setStatus(await llamaStatus());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      setStage(null);
    }
  }

  async function stop() {
    setBusy(true);
    try {
      await inferenceDisconnect();
      await llamaStop();
      setStatus(await llamaStatus());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const running = !!status?.running;
  const runningThisModel = running && status?.model === selectedModel;

  return (
    <Card className="mb-6">
      {/* Downloaded models */}
      <div className="flex items-start justify-between gap-4 flex-wrap mb-3">
        <div>
          <h2 className="font-medium mb-1">{t("engine.downloaded")}</h2>
          <p className="text-xs text-white/40">{t("models.importHint")}</p>
        </div>
        <Button onClick={importGguf} variant="secondary" icon={<FolderOpen className="h-4 w-4" />}>
          {t("models.importGguf")}
        </Button>
      </div>

      {models.length === 0 ? (
        <p className="text-sm text-white/40 mb-4">{t("engine.noneDownloaded")}</p>
      ) : (
        <div className="flex flex-col gap-1.5 mb-4">
          {models.map((m) => {
            const active = m.path === selectedModel;
            return (
              <div
                key={m.path}
                className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-sm ${
                  active ? "border-accent/40 bg-accent/10" : "border-white/10 bg-black/20"
                }`}
              >
                <Cpu className="h-4 w-4 text-white/40 shrink-0" />
                <span className="flex-1 min-w-0 truncate">{m.name}</span>
                <Badge>{fmtMb(m.size_mb)}</Badge>
                {running && status?.model === m.path && <Badge tone="success">{t("engine.inUse")}</Badge>}
                {!active && (
                  <Button size="sm" variant="ghost" onClick={() => onSelectModel(m.path)}>
                    {t("engine.use")}
                  </Button>
                )}
                {confirmDelete === m.file ? (
                  <>
                    <Button size="sm" variant="danger" onClick={() => removeModel(m)}>
                      {t("common.confirm")}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(null)}>
                      {t("common.cancel")}
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    title={t("common.delete")}
                    onClick={() => setConfirmDelete(m.file)}
                    icon={<Trash2 className="h-3.5 w-3.5" />}
                    disabled={running && status?.model === m.path}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Selected model */}
      {selectedModel && (
        <div className="rounded-lg bg-black/20 border border-white/10 p-3">
          <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
            <div className="min-w-0">
              <h3 className="font-medium truncate">{fileName(selectedModel)}</h3>
              <p className="text-[11px] text-white/30 truncate">{selectedModel}</p>
            </div>
            <Field label={t("models.preset")} hint={t("engine.presetHint")}>
              <Select
                className="w-40"
                value={preset}
                options={PRESETS.map((p) => ({ value: p, label: t(`models.preset.${p}`) }))}
                onChange={setPreset}
              />
            </Field>
          </div>

          {/* GGUF metadata */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-white/60 mb-3">
            {infoLoading && <span className="col-span-4 text-white/40">{t("engine.readingInfo")}</span>}
            {info && (
              <>
                <span>{t("engine.arch")} <b className="text-white/90">{info.architecture || "?"}</b></span>
                <span>{t("engine.layers")} <b className="text-white/90">{info.block_count ?? "?"}</b></span>
                <span>{t("engine.ctxTrain")} <b className="text-white/90">{info.context_length ?? "?"}</b></span>
                <span>{t("engine.quant")} <b className="text-white/90">{info.quant || "?"}</b></span>
                <span>{t("engine.size")} <b className="text-white/90">{fmtMb(info.size_mb)}</b></span>
                {info.expert_count && info.expert_count > 1 && (
                  <span><Badge tone="accent">{t("engine.moe")} ×{info.expert_count}</Badge></span>
                )}
              </>
            )}
          </div>

          {/* Prescription (auto + overrides) */}
          {effective && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-white/60">
                <span>backend <b className="text-white/90">{effective.backend}</b></span>
                <span>
                  ngl <b className="text-white/90">{effective.ngl}</b>
                  {effective.total_layers != null && !("ngl" in overrides) && (
                    <span className="text-white/40"> ({effective.offloaded_layers ?? 0}/{effective.total_layers} {t("engine.offload")})</span>
                  )}
                </span>
                <span>threads <b className="text-white/90">{effective.threads}</b></span>
                <span>ctx <b className="text-white/90">{effective.ctx}</b></span>
                <span>KV <b className="text-white/90">{effective.ctk}/{effective.ctv}</b></span>
                <span>{t("models.flashAttn")} <b className="text-white/90">{effective.flash_attn ? t("models.on") : t("models.off")}</b></span>
                <span>{t("models.mlock")} <b className="text-white/90">{effective.mlock ? t("models.on") : t("models.off")}</b></span>
                <span>{t("models.specDecode")} <b className="text-white/90">{draftModelPath ? t("models.on") : t("models.off")}</b>{modified && <Badge tone="warning" className="ml-2">{t("engine.modified")}</Badge>}</span>
              </div>
              {effective.warnings.length > 0 && (
                <ul className="mt-2 flex flex-col gap-0.5 text-[11px] text-amber-300/90">
                  {effective.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
                </ul>
              )}

              {/* Advanced flags editor */}
              <details className="mt-3 rounded-lg border border-white/10 bg-black/20 p-2.5" data-testid="advanced-flags">
                <summary className="cursor-pointer text-xs text-white/50 hover:text-white/70">
                  {t("engine.advanced")} <span className="text-white/30">— {t("engine.advancedHint")}</span>
                </summary>
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <Field label={t("engine.field.backend")}>
                    <Select
                      value={effective.backend}
                      options={["cpu", "vulkan", "cuda"].map((b) => ({ value: b, label: b }))}
                      onChange={(v) => setField("backend", v)}
                    />
                  </Field>
                  <Field label={t("engine.field.ngl")}>
                    <input type="number" min={0} max={999} value={effective.ngl} onChange={(e) => setField("ngl", Math.max(0, Math.min(999, Number(e.target.value) || 0)))} className={inputClass} />
                  </Field>
                  <Field label={t("engine.field.threads")}>
                    <input type="number" min={1} max={128} value={effective.threads} onChange={(e) => setField("threads", Math.max(1, Number(e.target.value) || 1))} className={inputClass} />
                  </Field>
                  <Field label={t("engine.field.ctx")}>
                    <input type="number" min={256} step={256} value={effective.ctx} onChange={(e) => setField("ctx", Math.max(256, Number(e.target.value) || 256))} className={inputClass} />
                  </Field>
                  <Field label={t("engine.field.batch")}>
                    <input type="number" min={32} step={32} value={effective.batch} onChange={(e) => setField("batch", Math.max(32, Number(e.target.value) || 32))} className={inputClass} />
                  </Field>
                  <Field label={t("engine.field.kv")}>
                    <Select
                      value={effective.ctk}
                      options={["q4_0", "q8_0", "f16"].map((k) => ({ value: k, label: k }))}
                      onChange={(v) => { setField("ctk", v); setField("ctv", v); }}
                    />
                  </Field>
                  <label className="flex items-center gap-2 text-white/70 mt-5">
                    <input type="checkbox" checked={effective.flash_attn} onChange={(e) => setField("flash_attn", e.target.checked)} className="accent-accent" />
                    {t("engine.field.flash")}
                  </label>
                  <label className="flex items-center gap-2 text-white/70 mt-5">
                    <input type="checkbox" checked={effective.mlock} onChange={(e) => setField("mlock", e.target.checked)} className="accent-accent" />
                    {t("engine.field.mlock")}
                  </label>
                </div>
                {modified && (
                  <Button variant="ghost" size="sm" className="mt-2" onClick={() => setOverrides({})}>
                    {t("engine.reset")}
                  </Button>
                )}
              </details>
              <div className="mt-2 flex items-center gap-2 flex-wrap">
                <Button onClick={pickDraft} variant="ghost" size="sm">
                  {draftModelPath ? t("models.changeDraft") : t("models.addDraft")}
                </Button>
                {draftModelPath && (
                  <>
                    <span className="text-[10px] text-white/40 truncate max-w-[220px]">{fileName(draftModelPath)}</span>
                    <Button onClick={() => setDraftModelPath(null)} variant="ghost" size="sm" className="text-white/30 hover:text-red-400">✕</Button>
                  </>
                )}
              </div>
            </>
          )}

          {/* Actions */}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {effective && binaryReady === false && (
              <Badge tone="warning">{t("models.downloadBinary")} · {effective.backend}</Badge>
            )}
            {!runningThisModel ? (
              <Button onClick={start} disabled={!effective} loading={busy} variant="success" size="sm">
                {busy ? t("models.starting") : t("models.start")}
              </Button>
            ) : (
              <Button onClick={stop} loading={busy} variant="danger" size="sm">
                {busy ? t("models.stopping") : t("models.stop")}
              </Button>
            )}
            {stage && <span className="text-xs text-amber-300 animate-pulse">{t(`engine.stage.${stage}`)}</span>}
            {running && (
              <Badge tone="success">
                {t("engine.running")} · {status?.backend} · :{status?.port}
              </Badge>
            )}
          </div>
          {status?.log_path && (
            <p className="mt-2 text-[10px] text-white/30 truncate">{t("engine.log")}: {status.log_path}</p>
          )}
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-400 whitespace-pre-wrap">{error}</p>}
    </Card>
  );
}
