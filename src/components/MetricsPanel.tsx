import { useEffect, useState } from "react";
import { inferenceMetrics, type InferenceMetrics } from "../api/client";
import { useI18n } from "../i18n";

export default function MetricsPanel() {
  const { t } = useI18n();
  const [metrics, setMetrics] = useState<InferenceMetrics | null>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      inferenceMetrics().then(setMetrics).catch(() => {});
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  if (!metrics || !metrics.connected) {
    return (
      <div className="flex items-center gap-2 text-xs text-white/30">
        <span className="w-2 h-2 rounded-full bg-white/20" />
        {t("metrics.noEngine")}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4 text-xs text-white/50">
      <div className="flex items-center gap-1">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-emerald-300">{metrics.active_slots} {t("metrics.active")}</span>
      </div>
      <span className="text-white/20">|</span>
      <span>{metrics.total_decoded} {t("metrics.tokensDecoded")}</span>
    </div>
  );
}
