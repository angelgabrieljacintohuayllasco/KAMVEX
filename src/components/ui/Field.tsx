import type { ReactNode } from "react";

export const inputClass =
  "w-full rounded-lg bg-black/20 border border-white/10 px-3 py-2 text-sm outline-none transition-colors focus:border-accent/50 placeholder:text-white/30";

export default function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="text-white/60">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="block mt-1 text-xs text-white/30">{hint}</span>}
    </label>
  );
}
