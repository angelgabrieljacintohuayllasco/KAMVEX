import type { ReactNode } from "react";

type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "bg-white/10 border-white/20 text-white/60",
  accent: "bg-accent/15 border-accent/40 text-accent",
  success: "bg-emerald-500/15 border-emerald-500/30 text-emerald-300",
  warning: "bg-amber-500/15 border-amber-500/30 text-amber-300",
  danger: "bg-red-500/15 border-red-500/30 text-red-300",
};

export default function Badge({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
