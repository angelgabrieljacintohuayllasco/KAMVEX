import type { ReactNode } from "react";

export default function Card({
  children,
  className = "",
  padded = true,
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  hover?: boolean;
}) {
  return (
    <div
      className={`rounded-card border border-white/10 bg-white/[0.03] shadow-card ${
        hover ? "transition-colors hover:bg-white/[0.06]" : ""
      } ${padded ? "p-5" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
