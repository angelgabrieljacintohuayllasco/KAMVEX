import type { ReactNode } from "react";
import { Cpu, Library, Loader2, Sparkles } from "lucide-react";
import { Select, StatusDot, type SelectOption } from "./ui";
import type { Dataset, LocalModel } from "../api/client";
import { useI18n } from "../i18n";

const AUTO_VALUE = "__auto__";

export default function TopBar({
  title,
  left,
  right,
}: {
  title?: string;
  left?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-white/10 px-5">
      <div className="flex min-w-0 items-center gap-3">
        {title && <h1 className="truncate text-sm font-medium text-white/80">{title}</h1>}
        {left}
      </div>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}

export function KnowledgeSelector({
  datasets,
  selectedDataset,
  setSelectedDataset,
  federated,
  setFederated,
}: {
  datasets: Dataset[];
  selectedDataset: string | null;
  setSelectedDataset: (s: string) => void;
  federated: boolean;
  setFederated: (f: boolean) => void;
}) {
  const { t } = useI18n();

  if (datasets.length === 0) return null;

  const options: SelectOption[] = [
    { value: AUTO_VALUE, label: t("chat.autoActive"), icon: <Sparkles className="h-3.5 w-3.5 text-accent" /> },
    ...datasets.map((d) => ({
      value: d.name,
      label: d.name,
      icon: <Library className="h-3.5 w-3.5 text-white/40" />,
    })),
  ];

  return (
    <Select
      className="w-56"
      value={federated ? AUTO_VALUE : selectedDataset}
      options={options}
      searchable={datasets.length > 6}
      searchPlaceholder={t("models.search")}
      onChange={(v) => {
        if (v === AUTO_VALUE) {
          setFederated(true);
        } else {
          setFederated(false);
          setSelectedDataset(v);
        }
      }}
    />
  );
}

export function EngineStatus({ running }: { running: boolean }) {
  const { t } = useI18n();
  return (
    <span title={running ? undefined : t("metrics.noEngineHint")}>
      <StatusDot
        tone={running ? "success" : "neutral"}
        pulse={running}
        label={running ? t("metrics.active") : t("metrics.noEngine")}
      />
    </span>
  );
}

const NONE_VALUE = "__none__";

export function LlmSelector({
  models,
  selected,
  onSelect,
  running,
  starting,
  goModels,
}: {
  models: LocalModel[];
  selected: string | null;
  onSelect: (path: string | null) => void;
  running: boolean;
  starting: boolean;
  goModels: () => void;
}) {
  const { t } = useI18n();

  if (models.length === 0) {
    return (
      <button
        onClick={goModels}
        className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 px-3 py-1.5 text-xs text-white/50 transition-colors"
      >
        <Cpu className="h-3.5 w-3.5" />
        {t("flow.goModels")}
      </button>
    );
  }

  const options: SelectOption[] = [
    { value: NONE_VALUE, label: t("flow.noLlm") },
    ...models.map((m) => ({
      value: m.path,
      label: `${m.name} (${m.size_mb >= 1000 ? `${(m.size_mb / 1000).toFixed(1)} GB` : `${m.size_mb} MB`})`,
      icon: <Cpu className="h-3.5 w-3.5 text-white/40" />,
    })),
  ];

  const selectedName = models.find((m) => m.path === selected)?.name;

  return (
    <div className="flex items-center gap-2">
      <Select
        className="w-56"
        value={selected ?? NONE_VALUE}
        options={options}
        searchable={models.length > 6}
        searchPlaceholder={t("models.search")}
        renderValue={() => (
          <span className="flex items-center gap-1.5 text-xs">
            <Cpu className="h-3.5 w-3.5 text-white/40" />
            {selectedName ?? t("flow.selectLlm")}
          </span>
        )}
        onChange={(v) => onSelect(v === NONE_VALUE ? null : v)}
      />
      {starting ? (
        <span className="flex items-center gap-1 text-xs text-amber-300">
          <Loader2 className="h-3 w-3 animate-spin" />
        </span>
      ) : (
        <StatusDot
          tone={running ? "success" : selected ? "warning" : "neutral"}
          pulse={running}
          label=""
        />
      )}
    </div>
  );
}
