export type AgentBMode = "statistical" | "grounded" | "free";

const MODES: { value: AgentBMode; label: string; color: string; desc: string }[] = [
  { value: "statistical", label: "Statistical", color: "emerald", desc: "0 alucinación — vocabulario bloqueado" },
  { value: "grounded", label: "LLM-grounded", color: "amber", desc: "LLM formatea sin inventar" },
  { value: "free", label: "LLM-free", color: "white", desc: "Chat libre con system prompt" },
];

export default function ModeSelector({
  mode,
  onChange,
  disabled,
}: {
  mode: AgentBMode;
  onChange: (m: AgentBMode) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-1 rounded-full bg-black/30 border border-white/10 px-1 py-0.5 text-xs">
      {MODES.map((m) => {
        const active = mode === m.value;
        const colorClasses = {
          emerald: active ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300" : "",
          amber: active ? "bg-amber-500/20 border-amber-500/40 text-amber-300" : "",
          white: active ? "bg-white/15 border-white/30 text-white/90" : "",
        }[m.color];
        return (
          <button
            key={m.value}
            onClick={() => onChange(m.value)}
            disabled={disabled}
            title={m.desc}
            className={`rounded-full border px-2 py-1 transition-colors ${
              active ? colorClasses : "border-transparent text-white/40 hover:text-white/60"
            } disabled:opacity-30`}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
