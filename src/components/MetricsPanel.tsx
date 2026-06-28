import { useEffect, useState } from "react";
import { inferenceMetrics, type InferenceMetrics } from "../api/client";
import { useI18n } from "../i18n";

function fmtTtft(ms: number): string {
  if (ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function ctxColor(pct: number): string {
  if (pct >= 90) return "text-red-400";
  if (pct >= 70) return "text-amber-400";
  return "text-emerald-400";
}

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

  const hasVram = metrics.vram_total_mb != null && metrics.vram_total_mb > 0;
  const vramPct = hasVram
    ? Math.round((metrics.vram_used_mb! / metrics.vram_total_mb!) * 100)
    : 0;
  const ramPct =
    metrics.ram_total_gb != null && metrics.ram_total_gb > 0
      ? Math.round((metrics.ram_used_gb! / metrics.ram_total_gb!) * 100)
      : 0;

  return (
    <div className="flex items-center gap-3 text-xs text-white/50 flex-wrap">
      {/* Status dot + active slots */}
      <div className="flex items-center gap-1">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-emerald-300">
          {metrics.active_slots} {t("metrics.active")}
        </span>
      </div>

      <Sep />

      {/* Tokens/s */}
      <Stat
        label={t("metrics.tokensPerSec")}
        value={metrics.tokens_per_second > 0 ? metrics.tokens_per_second.toFixed(1) : "—"}
        color={metrics.tokens_per_second > 0 ? "text-cyan-300" : "text-white/30"}
      />

      <Sep />

      {/* TTFT */}
      <Stat
        label={t("metrics.ttft")}
        value={fmtTtft(metrics.ttft_ms)}
        color={metrics.ttft_ms > 0 ? "text-indigo-300" : "text-white/30"}
      />

      <Sep />

      {/* Context fill */}
      {metrics.context_total > 0 && (
        <>
          <div className="flex items-center gap-1.5">
            <span className="text-white/40">{t("metrics.context")}</span>
            <span className={ctxColor(metrics.context_pct)}>
              {metrics.context_used}/{metrics.context_total}
            </span>
            <span className="text-white/30">({metrics.context_pct}%)</span>
            {/* Mini bar */}
            <span className="inline-block w-12 h-1.5 rounded-full bg-white/10 overflow-hidden align-middle">
              <span
                className={`block h-full rounded-full ${
                  metrics.context_pct >= 90
                    ? "bg-red-400"
                    : metrics.context_pct >= 70
                    ? "bg-amber-400"
                    : "bg-emerald-400"
                }`}
                style={{ width: `${Math.min(metrics.context_pct, 100)}%` }}
              />
            </span>
          </div>
          <Sep />
        </>
      )}

      {/* RAM */}
      {metrics.ram_total_gb != null && (
        <>
          <div className="flex items-center gap-1.5">
            <span className="text-white/40">{t("metrics.ram")}</span>
            <span className="text-white/70">
              {metrics.ram_used_gb}/{metrics.ram_total_gb}GB
            </span>
            <span className="text-white/30">({ramPct}%)</span>
          </div>
          <Sep />
        </>
      )}

      {/* VRAM (NVIDIA only) */}
      {hasVram && (
        <div className="flex items-center gap-1.5">
          <span className="text-white/40">{t("metrics.vram")}</span>
          <span className="text-white/70">
            {metrics.vram_used_mb}/{metrics.vram_total_mb}MB
          </span>
          <span className="text-white/30">({vramPct}%)</span>
        </div>
      )}
    </div>
  );
}

function Sep() {
  return <span className="text-white/20">|</span>;
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-white/40">{label}</span>
      <span className={color}>{value}</span>
    </div>
  );
}
