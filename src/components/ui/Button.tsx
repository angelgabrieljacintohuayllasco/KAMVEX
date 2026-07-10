import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";
type Size = "sm" | "md";

const base =
  "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40";

const variants: Record<Variant, string> = {
  primary: "bg-accent hover:bg-accent-hover text-accent-fg",
  secondary: "bg-white/10 hover:bg-white/20 text-white/90",
  ghost: "bg-transparent hover:bg-white/5 text-white/60 hover:text-white/90",
  danger: "bg-red-600 hover:bg-red-500 text-white",
  success: "bg-emerald-600 hover:bg-emerald-500 text-white",
};

const sizes: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
};

export default function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  circle = false,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  circle?: boolean;
}) {
  const shape = circle ? "rounded-full p-0 w-9 h-9" : sizes[size];
  return (
    <button
      disabled={disabled || loading}
      className={`${base} ${variants[variant]} ${shape} ${className}`}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

function Spinner() {
  return (
    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  );
}
