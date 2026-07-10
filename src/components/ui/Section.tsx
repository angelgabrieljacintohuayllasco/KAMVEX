import type { ReactNode } from "react";
import Card from "./Card";

export default function Section({
  title,
  description,
  children,
  actions,
  className = "",
}: {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`mb-6 ${className}`}>
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <h2 className="font-medium text-white/90">{title}</h2>
          {description && <p className="text-xs text-white/40 mt-0.5">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </Card>
  );
}
