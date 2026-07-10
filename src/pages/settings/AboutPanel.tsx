import { Section } from "../../components/ui";
import { useI18n } from "../../i18n";
import pkg from "../../../package.json";

export default function AboutPanel() {
  const { t } = useI18n();
  return (
    <Section title="KAMVEX">
      <Row k={t("settings.version")} v={pkg.version} />
      <Row k={t("settings.license")} v="Apache 2.0" />
    </Section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b border-white/5 py-2 text-sm last:border-0">
      <span className="text-white/50">{k}</span>
      <span className="font-medium">{v}</span>
    </div>
  );
}
