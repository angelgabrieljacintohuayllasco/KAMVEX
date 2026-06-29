import { useEffect, useState } from "react";
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

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">{t("models.title")}</h1>
      <p className="text-sm text-white/40 mb-6">
        {t("models.desc")}
      </p>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5 mb-4">
        <h2 className="font-medium mb-3">{t("models.model")}</h2>
        <button
          onClick={pickModel}
          className="rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-sm"
        >
          {modelPath ? t("models.changeModel") : t("models.importGguf")}
        </button>
        {modelPath && (
          <p className="text-xs text-white/50 break-all mt-2">{modelPath}</p>
        )}
        {modelPath && (
          <label className="block mt-3 text-sm">
            {t("models.sizeMb")}
            <input
              type="number"
              value={modelSizeMb}
              onChange={(e) => setModelSizeMb(Number(e.target.value))}
              className="mt-1 w-32 rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
            />
          </label>
        )}
      </section>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5 mb-4">
        <h2 className="font-medium mb-3">{t("models.autotune")}</h2>
        <label className="text-sm">
          {t("models.preset")}
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value)}
            className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm"
          >
            {PRESETS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <button
          onClick={computeTune}
          disabled={busy || !modelPath}
          className="mt-3 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 px-4 py-2 text-sm"
        >
          {t("models.computeFlags")}
        </button>
        {prescription && (
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-white/60">
            <span>backend: <b className="text-white/90">{prescription.backend}</b></span>
            <span>ngl: <b className="text-white/90">{prescription.ngl}</b></span>
            <span>threads: <b className="text-white/90">{prescription.threads}</b></span>
            <span>ctx: <b className="text-white/90">{prescription.ctx}</b></span>
            <span>batch: <b className="text-white/90">{prescription.batch}</b></span>
            <span>KV: <b className="text-white/90">{prescription.ctk}/{prescription.ctv}</b></span>
            <span>{t("models.flashAttn")}: <b className="text-white/90">{prescription.flash_attn ? t("models.on") : t("models.off")}</b></span>
            <span>{t("models.mlock")}: <b className="text-white/90">{prescription.mlock ? t("models.on") : t("models.off")}</b></span>
          </div>
        )}
      </section>

      {prescription && (
        <section className="rounded-xl border border-white/10 bg-white/5 p-5 mb-4">
          <h2 className="font-medium mb-3">{t("models.binary")}</h2>
          <button
            onClick={ensureBinary}
            disabled={downloading || binaryReady}
            className="rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 px-4 py-2 text-sm"
          >
            {binaryReady ? t("models.ready") : downloading ? t("models.downloading") : t("models.downloadBinary")}
          </button>
        </section>
      )}

      <section className="rounded-xl border border-white/10 bg-white/5 p-5">
        <div className="flex items-center gap-3">
          {!running ? (
            <button
              onClick={start}
              disabled={busy || !modelPath || !prescription || !binaryReady}
              className="rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 px-4 py-2 text-sm"
            >
              {busy ? t("models.starting") : t("models.start")}
            </button>
          ) : (
            <button
              onClick={stop}
              disabled={busy}
              className="rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-40 px-4 py-2 text-sm"
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
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </section>

      {/* HuggingFace Hub */}
      <section className="rounded-xl border border-white/10 bg-white/5 p-5 mt-4">
        <h2 className="font-medium mb-3">{t("models.hub")}</h2>
        {hubModels.length === 0 ? (
          <p className="text-xs text-white/40">{t("models.hubLoading")}</p>
        ) : (
          <div className="flex flex-col gap-4">
            {(["ultralight", "light", "medium", "large", "xl"] as const).map((cat) => {
              const models = hubModels.filter((m) => (m.category ?? "ultralight") === cat);
              if (models.length === 0) return null;
              return (
                <div key={cat}>
                  <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wide mb-2">
                    {t(`models.cat.${cat}`)}
                  </h3>
                  <div className="flex flex-col gap-2">
                    {models.map((m) => (
                      <div
                        key={m.repo + m.file}
                        className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-4 py-2"
                      >
                        <div>
                          <span className="text-sm font-medium">{m.name}</span>
                          <p className="text-xs text-white/40">{m.desc} · ~{m.size_mb} MB</p>
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
                          className="rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-3 py-1.5 text-xs"
                        >
                          {hubBusy === m.file ? t("models.downloading") : t("models.download")}
                        </button>
                      </div>
                    ))}
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
