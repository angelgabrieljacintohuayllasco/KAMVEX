import { useEffect, useMemo, useState } from "react";
import {
  llamaReady,
  llamaStart,
  llamaStop,
  llamaEnsureBinary,
  autotuneFlags,
  inferenceConnect,
  inferenceDisconnect,
  inferenceStatus,
  listHubModels,
  downloadHubModel,
  type Prescription,
  type HubModel,
} from "../api/client";
import { useI18n } from "../i18n";

const PRESETS = ["eco", "balanced", "max"] as const;

function formatSize(sizeMb: number): string {
  if (sizeMb >= 1000) return `${(sizeMb / 1000).toFixed(sizeMb % 1000 === 0 ? 0 : 1)} GB`;
  return `${sizeMb} MB`;
}

function extractParams(name: string): string | null {
  const match = name.match(/(\d+\.?\d*)B/);
  return match ? `${match[1]}B` : null;
}

function getCategoryClass(cat: string): string {
  switch (cat) {
    case "ultralight": return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
    case "light": return "bg-blue-500/15 text-blue-300 border-blue-500/30";
    case "medium": return "bg-amber-500/15 text-amber-300 border-amber-500/30";
    case "large": return "bg-orange-500/15 text-orange-300 border-orange-500/30";
    case "xl": return "bg-red-500/15 text-red-300 border-red-500/30";
    default: return "bg-white/10 text-white/60 border-white/20";
  }
}

export default function Models() {
  const { t } = useI18n();
  const [modelPath, setModelPath] = useState<string | null>(null);
  const [modelSizeMb, setModelSizeMb] = useState<number>(4000);
  const [preset, setPreset] = useState<string>("balanced");
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [binaryReady, setBinaryReady] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [hubModels, setHubModels] = useState<HubModel[]>([]);
  const [hubBusy, setHubBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");

  useEffect(() => {
    inferenceStatus().then((s) => setRunning(s.connected)).catch(() => {});
    listHubModels().then(setHubModels).catch(() => {});
  }, []);

  async function pickModel() {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      multiple: false,
      filters: [{ name: "GGUF", extensions: ["gguf"] }],
    });
    if (typeof selected === "string") {
      setModelPath(selected);
      setBinaryReady(false);
      setPrescription(null);
    }
  }

  async function computeTune() {
    if (!modelPath) return;
    setBusy(true);
    setError(null);
    try {
      const p = await autotuneFlags(modelSizeMb, preset);
      setPrescription(p);
      setBinaryReady(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function ensureBinary() {
    setDownloading(true);
    setError(null);
    try {
      const backend = prescription?.backend ?? "cpu";
      await llamaEnsureBinary(backend);
      setBinaryReady(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setDownloading(false);
    }
  }

  async function start() {
    if (!modelPath || !prescription) return;
    setBusy(true);
    setError(null);
    try {
      const flags = [
        "-ngl", String(prescription.ngl),
        "-t", String(prescription.threads),
        "-c", String(prescription.ctx),
        "-b", String(prescription.batch),
        "-ub", String(prescription.batch),
        "-ctk", prescription.ctk,
        "-ctv", prescription.ctv,
        ...(prescription.flash_attn ? ["-fa"] : []),
        ...(prescription.mlock ? ["--mlock"] : []),
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
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    setBusy(true);
    try {
      await inferenceDisconnect();
      await llamaStop();
      setRunning(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const filteredModels = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return hubModels;
    return hubModels.filter((m) =>
      m.name.toLowerCase().includes(q) || m.desc.toLowerCase().includes(q)
    );
  }, [hubModels, filter]);

  return (
    <div className="p-6 max-w-4xl">
      {/* Header estilo Jan */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold mb-1">{t("models.title")}</h1>
        <p className="text-sm text-white/40">{t("models.desc")}</p>
      </div>

      {/* Barra de búsqueda */}
      <div className="relative mb-6">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30">🔎</span>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("models.search")}
          className="w-full rounded-xl bg-black/20 border border-white/10 pl-10 pr-4 py-2.5 text-sm placeholder:text-white/30 outline-none focus:border-white/30"
        />
      </div>

      {/* Modelo local */}
      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-5 mb-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="font-medium mb-1">{t("models.localModel")}</h2>
            <p className="text-xs text-white/40">
              {modelPath ? modelPath : t("models.importHint")}
            </p>
          </div>
          <button
            onClick={pickModel}
            className="rounded-lg bg-white/10 hover:bg-white/20 px-4 py-2 text-sm"
          >
            {modelPath ? t("models.changeModel") : t("models.importGguf")}
          </button>
        </div>

        {modelPath && (
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="text-sm">
              {t("models.sizeMb")}
              <input
                type="number"
                value={modelSizeMb}
                onChange={(e) => setModelSizeMb(Number(e.target.value))}
                className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
              />
            </label>
            <label className="text-sm">
              {t("models.preset")}
              <select
                value={preset}
                onChange={(e) => setPreset(e.target.value)}
                className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
              >
                {PRESETS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>
        )}

        {modelPath && (
          <button
            onClick={computeTune}
            disabled={busy}
            className="mt-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-4 py-2 text-sm"
          >
            {t("models.computeFlags")}
          </button>
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
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                onClick={ensureBinary}
                disabled={downloading || binaryReady}
                className="rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 px-4 py-2 text-xs"
              >
                {binaryReady ? t("models.ready") : downloading ? t("models.downloading") : t("models.downloadBinary")}
              </button>
              {!running ? (
                <button
                  onClick={start}
                  disabled={busy || !prescription || !binaryReady}
                  className="rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 px-4 py-2 text-xs"
                >
                  {busy ? t("models.starting") : t("models.start")}
                </button>
              ) : (
                <button
                  onClick={stop}
                  disabled={busy}
                  className="rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-40 px-4 py-2 text-xs"
                >
                  {busy ? t("models.stopping") : t("models.stop")}
                </button>
              )}
              {running && (
                <span className="rounded-full bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 text-xs text-emerald-300">
                  {t("models.active")}
                </span>
              )}
            </div>
          </div>
        )}
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </section>

      {/* HuggingFace Hub estilo Jan */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-medium">{t("models.hub")}</h2>
          <span className="text-xs text-white/40">{filteredModels.length} modelos</span>
        </div>

        {hubModels.length === 0 ? (
          <p className="text-xs text-white/40">{t("models.hubLoading")}</p>
        ) : filteredModels.length === 0 ? (
          <p className="text-xs text-white/40">{t("models.noResults")}</p>
        ) : (
          <div className="flex flex-col gap-3">
            {filteredModels.map((m) => {
              const params = extractParams(m.name);
              const slow = m.size_mb > 6000;
              return (
                <div
                  key={m.repo + m.file}
                  className="group rounded-xl border border-white/10 bg-white/[0.03] p-4 hover:bg-white/[0.06] transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-white/90">{m.name}</h3>
                        <span className="text-xs text-white/50">{formatSize(m.size_mb)}</span>
                        {slow && (
                          <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300">
                            ⚠ {t("models.mayBeSlow")}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-white/50 mt-1">{m.desc}</p>
                      <div className="flex items-center gap-2 mt-3 flex-wrap">
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] ${getCategoryClass(m.category ?? "ultralight")}`}>
                          {t(`models.cat.${m.category ?? "ultralight"}`)}
                        </span>
                        {params && (
                          <span className="rounded-full border border-white/20 bg-white/5 px-2 py-0.5 text-[10px] text-white/60">
                            {params}
                          </span>
                        )}
                        <span className="rounded-full border border-white/20 bg-white/5 px-2 py-0.5 text-[10px] text-white/60">
                          GGUF
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={async () => {
                        setHubBusy(m.file);
                        try {
                          const res = await downloadHubModel(m.repo, m.file);
                          if (res.status === "error") setError(res.error ?? "error");
                          else setModelPath(res.path ?? "");
                        } catch (e) {
                          setError(String(e));
                        } finally {
                          setHubBusy(null);
                        }
                      }}
                      disabled={hubBusy !== null}
                      className="shrink-0 rounded-full border border-white/20 bg-white/10 hover:bg-white/20 disabled:opacity-40 px-4 py-1.5 text-xs transition-colors"
                    >
                      {hubBusy === m.file ? t("models.downloading") : `${t("models.download")} · Q4`}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
