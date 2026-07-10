import { useEffect, useState } from "react";
import { listDatasets, type Dataset } from "../../api/client";
import { Section, Badge } from "../../components/ui";
import { useI18n } from "../../i18n";

export default function KnowledgePanel() {
  const { t } = useI18n();
  const [datasets, setDatasets] = useState<Dataset[]>([]);

  useEffect(() => {
    listDatasets().then(setDatasets).catch(() => {});
  }, []);

  return (
    <Section title={t("settings.cat.knowledge")} description={t("settings.knowledgeHint")}>
      {datasets.length === 0 ? (
        <p className="text-sm text-white/40">{t("knowledge.empty")}</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {datasets.map((d) => (
            <div
              key={d.name}
              className="flex items-center justify-between rounded-lg bg-black/20 border border-white/10 px-3 py-2 text-sm"
            >
              <span className="text-white/80">{d.name}</span>
              <Badge>
                {d.n_records} {t("knowledge.records")}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
