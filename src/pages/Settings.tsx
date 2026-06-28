import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { detectHardware, HwInfo } from "../api/client";
import { useI18n } from "../i18n";

export default function Settings() {
  const { lang, setLang, t, theme, setTheme } = useI18n();
  const [hw, setHw] = useState<HwInfo | null>(null);
  const [port, setPort] = useState<number | null>(null);
  const [ready, setReady] = useState<boolean>(false);
  const [updateMsg, setUpdateMsg] = useState<string | null>(null);
  const [updateBusy, setUpdateBusy] = useState(false);

  useEffect(() => {
    detectHardware().then(setHw).catch(() => {});
    invoke<number>("sidecar_port").then(setPort).catch(() => {});
    invoke<boolean>("sidecar_ready").then(setReady).catch(() => {});
  }, []);

  const Row = ({ k, v }: { k: string; v: string }) => (
    <div className="flex justify-between border-b border-white/5 py-2 text-sm">
      <span className="text-white/50">{k}</span>
      <span className="font-medium">{v}</span>
    </div>
  );

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-semibold mb-4">{t("settings.title")}</h1>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5 mb-6">
        <h2 className="font-medium mb-2">{t("settings.backend")}</h2>
        <Row k={t("settings.port")} v={port ? String(port) : "…"} />
        <Row k={t("settings.status")} v={ready ? t("settings.active") : t("settings.starting")} />
      </section>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5 mb-6">
        <h2 className="font-medium mb-3">{t("settings.language")}</h2>
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setLang("es")}
            className={`rounded-lg px-4 py-2 text-sm ${lang === "es" ? "bg-indigo-600" : "bg-white/10 hover:bg-white/20"}`}
          >
            Español
          </button>
          <button
            onClick={() => setLang("en")}
            className={`rounded-lg px-4 py-2 text-sm ${lang === "en" ? "bg-indigo-600" : "bg-white/10 hover:bg-white/20"}`}
          >
            English
          </button>
        </div>
        <h2 className="font-medium mb-3">Theme</h2>
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setTheme("dark")}
            className={`rounded-lg px-4 py-2 text-sm ${theme === "dark" ? "bg-indigo-600" : "bg-white/10 hover:bg-white/20"}`}
          >
            Dark
          </button>
          <button
            onClick={() => setTheme("light")}
            className={`rounded-lg px-4 py-2 text-sm ${theme === "light" ? "bg-indigo-600" : "bg-white/10 hover:bg-white/20"}`}
          >
            Light
          </button>
        </div>
        <h2 className="font-medium mb-3">Updates</h2>
        <button
          onClick={async () => {
            setUpdateBusy(true);
            setUpdateMsg(null);
            try {
              const result = await invoke<string | null>("check_updates");
              setUpdateMsg(result ? `Update available: ${result}` : "KAMVEX is up to date");
            } catch (e) {
              setUpdateMsg(String(e));
            } finally {
              setUpdateBusy(false);
            }
          }}
          disabled={updateBusy}
          className="rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 px-4 py-2 text-sm"
        >
          {updateBusy ? "Checking…" : "Check for updates"}
        </button>
        {updateMsg && <p className="mt-2 text-xs text-white/50">{updateMsg}</p>}
      </section>

      <section className="rounded-xl border border-white/10 bg-white/5 p-5">
        <h2 className="font-medium mb-2">{t("settings.hardware")}</h2>
        {hw ? (
          <>
            <Row k={t("settings.cpu")} v={hw.cpu_brand || "—"} />
            <Row k={t("settings.physicalCores")} v={String(hw.physical_cores)} />
            <Row k={t("settings.logicalCores")} v={String(hw.logical_cores)} />
            <Row k={t("settings.totalRam")} v={`${hw.total_ram_gb.toFixed(1)} GB`} />
            <Row k={t("settings.availableRam")} v={`${hw.available_ram_gb.toFixed(1)} GB`} />
            {hw.gpus.length > 0 && (
              <>
                <div className="mt-3 mb-1 text-xs uppercase tracking-wider text-white/30">GPU</div>
                {hw.gpus.map((g, i) => (
                  <Row key={i} k={g.name} v={`${g.vendor} · ${g.backend}`} />
                ))}
              </>
            )}
          </>
        ) : (
          <p className="text-white/40 text-sm">{t("settings.detecting")}</p>
        )}
        <p className="text-xs text-white/30 mt-3">
          {t("settings.autotuneSoon")}
        </p>
      </section>
    </div>
  );
}
