export type SegmentedOption<T extends string = string> = {
  value: T;
  label: string;
  tone?: "neutral" | "success" | "warning" | "accent";
  disabled?: boolean;
  /** Visually dimmed but still clickable — use for "needs setup" states, not hard-disabled ones. */
  dim?: boolean;
  title?: string;
};

const toneActive: Record<string, string> = {
  neutral: "bg-white/15 border-white/30 text-white/90",
  success: "bg-emerald-500/20 border-emerald-500/40 text-emerald-300",
  warning: "bg-amber-500/20 border-amber-500/40 text-amber-300",
  accent: "bg-accent/20 border-accent/40 text-accent",
};

export default function SegmentedControl<T extends string = string>({
  value,
  options,
  onChange,
  size = "sm",
  className = "",
}: {
  value: T;
  options: SegmentedOption<T>[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
  className?: string;
}) {
  const pad = size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm";
  return (
    <div className={`inline-flex items-center gap-1 rounded-full border border-white/10 bg-black/20 p-0.5 ${className}`}>
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            disabled={opt.disabled}
            title={opt.title}
            onClick={() => onChange(opt.value)}
            className={`rounded-full border transition-colors ${pad} ${
              active ? toneActive[opt.tone ?? "neutral"] : "border-transparent text-white/40 hover:text-white/60"
            } ${opt.dim && !active ? "opacity-40" : ""}`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
