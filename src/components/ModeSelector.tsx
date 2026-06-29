import { useI18n } from "../i18n";

export type AgentBMode = "statistical" | "grounded" | "free";

const MODES: { value: AgentBMode; labelKey: string; color: string; descKey: string }[] = [
  { value: "statistical", labelKey: "mode.statistical", color: "emerald", descKey: "mode.statistical.desc" },
  { value: "grounded", labelKey: "mode.grounded", color: "amber", descKey: "mode.grounded.desc" },
  { value: "free", labelKey: "mode.free", color: "white", descKey: "mode.free.desc" },
];

export default function ModeSelector({
  mode,
  onChange,
  disabledModes = [],
}: {
  mode: AgentBMode;
  onChange: (m: AgentBMode) => void;
  disabledModes?: AgentBMode[];
}) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-1 rounded-full bg-black/30 border border-white/10 px-1 py-0.5 text-xs">
      {MODES.map((m) => {
        const active = mode === m.value;
        const isDisabled = disabledModes.includes(m.value);
        const colorClasses = {
          emerald: active ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300" : "",
          amber: active ? "bg-amber-500/20 border-amber-500/40 text-amber-300" : "",
          white: active ? "bg-white/15 border-white/30 text-white/90" : "",
        }[m.color];
        return (
          <button
            key={m.value}
            onClick={() => onChange(m.value)}
            disabled={isDisabled}
            title={t(m.descKey)}
            className={`rounded-full border px-2 py-1 transition-colors ${
              active ? colorClasses : "border-transparent text-white/40 hover:text-white/60"
            } disabled:opacity-30 disabled:cursor-not-allowed`}
          >
            {t(m.labelKey)}
          </button>
        );
      })}
    </div>
  );
}
