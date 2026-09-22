import { useEffect, useState } from "react";
import {
  appDirs,
  health,
  llamaStatus,
  sidecarStatus,
  type AppDirs,
  type HealthInfo,
  type LlamaStatus,
  type SidecarStatus,
} from "../../api/client";
import { Section } from "../../components/ui";
import { useI18n } from "../../i18n";
import Row from "./Row";

export default function EnginePanel() {
  const { t } = useI18n();
  const [sidecar, setSidecar] = useState<SidecarStatus | null>(null);
  const [info, setInfo] = useState<HealthInfo | null>(null);
  const [dirs, setDirs] = useState<AppDirs | null>(null);
  const [llama, setLlama] = useState<LlamaStatus | null>(null);

  useEffect(() => {
    const tick = () => {
      sidecarStatus().then(setSidecar).catch(() => {});
      health().then(setInfo).catch(() => setInfo(null));
      llamaStatus().then(setLlama).catch(() => {});
    };
    tick();
    appDirs().then(setDirs).catch(() => {});
    const id = setInterval(tick, 4000);
    return () => clearInterval(id);
  }, []);

  const yesNo = (v: boolean | undefined) => (v ? t("settings.available") : t("settings.unavailable"));

  return (
    <>
      <Section title={t("settings.backend")}>
        <Row k={t("settings.port")} v={sidecar ? String(sidecar.port) : "…"} />
        <Row k={t("settings.status")} v={sidecar?.ready ? t("settings.active") : t("settings.starting")} />
        <Row k={t("settings.sidecarLaunch")} v={sidecar?.launch ?? "…"} />
        {sidecar?.pid != null && <Row k={t("settings.pid")} v={String(sidecar.pid)} />}
        {info && (
          <>
            <Row k={t("settings.sidecarVersion")} v={info.version} />
            <Row k={t("settings.dasa")} v={yesNo(info.dasa)} />
            <Row k={t("settings.embeddings")} v={info.embeddings} />
          </>
        )}
        {sidecar?.log_path && <Row k={t("settings.logs")} v={sidecar.log_path} />}
      </Section>

      <Section title={t("settings.inference")}>
        <Row k={t("settings.status")} v={llama?.running ? `${t("settings.active")} · ${llama.backend} · :${llama.port}` : t("settings.stopped")} />
        {llama?.model && <Row k={t("models.model")} v={llama.model} />}
        {llama?.log_path && <Row k={t("settings.logs")} v={llama.log_path} />}
      </Section>

      {dirs && (
        <Section title={t("settings.dirs")}>
          <Row k={t("settings.dataDir")} v={dirs.data} />
          <Row k={t("settings.modelsDir")} v={dirs.models} />
          <Row k={t("settings.binariesDir")} v={dirs.binaries} />
          <Row k={t("settings.logsDir")} v={dirs.logs} />
        </Section>
      )}
    </>
  );
}
