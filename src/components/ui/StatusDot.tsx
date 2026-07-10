type Tone = "success" | "neutral" | "warning" | "danger";

const colors: Record<Tone, string> = {
  success: "bg-emerald-400",
  neutral: "bg-white/20",
  warning: "bg-amber-400",
  danger: "bg-red-400",
};

export default function StatusDot({
  tone = "neutral",
  pulse = false,
  label,
  className = "",
}: {
  tone?: Tone;
  pulse?: boolean;
  label?: string;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span className={`h-2 w-2 rounded-full ${colors[tone]} ${pulse ? "animate-pulse" : ""}`} />
      {label && <span className="text-xs text-white/50">{label}</span>}
    </span>
  );
}
