import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";

export type SelectOption<T extends string = string> = {
  value: T;
  label: string;
  icon?: ReactNode;
};

export default function Select<T extends string = string>({
  value,
  options,
  onChange,
  placeholder = "Seleccionar…",
  searchable = false,
  searchPlaceholder = "Buscar…",
  emptyLabel = "Sin resultados",
  className = "",
  renderValue,
}: {
  value: T | null;
  options: SelectOption<T>[];
  onChange: (v: T) => void;
  placeholder?: string;
  searchable?: boolean;
  searchPlaceholder?: string;
  emptyLabel?: string;
  className?: string;
  renderValue?: (opt: SelectOption<T> | undefined) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const selected = options.find((o) => o.value === value);
  const filtered =
    searchable && query.trim()
      ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
      : options;

  return (
    <div
      ref={ref}
      className={`relative ${className}`}
      onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-left outline-none transition-colors hover:border-white/20 focus-visible:border-accent/50"
      >
        <span className="truncate text-white/80">
          {renderValue ? (
            renderValue(selected)
          ) : selected ? (
            selected.label
          ) : (
            <span className="text-white/30">{placeholder}</span>
          )}
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-white/40 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="absolute z-50 mt-1.5 w-full min-w-[180px] animate-pop-in rounded-lg border border-white/10 bg-[#0b0e14] shadow-elevated overflow-hidden">
          {searchable && (
            <div className="border-b border-white/10 p-1.5">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                className="w-full rounded-md bg-white/5 px-2 py-1.5 text-xs outline-none placeholder:text-white/30"
              />
            </div>
          )}
          <div className="max-h-64 overflow-y-auto p-1">
            {filtered.length === 0 && (
              <p className="px-2 py-2 text-xs text-white/30">{emptyLabel}</p>
            )}
            {filtered.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                  opt.value === value ? "bg-accent/15 text-accent" : "text-white/70 hover:bg-white/5"
                }`}
              >
                {opt.icon}
                <span className="flex-1 min-w-0 truncate">{opt.label}</span>
                {opt.value === value && <Check className="h-3.5 w-3.5 shrink-0" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
