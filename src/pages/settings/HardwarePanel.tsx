import { useEffect, useState } from "react";
import { detectHardware, HwInfo } from "../../api/client";
import { Section } from "../../components/ui";
import { useI18n } from "../../i18n";
import Row from "./Row";

export default function HardwarePanel() {
  const { t } = useI18n();
  const [hw, setHw] = useState<HwInfo | null>(null);

  useEffect(() => {
    detectHardware().then(setHw).catch(() => {});
  }, []);

  return (
    <Section title={t("settings.hardware")}>
      {hw ? (
        <>
          <Row k={t("settings.cpu")} v={hw.cpu_brand || "—"} />
          <Row k={t("settings.physicalCores")} v={String(hw.physical_cores)} />
          <Row k={t("settings.logicalCores")} v={String(hw.logical_cores)} />
          <Row k={t("settings.totalRam")} v={`${hw.total_ram_gb.toFixed(1)} GB`} />
          <Row k={t("settings.availableRam")} v={`${hw.available_ram_gb.toFixed(1)} GB`} />
          {hw.gpus.length > 0 && (
            <>
              <div className="mt-3 mb-1 text-xs uppercase tracking-wider text-white/30">{t("settings.gpu")}</div>
              {hw.gpus.map((g, i) => (
                <Row key={i} k={g.name} v={`${g.vendor} · ${g.backend}`} />
              ))}
            </>
          )}
        </>
      ) : (
        <p className="text-white/40 text-sm">{t("settings.detecting")}</p>
      )}
      <p className="text-xs text-white/30 mt-3">{t("settings.autotuneSoon")}</p>
    </Section>
  );
}
