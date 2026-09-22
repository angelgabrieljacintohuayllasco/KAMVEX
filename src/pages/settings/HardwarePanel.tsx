import { useEffect, useState } from "react";
import { detectHardware, type HwInfo } from "../../api/client";
import { Badge, Section } from "../../components/ui";
import { useI18n } from "../../i18n";
import Row from "./Row";

function gb(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

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
          <Row
            k={t("settings.isa")}
            v={[hw.has_avx2 ? "AVX2" : null, hw.has_avx512 ? "AVX-512" : null].filter(Boolean).join(" · ") || "—"}
          />
          <Row k={t("settings.totalRam")} v={`${hw.total_ram_gb.toFixed(1)} GB`} />
          <Row k={t("settings.availableRam")} v={`${hw.available_ram_gb.toFixed(1)} GB`} />
          <Row
            k={t("settings.backends")}
            v={[hw.has_cuda ? "CUDA" : null, hw.has_vulkan ? "Vulkan" : null, "CPU"].filter(Boolean).join(" · ")}
          />
          <div className="mt-3 mb-1 text-xs uppercase tracking-wider text-white/30">{t("settings.gpu")}</div>
          {hw.gpus.length === 0 && <p className="text-sm text-white/40">{t("settings.noGpu")}</p>}
          {hw.gpus.map((g, i) => (
            <div key={i} className="flex items-center justify-between border-b border-white/5 py-2 text-sm gap-3">
              <span className="text-white/70 truncate">{g.name}</span>
              <span className="flex items-center gap-1.5 shrink-0">
                <Badge>{g.vendor}</Badge>
                <Badge tone="accent">{g.backend}</Badge>
                <Badge tone={g.integrated ? "warning" : "success"}>
                  {g.integrated ? t("settings.integrated") : t("settings.discrete")}
                </Badge>
                {g.vram_mb > 0 && <Badge>{t("settings.vram")} {gb(g.vram_mb)}</Badge>}
              </span>
            </div>
          ))}
        </>
      ) : (
        <p className="text-white/40 text-sm">{t("settings.detecting")}</p>
      )}
      <p className="text-xs text-white/30 mt-3">{t("settings.autotuneSoon")}</p>
    </Section>
  );
}
