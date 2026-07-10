import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Section } from "../../components/ui";
import { useI18n } from "../../i18n";
import Row from "./Row";

export default function EnginePanel() {
  const { t } = useI18n();
  const [port, setPort] = useState<number | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    invoke<number>("sidecar_port").then(setPort).catch(() => {});
    invoke<boolean>("sidecar_ready").then(setReady).catch(() => {});
  }, []);

  return (
    <Section title={t("settings.backend")}>
      <Row k={t("settings.port")} v={port ? String(port) : "…"} />
      <Row k={t("settings.status")} v={ready ? t("settings.active") : t("settings.starting")} />
    </Section>
  );
}
