import type { ButtonHTMLAttributes, ReactNode } from "react";

export default function IconButton({
  icon,
  size = "md",
  active = false,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: ReactNode;
  size?: "sm" | "md";
  active?: boolean;
}) {
  const dims = size === "sm" ? "h-7 w-7" : "h-9 w-9";
  return (
    <button
      className={`inline-flex items-center justify-center rounded-lg transition-colors disabled:opacity-40 ${dims} ${
        active ? "bg-white/10 text-white" : "text-white/50 hover:bg-white/5 hover:text-white/90"
      } ${className}`}
      {...rest}
    >
      {icon}
    </button>
  );
}
